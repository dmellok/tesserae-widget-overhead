"""AI paintings of aircraft through fal.ai: each airframe painted once from
its own photograph, in a style, on white paper (cut out on the page) or as a
whole picture on a painted backdrop. The budget, the queue and the files are
the Specimen Sheet's, trimmed to what an aircraft needs. Loaded by path."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _sibling(name: str) -> Any:
    full = f"_tesserae_plugins.overhead_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


N = _sibling("net")
T = _sibling("tray")

FAL = "https://fal.run/"
T2I_ENDPOINT = "fal-ai/nano-banana"  # a picture from words alone, for what has no photograph
MODELS: dict[str, dict[str, str]] = {
    "nano_banana": {"label": "Nano Banana", "endpoint": "fal-ai/nano-banana/edit", "cost": "about US$0.04"},
    "nano_banana_pro": {"label": "Nano Banana Pro", "endpoint": "fal-ai/nano-banana-pro/edit", "cost": "about US$0.15"},
    "flux_kontext": {"label": "FLUX.1 Kontext Pro", "endpoint": "fal-ai/flux-pro/kontext", "cost": "about US$0.04"},
    "gpt_image": {"label": "GPT Image 2", "endpoint": "openai/gpt-image-2/edit", "cost": "about US$0.05"},
    "seedream": {"label": "Seedream 4", "endpoint": "fal-ai/bytedance/seedream/v4/edit", "cost": "about US$0.03"},
}
DEFAULT_MODEL = "nano_banana"
GEN_TIMEOUT_S = 120
GEN_DAILY_CAP = 12
UNLIMITED = 10**9
GEN_RETRY_S = 6 * 3600
PER_FETCH = 3
BATCH_PARALLEL = 3
_PARALLEL = BATCH_PARALLEL
_PER_FETCH = PER_FETCH
STOPPED = "stopped"
PROMPT_VERSION = 3
CUT_VERSION = 3
NOTE_NO_KEY = "AI paintings need a fal.ai key in the Overhead settings."
NOTE_GEN_CAP = "AI paintings: to-day's limit of {cap} is used up; more to-morrow."
NOTE_NO_PHOTO = "No photograph of this airframe to paint from."

# ----------------------------------------------------------------------
# Styles: an id, a label and how the picture is made. {kind} is "aircraft".
# ----------------------------------------------------------------------
STYLES: dict[str, tuple[str, str]] = {
    "poster": (
        "Vintage airline poster",
        "a vintage mid-century airline poster illustration in gouache: flat confident shapes, a limited palette of warm tones, crisp edges with a little paper texture, the aircraft rendered with affection and accuracy",
    ),
    "engraving_colour": (
        "Hand-coloured engraving",
        "a hand-coloured copperplate engraving from a nineteenth-century technical atlas: fine engraved linework and stippling under delicate watercolour washes, the livery's colours kept true",
    ),
    "engraving": (
        "Black-ink engraving",
        "a black-ink copperplate engraving from a Victorian encyclopaedia: fine cross-hatching and stippling, no colour at all",
    ),
    "technical": (
        "Technical ink drawing",
        "a precise technical ink illustration from a manufacturer's brochure: clean ruled linework, light hatching for shadow, the panel lines and windows drawn, no colour",
    ),
    "watercolour": (
        "Loose watercolour",
        "a loose, airy watercolour with soft wet edges, a few precise details on the nose and tail and plenty of white space",
    ),
    "woodblock": (
        "Japanese woodblock print",
        "a Japanese woodblock print: flat areas of colour with a fine dark keyline and the texture of washi paper",
    ),
    "linocut": (
        "Linocut",
        "a bold linocut print in black ink with one muted colour: strong carved lines, simple shapes, a little texture from the block",
    ),
    "deco": (
        "Art Deco travel poster",
        "an Art Deco travel poster of the 1930s: streamlined geometric shapes, sweeping speed lines, a palette of cream, teal and vermilion, airbrushed gradients",
    ),
    "midcentury": (
        "Mid-century flat illustration",
        "a mid-century modern illustration in the manner of a 1960s airline brochure: the aircraft reduced to clean geometric shapes, flat colour in a handful of tones, no outlines",
    ),
    "pencil": (
        "Pencil study",
        "a careful graphite pencil study: soft shading, the metal's sheen suggested with a few highlights, no colour",
    ),
    "pointillism": (
        "Pointillism",
        "a pointillist painting built from thousands of small dots of pure colour, the aircraft's form emerging from the dots",
    ),
    "blueprint": (
        "Blueprint",
        "a cyanotype blueprint: fine white linework on deep Prussian blue paper, dimension ticks and construction lines",
    ),
    "cutaway": (
        "Magazine cutaway",
        "a 1950s magazine cutaway illustration: the fuselage opened to show the cockpit, cabin and cargo in neat sections, tiny figures in the seats, painted in gouache with a draughtsman's precision",
    ),
    "stamp": (
        "Postage stamp",
        "a finely engraved postage stamp: the aircraft in the stamp's engraved linework within an ornate perforated border, the country and value lettered in the stamp's own style, the whole stamp filling the picture",
    ),
    "tattoo": (
        "Tattoo flash",
        "an old-school tattoo flash sheet drawing: bold black outlines, a flat limited palette of red, yellow and green, simple shading, a ribbon banner curling beneath",
    ),
    "riso": (
        "Risograph",
        "a two-colour risograph print in fluorescent pink and blue ink only: the aircraft reduced to two overprinted flat ink layers with grainy texture, slight misregistration and coarse halftone shading, no photographic detail at all",
    ),
    "pixel": (
        "Pixel art",
        "coarse pixel art as from a 16-bit video game: the aircraft drawn at a tiny resolution of about 96 pixels across and scaled up so every square pixel is plainly visible, a palette of sixteen colours, stair-stepped edges, dithered shading, nothing smooth",
    ),
    "lowpoly": (
        "Low-poly render",
        "a low-polygon 3D render: the aircraft built from a few hundred large flat-shaded triangles so that every facet shows as a visible flat plane with a hard edge, no smooth surfaces, soft studio lighting",
    ),
    "papercraft": (
        "Paper craft",
        "a paper model of the aircraft made from cut and folded card, photographed on a table: visible folds, glued tabs and the cut edges of the card, lit from the side",
    ),
    "toybrick": (
        "Toy bricks",
        "a model of the aircraft built from interlocking plastic toy bricks, rendered as a product photograph: rows of round studs along the top, every curve stepped into blocky brick shapes, glossy moulded plastic, the livery in brick colours",
    ),
    "charcoal": (
        "Charcoal",
        "a drawing in charcoal sticks on rough toothy paper: visibly smudged by hand, strokes and finger-rubbed shading plain to see, a few sharp lines on the nose and tail, nothing photographic, no colour",
    ),
    "stained_glass": (
        "Stained glass",
        "a stained-glass window design: the aircraft made of flat panes of coloured glass separated by thick black lead lines, the light coming through the glass",
    ),
    "gilt": (
        "Illuminated manuscript",
        "an illuminated manuscript miniature: the aircraft painted in tempera with gold leaf on the tail and the engines, a fine red and blue filigree border",
    ),
    "pulp": (
        "Pulp cover",
        "a 1950s pulp science-fiction magazine cover painting: airbrushed, dramatic, saturated, the aircraft heroic against a lurid sky",
    ),
    "synthwave": (
        "Synthwave",
        "a synthwave illustration: neon pink and cyan on a dark purple ground, a glowing grid horizon and a striped sun, the aircraft in chrome",
    ),
    "chalk": (
        "Chalkboard",
        "a chalk drawing on a dark blackboard: white and coloured chalk, soft smudges, the lines a little dusty",
    ),
}
STYLE_IDS = (*STYLES, "builder", "custom")
# Styles without colour: the prompt asks for black, white and grey only
MONO = {"engraving", "technical", "pencil", "charcoal"}
# Styles that make a whole picture on their own ground, never cut out
OWN_PAPER = {"blueprint", "stamp", "synthwave", "chalk", "gilt", "pulp"}
CUSTOM_EXAMPLE = (
    "a chalk pastel drawing on grey paper, soft and smudgy, with the sun catching the fuselage"
)
CUSTOM_PRESETS = [
    {"label": "Gouache poster", "value": "a vintage airline poster in gouache: flat confident shapes, a warm limited palette, crisp edges"},
    {"label": "Cutaway", "value": "a 1950s magazine cutaway illustration: the fuselage opened to show seats and cargo, labelled in small neat capitals"},
    {"label": "Chalk pastel", "value": CUSTOM_EXAMPLE},
    {"label": "Aviation art", "value": "a traditional oil painting in the manner of classic aviation art: dramatic light, polished metal, confident brushwork"},
    {"label": "Comic ink", "value": "a comic-book ink drawing with bold outlines, hatched shadows and flat halftone colour"},
    {"label": "Neon line", "value": "a single-weight neon line drawing on white: one continuous glowing line describing the aircraft"},
]
_CUSTOM_RE = re.compile(r"custom[a-z]{8}")

BUILDER: dict[str, tuple[str, str, tuple[tuple[str, str, str], ...]]] = {
    "medium": ("Medium", "gouache", (
        ("gouache", "Gouache", "a flat gouache painting"),
        ("watercolour", "Watercolour", "a loose watercolour painting"),
        ("oil", "Oil paint", "an oil painting with visible brushwork"),
        ("pastel", "Soft pastel", "a soft pastel drawing"),
        ("coloured_pencil", "Coloured pencil", "a coloured-pencil drawing"),
        ("pencil", "Graphite pencil", "a graphite pencil drawing"),
        ("ink", "Pen and ink", "a pen-and-ink drawing"),
        ("engraving", "Engraving", "a copperplate engraving"),
        ("lithograph", "Lithograph", "a hand-coloured lithograph"),
        ("woodblock", "Woodblock", "a woodblock print"),
        ("linocut", "Linocut", "a linocut print"),
        ("screenprint", "Screen print", "a screen print with a few flat inks"),
        ("vector", "Flat vector", "a flat vector illustration"),
        ("airbrush", "Airbrush", "an airbrushed illustration"),
        ("papercut", "Paper cut", "layered cut paper"),
    )),
    "period": ("Period or school", "", (
        ("", "None in particular", ""),
        ("1930s", "1930s travel poster", "in the manner of a 1930s travel poster"),
        ("1950s", "1950s airline brochure", "in the manner of a 1950s airline brochure"),
        ("1960s", "1960s jet-age", "in the jet-age style of the 1960s"),
        ("victorian", "Victorian technical plate", "in the manner of a Victorian technical plate"),
        ("bauhaus", "Bauhaus", "in the Bauhaus manner"),
        ("ukiyoe", "Ukiyo-e", "in the manner of a Japanese ukiyo-e print"),
        ("deco", "Art Deco", "in the Art Deco manner"),
        ("retrofuture", "Retro-futurism", "in a retro-futurist manner"),
    )),
    "palette": ("Palette", "", (
        ("", "As the livery is", ""),
        ("limited", "A few warm tones", "in a limited palette of a few warm tones"),
        ("muted", "Muted", "in muted, dusty colours"),
        ("vivid", "Vivid", "in vivid saturated colour"),
        ("duotone", "Two inks", "in two inks only"),
        ("mono", "Black and white", "in black and white only"),
        ("sepia", "Sepia", "in sepia tones"),
    )),
    "line": ("Line", "", (
        ("", "As the medium has it", ""),
        ("fine", "Fine", "with fine delicate line"),
        ("bold", "Bold", "with bold confident outlines"),
        ("none", "No outlines", "with no outlines, shapes meeting edge to edge"),
        ("sketchy", "Sketchy", "with loose sketchy line"),
    )),
    "texture": ("Texture", "", (
        ("", "As the medium has it", ""),
        ("paper", "Paper grain", "with visible paper grain"),
        ("print", "Print texture", "with the texture of a print, slightly misregistered"),
        ("smooth", "Smooth", "smooth and clean"),
        ("halftone", "Halftone", "with halftone dots in the shading"),
    )),
    "mood": ("Mood", "", (
        ("", "Plain", ""),
        ("heroic", "Heroic", "heroic and dramatic, lit from below"),
        ("calm", "Calm", "calm and serene"),
        ("nostalgic", "Nostalgic", "warm and nostalgic"),
        ("technical", "Precise", "precise and matter-of-fact"),
    )),
}


def build_how(options: dict[str, Any]) -> str:
    """The style builder's picks as one style description."""
    parts: list[str] = []
    for name, (_label, default, choices) in BUILDER.items():
        pick = str(options.get(f"build_{name}") or default)
        phrase = next((p for v, _l, p in choices if v == pick), "")
        if name == "medium":
            phrase = (phrase or choices[0][2]) + " of the {kind}"
        if phrase:
            parts.append(phrase)
    extra = " ".join(str(options.get("build_extra") or "").split())[:300]
    if extra:
        parts.append(extra)
    return ", ".join(parts)


