#!/usr/bin/env python3
"""That 1 Painter — AI color-preview engine ("render.ai"-style).

Takes a real photo of a customer's house and produces a photorealistic
"what it could look like" recolor, then packages it to the v2 brand
standard as a CURRENT -> PREVIEW reveal reel and/or a static card.

Two backends:

  gemini  Photoreal recolor via Google's Gemini image-editing API
          (model gemini-2.5-flash-image). Needs GEMINI_API_KEY in the
          environment. This is the production path.
  local   Deterministic hue-band recolor (no AI, no network). Good for
          pipeline tests and rough demos; output is watermarked
          "DEMO MODE". Selects pixels near the sampled siding hue and
          maps them to the target color, preserving luminance texture.

Every output carries the disclaimer strip "AI color visualization —
actual results may vary" so previews are never mistaken for real afters.

Usage:
  python3 tools/preview_engine.py --photo house.jpg \
      --color "SW 7048 Urbane Bronze" --hex 54504A \
      --backend gemini --city "Oregon City" \
      [--music bed.wav --logo logo.png] [--out-dir previews/]

Produces in --out-dir:
  preview_recolor.png   the recolored photo
  preview_card.jpg      static 4:5 side-by-side card (brand standard)
  preview_reveal.mp4    9:16 CURRENT->PREVIEW reveal (if --music given)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

NAVY = (11, 27, 58)
COBALT = (37, 99, 235)
SKY = (56, 189, 248)
GOLD = (251, 191, 36)
SLATE = (148, 163, 184)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ----------------------------------------------------------------------
# Backends
# ----------------------------------------------------------------------

def recolor_gemini(photo: Path, color_name: str, hex_code: str, dst: Path) -> None:
    """Photoreal recolor through the Gemini image-editing API."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "GEMINI_API_KEY is not set. Add it as an environment secret "
            "(Claude Code environment settings) and re-run, or use "
            "--backend local for a demo render."
        )

    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    img.thumbnail((1536, 1536))  # keep request small; API returns ~1MP anyway
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = (
        "Repaint ONLY the painted siding and body of this house in the color "
        f"{color_name} (hex #{hex_code}). Keep the trim, roof, windows, doors, "
        "landscaping, sky, driveway and everything else exactly as they are. "
        "Photorealistic, same lighting, same camera angle. Do not add or "
        "remove any objects."
    )
    body = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]
        }],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode()

    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)

    for part in payload["candidates"][0]["content"]["parts"]:
        data = part.get("inlineData") or part.get("inline_data")
        if data:
            dst.write_bytes(base64.b64decode(data["data"]))
            return
    sys.exit("Gemini returned no image — response: " + json.dumps(payload)[:500])


