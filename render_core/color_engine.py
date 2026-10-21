#!/usr/bin/env python3
"""That 1 Painter — the one color engine (Gap #2).

`recolor(photo_path, palette_id, surfaces)` is the single recolor entry
point shared by Render Studio previews, Chip 3.0 postcards and anything
else that shows a customer their house in a new color.

Backends (auto-selected):
  gemini  GEMINI_API_KEY set -> photoreal recolor via Gemini image editing
          (Nano Banana family, gemini-2.5-flash-image) with structure
          preservation: same roofline, windows, landscaping.
  local   No key -> deterministic hue-band recolor (texture-preserving);
          outputs additionally watermarked DEMO MODE.

Every output is stamped with the small "Color concept" disclosure label
from render_core/brand.json — mandatory, never strip it.

Colors come from render_core/palettes.json (the single palette source):
pass `palette_id` (e.g. "modern-gray") to use a palette's body color, or
`color_name` + `hex_code` for a one-off.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

CORE = Path(__file__).parent
BRAND = json.loads((CORE / "brand.json").read_text())
PALETTES = json.loads((CORE / "palettes.json").read_text())

GEMINI_MODEL = "gemini-2.5-flash-image"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in BRAND["font"]["files"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def resolve_color(palette_id: str | None = None,
                  color_name: str | None = None,
                  hex_code: str | None = None) -> tuple[str, str]:
    """-> (display name, '#RRGGBB'). palette_id wins, then explicit pair."""
    if palette_id:
        for p in PALETTES["palettes"]:
            if p["id"] == palette_id:
                return p["body"]["name"], p["body"]["hex"]
        raise ValueError(f"unknown palette_id {palette_id!r} — see render_core/palettes.json")
    if hex_code:
        return color_name or hex_code, "#" + hex_code.lstrip("#").upper()
    raise ValueError("pass palette_id, or color_name + hex_code")


def stamp_disclosure(img: Image.Image, demo: bool) -> Image.Image:
    """Small corner 'Color concept' label — the mandatory disclosure."""
    img = img.convert("RGB")
    text = "COLOR CONCEPT" + (" · DEMO MODE" if demo else "")
    f = _font(max(20, img.width // 42))
    d = ImageDraw.Draw(img, "RGBA")
    tw = d.textlength(text, font=f)
    pad = f.size // 2
    x0, y0 = img.width - tw - pad * 3, img.height - f.size - pad * 3
    d.rounded_rectangle(
        (x0, y0, img.width - pad, img.height - pad),
        radius=f.size // 2 + 2, fill=(5, 19, 45, 200),
    )
    d.text((x0 + pad, y0 + pad // 2 + 2), text, font=f, fill=(237, 240, 242))
    return img


def _recolor_gemini(photo: Path, name: str, hexv: str, surfaces: tuple[str, ...]) -> Image.Image:
    api_key = os.environ["GEMINI_API_KEY"]
    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    img.thumbnail((1536, 1536))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)

    surface_txt = " and ".join(surfaces) if surfaces else "painted siding and body"
    prompt = (
        f"Repaint ONLY the {surface_txt} of this house in {name} (hex {hexv}). "
        "Structure preservation is mandatory: identical roofline, windows, doors, "
        "trim (unless trim is listed), landscaping, sky, driveway, camera angle "
        "and lighting. Photorealistic. Do not add or remove any objects."
    )
    body = json.dumps({
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": "image/jpeg",
                             "data": base64.b64encode(buf.getvalue()).decode()}},
        ]}],
        # Image models reject IMAGE-only responseModalities on this API;
        # text+image is the supported combination and we pick the image part.
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode()
    req = urllib.request.Request(
        GEMINI_URL, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        # Surface the API's own reason — a truncated traceback hides it.
        detail = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Gemini HTTP {e.code}: {detail}") from None
    for part in payload["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            return Image.open(BytesIO(base64.b64decode(data["data"]))).convert("RGB")
    raise RuntimeError("Gemini returned no image: " + json.dumps(payload)[:400])


def _recolor_local(photo: Path, hexv: str) -> Image.Image:
    """No-AI fallback: dominant-hue band remap, luminance-preserving."""
    import colorsys
    from collections import Counter

    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    hsv = img.convert("HSV")
    px_h, px_s, px_v = [ch.load() for ch in hsv.split()]
    w, h = img.size
    counts: Counter[int] = Counter()
    for y in range(int(h * 0.25), int(h * 0.75), 4):
        for x in range(0, w, 4):
            if px_s[x, y] > 40 and 40 < px_v[x, y] < 240:
                counts[px_h[x, y] // 8] += 1
    if not counts:
        raise RuntimeError("local backend: no dominant siding hue found")
    dom = counts.most_common(1)[0][0] * 8 + 4

    hx = hexv.lstrip("#")
    tr, tg, tb = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
    th, ts, tv = colorsys.rgb_to_hsv(tr / 255, tg / 255, tb / 255)
    out = img.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            hue, sat, val = px_h[x, y], px_s[x, y], px_v[x, y]
            dh = min(abs(hue - dom), 256 - abs(hue - dom))
            if dh <= 14 and sat > 30 and val > 30:
                r, g, b = colorsys.hsv_to_rgb(th, ts, (val / 255) * max(tv, 0.35) / 0.62)
                op[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    return out


def recolor(photo_path: str | Path,
            palette_id: str | None = None,
            surfaces: tuple[str, ...] = ("siding", "body"),
            color_name: str | None = None,
            hex_code: str | None = None,
            out_path: str | Path | None = None,
            backend: str | None = None) -> Path:
    """The single recolor entry point. Returns the stamped image path."""
    photo = Path(photo_path)
    name, hexv = resolve_color(palette_id, color_name, hex_code)
    backend = backend or ("gemini" if os.environ.get("GEMINI_API_KEY") else "local")
    demo = backend != "gemini"
    img = _recolor_local(photo, hexv) if demo else _recolor_gemini(photo, name, hexv, surfaces)
    img = stamp_disclosure(img, demo)
    dst = Path(out_path) if out_path else photo.with_name(photo.stem + f".concept.{backend}.png")
    img.save(dst)
    return dst


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--photo", required=True)
    p.add_argument("--palette", help="palette id from render_core/palettes.json")
    p.add_argument("--color", help="one-off color name")
    p.add_argument("--hex", help="one-off hex")
    p.add_argument("--surfaces", default="siding,body")
    p.add_argument("--out")
    p.add_argument("--backend", choices=["gemini", "local"])
    a = p.parse_args()
    dst = recolor(a.photo, a.palette, tuple(s.strip() for s in a.surfaces.split(",")),
                  a.color, a.hex, a.out, a.backend)
    print(dst)