# ----------------------------------------------------------------------
# Backdrops: none keeps the aircraft alone on white paper for the cut-out;
# the rest make a whole picture that fills its frame.
# ----------------------------------------------------------------------
BACKDROPS: dict[str, tuple[str, str]] = {
    "none": ("None: the aircraft alone, cut out on the page", ""),
    "sky": ("A clear sky", "a clear sky in the same style, the light of the time of day"),
    "clouds": ("Above the clouds", "a sea of cloud below and a deep sky above, in the same style"),
    "sunset": ("Sunset", "a sunset sky in the same style, the aircraft lit warmly from the side"),
    "night": ("Night", "a night sky in the same style, the aircraft's lights on and the cabin windows glowing"),
    "storm": ("Storm light", "a brooding storm sky in the same style, a shaft of light on the aircraft"),
    "ornate": ("Ornate framed plate", "a decorative backdrop in the same style, a patterned or foliate ground within a drawn ornamental border that fills the whole picture to its edges, the page's own art in that style and nothing modern"),
    "live": ("The sky as it is now: time of day and weather", ""),
}

GEN = (
    "Draw the {typ} in the reference photo, registration {reg} in {air} livery, afresh as {style}: "
    "a new illustration of this very aircraft in that style, not the photo restyled. The reference photo is for "
    "identity only: its exact livery, colours, logo placement, shape and proportions are kept. The aircraft "
    "in flight, {view}, with its undercarriage up{scene}. {page} No text or lettering beyond the livery's own, "
    "no border, no signature.{outline}"
)
# The visitors: id -> (name for the caption, how the painter is told it, pool). A famous
# craft is described by its shape alone, never named to the painter.
UFOS: dict[str, tuple[str, str, str]] = {
    "saucer": ("Flying saucer", "a classic flying saucer of unmistakably alien make: a wide seamless disc with a low dome, its hull a single flawless surface of pearlescent silver with no panels, rivets or seams, a ring of slowly pulsing coloured lights round its rim and a cold blue-white beam glowing beneath it", "classic"),
    "triangle": ("Black triangle", "a vast flat black triangle of plainly alien origin: a perfect equilateral slab of light-swallowing matte black with no edges or features of any kind, a brilliant white orb of light at each corner and a slowly pulsing red one in the middle, hanging utterly still in the air", "classic"),
    "cigar": ("Cigar craft", "a long cigar-shaped craft of alien origin: a seamless tapering hull of liquid mercury, mirror-bright and rippling, with no wings, windows, engines or markings whatever, trailing a faint shimmer of distorted air", "classic"),
    "orb": ("Glowing orb", "a plainly alien orb: a perfect sphere of plasma-bright light, its surface swirling with colour like a soap bubble, haloed in a glow and crackling with faint tendrils of energy, hanging in the air", "classic"),
    "tictac": ("Tic-tac craft", "a tic-tac craft of alien make: a smooth white featureless capsule like an enormous lozenge, its surface faintly luminous, with no wings, windows, engines or markings, the air round it bent and shimmering", "classic"),
    "adamski": ("Adamski saucer", "a bell-shaped saucer of unmistakably alien make, in the Adamski manner: a seamless domed top with a ring of glowing portholes, a flared skirt and three glowing spheres beneath, the whole hull a flawless unearthly metal with no panels or rivets", "classic"),
    "enterprise": ("Enterprise", "a gleaming white starship: a broad flat saucer section joined by a slim neck to a secondary hull, with two long glowing warp nacelles held out on swept pylons", "famous"),
    "falcon": ("Millennium Falcon", "a battered pale grey disc-shaped light freighter with a forward mandible gap, a cockpit tube on one side and a blue engine glow across its stern", "famous"),
    "xwing": ("X-wing", "a sleek single-seat starfighter with a long nose, four engines, and four wings opened into an X, white with red stripes", "famous"),
    "tie": ("TIE fighter", "a small grey spherical cockpit pod held between two tall black hexagonal solar-panel wings", "famous"),
    "destroyer": ("Star Destroyer", "an immense grey wedge-shaped warship, kilometres long, its surface built up in layered plates with a bridge tower rising from the stern", "famous"),
    "nostromo": ("Nostromo", "a dark, boxy, heavily industrial deep-space commercial towing ship, bristling with antennas and pipework, hauling a vast ore refinery behind it", "famous"),
    "serenity": ("Serenity", "a mid-bulk transport ship with a bulbous forward cabin, a slim body and a great round glowing tail engine, in the shape of a firefly", "famous"),
    "discovery": ("Discovery One", "a long white spine of spherical modules and lattice, with a large white sphere at the front and engines at the far end", "famous"),
    "eagle": ("Eagle Transporter", "a skeletal lattice-framed lunar transporter with a cockpit pod at the front, a cargo pod slung beneath and four landing legs", "famous"),
    "tb2": ("Thunderbird 2", "a huge green heavy cargo aircraft with forward-swept wings, a bulbous body and a pod carried in its belly", "famous"),
    "birdofprey": ("Bird-of-Prey", "a dark green predatory warship with a long neck, a beaked forward section and great wings swept down for attack", "famous"),
    "rocinante": ("Rocinante", "a lean grey corvette-class gunship with a stepped hull, rail guns and bright drive flames", "famous"),
    "viper": ("Colonial Viper", "a stubby single-seat space fighter with a pointed nose, three engines in a row and short swept wings", "famous"),
    "tardis": ("Police box", "a blue 1960s British police telephone box with a lamp on top, tumbling through the air", "famous"),
    "heartofgold": ("Heart of Gold", "a gleaming white starship shaped exactly like a running shoe", "famous"),
    "shuttle": ("Space Shuttle", "the Space Shuttle orbiter in flight, white with black tiles beneath, its gear up", "real"),
    "apollo_csm": ("Apollo command module", "the Apollo command and service module: a silver cone on a cylindrical service module with a dish antenna", "real"),
    "lunar_module": ("Lunar module", "the Apollo lunar module: a gold-foil descent stage on four spidery legs with a boxy grey ascent stage above", "real"),
    "sputnik": ("Sputnik", "Sputnik: a polished metal sphere with four long trailing antennae", "real"),
    "starship": ("Starship", "a tall stainless-steel rocket with a pointed nose and four flaps, gleaming", "real"),
    "vostok": ("Vostok", "the Vostok spacecraft: a spherical capsule atop a conical equipment module", "real"),
    "voyager": ("Voyager probe", "the Voyager space probe: a large white dish antenna on a bus with a long boom", "real"),
    "iss": ("Space station", "the International Space Station: a long truss carrying great golden solar arrays and a cluster of white modules", "real"),
    "zeppelin": ("Zeppelin", "a vast silver rigid airship with a gondola beneath and tail fins", "real"),
}
UFO_POOLS = ("classic", "famous", "real", "all")
POOL_LABELS = {"classic": "UFO", "famous": "Film", "real": "Real"}


