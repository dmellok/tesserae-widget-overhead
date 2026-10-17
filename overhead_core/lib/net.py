"""Network, cache and picture helpers shared by the widget's modules: one
HTTP call with the widget's User-Agent, JSON, an on-disk fetch cache, a
picture resized (and converted for a greyscale or black-and-white panel)
as a JPEG data URI, the paper colour round a plate, and the bundled fonts
as @font-face rules. Loaded by server.py by path."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
USER_AGENT = "tesserae-overhead/0.1 (+https://github.com/dmellok/tesserae-widget-overhead)"
HTTP_TIMEOUT_S = 6  # a widget has six seconds in all; no one call may take them
IMG_MAX_BYTES = 12_000_000


def write(path: Path, data: bytes) -> None:
    """Write via a temp file and rename, so a concurrent render never reads a
    half-written file."""
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{id(data)}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)


def read_json(path: Path, default: Any) -> Any:
    with contextlib.suppress(OSError, json.JSONDecodeError, UnicodeDecodeError):
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:60] or "x"


def http(
    url: str,
    token: str = "",
    accept: str = "application/json",
    *,
    auth_scheme: str = "Bearer",
    body: bytes | None = None,
    timeout: float = HTTP_TIMEOUT_S,
    detail: bool = False,
    ua: str = "",
) -> tuple[bytes | None, str | None]:
    """(bytes, None) or (None, why): "auth", "unreachable", "too large",
    or "HTTP <code>" (with the server's own message when ``detail``)."""
    headers = {"User-Agent": ua or USER_AGENT, "Accept": accept}
    if token:
        headers["Authorization"] = f"{auth_scheme} {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(IMG_MAX_BYTES + 1)
            return (None, "too large") if len(data) > IMG_MAX_BYTES else (data, None)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403) and not detail:
            return None, "auth"
        why = f"HTTP {err.code}"
        if detail:
            with contextlib.suppress(Exception):
                got = json.loads(err.read(20_000).decode("utf-8", "replace"))
                msg = got.get("detail") if isinstance(got, dict) else None
                if isinstance(msg, list) and msg and isinstance(msg[0], dict):
                    msg = msg[0].get("msg")
                if isinstance(msg, str) and msg.strip():
                    why += f": {msg.strip()[:160]}"
        return None, why
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, "unreachable"


def get_json(url: str, token: str = "", **kw: Any) -> tuple[Any | None, str | None]:
    body, err = http(url, token, **kw)
    if err or body is None:
        return None, err
    try:
        return json.loads(body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "not json"


def cached_get(data_dir: Path, url: str, token: str = "", ua: str = "") -> bytes | None:
    """Fetch a picture once and keep it; a failure is remembered for a day so
    a dead link isn't retried on every refresh."""
    folder = data_dir / "img"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:20]
    path, miss = folder / f"{key}.bin", folder / f"{key}.miss"
    if path.exists():
        with contextlib.suppress(OSError):
            return path.read_bytes()
    if miss.exists() and time.time() - miss.stat().st_mtime < 86400:
        return None
    body, err = http(url, token, accept="image/*", timeout=8, ua=ua)
    if err or not body:
        with contextlib.suppress(OSError):
            miss.touch()
        return None
    write(path, body)
    return body


def render(
    raw: bytes,
    size: int,
    box: list[float] | None = None,
    cache: Path | None = None,
    levels: str = "colour",
) -> str:
    """Crop to ``box`` (fractions), fit the longest edge to ``size`` and
    return a JPEG data URI; cached per (source, box, size, levels) when
    ``cache`` is given. For a greyscale or black-and-white panel the picture
    is converted here with the contrast stretched, so a watercolour plate
    still reads once the panel dithers it."""
    if cache is not None and levels != "colour":
        cache = cache.with_name(f"{cache.stem}_{levels}{cache.suffix}")
    if cache is not None and cache.exists():
        with contextlib.suppress(OSError):
            return (
                "data:image/jpeg;base64,"
                + base64.b64encode(cache.read_bytes()).decode()
            )
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow ships with Tesserae
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:  # noqa: BLE001 - any undecodable image is just skipped
        return ""
    if box and len(box) == 4:
        w, h = im.size
        x0, y0, x1, y1 = (max(0.0, min(1.0, float(v))) for v in box)
        if x1 - x0 > 0.05 and y1 - y0 > 0.05:
            im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    im.thumbnail((size, size), Image.Resampling.LANCZOS)
    if levels != "colour":
        cutoff = {"gray16": 0.5, "gray4": 1.0, "mono": 1.0}.get(levels, 1.0)
        im = ImageOps.autocontrast(im.convert("L"), cutoff=cutoff)
        if levels == "mono":
            # the panel dithers every mid-tone to a texture, and a plate's
            # reds and greens all sit in the mid-tones, so lift them a little
            im = im.point([round(255 * (i / 255) ** 0.8) for i in range(256)])
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    data = out.getvalue()
    if cache is not None:
        write(cache, data)
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def aspect_of(src: str) -> float:
    """Width over height of a JPEG data URI (its header only is read), or
    0.8 when it cannot be told; the page lays placeholders out from it
    before it has decoded a picture."""
    try:
        from PIL import Image

        head, _, data = src.partition(",")
        with Image.open(io.BytesIO(base64.b64decode(data))) as im:
            w, h = im.size
        return round(w / h, 3) if w and h else 0.8
    except Exception:  # noqa: BLE001 - any odd picture just gets the default
        return 0.8


def paper_of(src: str, cache: Path, levels: str = "colour") -> str:
    """The page colour round a plate, as #rrggbb: the median of a thin band
    along the picture's edges."""
    if levels == "mono":
        return "#ffffff"
    if levels != "colour":
        cache = cache.with_name(f"{cache.stem}_{levels}{cache.suffix}")
    with contextlib.suppress(OSError):
        hit = cache.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"#[0-9a-f]{6}", hit):
            return hit
    colour = "#f3ead6"
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))).convert(
            "RGB"
        )
        w, h = im.size
        b = max(2, min(w, h) // 40)
        bands = [
            im.crop((0, 0, w, b)),
            im.crop((0, h - b, w, h)),
            im.crop((0, 0, b, h)),
            im.crop((w - b, 0, w, h)),
        ]
        import numpy as np

        px = np.concatenate([np.asarray(x).reshape(-1, 3) for x in bands])
        r, g, bl = (int(v) for v in np.median(px, axis=0))
        colour = f"#{r:02x}{g:02x}{bl:02x}"
    except Exception:  # noqa: BLE001 - fall back to the default cream
        pass
    write(cache, colour.encode())
    return colour


def font_css(groups: tuple[str, ...]) -> str:
    """@font-face rules for the bundled faces in ``groups``, as data URIs."""
    if not groups:
        return ""
    manifest = read_json(HERE / "fonts" / "fonts.json", None)
    if not isinstance(manifest, dict):
        return ""
    rules = []
    for file, face in manifest.items():
        if face.get("group") not in groups:
            continue
        try:
            data = base64.b64encode((HERE / "fonts" / file).read_bytes()).decode()
        except OSError:
            continue
        rules.append(
            f"@font-face{{font-family:'{face['family']}';font-style:{face['style']};"
            f"font-weight:{face['weight']};font-display:block;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{face['range']};}}"
        )
    return "".join(rules)
