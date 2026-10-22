"""Paint the style picker's sample pictures: one airliner, from one openly
licensed Wikimedia Commons photograph, in every style, through fal.ai, as
small JPEGs in overhead_core/static/styles/ that the cluster's, plate's and
scene's Style options point at (``choices[].image``). About US$0.04 a style.

    FAL_KEY=... python3 overhead_core/tools/style_previews.py            # the missing ones
    python3 overhead_core/tools/style_previews.py --key-file ~/fal_key --only poster,deco --force

The reference and its credit are in REFERENCE below and in ATTRIBUTION.md;
the full-size paintings go to overhead_core/tools/out/styles/ (not shipped).
Needs a Tesserae checkout beside this repo (or TESSERAE_REPO) for app.fal."""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TESSERAE = Path(os.environ.get("TESSERAE_REPO") or ROOT.parent / "tesserae")
if str(_TESSERAE) not in sys.path:
    sys.path.insert(0, str(_TESSERAE))
from app import fal  # noqa: E402

OUT = ROOT / "overhead_core" / "static" / "styles"
FULL = ROOT / "overhead_core" / "tools" / "out" / "styles"
THUMB = (320, 240)
LARGE = (800, 600)  # the picker's enlarged view, in static/styles/large/
REFERENCE = {
    "reg": "VH-VZX",
    "typ": "Boeing 737-800",
    "air": "Qantas",
    "src": "https://upload.wikimedia.org/wikipedia/commons/f/f8/Qantas_737-800_landing_runway_03_%288117771186%29.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original",
    "by": "Jordan Vuong",
    "lic": "CC BY 2.0",
    "link": "https://commons.wikimedia.org/wiki/File:Qantas_737-800_landing_runway_03_(8117771186).jpg",
}
UA = "TesseraeStylePreviews/1.0 (https://github.com/dmellok/tesserae-widget-overhead)"


def _paint_module():
    spec = importlib.util.spec_from_file_location(
        "overhead_cluster_server", ROOT / "overhead_cluster" / "server.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._lib("paint")


def _reference() -> bytes:
    cache = FULL / "reference.jpg"
    if cache.exists():
        return cache.read_bytes()
    req = urllib.request.Request(REFERENCE["src"], headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=30).read()
    FULL.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(raw)
    return raw


def thumbnail(raw: bytes, size: tuple[int, int] = THUMB) -> bytes:
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(raw)).convert("RGB")
    # close in on the aircraft: the paper is what the corners show, and the
    # sample is cut to what differs from it, with a margin, before the fit
    from PIL import ImageChops

    w, h = im.size
    corners = [
        im.getpixel(xy) for xy in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))
    ]
    paper = tuple(sorted(c[i] for c in corners)[1] for i in range(3))
    diff = (
        ImageChops.difference(im, Image.new("RGB", im.size, paper))
        .convert("L")
        .point(lambda v: 255 if v > 28 else 0)
    )
    box = diff.getbbox()
    if box and (box[2] - box[0]) < w * 0.97:
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        # widen to the sample's shape, with a tenth of margin round it
        tw = max(bw * 1.12, bh * 1.12 * size[0] / size[1])
        th = tw * size[1] / size[0]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        crop = (int(cx - tw / 2), int(cy - th / 2), int(cx + tw / 2), int(cy + th / 2))
        bg = Image.new("RGB", (crop[2] - crop[0], crop[3] - crop[1]), paper)
        bg.paste(
            im.crop(
                (max(0, crop[0]), max(0, crop[1]), min(w, crop[2]), min(h, crop[3]))
            ),
            (max(0, -crop[0]), max(0, -crop[1])),
        )
        im = bg
    im = ImageOps.fit(im, size, method=Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80, optimize=True, progressive=True)
    return out.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--key-file", default="")
    ap.add_argument("--only", default="", help="comma-separated style ids")
    ap.add_argument(
        "--force", action="store_true", help="paint again even when the sample exists"
    )
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument(
        "--rethumb",
        action="store_true",
        help="remake the samples from the kept paintings, nothing painted",
    )
    a = ap.parse_args()
    if a.rethumb:
        n = 0
        for f in sorted(FULL.glob("*.jpg")):
            if f.stem != "reference" and (not a.only or f.stem in a.only.split(",")):
                (OUT / f.name).write_bytes(thumbnail(f.read_bytes()))
                (OUT / "large").mkdir(exist_ok=True)
                (OUT / "large" / f.name).write_bytes(thumbnail(f.read_bytes(), LARGE))
                n += 1
        print(f"{n} samples made again from the kept paintings")
        return 0
    key = (
        Path(a.key_file).expanduser().read_text(encoding="utf-8").strip()
        if a.key_file
        else ""
    ) or os.environ.get("FAL_KEY", "").strip()
    if not key:
        print("no fal.ai key: --key-file or FAL_KEY", file=sys.stderr)
        return 2
    P = _paint_module()
    styles = [s for s in P.STYLES if s not in P.HIDDEN and (not a.only or s in a.only.split(","))]
    todo = [s for s in styles if a.force or not (OUT / f"{s}.jpg").exists()]
    ref = fal.data_uri(_reference())
    OUT.mkdir(parents=True, exist_ok=True)
    FULL.mkdir(parents=True, exist_ok=True)
    client = fal.FalClient(key)

    def one(style: str) -> str:
        job = {
            "reg": REFERENCE["reg"],
            "typ": REFERENCE["typ"],
            "air": REFERENCE["air"],
            "style": style,
            "how": "",
            "backdrop": "none",
            "sky_words": "",
            "view": "side",
            "fidelity": "photo",
            "model": P.DEFAULT_MODEL,
            "logo_ref": "",
            "photo": ref,
            "aspect": "4:3",
        }
        try:
            model = P.model_for(style, P.DEFAULT_MODEL)
            raw = client.generate(
                model, P.prompt_for({**job, "model": model}), refs=[ref], aspect="4:3", retries=1
            )
        except Exception as exc:  # noqa: BLE001 - one style failing leaves the rest
            return f"{style}: failed ({exc})"
        (FULL / f"{style}.jpg").write_bytes(raw)
        (OUT / f"{style}.jpg").write_bytes(thumbnail(raw))
        (OUT / "large").mkdir(exist_ok=True)
        (OUT / "large" / f"{style}.jpg").write_bytes(thumbnail(raw, LARGE))
        return f"{style}: ok"

    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        for line in pool.map(one, todo):
            print(line, flush=True)
    print(
        f"{len(todo)} asked, about US${client.spent_cents / 100:.2f} spent", flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