def ufo_choices(pool: str) -> list[str]:
    return [k for k, v in UFOS.items() if pool == "all" or v[2] == pool] or [k for k, v in UFOS.items() if v[2] == "classic"]


def visitors_of(chosen: Any) -> list[str]:
    """The craft ticked, or the classics when none of the ticks is a craft."""
    got = [str(c) for c in chosen if str(c) in UFOS] if isinstance(chosen, list) else []
    return got or ufo_choices("classic")


GEN_UFO = (
    "Draw an unidentified flying object as {style}: {what}, seen from the side and a little below, in the air.{alien} "
    "{page} No text or lettering, no border, no signature.{outline}"
)
ALIEN = (
    " Nothing about it is man-made: it has no rivets, panel lines, hatches, wings, fins, engines, exhaust, antennas, "
    "lettering or national markings, no aircraft or rocket parts at all; its hull is a seamless unknown material, "
    "and it hovers without any visible means of lift, with an unearthly glow about it."
)
GEN_FAITHFUL = (
    "Render the {typ} in the reference photo, registration {reg} in {air} livery, as {style}: a faithful "
    "translation of this very photograph into that medium. The photograph is the authority: the same aircraft at "
    "the same angle and attitude as photographed; every element of the livery as it actually appears in the "
    "photograph, its colours, lettering, logos and the registration, whatever the operator's usual colours, and "
    "the particular details of this airframe, its winglets, engines, doors and antennas, reproduced exactly as "
    "they are in the photograph; only the medium changes{scene}. {page} No text or lettering beyond the livery's "
    "own, no border, no signature.{outline}"
)
FIDELITIES = ("photo", "free")
PAGE_ALONE = (
    "The aircraft alone on plain, pure white paper with a clear margin all round and nothing else on the page: "
    "no sky, cloud, ground, runway, shadow, contrail or ornament round or behind it. The style says how the "
    "aircraft is drawn and nothing else."
)
PAGE_WHOLE = "The picture complete, filling the frame edge to edge."
OUTLINE = (
    " The whole aircraft is drawn with a fine, clear, unbroken dark contour line along its entire "
    "outline, fuselage, wings, tail and engines, so that a white or pale part is never lost against "
    "the white paper."
)
VIEWS = {
    "side": "seen from the side and a little below",
    "livery": "seen exactly from the side at eye level, a pure profile view as in an airline's livery drawing, the whole aircraft level and centred, every window and door of the livery shown",
    "quarter": "seen from the front quarter, a little below",
    "above": "seen from above and behind, banking gently",
}
MONO_WORDS = (
    "its exact livery, colours, logo placement, shape and proportions are kept",
    "its exact livery, logo placement, shape and proportions are kept, rendered without any colour: black, white and grey only",
)


