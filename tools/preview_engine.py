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
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from render_core.color_engine import BRAND, recolor as core_recolor  # noqa: E402

NAVY = tuple(int(BRAND["colors"]["navy"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
COBALT = tuple(int(BRAND["colors"]["cobalt"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
SKY = tuple(int(BRAND["colors"]["azure"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
GOLD = tuple(int(BRAND["colors"]["gold"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
SLATE = (148, 163, 184)

FONT_CANDIDATES = list(BRAND["font"]["files"])


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


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
    core_recolor(photo, color_name=args.color, hex_code=hex_code,
                 out_path=recolor, backend=args.backend)
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
