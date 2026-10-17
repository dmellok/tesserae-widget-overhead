"""Write the four widgets' plugin.json from one description, so the shared
options never drift apart. Run after editing: python tools/manifests.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "overhead_core" / "lib"))
VERSION = "0.1.16"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_tesserae_plugins.overhead_core.paint", ROOT / "overhead_core" / "lib" / "paint.py")
_paint = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = _paint
_spec.loader.exec_module(_paint)
STYLES = [(k, v[0]) for k, v in _paint.STYLES.items()] + [("builder", "Build my own"), ("custom", "Your own prompt")]
BUILDER = {
    "medium": ("Medium", "gouache", [("gouache", "Gouache"), ("watercolour", "Watercolour"), ("oil", "Oil paint"), ("pastel", "Soft pastel"), ("coloured_pencil", "Coloured pencil"), ("pencil", "Graphite pencil"), ("ink", "Pen and ink"), ("engraving", "Engraving"), ("lithograph", "Lithograph"), ("woodblock", "Woodblock"), ("linocut", "Linocut"), ("screenprint", "Screen print"), ("vector", "Flat vector"), ("airbrush", "Airbrush"), ("papercut", "Paper cut")]),
    "period": ("Period or school", "", [("", "None in particular"), ("1930s", "1930s travel poster"), ("1950s", "1950s airline brochure"), ("1960s", "1960s jet-age"), ("victorian", "Victorian technical plate"), ("bauhaus", "Bauhaus"), ("ukiyoe", "Ukiyo-e"), ("deco", "Art Deco"), ("retrofuture", "Retro-futurism")]),
    "palette": ("Palette", "", [("", "As the livery is"), ("limited", "A few warm tones"), ("muted", "Muted"), ("vivid", "Vivid"), ("duotone", "Two inks"), ("mono", "Black and white"), ("sepia", "Sepia")]),
    "line": ("Line", "", [("", "As the medium has it"), ("fine", "Fine"), ("bold", "Bold"), ("none", "No outlines"), ("sketchy", "Sketchy")]),
    "texture": ("Texture", "", [("", "As the medium has it"), ("paper", "Paper grain"), ("print", "Print texture"), ("smooth", "Smooth"), ("halftone", "Halftone")]),
    "mood": ("Mood", "", [("", "Plain"), ("heroic", "Heroic"), ("calm", "Calm"), ("nostalgic", "Nostalgic"), ("technical", "Precise")]),
}
PRESETS = [
    {"label": "Gouache poster", "value": "a vintage airline poster in gouache: flat confident shapes, a warm limited palette, crisp edges"},
    {"label": "Cutaway", "value": "a 1950s magazine cutaway illustration: the fuselage opened to show seats and cargo, labelled in small neat capitals"},
    {"label": "Chalk pastel", "value": "a chalk pastel drawing on grey paper, soft and smudgy, with the sun catching the fuselage"},
    {"label": "Aviation art", "value": "a traditional oil painting in the manner of classic aviation art: dramatic light, polished metal, confident brushwork"},
    {"label": "Comic ink", "value": "a comic-book ink drawing with bold outlines, hatched shadows and flat halftone colour"},
    {"label": "Neon line", "value": "a single-weight neon line drawing on white: one continuous glowing line describing the aircraft"},
]
BACKDROPS = [("none", "None: the aircraft alone, cut out on the page"), ("live", "The sky as it is now: time of day and weather"), ("sky", "A clear sky"), ("clouds", "Above the clouds"), ("sunset", "Sunset"), ("night", "Night"), ("storm", "Storm light"), ("ornate", "Ornate framed plate")]
MODELS = [("nano_banana", "Nano Banana (about US$0.04)"), ("nano_banana_pro", "Nano Banana Pro (about US$0.15)"), ("flux_kontext", "FLUX.1 Kontext Pro (about US$0.04)"), ("gpt_image", "GPT Image 2 (about US$0.05)"), ("seedream", "Seedream 4 (about US$0.03)")]


def sel(name, label, default, choices, **kw):
    return {"name": name, "type": "select", "label": label, "default": default, "choices": [{"value": v, "label": l} for v, l in choices], **kw}


def where_options():
    return [
        sel("source", "Positions from", "adsb_lol", [("adsb_lol", "adsb.lol (the community feed, no key)"), ("receiver", "A receiver of your own")], help="adsb.lol aggregates thousands of receivers and needs nothing from you. A receiver of your own (readsb, dump1090, tar1090) answers at /data/aircraft.json and sees what it sees."),
        {"name": "receiver_url", "type": "string", "label": "Receiver address", "default": "", "help": "For example http://pi.local:8080; the widget asks for /data/aircraft.json.", "show_if": {"source": "receiver"}},
        {"name": "location", "type": "location_search", "label": "Place", "default": "", "help": "The point the distances and bearings are from. Falls back to the app's location."},
        sel("radius_km", "Within", "25", [(v, f"{v} km") for v in ("5", "10", "15", "25", "35", "50", "80")]),
        {"name": "include_ground", "type": "boolean", "label": "Include aircraft on the ground", "default": False},
        sel("order", "Order", "nearest", [("nearest", "Nearest first"), ("lowest", "Lowest first"), ("highest", "Highest first"), ("largest", "Largest first"), ("fastest", "Fastest first")]),
    ]


def picture_options(with_backdrop: bool, many: bool, scene: bool = False):
    show = {"pictures": "paintings"}
    out = [
        sel("pictures", "Pictures", "photos", [("photos", "Photographs of the airframe (planespotters.net)"), ("paintings", "AI paintings, each from its own photograph")], help="Photographs cost nothing. AI paintings paint each airframe once, from its photograph, in the style below, at about US$0.04 a painting; needs a fal.ai key in the Overhead Core settings."),
        sel("style", "Style", "poster", STYLES, show_if=show),
        {"name": "custom_style", "type": "textarea", "label": "Your own prompt", "default": "", "show_if": {"pictures": "paintings", "style": "custom"}, "presets": PRESETS, "help": "The medium and the look; the widget adds the aircraft, its photograph and the paper. Pick an example above to start from."},
    ]
    for name, (label, default, choices) in BUILDER.items():
        out.append(sel(f"build_{name}", label, default, choices, show_if={"pictures": "paintings", "style": "builder"}))
    out.append({"name": "build_extra", "type": "string", "label": "Your own words", "default": "", "show_if": {"pictures": "paintings", "style": "builder"}, "help": "Added to the style: for example, with a little gold leaf on the tail."})
    if with_backdrop:
        out.append(sel("backdrop", "Backdrop", "sky" if scene else "none", BACKDROPS if not scene else BACKDROPS[1:], show_if=show, help="None keeps the aircraft alone on the page, cut out. The rest paint a whole picture that fills its frame, in the same style. The sky as it is now takes the time of day (dawn, morning, midday, afternoon, dusk, night) and the weather (Open-Meteo: clear, cloud, overcast, fog, rain, snow, storm) at the place, and paints each condition once per aircraft, so a changing sky costs more paintings."))
    out.append(sel("fidelity", "Faithfulness", "photo", [("photo", "As photographed: the same angle, every mark of the livery"), ("free", "Drawn afresh: the model's own composition, the view below")], show_if=show, help="As photographed translates the airframe's photograph into the medium and keeps its angle, livery, lettering and registration exactly. Drawn afresh lets the model compose the aircraft anew in the style, in the view chosen below; liveries drift more."))
    out.append(sel("view", "View", "side", [("side", "From the side, a little below"), ("livery", "Side-on: a pure profile, as a livery drawing"), ("quarter", "From the front quarter"), ("above", "From above, banking")], show_if={"pictures": "paintings", "fidelity": "free"}))
    out.append(sel("model", "Model", "nano_banana", MODELS, show_if=show, help="All on fal.ai, all painting from the photograph. Nano Banana is faithful and cheap, and keeps the more abstract styles (low-poly, charcoal, toy bricks, stained glass) close to the photograph; Nano Banana Pro and FLUX follow those styles further."))
    out.append({"name": "ufo", "type": "slider", "label": "Chance of a UFO", "default": 0, "min": 0, "max": 100, "step": 5, "unit": "%", "show_if": show, "help": "Each hour, this chance that an unidentified contact joins the page, painted in the page's style, with no transponder and a made-up height and bearing. For fun. Each craft in a style is one painting against the daily limit."})
    out.append({"name": "visitors", "type": "multiselect", "label": "Who visits", "default": _paint.ufo_choices("classic"), "show_if": {"pictures": "paintings", "ufo": {"not": 0}}, "help": "Tick the craft the roll may bring. Most are painted from a reference picture (Wikimedia Commons and NASA, credited on the page); a famous craft is described to the painter by its shape, never named. With nothing ticked, the classic UFOs.", "choices": [{"value": k, "label": f"{_paint.POOL_LABELS[v[2]]}: {v[0]}"} for k, v in _paint.UFOS.items()]})
    if many:
        out.append(sel("unpainted", "Until an aircraft is painted", "silhouette", [("silhouette", "Show a silhouette"), ("photo", "Show its photograph"), ("skip", "Only painted aircraft: leave the rest off the page")], show_if=show, help="Only painted aircraft shows a page of paintings alone; it says so while the first are being painted."))
    else:
        out.append(sel("unpainted", "Until the aircraft is painted", "photo", [("photo", "Show its photograph"), ("silhouette", "Show a silhouette"), ("skip", "Only a painted aircraft: the nearest one already painted")], show_if=show, help="Only a painted aircraft looks among the nearest six for one already painted and keeps painting them, so the page has one most of the time; it says so until the first lands."))
    return out


def page_options(labels_default):
    return [
        {"name": "labels", "type": "multiselect", "label": "Label lines", "default": labels_default, "help": "In this order, under or beside each aircraft.", "choices": [{"value": v, "label": l} for v, l in [("airline", "Airline"), ("type", "Type"), ("reg", "Registration"), ("route", "Route"), ("altitude", "Altitude and trend"), ("distance", "Distance and bearing"), ("speed", "Ground speed"), ("heading", "Heading")]]},
        sel("logos", "Airline logos", "off", [("off", "Off: the airline's name"), ("on", "On: fetched from the web")], help="The airlines' own marks, fetched at render time from the service chosen in the Overhead Core settings and kept on your server; nothing ships with the widget. They are the airlines' trademarks: keep this off on anything you publish."),
        {"name": "title", "type": "string", "label": "Title", "default": "", "help": "Blank uses the place."},
        sel("header", "Title line", "top", [("top", "Above the page"), ("bottom", "Below the page"), ("hidden", "Hidden")]),
        sel("footer", "Foot of the page", "show", [("show", "Status and credits"), ("credits", "Credits only"), ("hide", "Nothing")]),
        sel("paper", "Paper", "cream", [("cream", "Cream"), ("white", "White"), ("aged", "Aged"), ("blueprint", "Blueprint: pale ink on blue"), ("sky", "A soft sky wash")]),
        sel("panel", "Panel", "colour", [("colour", "Colour"), ("gray16", "16 greys"), ("gray4", "4 greys"), ("mono", "Black and white")], help="What the panel can show. Pictures are converted and contrast-stretched to match."),
        sel("text_size", "Text size", "100", [(v, f"{v}%") for v in ("60", "80", "100", "125", "150")]),
        sel("font", "Type", "fell", [("fell", "IM Fell English: the old plate"), ("archivo", "Archivo Narrow: clean and plain"), ("georgia", "Georgia: a modern serif"), ("page", "The dashboard's own font")], help="The face the page is set in. The dashboard's own font follows the page's font picker."),
    ]


WIDGETS = {
    "overhead_photo": {
        "name": "Overhead: Photo",
        "icon": "ph-airplane-in-flight",
        "description": "The nearest aircraft to a place, right now, as a full-bleed photograph of the very airframe (planespotters.net) with its callsign, type, route, height and distance, and the next few along a strip. Positions from adsb.lol or a receiver of your own.",
        "options": lambda: where_options() + [
            {"name": "strip", "type": "number", "label": "More aircraft along the strip", "default": 5, "help": "0 to 8 after the nearest."},
            sel("photo_fit", "Photograph", "cover", [("cover", "Fills the page"), ("contain", "Fits inside the page")]),
        ] + page_options(["route", "altitude", "distance", "speed"]),
    },
    "overhead_plate": {
        "name": "Overhead: Plate",
        "icon": "ph-frame-corners",
        "description": "One aircraft overhead as a plate: painted from its own photograph in a style of your choosing, in a ruled frame, with its particulars beside it. Its photograph until the painting lands, or without a fal.ai key.",
        "options": lambda: where_options() + picture_options(True, False) + page_options(["route", "altitude", "distance"]),
    },
    "overhead_cluster": {
        "name": "Overhead: Cluster",
        "icon": "ph-airplane-tilt",
        "description": "Everything in the air near a place on one page: each aircraft painted from its own photograph and cut out, sized by its wingspan, with a caption; or, with photographs, a spotter's log of cards. Twelve styles, a style builder and your own prompt.",
        "options": lambda: where_options() + [{"name": "count", "type": "number", "label": "How many", "default": 8, "help": "1 to 12."}] + picture_options(False, True) + [
            {"name": "scale", "type": "slider", "label": "Scale", "default": 100, "min": 40, "max": 100, "step": 5, "unit": "%", "help": "How far the painted cluster runs out to the margins. 100% fills the page; less packs it into the middle with more paper round it.", "show_if": {"pictures": "paintings"}},
        ] + page_options(["type", "route", "altitude", "distance"]),
    },
    "overhead_scene": {
        "name": "Overhead: Scene",
        "icon": "ph-cloud-sun",
        "description": "The nearest aircraft as one whole painting across the page: the airframe from its own photograph on a painted backdrop (sky, clouds, sunset, night, storm or an ornate plate), with its particulars set over it. Its photograph without a fal.ai key.",
        "options": lambda: where_options() + picture_options(True, False, scene=True) + page_options(["route", "altitude", "distance"]),
    },
}

for wid, w in WIDGETS.items():
    manifest = {
        "tesserae_compat": "1.x",
        "name": w["name"],
        "version": VERSION,
        "kind": "widget",
        "description": w["description"],
        "icon": w["icon"],
        "supports": {"sizes": ["sm", "md", "lg"]},
        "requires": ["network:*", "settings:plugin/overhead_core", "plugin:overhead_core"],
        "render": {"needs_network": True},
        "design": {"palette": "extended"},
        "cell_options": w["options"](),
        "data_schema": {"fields": [{"name": "title", "type": "str", "label": "Title"}, {"name": "airborne", "type": "num", "label": "Aircraft airborne within reach"}, {"name": "aircraft", "type": "arr", "label": "Aircraft shown"}]},
    }
    names = [o["name"] for o in manifest["cell_options"]]
    assert len(names) == len(set(names)), wid
    (ROOT / wid / "plugin.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(wid, len(names), "options")