def style_of(style: str | None) -> tuple[str, str]:
    if style in STYLES:
        return STYLES[style]
    if style and _CUSTOM_RE.fullmatch(style):
        return ("Your own style", _CUSTOM.get(style, ""))
    return STYLES["poster"]


def custom_tag(how: str) -> str:
    digest = hashlib.sha1(" ".join(how.split()).lower().encode()).hexdigest()
    return "custom" + "".join("abcdefghijklmnopqrstuvwxyz"[int(c, 16) % 26] for c in digest[:8])


_CUSTOM: dict[str, str] = {}


def register_custom(how: str) -> str:
    tag = custom_tag(how)
    _CUSTOM[tag] = how
    return tag


def ufo_key(shape: str, style: str) -> str:
    return f"ufo_{N.slug(shape)}--{style}--p{PROMPT_VERSION}"


def key_for(reg: str, style: str, backdrop: str = "none", view: str = "side", model: str = DEFAULT_MODEL, sky: str = "", fidelity: str = "photo") -> str:
    parts = [N.slug(reg), style, f"p{PROMPT_VERSION}"]
    if fidelity == "free":
        parts.append("free")
    else:
        view = "side"  # as photographed: the view is the photograph's
    if backdrop == "live":
        parts.append(f"bd_{N.slug(sky or 'midday_clear')[:24]}")
    elif backdrop != "none":
        parts.append(f"bd_{backdrop}")
    if view != "side":
        parts.append(f"v_{view}")
    if model != DEFAULT_MODEL:
        parts.append(f"m_{model}")
    return "--".join(parts)