def recolor_local(photo: Path, hex_code: str, dst: Path) -> None:
    """No-AI fallback: shift pixels near the dominant siding hue to the
    target color, keeping per-pixel luminance so texture survives.
    Rough by design — always watermarked DEMO MODE by the caller."""
    import colorsys

    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    hsv = img.convert("HSV")
    px_h, px_s, px_v = [ch.load() for ch in hsv.split()]
    w, h = img.size

    # Sample the dominant hue in the middle band of the image (siding zone).
    from collections import Counter

    counts: Counter[int] = Counter()
    for y in range(int(h * 0.25), int(h * 0.75), 4):
        for x in range(0, w, 4):
            if px_s[x, y] > 40 and 40 < px_v[x, y] < 240:
                counts[px_h[x, y] // 8] += 1
    if not counts:
        sys.exit("local backend: could not find a dominant siding hue")
    dom = counts.most_common(1)[0][0] * 8 + 4

    tr, tg, tb = (int(hex_code[i:i + 2], 16) for i in (0, 2, 4))
    th, ts, tv = colorsys.rgb_to_hsv(tr / 255, tg / 255, tb / 255)

    out = img.copy()
    op = out.load()
    for y in range(h):
        for x in range(w):
            hue, sat, val = px_h[x, y], px_s[x, y], px_v[x, y]
            dh = min(abs(hue - dom), 256 - abs(hue - dom))
            if dh <= 14 and sat > 30 and val > 30:
                # keep texture: scale target value by pixel luminance
                r, g, b = colorsys.hsv_to_rgb(th, ts, (val / 255) * max(tv, 0.35) / 0.62)
                op[x, y] = (int(r * 255), int(g * 255), int(b * 255))
    out.save(dst)


# ----------------------------------------------------------------------
# Branded packaging
# ----------------------------------------------------------------------

def disclaimer_strip(im: Image.Image, demo: bool) -> Image.Image:
    """Bottom strip: AI-visualization disclaimer (+ DEMO MODE watermark)."""
    w, h = im.size
    strip_h = max(44, h // 28)
    out = Image.new("RGB", (w, h + strip_h), NAVY)
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    f = load_font(int(strip_h * 0.48))
    msg = "AI color visualization — actual results may vary"
    if demo:
        msg += "  ·  DEMO MODE (no AI backend)"
    d.text(((w - d.textlength(msg, font=f)) / 2, h + strip_h * 0.26), msg, font=f, fill=SLATE)
    return out


def make_card(before: Path, preview: Path, color_name: str, city: str,
              logo: Path | None, demo: bool, dst: Path) -> None:
    """Static 4:5 stacked card: navy header, CURRENT / PREVIEW, CTA strip."""
    W, H = 1080, 1350
    card = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(card)

    header_h, cta_h = 120, 150
    photo_h = (H - header_h - cta_h) // 2

    f_head = load_font(46)
    title = "SEE IT BEFORE WE PAINT IT"
    title_w = W - 300 if logo and logo.exists() else W  # keep clear of the logo
    d.text(((title_w - d.textlength(title, font=f_head)) / 2, 36), title, font=f_head, fill=(255, 255, 255))

    def fit(p: Path) -> Image.Image:
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        return ImageOps.fit(im, (W, photo_h), Image.LANCZOS)

    card.paste(fit(before), (0, header_h))
    card.paste(fit(preview), (0, header_h + photo_h))

    def chip(text: str, cy: int) -> None:
        f = load_font(40)
        tw = d.textlength(text, font=f)
        cw, ch = int(tw + 70), 66
        chip_im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cd = ImageDraw.Draw(chip_im)
        for x in range(cw):  # simple horizontal cobalt->sky gradient
            t = x / cw
            col = tuple(int(COBALT[i] + (SKY[i] - COBALT[i]) * t) for i in range(3)) + (255,)
            cd.line([(x, 0), (x, ch)], fill=col)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=ch // 2, fill=255)
        chip_im.putalpha(mask)
        cd = ImageDraw.Draw(chip_im)
        cd.text((35, (ch - 40) / 2 - 4), text, font=f, fill=(255, 255, 255))
        card.paste(chip_im, (24, cy), chip_im)

    chip("CURRENT", header_h + 20)
    chip(f"PREVIEW · {color_name.upper()}", header_h + photo_h + 20)

    y = H - cta_h + 18
    f_cta = load_font(40)
    line = f"FREE ESTIMATE  ·  {city}, OR"
    d.text(((W - d.textlength(line, font=f_cta)) / 2, y), line, font=f_cta, fill=(255, 255, 255))
    f_small = load_font(28)
    msg = "AI color visualization — actual results may vary"
    if demo:
        msg += " · DEMO MODE"
    d.text(((W - d.textlength(msg, font=f_small)) / 2, y + 58), msg, font=f_small, fill=SLATE)
    d.text(((W - d.textlength("CCB #249983", font=f_small)) / 2, y + 96), "CCB #249983",
           font=f_small, fill=SLATE)

    if logo and logo.exists():
        lg = Image.open(logo).convert("RGBA")
        lg.thumbnail((240, 70))
        card.paste(lg, (W - lg.width - 24, 30), lg)

    card.save(dst, quality=93)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--photo", required=True, help="Real photo of the house (the 'current' shot)")
    p.add_argument("--color", required=True, help="Color name, e.g. 'SW 7048 Urbane Bronze'")
    p.add_argument("--hex", required=True, help="Target color hex, e.g. 54504A")
    p.add_argument("--backend", choices=["gemini", "local"], default="gemini")
    p.add_argument("--city", default="Portland")
    p.add_argument("--music", help="Music bed — also builds the 9:16 reveal when given")
    p.add_argument("--logo", help="Brand logo PNG")
    p.add_argument("--out-dir", default="previews")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    photo = Path(args.photo)
    hex_code = args.hex.lstrip("#")
    demo = args.backend == "local"

    recolor = out_dir / "preview_recolor.png"
    if demo:
        recolor_local(photo, hex_code, recolor)
    else:
        recolor_gemini(photo, args.color, hex_code, recolor)
    print(f"recolor -> {recolor}")

    card = out_dir / "preview_card.jpg"
    make_card(photo, recolor, args.color, args.city,
              Path(args.logo) if args.logo else None, demo, card)
    print(f"card    -> {card}")

    if args.music:
        reveal = out_dir / "preview_reveal.mp4"
        labeled = out_dir / "_preview_labeled.png"
        disclaimer_strip(ImageOps.exif_transpose(Image.open(recolor)).convert("RGB"),
                         demo).save(labeled)
        cmd = [
            sys.executable, str(Path(__file__).parent / "reveal_builder.py"),
            "--before", str(photo), "--after", str(labeled),
            "--city", args.city, "--music", args.music,
            "--label-before", "CURRENT", "--label-after", "PREVIEW",
            "--out", str(reveal),
        ]
        if args.logo:
            cmd += ["--logo", args.logo]
        subprocess.run(cmd, check=True)
        print(f"reveal  -> {reveal}")


if __name__ == "__main__":
    main()
