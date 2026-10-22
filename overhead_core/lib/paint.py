"""AI paintings of aircraft through fal.ai: each airframe painted once from
its own photograph, in a style, on white paper (cut out on the page) or as a
whole picture on a painted backdrop. The prompts, the styles and the cut-out
are here; the budget, the queue, the files and the admin page are Tesserae's
(``app.artwork``, 0.463 and later). Loaded by path."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import re
import sys
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

try:
    from app import artwork  # Tesserae 0.463+: the pictures a widget makes and keeps
    from app import fal as _fal
except (
    ImportError
):  # an older Tesserae: the widgets still draw, from photographs, and say why
    artwork = None  # type: ignore[assignment]
    _fal = None  # type: ignore[assignment]

NEEDS_HOST = "AI paintings need Tesserae 0.463 or later; this server is older, so the photographs show."


class _NoArt:
    """What ART.open() hands a fetch on a Tesserae without app.artwork: every
    request answers no_host, nothing is started, the note says why."""

    key = ""
    preview = False
    settled = True
    subject = ""
    cell = ""
    cap = 0
    started = 0
    pending = 0
    busy = False
    c = None

    def __init__(self) -> None:
        self.states: dict[str, int] = {}
        self.asked: dict[str, Any] = {}
        self.data_dir = Path(".")

    def request(
        self, key: str, payload: dict[str, Any], *, title: str = "", want: bool = True
    ) -> Any:
        from types import SimpleNamespace

        self.states["no_host"] = self.states.get("no_host", 0) + 1
        return SimpleNamespace(
            key=key,
            state="no_host",
            ready=False,
            path=None,
            meta={},
            why=NEEDS_HOST,
            credit="",
        )

    def url(self, *a: Any, **k: Any) -> str:
        return ""

    def picture(self, *a: Any, **k: Any) -> None:
        return None

    def live(self) -> dict[str, int]:
        return {"live_refresh_s": 0, "live_pending": 0}

    def notes(self) -> list[str]:
        return [NEEDS_HOST] if self.states.get("no_host") else []

    def status(self) -> list[str]:
        return []

    def finish(self, *a: Any, **k: Any) -> None:
        return None


class _NoArtwork:
    """The collection on an older Tesserae: it opens to _NoArt and answers
    nothing to everything else (the paintings page does not exist there)."""

    name = "paintings"
    href = "/plugins/overhead_core/"
    actions: list[Any] = []
    extra_template = None
    extra_context = None
    _DEFAULTS: dict[str, Any] = {
        "state": "none",
        "why_failed": "",
        "held": {},
        "dashboards": [],
        "listing": [],
        "errors": [],
        "versions": [],
        "budget_used": 0,
        "cap": 0,
        "adopt": False,
        "progress": {
            "running": [],
            "queued": [],
            "finished": [],
            "used": 0,
            "cap": 0,
            "used_text": "",
            "cap_text": "",
            "held": 0,
        },
    }

    def open(
        self,
        ctx: dict[str, Any],
        settings: dict[str, Any] | None,
        *,
        subject: str = "",
        cell: str = "",
    ) -> _NoArt:
        return _NoArt()

    def folder(self, data_dir: Path) -> Path:
        return Path(data_dir) / self.name

    def __getattr__(self, name: str) -> Any:
        default = self._DEFAULTS.get(name)
        return lambda *a, **k: default


FAL = "https://fal.run/"
T2I_ENDPOINT = (
    "fal-ai/nano-banana"  # a picture from words alone, for what has no photograph
)
MODELS: dict[str, dict[str, str]] = {
    "nano_banana": {
        "label": "Nano Banana",
        "endpoint": "fal-ai/nano-banana/edit",
        "cost": "about US$0.04",
        "cents": 4,
    },
    "nano_banana_pro": {
        "label": "Nano Banana Pro",
        "endpoint": "fal-ai/nano-banana-pro/edit",
        "cost": "about US$0.15",
        "cents": 15,
    },
    "flux_kontext": {
        "label": "FLUX.1 Kontext Pro",
        "endpoint": "fal-ai/flux-pro/kontext",
        "cost": "about US$0.04",
        "cents": 4,
    },
    "gpt_image": {
        "label": "GPT Image 2",
        "endpoint": "openai/gpt-image-2/edit",
        "cost": "about US$0.05",
        "cents": 5,
    },
    "seedream": {
        "label": "Seedream 4",
        "endpoint": "fal-ai/bytedance/seedream/v4/edit",
        "cost": "about US$0.03",
        "cents": 3,
    },
}
DEFAULT_MODEL = "nano_banana"
GEN_TIMEOUT_S = 120
GEN_DAILY_CAP = 12  # paintings a day, the setting before the budget was in dollars
GEN_DAILY_CENTS = 400  # US$4 a day, about a hundred Nano Banana paintings
TYPICAL_CENTS = 4
UNLIMITED = 10**9
GEN_RETRY_S = 6 * 3600
PER_FETCH = 3
BATCH_PARALLEL = 3
_PARALLEL = BATCH_PARALLEL
_PER_FETCH = PER_FETCH
STOPPED = "stopped"
PROMPT_VERSION = 3
CUT_VERSION = 4  # the cut-outs are redone from the kept paintings when this changes
# a backdrop painting's drawn mount is cut off again when this changes
MOUNT_VERSION = 1
TRIM = 0.01  # the share of the page's shorter side cut off each edge before the cut-out
NOTE_NO_KEY = (
    "AI pictures need a fal.ai key: this widget's own, or the app's under Settings."
)
NOTE_GEN_CAP = "AI paintings: to-day's budget of {cap} is spent; more to-morrow."
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
# Kept working for cells already set to them, left out of the Style picker: at panel size they
# read as another style, or stay too close to the photograph
HIDDEN = frozenset({"woodblock", "midcentury", "engraving_colour", "pointillism", "pencil", "papercraft"})
STYLE_IDS = (*STYLES, "builder", "custom")
# Styles without colour: the prompt asks for black, white and grey only
MONO = {"engraving", "technical", "pencil", "charcoal"}
# Styles that make a whole picture on their own ground, never cut out
OWN_PAPER = {"blueprint", "stamp", "synthwave", "chalk", "gilt", "pulp"}
CUSTOM_EXAMPLE = "a chalk pastel drawing on grey paper, soft and smudgy, with the sun catching the fuselage"
CUSTOM_PRESETS = [
    {
        "label": "Gouache poster",
        "value": "a vintage airline poster in gouache: flat confident shapes, a warm limited palette, crisp edges",
    },
    {
        "label": "Cutaway",
        "value": "a 1950s magazine cutaway illustration: the fuselage opened to show seats and cargo, labelled in small neat capitals",
    },
    {"label": "Chalk pastel", "value": CUSTOM_EXAMPLE},
    {
        "label": "Aviation art",
        "value": "a traditional oil painting in the manner of classic aviation art: dramatic light, polished metal, confident brushwork",
    },
    {
        "label": "Comic ink",
        "value": "a comic-book ink drawing with bold outlines, hatched shadows and flat halftone colour",
    },
    {
        "label": "Neon line",
        "value": "a single-weight neon line drawing on white: one continuous glowing line describing the aircraft",
    },
]
_CUSTOM_RE = re.compile(r"custom[a-z]{8}")

BUILDER: dict[str, tuple[str, str, tuple[tuple[str, str, str], ...]]] = {
    "medium": (
        "Medium",
        "gouache",
        (
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
        ),
    ),
    "period": (
        "Period or school",
        "",
        (
            ("", "None in particular", ""),
            ("1930s", "1930s travel poster", "in the manner of a 1930s travel poster"),
            (
                "1950s",
                "1950s airline brochure",
                "in the manner of a 1950s airline brochure",
            ),
            ("1960s", "1960s jet-age", "in the jet-age style of the 1960s"),
            (
                "victorian",
                "Victorian technical plate",
                "in the manner of a Victorian technical plate",
            ),
            ("bauhaus", "Bauhaus", "in the Bauhaus manner"),
            ("ukiyoe", "Ukiyo-e", "in the manner of a Japanese ukiyo-e print"),
            ("deco", "Art Deco", "in the Art Deco manner"),
            ("retrofuture", "Retro-futurism", "in a retro-futurist manner"),
        ),
    ),
    "palette": (
        "Palette",
        "",
        (
            ("", "As the livery is", ""),
            ("limited", "A few warm tones", "in a limited palette of a few warm tones"),
            ("muted", "Muted", "in muted, dusty colours"),
            ("vivid", "Vivid", "in vivid saturated colour"),
            ("duotone", "Two inks", "in two inks only"),
            ("mono", "Black and white", "in black and white only"),
            ("sepia", "Sepia", "in sepia tones"),
        ),
    ),
    "line": (
        "Line",
        "",
        (
            ("", "As the medium has it", ""),
            ("fine", "Fine", "with fine delicate line"),
            ("bold", "Bold", "with bold confident outlines"),
            ("none", "No outlines", "with no outlines, shapes meeting edge to edge"),
            ("sketchy", "Sketchy", "with loose sketchy line"),
        ),
    ),
    "texture": (
        "Texture",
        "",
        (
            ("", "As the medium has it", ""),
            ("paper", "Paper grain", "with visible paper grain"),
            (
                "print",
                "Print texture",
                "with the texture of a print, slightly misregistered",
            ),
            ("smooth", "Smooth", "smooth and clean"),
            ("halftone", "Halftone", "with halftone dots in the shading"),
        ),
    ),
    "mood": (
        "Mood",
        "",
        (
            ("", "Plain", ""),
            ("heroic", "Heroic", "heroic and dramatic, lit from below"),
            ("calm", "Calm", "calm and serene"),
            ("nostalgic", "Nostalgic", "warm and nostalgic"),
            ("technical", "Precise", "precise and matter-of-fact"),
        ),
    ),
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
    "sky": (
        "A clear sky",
        "a clear sky in the same style, the light of the time of day",
    ),
    "clouds": (
        "Above the clouds",
        "a sea of cloud below and a deep sky above, in the same style",
    ),
    "sunset": (
        "Sunset",
        "a sunset sky in the same style, the aircraft lit warmly from the side",
    ),
    "night": (
        "Night",
        "a night sky in the same style, the aircraft's lights on and the cabin windows glowing",
    ),
    "storm": (
        "Storm light",
        "a brooding storm sky in the same style, a shaft of light on the aircraft",
    ),
    "ornate": (
        "Ornate framed plate",
        "a decorative backdrop in the same style, a patterned or foliate ground within a drawn ornamental border that fills the whole picture to its edges, the page's own art in that style and nothing modern",
    ),
    "live": ("The sky as it is now: time of day and weather", ""),
}

GEN = (
    "Draw the {typ} in the reference photo, registration {reg} in {air} livery, flying with its wheels up, "
    "afresh as {style}: "
    "a new illustration of this very aircraft in that style, not the photo restyled. The reference photo is for "
    "identity only: its exact livery, colours, logo placement, shape and proportions are kept. The aircraft "
    "in flight, {view}, with its undercarriage up{scene}. The airline's emblem on the tail and the lettering along "
    "the fuselage are reproduced exactly as in the photograph.{logo} {gear} {page} No text or lettering beyond the "
    "livery's own, no border, no signature.{outline}"
)
# The visitors: id -> (name for the caption, how the painter is told it, pool). A famous
# craft is described by its shape alone, never named to the painter.
UFOS: dict[str, tuple[str, str, str]] = {
    "saucer": (
        "Flying saucer",
        "a classic flying saucer of unmistakably alien make: a wide seamless disc with a low dome, its hull a single flawless surface of pearlescent silver with no panels, rivets or seams, a ring of slowly pulsing coloured lights round its rim and a cold blue-white beam glowing beneath it",
        "classic",
    ),
    "triangle": (
        "Black triangle",
        "a vast flat black triangle of plainly alien origin: a perfect equilateral slab of light-swallowing matte black with no edges or features of any kind, a brilliant white orb of light at each corner and a slowly pulsing red one in the middle, hanging utterly still in the air",
        "classic",
    ),
    "cigar": (
        "Cigar craft",
        "a long cigar-shaped craft of alien origin: a seamless tapering hull of liquid mercury, mirror-bright and rippling, with no wings, windows, engines or markings whatever, trailing a faint shimmer of distorted air",
        "classic",
    ),
    "orb": (
        "Glowing orb",
        "a plainly alien orb: a perfect sphere of plasma-bright light, its surface swirling with colour like a soap bubble, haloed in a glow and crackling with faint tendrils of energy, hanging in the air",
        "classic",
    ),
    "tictac": (
        "Tic-tac craft",
        "a tic-tac craft of alien make: a smooth white featureless capsule like an enormous lozenge, its surface faintly luminous, with no wings, windows, engines or markings, the air round it bent and shimmering",
        "classic",
    ),
    "adamski": (
        "Adamski saucer",
        "a bell-shaped saucer of unmistakably alien make, in the Adamski manner: a seamless domed top with a ring of glowing portholes, a flared skirt and three glowing spheres beneath, the whole hull a flawless unearthly metal with no panels or rivets",
        "classic",
    ),
    "enterprise": (
        "Enterprise",
        "a gleaming white starship: a broad flat saucer section joined by a slim neck to a secondary hull, with two long glowing warp nacelles held out on swept pylons",
        "famous",
    ),
    "falcon": (
        "Millennium Falcon",
        "a battered pale grey disc-shaped light freighter with a forward mandible gap, a cockpit tube on one side and a blue engine glow across its stern",
        "famous",
    ),
    "xwing": (
        "X-wing",
        "a sleek single-seat starfighter with a long nose, four engines, and four wings opened into an X, white with red stripes",
        "famous",
    ),
    "tie": (
        "TIE fighter",
        "a small grey spherical cockpit pod held between two tall black hexagonal solar-panel wings",
        "famous",
    ),
    "destroyer": (
        "Star Destroyer",
        "an immense grey wedge-shaped warship, kilometres long, its surface built up in layered plates with a bridge tower rising from the stern",
        "famous",
    ),
    "nostromo": (
        "Nostromo",
        "a dark, boxy, heavily industrial deep-space commercial towing ship, bristling with antennas and pipework, hauling a vast ore refinery behind it",
        "famous",
    ),
    "serenity": (
        "Serenity",
        "a mid-bulk transport ship with a bulbous forward cabin, a slim body and a great round glowing tail engine, in the shape of a firefly",
        "famous",
    ),
    "discovery": (
        "Discovery One",
        "a long white spine of spherical modules and lattice, with a large white sphere at the front and engines at the far end",
        "famous",
    ),
    "eagle": (
        "Eagle Transporter",
        "a skeletal lattice-framed lunar transporter with a cockpit pod at the front, a cargo pod slung beneath and four landing legs",
        "famous",
    ),
    "tb2": (
        "Thunderbird 2",
        "a huge green heavy cargo aircraft with forward-swept wings, a bulbous body and a pod carried in its belly",
        "famous",
    ),
    "birdofprey": (
        "Bird-of-Prey",
        "a dark green predatory warship with a long neck, a beaked forward section and great wings swept down for attack",
        "famous",
    ),
    "rocinante": (
        "Rocinante",
        "a lean grey corvette-class gunship with a stepped hull, rail guns and bright drive flames",
        "famous",
    ),
    "viper": (
        "Colonial Viper",
        "a stubby single-seat space fighter with a pointed nose, three engines in a row and short swept wings",
        "famous",
    ),
    "tardis": (
        "Police box",
        "a blue 1960s British police telephone box with a lamp on top, tumbling through the air",
        "famous",
    ),
    "heartofgold": (
        "Heart of Gold",
        "a gleaming white starship shaped exactly like a running shoe",
        "famous",
    ),
    "shuttle": (
        "Space Shuttle",
        "the Space Shuttle orbiter in flight, white with black tiles beneath, its gear up",
        "real",
    ),
    "apollo_csm": (
        "Apollo command module",
        "the Apollo command and service module: a silver cone on a cylindrical service module with a dish antenna",
        "real",
    ),
    "lunar_module": (
        "Lunar module",
        "the Apollo lunar module: a gold-foil descent stage on four spidery legs with a boxy grey ascent stage above",
        "real",
    ),
    "sputnik": (
        "Sputnik",
        "Sputnik: a polished metal sphere with four long trailing antennae",
        "real",
    ),
    "starship": (
        "Starship",
        "a tall stainless-steel rocket with a pointed nose and four flaps, gleaming",
        "real",
    ),
    "vostok": (
        "Vostok",
        "the Vostok spacecraft: a spherical capsule atop a conical equipment module",
        "real",
    ),
    "voyager": (
        "Voyager probe",
        "the Voyager space probe: a large white dish antenna on a bus with a long boom",
        "real",
    ),
    "iss": (
        "Space station",
        "the International Space Station: a long truss carrying great golden solar arrays and a cluster of white modules",
        "real",
    ),
    "zeppelin": (
        "Zeppelin",
        "a vast silver rigid airship with a gondola beneath and tail fins",
        "real",
    ),
}
# Reference pictures for the visitors, from Wikimedia Commons (title, licence, author) and NASA,
# each handed to the painter for the craft's shape; a craft without one is painted from words alone.
UFO_REFS: dict[str, dict[str, str]] = {
    "saucer": {
        "title": "UFO landing, artistic representation.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cd/UFO_landing%2C_artistic_representation.jpg/960px-UFO_landing%2C_artistic_representation.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "Віщун",
    },
    "triangle": {
        "title": "Triangle shaped ufo rend 1.png",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/26/Triangle_shaped_ufo_rend_1.png/960px-Triangle_shaped_ufo_rend_1.png?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "Merikanto",
    },
    "cigar": {
        "title": "Cigar shaped ufo 3 1 1 1.png",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fa/Cigar_shaped_ufo_3_1_1_1.png/960px-Cigar_shaped_ufo_3_1_1_1.png?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC0",
        "by": "Merikanto",
    },
    "orb": {
        "title": "Foofighter.png",
        "src": "https://upload.wikimedia.org/wikipedia/commons/9/91/Foofighter.png?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original",
        "lic": "Public domain",
        "by": "Crobard (Wikimedia Commons)",
    },
    "tictac": {
        "title": "КГ – НЛО («Тик-Так»).jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1c/%D0%9A%D0%93_%E2%80%93_%D0%9D%D0%9B%D0%9E_%28%C2%AB%D0%A2%D0%B8%D0%BA-%D0%A2%D0%B0%D0%BA%C2%BB%29.jpg/960px-%D0%9A%D0%93_%E2%80%93_%D0%9D%D0%9B%D0%9E_%28%C2%AB%D0%A2%D0%B8%D0%BA-%D0%A2%D0%B0%D0%BA%C2%BB%29.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "Dimitar Naydenov",
    },
    "enterprise": {
        "title": "Starship Enterprise - geograph.org.uk - 3188968.jpg",
        "src": "https://upload.wikimedia.org/wikipedia/commons/4/4f/Starship_Enterprise_-_geograph.org.uk_-_3188968.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail_unscaled",
        "lic": "CC BY-SA 2.0",
        "by": "David Dixon ",
    },
    "falcon": {
        "title": "Millennium Falcon 2.webp",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/99/Millennium_Falcon_2.webp/960px-Millennium_Falcon_2.webp?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC0",
        "by": "Wikideas1",
    },
    "tie": {
        "title": "TIE Fighter.webp",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/13/TIE_Fighter.webp/960px-TIE_Fighter.webp?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC0",
        "by": "Wikideas1",
    },
    "discovery": {
        "title": "Discovery One model from 2001 - A Space Odyssey - montage on black background.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fb/Discovery_One_model_from_2001_-_A_Space_Odyssey_-_montage_on_black_background.jpg/960px-Discovery_One_model_from_2001_-_A_Space_Odyssey_-_montage_on_black_background.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "William Beutler (photograph), montage on Wikimedia Commons",
    },
    "tb2": {
        "title": "NMM Thunderbird 2.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/NMM_Thunderbird_2.jpg/960px-NMM_Thunderbird_2.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "Chemical Engineer",
    },
    "tardis": {
        "title": 'Police Box "Tardis".jpg',
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/82/Police_Box_%22Tardis%22.jpg/960px-Police_Box_%22Tardis%22.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY-SA 4.0",
        "by": "Scaider",
    },
    "shuttle": {
        "title": "STS-135 Atlantis approaches the ISS.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/69/STS-135_Atlantis_approaches_the_ISS.jpg/960px-STS-135_Atlantis_approaches_the_ISS.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "Public domain",
        "by": "NASA",
    },
    "apollo_csm": {
        "title": "Apollo 17 Command-Service modules photographed from lunar module in orbit (as17-145-22254).jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0d/Apollo_17_Command-Service_modules_photographed_from_lunar_module_in_orbit_%28as17-145-22254%29.jpg/960px-Apollo_17_Command-Service_modules_photographed_from_lunar_module_in_orbit_%28as17-145-22254%29.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "Public domain",
        "by": "NASA Johnson Space Center",
    },
    "lunar_module": {
        "title": "Earth, Moon and Lunar Module, AS11-44-6643.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/81/Earth%2C_Moon_and_Lunar_Module%2C_AS11-44-6643.jpg/960px-Earth%2C_Moon_and_Lunar_Module%2C_AS11-44-6643.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "Public domain",
        "by": "NASA / Apollo 11",
    },
    "sputnik": {
        "title": "Sputnik 1 satellite replica.png",
        "src": "https://upload.wikimedia.org/wikipedia/commons/0/07/Sputnik_1_satellite_replica.png?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail_unscaled",
        "lic": "Public domain",
        "by": "Soyuz235",
    },
    "starship": {
        "title": "SpaceX Starship during IFT-5.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b3/SpaceX_Starship_during_IFT-5.jpg/960px-SpaceX_Starship_during_IFT-5.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC BY 2.0",
        "by": "Steve Jurvetson",
    },
    "vostok": {
        "title": "Vostok spacecraft replica.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7b/Vostok_spacecraft_replica.jpg/960px-Vostok_spacecraft_replica.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "CC0",
        "by": "Pascal (Flickr user: pasukaru76)",
    },
    "voyager": {
        "title": "Voyager spacecraft model.png",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/60/Voyager_spacecraft_model.png/960px-Voyager_spacecraft_model.png?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "Public domain",
        "by": "National Aeronautics and Space Administration (NASA)",
    },
    "iss": {
        "title": "STS-134 International Space Station after undocking.jpg",
        "src": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c9/STS-134_International_Space_Station_after_undocking.jpg/960px-STS-134_International_Space_Station_after_undocking.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail",
        "lic": "Public domain",
        "by": "NASA",
    },
}
UFO_POOLS = ("classic", "famous", "real", "all")
POOL_LABELS = {"classic": "UFO", "famous": "Film", "real": "Real"}


def ufo_choices(pool: str) -> list[str]:
    return [k for k, v in UFOS.items() if pool == "all" or v[2] == pool] or [
        k for k, v in UFOS.items() if v[2] == "classic"
    ]


def own_refs(text: Any) -> dict[str, dict[str, str]]:
    """The owner's own reference pictures, one a line: ``craft = URL or path``.
    A craft's own picture is used over the bundled one."""
    out: dict[str, dict[str, str]] = {}
    for line in str(text or "").splitlines():
        if "=" not in line:
            continue
        cid, _, src = line.partition("=")
        cid, src = cid.strip().lower(), src.strip()
        if cid in UFOS and src:
            out[cid] = {"title": "", "src": src, "lic": "", "by": "your own picture"}
    return out