def prompt_for(job: dict[str, Any]) -> str:
    _label, how = style_of(job.get("style"))
    how = str(job.get("how") or how).replace("{kind}", "aircraft")
    if job.get("ufo"):
        what = UFOS.get(str(job["ufo"]), UFOS["saucer"])[1]
        alone = str(job.get("style") or "") not in OWN_PAPER
        pool = UFOS.get(str(job["ufo"]), UFOS["saucer"])[2]
        text = GEN_UFO.format(style=how.replace("aircraft", "craft"), what=what, alien=ALIEN if pool == "classic" else "", page=PAGE_ALONE.replace("The aircraft", "The craft").replace("the aircraft", "the craft") if alone else PAGE_WHOLE, outline=OUTLINE.replace("aircraft", "craft") if alone else "")
        if str(job.get("style") or "") in MONO:
            text += " Rendered without any colour: black, white and grey only."
        return text
    backdrop = str(job.get("backdrop") or "none")
    scene = f", across {BACKDROPS[backdrop][1]}" if backdrop in BACKDROPS and backdrop not in ("none", "live") else ""
    if backdrop == "live":
        scene = f", across {job.get('sky_words') or 'a clear sky in the same style'}"
    if backdrop == "ornate":
        scene = ", as the single subject of an ornate framed plate: the aircraft large in the middle on " + BACKDROPS["ornate"][1]
    alone = backdrop == "none" and str(job.get("style") or "") not in OWN_PAPER
    if str(job.get("fidelity") or "photo") != "free":
        text = GEN_FAITHFUL.format(
            typ=job.get("typ") or "aircraft",
            reg=job.get("reg") or "",
            air=job.get("air") or "its own",
            style=how,
            scene=scene.replace(", across ", ", set across ") if scene and backdrop != "ornate" else scene,
            page=PAGE_ALONE if alone else PAGE_WHOLE,
            outline=OUTLINE if alone else "",
        )
        if str(job.get("style") or "") in MONO:
            text = text.replace("its colours, lettering, logos", "its lettering, logos").replace("only the medium changes", "only the medium changes, rendered without any colour: black, white and grey only")
        return text
    text = GEN.format(
        typ=job.get("typ") or "aircraft",
        reg=job.get("reg") or "",
        air=job.get("air") or "its own",
        style=how,
        view=VIEWS.get(str(job.get("view") or "side"), VIEWS["side"]),
        scene=scene,
        page=PAGE_ALONE if alone else PAGE_WHOLE,
        outline=OUTLINE if alone else "",
    )
    if str(job.get("style") or "") in MONO:
        text = text.replace(*MONO_WORDS)
    return text


def request_body(model: str, prompt: str, image_url: str, aspect: str) -> dict[str, Any]:
    urls = [image_url]
    portrait = aspect == "3:4"
    if model == "flux_kontext":
        return {"prompt": prompt, "image_url": urls[0], "num_images": 1, "output_format": "jpeg", "aspect_ratio": aspect}
    if model == "gpt_image":
        return {"prompt": prompt, "image_urls": urls, "image_size": "portrait_4_3" if portrait else "landscape_4_3", "background": "opaque", "quality": "medium", "output_format": "jpeg", "num_images": 1}
    if model == "seedream":
        return {"prompt": prompt, "image_urls": urls, "image_size": "portrait_4_3" if portrait else "landscape_4_3", "num_images": 1}
    body: dict[str, Any] = {"prompt": prompt, "image_urls": urls, "num_images": 1, "output_format": "jpeg", "aspect_ratio": aspect}
    if model == "nano_banana_pro":
        body["resolution"] = "1K"
    return body


def model_of(model: str | None) -> str:
    return model if model in MODELS else DEFAULT_MODEL


# ----------------------------------------------------------------------
# Files, budget, state
# ----------------------------------------------------------------------
def gen_dir(data_dir: Path) -> Path:
    folder = data_dir / "gen"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def budget_used(folder: Path) -> int:
    used = N.read_json(folder / "budget.json", {})
    return int(used.get(time.strftime("%Y-%m-%d"), 0)) if isinstance(used, dict) else 0


def _spend(folder: Path) -> None:
    with _LOCK:
        N.write(folder / "budget.json", json.dumps({time.strftime("%Y-%m-%d"): budget_used(folder) + 1}).encode())


def whole(value: Any, default: int, low: int = 0, high: int = 100000) -> int:
    with contextlib.suppress(TypeError, ValueError):
        if str(value).strip() != "":
            return min(high, max(low, int(float(value))))
    return default


def daily_cap(settings: dict[str, Any] | None) -> int:
    n = whole((settings or {}).get("gen_daily_cap"), GEN_DAILY_CAP)
    return n or UNLIMITED


def configure(settings: dict[str, Any] | None) -> None:
    global _PARALLEL, _PER_FETCH
    s = settings or {}
    _PER_FETCH = whole(s.get("gen_per_refresh"), PER_FETCH, 1, 50)
    _PARALLEL = whole(s.get("gen_parallel"), BATCH_PARALLEL, 1, 8)


def per_fetch() -> int:
    return _PER_FETCH


def archive(folder: Path, key: str) -> None:
    arch = folder / "archive"
    arch.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for ext in (".jpg", ".json"):
        with contextlib.suppress(OSError):
            os.replace(folder / f"{key}{ext}", arch / f"{key}__{stamp}{ext}")
    drop_derived(folder, key)


def drop_derived(folder: Path, key: str) -> None:
    pattern = re.compile(rf"{re.escape(key)}(_\d+(_\w+)?\.(jpg|png)|_cut\d*(_\w+)?\.png|\.paper)")
    with contextlib.suppress(OSError):
        for f in folder.iterdir():
            if pattern.fullmatch(f.name):
                with contextlib.suppress(OSError):
                    f.unlink()


def state(key: str, folder: Path) -> str:
    with _LOCK:
        if key in _PAINTING:
            return "running"
    if (folder / f"{key}.jpg").exists():
        return "ready"
    err = N.read_json(folder / f"{key}.err", None)
    if isinstance(err, dict) and time.time() - float(err.get("at") or 0) < GEN_RETRY_S:
        return "failed"
    return "none"


def why_failed(key: str, folder: Path) -> str:
    err = N.read_json(folder / f"{key}.err", None)
    return str(err.get("why") or "") if isinstance(err, dict) else ""