def ref_for(cid: str, own: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    return (own or {}).get(cid) or UFO_REFS.get(cid, {})


def visitors_of(chosen: Any) -> list[str]:
    """The craft ticked, or the classics when none of the ticks is a craft."""
    got = [str(c) for c in chosen if str(c) in UFOS] if isinstance(chosen, list) else []
    return got or ufo_choices("classic")


GEN_UFO = (
    "Draw an unidentified flying object as {style}: {what}, seen from the side and a little below, in the air.{alien} "
    "{page} No text or lettering, no border, no signature.{outline}"
)
GEN_UFO_REF = (
    "Draw the craft in the reference picture afresh as {style}: {what}. The reference picture is for the craft's "
    "shape and proportions alone, which are kept exactly; everything else in it, its setting, background, people, "
    "stands and text, is left out, and the composition and lighting are the illustration's own: the craft seen "
    "from the side and a little below, in the air.{alien} {page} No text or lettering, no border, no signature.{outline}"
)
ALIEN = (
    " Nothing about it is man-made: it has no rivets, panel lines, hatches, wings, fins, engines, exhaust, antennas, "
    "lettering or national markings, no aircraft or rocket parts at all; its hull is a seamless unknown material, "
    "and it hovers without any visible means of lift, with an unearthly glow about it."
)
GEN_FAITHFUL = (
    "Render the {typ} in the reference photo, registration {reg} in {air} livery, flying with its wheels up, "
    "as {style}: a faithful "
    "picture of this very aircraft in that medium. The photograph is the authority on the aircraft: the same "
    "aircraft at the same angle as photographed; every element of the livery as it actually appears in the "
    "photograph, its colours, lettering, logos and the registration, whatever the operator's usual colours, and "
    "the particular details of this airframe, its winglets, engines, doors and antennas, reproduced exactly as "
    "they are in the photograph, all but the landing gear, which is never copied from it: the wheels are up"
    "{scene}. Take particular care over the airline's emblem "
    "on the tail and the lettering along the fuselage: reproduce their shape, colours and placement exactly as in "
    "the photograph, inventing nothing; where the photograph is too small to read a mark, draw the airline's actual "
    "mark rather than a guess.{logo} {gear} {medium} {page} No text or lettering beyond the livery's own, no "
    "border, no signature.{outline} Last, and above everything the photograph shows: the wheels are up and out "
    "of sight, no landing gear drawn at all."
)
# Whatever the photograph caught it doing, the aircraft is painted in the air with its wheels up
GEAR_UP = (
    "The aircraft is in flight with its landing gear fully retracted: no wheels, struts or open gear doors "
    "anywhere, the belly and the wings' undersides clean and closed, even where the photograph shows it "
    "landing, taxiing or parked, and no tyre smoke, runway or ground beneath it."
)
# The photograph decides what the aircraft is; the medium decides how every part of the picture is made
MEDIUM_ONLY = (
    "Every part of the picture is made in that medium, the aircraft included: nothing photographic is left, "
    "no photographic shading, reflections, sky, background or texture from the photograph, which is used only "
    "for what the aircraft is."
)
# A style on its own ground (a blackboard, a blueprint, a stamp): the photograph's setting goes, and the
# medium's own ground fills the page round the aircraft
PAGE_OWN = (
    "Only the aircraft comes from the photograph: its setting, the runway, ground, grass, buildings, trees, "
    "hills, poles, sky and people, is left out entirely, and the medium's own ground fills the whole picture "
    "round the aircraft, edge to edge."
)
LOGO_REF = (
    " The second picture is the airline's own mark: the emblem on the tail and the lettering on the fuselage carry "
    "exactly this mark, in its own colours and proportions."
)
FIDELITIES = ("photo", "free")
PAGE_ALONE = (
    "The whole aircraft fits well inside the picture, about three quarters of its width, centred, with the nose, "
    "tail and wingtips all clear of the edges. "
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
    return "custom" + "".join(
        "abcdefghijklmnopqrstuvwxyz"[int(c, 16) % 26] for c in digest[:8]
    )


_CUSTOM: dict[str, str] = {}


def register_custom(how: str) -> str:
    tag = custom_tag(how)
    _CUSTOM[tag] = how
    return tag


def ufo_key(shape: str, style: str) -> str:
    return f"ufo_{N.slug(shape)}--{style}--p{PROMPT_VERSION}"


def key_for(
    reg: str,
    style: str,
    backdrop: str = "none",
    view: str = "side",
    model: str = DEFAULT_MODEL,
    sky: str = "",
    fidelity: str = "photo",
) -> str:
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
        tmpl = GEN_UFO_REF if job.get("photo") else GEN_UFO
        text = tmpl.format(
            style=how.replace("aircraft", "craft"),
            what=what,
            alien=ALIEN if pool == "classic" else "",
            page=PAGE_ALONE.replace("The aircraft", "The craft").replace(
                "the aircraft", "the craft"
            )
            if alone
            else PAGE_WHOLE,
            outline=OUTLINE.replace("aircraft", "craft") if alone else "",
        )
        if str(job.get("style") or "") in MONO:
            text += " Rendered without any colour: black, white and grey only."
        return text
    backdrop = str(job.get("backdrop") or "none")
    scene = (
        f", across {BACKDROPS[backdrop][1]}"
        if backdrop in BACKDROPS and backdrop not in ("none", "live")
        else ""
    )
    if backdrop == "live":
        scene = f", across {job.get('sky_words') or 'a clear sky in the same style'}"
    if backdrop == "ornate":
        scene = (
            ", as the single subject of an ornate framed plate: the aircraft large in the middle on "
            + BACKDROPS["ornate"][1]
        )
    alone = backdrop == "none" and str(job.get("style") or "") not in OWN_PAPER
    if str(job.get("fidelity") or "photo") != "free":
        text = GEN_FAITHFUL.format(
            typ=job.get("typ") or "aircraft",
            reg=job.get("reg") or "",
            air=job.get("air") or "its own",
            style=how,
            scene=scene.replace(", across ", ", set across ")
            if scene and backdrop != "ornate"
            else scene,
            logo=LOGO_REF if job.get("logo_ref") else "",
            gear=GEAR_UP,
            medium=MEDIUM_ONLY,
            page=PAGE_ALONE
            if alone
            else PAGE_OWN
            if backdrop == "none"
            else PAGE_WHOLE,
            outline=OUTLINE if alone else "",
        )
        if str(job.get("style") or "") in MONO:
            text = text.replace(
                "its colours, lettering, logos", "its lettering, logos"
            ).replace(
                "which is used only for what the aircraft is.",
                "which is used only for what the aircraft is. Rendered without any colour: black, white and grey only.",
            )
        return text
    text = GEN.format(
        gear=GEAR_UP,
        typ=job.get("typ") or "aircraft",
        reg=job.get("reg") or "",
        air=job.get("air") or "its own",
        style=how,
        view=VIEWS.get(str(job.get("view") or "side"), VIEWS["side"]),
        scene=scene,
        logo=LOGO_REF if job.get("logo_ref") else "",
        page=PAGE_ALONE if alone else PAGE_WHOLE,
        outline=OUTLINE if alone else "",
    )
    if str(job.get("style") or "") in MONO:
        text = text.replace(*MONO_WORDS)
    return text


def model_of(model: str | None) -> str:
    return model if model in MODELS else DEFAULT_MODEL


# Styles that build the aircraft out of something (pixels, glass, facets, card, bricks): Nano Banana keeps
# them close to the photograph, GPT Image 2 makes them, so a cell left on Nano Banana paints these with it
STYLE_MODEL = {
    "pixel": "gpt_image",
    "stained_glass": "gpt_image",
    "lowpoly": "gpt_image",
    "papercraft": "gpt_image",
    "toybrick": "gpt_image",
    "riso": "gpt_image",  # Nano Banana draws the wheels down in this one, whatever it is told
}


def model_for(style: str, model: str) -> str:
    """The model a painting in ``style`` is made with: the cell's own, or for a
    style Nano Banana cannot make, GPT Image 2 in its place."""
    return STYLE_MODEL.get(style, model) if model == DEFAULT_MODEL else model


# ----------------------------------------------------------------------
# Files, budget, state
# ----------------------------------------------------------------------
ART: Any = (
    artwork.Collection(
        "overhead_core",
        "paintings",
        make=lambda job: make(job),
        label="Overhead",
        title="Painting aircraft",
        facet="style",
        facet_label=lambda s: style_of(s)[0],
    )
    if artwork is not None
    else _NoArtwork()
)
UNLIMITED = artwork.UNLIMITED if artwork is not None else 10**9


OLD_DERIVED_RE = r".*(_\d+(_\w+)?\.(jpg|png)|_cut\d*(_\w+)?\.png|\.paper)"


def _old_job(job: dict[str, Any]) -> tuple[dict[str, Any], str]:
    payload = {k: v for k, v in job.items() if k not in ("key", "subject", "origin")}
    who = job.get("reg") or job.get("ufo") or job.get("key")
    return payload, f"{who}, {job['typ']}" if job.get("typ") else str(who)


def adopt_old_install(data_dir: Path) -> bool:
    """Before 0.2.0 the paintings lived in gen/ with the budget already in
    cents; they become the collection's, with what the previews held and the
    dashboards asked for."""
    return ART.adopt(
        Path(data_dir), "gen", drop=OLD_DERIVED_RE, job_to_payload=_old_job
    )


def gen_dir(data_dir: Path) -> Path:
    """The paintings' folder, the collection's, for the tools and the tests."""
    return ART.folder(Path(data_dir))


def _data_dir(path: Path) -> Path:
    """The plugin's data dir from either it or the paintings folder under it."""
    path = Path(path)
    return path.parent if path.name == ART.name else path


def budget_used(path: Path) -> int:
    return ART.budget_used(_data_dir(path))


def daily_cap(settings: dict[str, Any] | None) -> int:
    return ART.cap(settings)


def dollars(cents: int) -> str:
    return "no limit" if cents >= UNLIMITED else f"US${cents / 100:.2f}"


def cost_cents(model: str) -> int:
    return int(MODELS.get(model, MODELS[DEFAULT_MODEL]).get("cents") or TYPICAL_CENTS)


def whole(value: Any, default: int, low: int = 0, high: int = 100000) -> int:
    with contextlib.suppress(TypeError, ValueError):
        if str(value).strip() != "":
            return min(high, max(low, int(float(value))))
    return default


def state(key: str, path: Path) -> str:
    return ART.state(key, _data_dir(path))


def why_failed(key: str, path: Path) -> str:
    return ART.why_failed(key, _data_dir(path))


def archive(path: Path, key: str) -> None:
    ART.archive(key, _data_dir(path))


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
    # the outermost rim goes first: a darker edge, a vignette or a frame line the model
    # left along the page's edge would otherwise stay as a line
    trim = max(6, int(round(min(im.size) * TRIM)))
    if im.width > 4 * trim and im.height > 4 * trim:
        im = im.crop((trim, trim, im.width - trim, im.height - trim))
    a = np.asarray(im).astype(float)
    H, W = a.shape[:2]
    c = 30
    corners = np.concatenate(
        [
            a[:c, :c].reshape(-1, 3),
            a[:c, -c:].reshape(-1, 3),
            a[-c:, :c].reshape(-1, 3),
            a[-c:, -c:].reshape(-1, 3),
        ]
    )
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
    small = (
        paperlike[: H // s * s, : W // s * s]
        .reshape(H // s, s, W // s, s)
        .all(axis=(1, 3))
    )
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
            bg[h - lo :, :] = True
        for lo in (ix, rim):
            bg[:, :lo] = True
            bg[:, w - lo :] = True
        keep_small = ~bg
        if keep_small.mean() < 0.6:
            break
    # stray slivers (a stroke left at an edge, a speck) go; the aircraft and anything of size stays
    lab = np.zeros(keep_small.shape, dtype=np.int32)
    sizes: dict[int, int] = {}
    boxes: dict[int, tuple[int, int, int, int]] = {}
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if keep_small[y0, x0] and not lab[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                lab[y0, x0] = n
                count = 0
                y_lo = y_hi = y0
                x_lo = x_hi = x0
                while stack:
                    y, x = stack.pop()
                    count += 1
                    y_lo, y_hi = min(y_lo, y), max(y_hi, y)
                    x_lo, x_hi = min(x_lo, x), max(x_hi, x)
                    for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        if (
                            0 <= ny < h
                            and 0 <= nx < w
                            and keep_small[ny, nx]
                            and not lab[ny, nx]
                        ):
                            lab[ny, nx] = n
                            stack.append((ny, nx))
                sizes[n] = count
                boxes[n] = (y_lo, y_hi, x_lo, x_hi)
    if sizes:
        biggest = max(sizes.values())
        floor = max(40, int(0.004 * h * w), biggest // 40)
        for k, count in sizes.items():
            y_lo, y_hi, x_lo, x_hi = boxes[k]
            bh, bw = y_hi - y_lo + 1, x_hi - x_lo + 1
            # a frame line the model drew round the page, or what is left of one: a long thin
            # run on its own, or a hollow rectangle; never part of the aircraft, which is one piece
            line = (bh <= 0.03 * h and bw >= 0.3 * w) or (
                bw <= 0.03 * w and bh >= 0.3 * h
            )
            hollow = bw >= 0.5 * w and bh >= 0.5 * h and count < 0.06 * bh * bw
            if count < floor or line or hollow:
                keep_small[lab == k] = False
    keep = np.zeros((H, W), dtype=bool)
    keep[: h * s, : w * s] = np.kron(keep_small, np.ones((s, s), dtype=bool))
    # the edge: soft where the paint meets the paper, hard inside the outline
    soft = np.clip((d - thr) / 35, 0, 1)
    hard = (
        Image.fromarray((keep * 255).astype("uint8"))
        .filter(ImageFilter.MinFilter(3))
        .filter(ImageFilter.MaxFilter(3))
    )
    hard_a = np.asarray(hard) > 0
    alpha = np.where(hard_a, np.maximum(soft, 0.98), 0.0)
    alpha8 = np.asarray(
        Image.fromarray((alpha * 255).astype("uint8")).filter(
            ImageFilter.GaussianBlur(0.6)
        )
    )
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


# ----------------------------------------------------------------------
# A backdrop painting's mount. Asked for a sky to the edges, a model now and
# then draws the picture on a sheet with a plain margin of paper along an edge
# or two, which reads as a border round a page meant to be all sky. The margin
# is a flat light band of one colour with a sharp step to the painting inside.
# ----------------------------------------------------------------------
MOUNT_MAX = 0.15  # no deeper than this share of the side it is cut from


def mount_of(raw: bytes) -> tuple[int, int, int, int] | None:
    """The box inside a plain paper margin drawn along any of the painting's
    edges, as (left, top, right, bottom), or None when the painting reaches
    its edges."""
    try:
        import numpy as np
        from PIL import Image

        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:  # noqa: BLE001 - an unreadable picture is shown as it is
        return None
    a = np.asarray(im).astype(float)
    h, w = a.shape[:2]
    if h < 40 or w < 40:
        return None

    def depth(lines: Any, limit: int) -> int:
        # lines[i] is the i-th row or column in from the edge, as (pixels, 3)
        edge = np.median(lines[0], axis=0)
        if edge.mean() < 200 or edge.max() - edge.min() > 45:
            return 0  # not paper: a sky, a night, a coloured ground
        n = 0
        while n < limit:
            near = np.sqrt(((lines[n] - edge) ** 2).sum(-1)) < 22
            if near.mean() < 0.96:
                break
            n += 1
        if n < 2 or n >= limit:
            return 0
        inside = lines[min(n + 4, len(lines) - 1)].mean(axis=0)
        return n if np.sqrt(((inside - edge) ** 2).sum()) > 60 else 0

    lim_x, lim_y = int(w * MOUNT_MAX), int(h * MOUNT_MAX)
    left = depth(a.transpose(1, 0, 2), lim_x)
    right = depth(a.transpose(1, 0, 2)[::-1], lim_x)
    top = depth(a, lim_y)
    bottom = depth(a[::-1], lim_y)
    if not (left or right or top or bottom):
        return None
    pad = max(
        2, round(min(w, h) * 0.006)
    )  # and the drawn rule along the margin's inner edge
    box = (
        left + pad if left else 0,
        top + pad if top else 0,
        w - (right + pad if right else 0),
        h - (bottom + pad if bottom else 0),
    )
    return box if box[2] - box[0] > w // 2 and box[3] - box[1] > h // 2 else None


def unmounted(art: Any, key: str, path: Path) -> str:
    """The variant of a backdrop painting with its drawn mount cut off, made
    once beside it; '' when it has none."""
    variant = f"mount{MOUNT_VERSION}"
    folder = art.c.folder(art.data_dir)
    done, none = folder / f"{key}__{variant}.png", folder / f"{key}__{variant}.none"
    if done.exists():
        return variant
    if none.exists():
        return ""
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    box = mount_of(raw)
    if box is None:
        with contextlib.suppress(OSError):
            none.touch()
        return ""
    from PIL import Image

    buf = io.BytesIO()
    Image.open(io.BytesIO(raw)).convert("RGB").crop(box).save(buf, "PNG", optimize=True)
    N.write(done, buf.getvalue())
    return variant


def picture(
    art: Any, key: str, px: int, levels: str, whole_: bool, sky: bool = False
) -> dict[str, Any] | None:
    """A kept painting for the page: the whole picture as a JPEG data URI, or
    the cut-out as a PNG with alpha, resized for the cell and the panel and
    cached by the collection. ``sky``: a painting on a backdrop meant to reach
    the edges, so a paper margin the model drew round it is cut off."""
    c, data_dir = art.c, art.data_dir
    if c is None:
        return None
    path = c.path(key, data_dir)
    if path is None:
        return None
    meta = c.meta(key, data_dir)
    credit = str(meta.get("credit") or "")
    if whole_:
        variant = unmounted(art, key, path) if sky else ""
        src = (
            art.url(key, px=px, levels=levels, variant=variant)
            if variant
            else art.url(key, px=px, levels=levels)
        )
        return (
            {
                "src": src,
                "kind": "painting",
                "whole": True,
                "credit": credit,
                "aspect": N.aspect_of(src),
            }
            if src
            else None
        )
    variant = f"cut{CUT_VERSION}"
    cut = c.folder(data_dir) / f"{key}__{variant}.png"
    if not cut.exists():
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        png = cut_out(raw)
        if not png:
            c.note_error(
                key,
                data_dir,
                "the painting could not be cut out",
                title=str(meta.get("title") or key),
            )
            return None
        N.write(cut, png)
    src = art.url(key, px=px, levels=levels, cut=True, variant=variant)
    return (
        {
            "src": src,
            "kind": "painting",
            "whole": False,
            "credit": credit,
            "aspect": N.aspect_of(src),
        }
        if src
        else None
    )


def _local(path: str) -> bytes | None:
    with contextlib.suppress(OSError):
        return Path(path).expanduser().read_bytes()
    return None


def make(job: Any) -> tuple[bytes, dict[str, Any]]:
    """One painting, on a worker thread: the prompt from the payload, the
    reference pictures handed over inline, the picture from fal.ai through
    the collection's budget. Raises ArtworkError with why not."""
    j = job.payload
    photo = str(j.get("photo") or "")
    t2i = bool(j.get("ufo")) and not photo
    if not photo and not t2i:
        raise artwork.ArtworkError("no photo")
    model = model_of(j.get("model"))
    prompt = prompt_for(j)
    aspect = str(j.get("aspect") or "4:3")
    if photo and j.get("ufo") and not photo.startswith("data:"):
        # a reference picture is read here, a file on this server or a page fetched with the
        # widget's own User-Agent, and handed over inline: fal.ai's own fetch of a Commons picture is refused
        raw_ref = (
            N.cached_get(job.data_dir, photo)
            if photo.startswith(("http://", "https://"))
            else _local(photo)
        )
        if not raw_ref:
            raise artwork.ArtworkError("the reference picture could not be read")
        photo = _fal.data_uri(raw_ref)
    refs = (
        []
        if t2i
        else [photo]
        + (
            [str(j["logo_ref"])]
            if j.get("logo_ref") and model != "flux_kontext"
            else []
        )
    )
    raw = job.fal.generate(
        "nano_banana_t2i" if t2i else model, prompt, refs=refs, aspect=aspect, retries=1
    )
    label = MODELS["nano_banana" if t2i else model]["label"]
    credit = (
        f"an unidentified object painted by {label}"
        if t2i
        else f"painted by {label} from your own picture"
        if j.get("ufo") and j.get("by") == "your own picture"
        else f"painted by {label} from a picture by {j.get('by') or 'a Commons contributor'} (Wikimedia Commons, {j.get('lic') or 'open licence'})"
        if j.get("ufo")
        else f"painted by {label} from a photograph by {j.get('by') or 'a planespotter'} (planespotters.net)"
    )
    meta = {
        "reg": j.get("reg"),
        "typ": j.get("typ"),
        "air": j.get("air"),
        "style": j.get("style"),
        "how": j.get("how") or "",
        "backdrop": j.get("backdrop") or "none",
        "model": model,
        "credit": credit,
        "ufo": j.get("ufo") or "",
        "photo_by": j.get("by") or "",
        "photo_link": j.get("link") or "",
        "by": j.get("by") or "",
        "link": j.get("link") or "",
        "prompt": prompt,
        "prompt_version": PROMPT_VERSION,
    }
    return raw, meta