# ----------------------------------------------------------------------
# The cut-out: a painting on white paper becomes a PNG with alpha, the
# paper's colour read from the corners and the noise of its texture allowed
# for, so a cream or grainy paper cuts as cleanly as a white one.
# ----------------------------------------------------------------------
def cut_out(raw: bytes) -> bytes | None:
    """The painting as a PNG with alpha. The paper is what is paper-coloured
    and reaches the edge of the page; everything else, a white fuselage inside
    its contour line included, is the aircraft and stays."""
    try:
        import numpy as np
        from PIL import Image, ImageFilter
    except ImportError:  # pragma: no cover
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    a = np.asarray(im).astype(float)
    H, W = a.shape[:2]
    c = 30
    corners = np.concatenate([a[:c, :c].reshape(-1, 3), a[:c, -c:].reshape(-1, 3), a[-c:, :c].reshape(-1, 3), a[-c:, -c:].reshape(-1, 3)])
    paper = np.median(corners, axis=0)
    # the paper's own grain, measured on the corner pixels that are paper (a frame line or a
    # wingtip in a corner would otherwise read as grain and let the whole page through)
    spread = np.sqrt(((corners - paper) ** 2).sum(-1))
    near = spread[spread < 60]
    noise = float(near.std()) if len(near) > 50 else 0.0
    d = np.sqrt(((a - paper) ** 2).sum(-1))
    thr = max(22.0, 10 + 4 * noise)
    paperlike = d < thr
    # the paper: the paper-coloured region joined to the page's edge, found on a half-size mask.
    # A frame line or a vignette the model drew round the page would wall the flood in and keep
    # the whole page; then the seeds move inward, a little at a time, until the page lets go.
    s = 2
    small = paperlike[: H // s * s, : W // s * s].reshape(H // s, s, W // s, s).all(axis=(1, 3))
    h, w = small.shape
    keep_small = None
    for inset in (0, 0.03, 0.06, 0.1, 0.15):
        iy, ix = int(h * inset), int(w * inset)
        bg = np.zeros_like(small)
        stack = []
        for x in range(ix, w - ix):
            for y in (iy, h - 1 - iy):
                if small[y, x]:
                    stack.append((y, x))
        for y in range(iy, h - iy):
            for x in (ix, w - 1 - ix):
                if small[y, x]:
                    stack.append((y, x))
        for y, x in stack:
            bg[y, x] = True
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and small[ny, nx] and not bg[ny, nx]:
                    bg[ny, nx] = True
                    stack.append((ny, nx))
        # everything outside the seed ring is paper too, frame and all; and the page's outermost
        # rim always, since a darker edge the model left there would otherwise stay as a line
        rim = max(1, int(round(min(h, w) * 0.012)))
        for lo in (iy, rim):
            bg[:lo, :] = True
            bg[h - lo:, :] = True
        for lo in (ix, rim):
            bg[:, :lo] = True
            bg[:, w - lo:] = True
        keep_small = ~bg
        if keep_small.mean() < 0.6:
            break
    # stray slivers (a stroke left at an edge, a speck) go; the aircraft and anything of size stays
    lab = np.zeros(keep_small.shape, dtype=np.int32)
    sizes: dict[int, int] = {}
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if keep_small[y0, x0] and not lab[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                lab[y0, x0] = n
                count = 0
                while stack:
                    y, x = stack.pop()
                    count += 1
                    for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        if 0 <= ny < h and 0 <= nx < w and keep_small[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            stack.append((ny, nx))
                sizes[n] = count
    if sizes:
        biggest = max(sizes.values())
        floor = max(40, int(0.004 * h * w), biggest // 40)
        for k, count in sizes.items():
            if count < floor:
                keep_small[lab == k] = False
    keep = np.zeros((H, W), dtype=bool)
    keep[: h * s, : w * s] = np.kron(keep_small, np.ones((s, s), dtype=bool))
    # the edge: soft where the paint meets the paper, hard inside the outline
    soft = np.clip((d - thr) / 35, 0, 1)
    hard = Image.fromarray((keep * 255).astype("uint8")).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    hard_a = np.asarray(hard) > 0
    alpha = np.where(hard_a, np.maximum(soft, 0.98), 0.0)
    alpha8 = np.asarray(Image.fromarray((alpha * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.6)))
    share = (alpha8 > 40).mean()
    if share < 0.004 or share > 0.9:
        return None
    rgba = np.dstack([a.astype("uint8"), alpha8])
    out = Image.fromarray(rgba.astype("uint8"), "RGBA")
    bbox = Image.fromarray(alpha8).point(lambda p: 255 if p > 40 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def picture(key: str, folder: Path, px: int, levels: str, whole_: bool) -> dict[str, Any] | None:
    """A kept painting for the page: the cut-out as a PNG data URI (or the
    whole picture as a JPEG), resized, cached per size and panel."""
    img = folder / f"{key}.jpg"
    if not img.exists():
        return None
    meta = N.read_json(folder / f"{key}.json", {})
    meta = meta if isinstance(meta, dict) else {}
    try:
        raw = img.read_bytes()
    except OSError:
        return None
    if whole_:
        src = N.render(raw, px, None, folder / f"{key}_{px}.jpg", levels)
        return {"src": src, "kind": "painting", "whole": True, "credit": str(meta.get("credit") or ""), "aspect": N.aspect_of(src)} if src else None
    cut = folder / f"{key}_cut{CUT_VERSION}.png"
    if not cut.exists():
        png = cut_out(raw)
        if not png:
            N.write(folder / f"{key}.err", json.dumps({"why": "the painting could not be cut out", "at": int(time.time())}).encode())
            return None
        N.write(cut, png)
    try:
        png = cut.read_bytes()
    except OSError:
        return None
    src = _png_uri(png, px, folder / f"{key}_cut{CUT_VERSION}_{px}_{levels}.png", levels)
    return {"src": src, "kind": "painting", "whole": False, "credit": str(meta.get("credit") or ""), "aspect": N.aspect_of(src)} if src else None


def _png_uri(png: bytes, px: int, cache: Path, levels: str) -> str:
    if cache.exists():
        with contextlib.suppress(OSError):
            return "data:image/png;base64," + base64.b64encode(cache.read_bytes()).decode()
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        return "data:image/png;base64," + base64.b64encode(png).decode()
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return ""
    im.thumbnail((px, px), Image.Resampling.LANCZOS)
    if levels != "colour":
        rgb, alpha = im.convert("RGB"), im.split()[3]
        cutoff = {"gray16": 0.5}.get(levels, 1.0)
        grey = ImageOps.autocontrast(rgb.convert("L"), cutoff=cutoff)
        if levels == "mono":
            grey = grey.point([round(255 * (i / 255) ** 0.8) for i in range(256)])
        im = Image.merge("LA", (grey, alpha))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    data = out.getvalue()
    N.write(cache, data)
    return "data:image/png;base64," + base64.b64encode(data).decode()


# ----------------------------------------------------------------------
# The queue
# ----------------------------------------------------------------------
_PAINTING: set[str] = set()
_SINCE: dict[str, tuple[float, str, str]] = {}
_FINISHED: list[tuple[str, float]] = []
_QUEUE: list[tuple[dict[str, Any], Path, str, int | None]] = []
_STOPS: dict[str, threading.Event] = {}
_WORKERS = 0
_LOCK = threading.Lock()
_TRAY = T.Batch("paint", "Painting aircraft")


def paint(job: dict[str, Any], data_dir: Path, fal_key: str, stop: threading.Event | None = None) -> str | None:
    """Make one painting; None when done, else why not."""
    folder = gen_dir(data_dir)
    key = job["key"]
    if (folder / f"{key}.jpg").exists():
        return None
    photo = str(job.get("photo") or "")
    t2i = bool(job.get("ufo"))
    if not photo and not t2i:
        N.write(folder / f"{key}.err", json.dumps({"why": "no photo", "at": int(time.time())}).encode())
        return "no photo"
    model = "nano_banana" if t2i else model_of(job.get("model"))
    prompt = prompt_for(job)
    aspect = str(job.get("aspect") or "4:3")
    _spend(folder)
    got = err = None
    for attempt in range(2):
        body = (
            {"prompt": prompt, "num_images": 1, "output_format": "jpeg", "aspect_ratio": aspect}
            if t2i
            else request_body(model, prompt, photo, aspect)
        )
        got, err = N.get_json(
            FAL + (T2I_ENDPOINT if t2i else MODELS[model]["endpoint"]),
            fal_key,
            auth_scheme="Key",
            body=json.dumps(body).encode(),
            timeout=GEN_TIMEOUT_S,
            detail=True,
        )
        if stop is not None and stop.is_set():
            return STOPPED
        # a 422 is the model declining this prompt this once; the same prompt usually goes through on a second ask
        if got is not None or not (err or "").startswith("HTTP 422") or attempt:
            break
    url = ""
    if isinstance(got, dict):
        imgs = got.get("images")
        if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict):
            url = str(imgs[0].get("url") or "")
    if not url:
        why = {"auth": "fal.ai refused the key", "unreachable": "fal.ai could not be reached"}.get(err or "", err or "no image came back")
        N.write(folder / f"{key}.err", json.dumps({"why": why, "at": int(time.time())}).encode())
        return why
    raw, err2 = N.http(url, accept="image/*", timeout=60)
    if not raw:
        N.write(folder / f"{key}.err", json.dumps({"why": f"the painting could not be fetched ({err2})", "at": int(time.time())}).encode())
        return "fetch failed"
    N.write(folder / f"{key}.jpg", raw)
    N.write(
        folder / f"{key}.json",
        json.dumps(
            {
                "reg": job.get("reg"), "typ": job.get("typ"), "air": job.get("air"), "style": job.get("style"),
                "how": job.get("how") or "", "backdrop": job.get("backdrop") or "none", "model": model,
                "credit": f"an unidentified object painted by {MODELS[model]['label']}" if t2i else f"painted by {MODELS[model]['label']} from a photograph by {job.get('by') or 'a planespotter'} (planespotters.net)",
                "ufo": job.get("ufo") or "",
                "photo_by": job.get("by") or "", "photo_link": job.get("link") or "", "prompt": prompt,
                "made": int(time.time()), "prompt_version": PROMPT_VERSION,
            },
            ensure_ascii=False,
        ).encode(),
    )
    with contextlib.suppress(OSError):
        (folder / f"{key}.err").unlink()
    return None


def _finish(key: str) -> None:
    with _LOCK:
        _PAINTING.discard(key)
        _SINCE.pop(key, None)
        _STOPS.pop(key, None)
        _FINISHED.append((key, time.time()))
        del _FINISHED[:-20]
    _TRAY.done(key)


def _note_stopped(key: str, job: dict[str, Any], data_dir: Path) -> None:
    N.write(gen_dir(data_dir) / f"{key}.err", json.dumps({"why": STOPPED, "at": int(time.time()), "reg": job.get("reg")}).encode())


def _run_one(job: dict[str, Any], data_dir: Path, fal_key: str) -> None:
    key = job["key"]
    stop = _STOPS[key]

    def go() -> None:
        try:
            why = paint(job, data_dir, fal_key, stop)
            if why == STOPPED:
                _note_stopped(key, job, data_dir)
        except Exception as exc:  # noqa: BLE001
            if not stop.is_set():
                N.write(gen_dir(data_dir) / f"{key}.err", json.dumps({"why": str(exc)[:200], "at": int(time.time())}).encode())

    t = threading.Thread(target=go, name=f"overhead-paint-{key[:16]}", daemon=True)
    t.start()
    while t.is_alive() and not stop.is_set():
        t.join(0.25)
    if stop.is_set():
        _note_stopped(key, job, data_dir)


def _work() -> None:
    global _WORKERS
    while True:
        with _LOCK:
            if not _QUEUE:
                _WORKERS -= 1
                return
            job, data_dir, fal_key, cap = _QUEUE.pop(0)
            key = job["key"]
            _STOPS[key] = threading.Event()
            _SINCE[key] = (time.time(), str(job.get("reg") or key), str(job.get("style") or "poster"))
        try:
            if cap is not None and budget_used(gen_dir(data_dir)) >= cap:
                continue
            _run_one(job, data_dir, fal_key)
        finally:
            _finish(key)


def start(job: dict[str, Any], data_dir: Path, fal_key: str, cap: int | None = None) -> bool:
    global _WORKERS
    key = job["key"]
    if not job.get("how"):
        job["how"] = style_of(job.get("style"))[1]
    with _LOCK:
        if key in _PAINTING:
            return False
        _PAINTING.add(key)
        _QUEUE.append((job, data_dir, fal_key, cap))
        _TRAY.add(key, lambda: stop_all(data_dir))
        spawn = _WORKERS < _PARALLEL
        if spawn:
            _WORKERS += 1
    if spawn:
        threading.Thread(target=_work, name="overhead-paint-worker", daemon=True).start()
    return True


def start_batch(jobs: list[dict[str, Any]], data_dir: Path, fal_key: str, cap: int) -> bool:
    queued = False
    for job in jobs:
        if budget_used(gen_dir(data_dir)) >= cap:
            break
        queued = start(job, data_dir, fal_key, cap) or queued
    return queued


def stop(key: str, data_dir: Path) -> bool:
    with _LOCK:
        for i, (job, *_rest) in enumerate(_QUEUE):
            if job["key"] == key:
                gone = _QUEUE.pop(i)[0]
                _PAINTING.discard(key)
                break
        else:
            gone = None
            ev = _STOPS.get(key)
            if ev is None:
                return False
            ev.set()
    if gone is not None:
        _note_stopped(key, gone, data_dir)
    _TRAY.done(key, stopped=True)
    return True


def cull_queued(subject: str, keep: set[str]) -> list[str]:
    gone: list[str] = []
    with _LOCK:
        for i in range(len(_QUEUE) - 1, -1, -1):
            job = _QUEUE[i][0]
            if job.get("origin") == "preview" and job.get("subject") == subject and job["key"] not in keep:
                _QUEUE.pop(i)
                _PAINTING.discard(job["key"])
                gone.append(job["key"])
    for key in gone:
        _TRAY.done(key, stopped=True)
    return gone


def stop_all(data_dir: Path) -> int:
    with _LOCK:
        keys = [j["key"] for j, *_r in _QUEUE] + list(_STOPS)
    return sum(1 for k in keys if stop(k, data_dir))


def may_start(key: str, folder: Path, fal_key: str, cap: int) -> tuple[bool, str]:
    st = state(key, folder)
    if st != "none":
        return False, st
    if not fal_key:
        return False, "no_key"
    if budget_used(folder) >= cap:
        return False, "capped"
    return True, ""


def progress(folder: Path, cap: int, has_key: bool) -> dict[str, Any]:
    now = time.time()
    with _LOCK:
        running = [{"key": k, "name": name, "style": style_of(style)[0], "seconds": int(now - since)} for k, (since, name, style) in _SINCE.items()]
        queued = [{"key": j["key"], "name": str(j.get("reg") or j["key"]), "style": style_of(j.get("style"))[0]} for j, *_r in _QUEUE]
        finished = [{"key": k, "at": int(at)} for k, at in _FINISHED]
    return {"running": running, "queued": queued, "finished": finished, "used": budget_used(folder), "cap": cap, "has_key": has_key}
