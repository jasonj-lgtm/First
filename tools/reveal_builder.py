#!/usr/bin/env python3
"""That 1 Painter — before/after reveal builder (v2 brand standard).

Assembles a 9:16 reveal reel from a matched before/after photo pair:

    BEFORE beat (Ken Burns + blue animated chip)
    -> AFTER beat (Ken Burns + blue animated chip)
    -> CTA/proof card (FREE ESTIMATE · <City>, OR · <n> FIVE-STAR REVIEWS · CCB #...)

v2 standard (all mandatory): motion on every beat, music bed, blue
gradient Before/After chips that animate in, geo-anchored CTA/proof close.

Usage:
    python3 tools/reveal_builder.py \
        --before before.jpg --after after.jpg --city Hillsboro \
        --music track.mp3 [--logo logo.png] [--out reveal.mp4] \
        [--reviews 351] [--ccb 249983] [--beat 4.0] [--cta 2.5]

Requires: ffmpeg on PATH, Pillow.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
FPS = 30

# Brand palette (navy/cobalt; chips use the blue logo-gradient convention).
NAVY = (11, 25, 48)
BLUE_A = (30, 111, 224)   # cobalt
BLUE_B = (74, 168, 255)   # lighter logo blue
WHITE = (255, 255, 255)
GOLD = (255, 200, 64)     # star accent on the proof line

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def fit_photo(src: Path, dst: Path) -> None:
    """Scale-and-crop a photo to cover the full 1080x1920 frame."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.5)).save(dst)


def make_chip(text: str, dst: Path) -> None:
    """Rounded blue-gradient label chip ('BEFORE' / 'AFTER'), transparent PNG."""
    font = load_font(84)
    pad_x, pad_y = 70, 34
    tw = int(font.getlength(text))
    th = font.size
    cw, ch = tw + pad_x * 2, th + pad_y * 2

    # Horizontal cobalt -> light-blue gradient, masked to a rounded rect.
    gradient = Image.new("RGB", (cw, ch))
    for x in range(cw):
        t = x / max(cw - 1, 1)
        gradient.paste(
            tuple(int(a + (b - a) * t) for a, b in zip(BLUE_A, BLUE_B)),
            (x, 0, x + 1, ch),
        )
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), radius=ch // 2, fill=255)

    # Soft drop shadow behind the chip.
    margin = 24
    chip = Image.new("RGBA", (cw + margin * 2, ch + margin * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", chip.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (margin, margin + 6, margin + cw - 1, margin + ch + 5), radius=ch // 2, fill=(0, 0, 0, 130)
    )
    chip.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    chip.paste(gradient, (margin, margin), mask)
    draw = ImageDraw.Draw(chip)
    draw.text(
        (margin + pad_x, margin + pad_y - th * 0.12),
        text,
        font=font,
        fill=WHITE,
    )
    chip.save(dst)


def make_cta_card(city: str, reviews: str, ccb: str, logo: Path | None, dst: Path) -> None:
    """Full-frame navy CTA/proof card — the close every reveal must keep."""
    card = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(card)

    # Subtle vertical sheen so the card isn't flat.
    for y in range(H):
        t = abs(y / H - 0.32)
        lift = max(0, int(26 * (1 - t * 2.2)))
        draw.line([(0, y), (W, y)], fill=tuple(c + lift for c in NAVY))

    y = int(H * 0.20)
    if logo and logo.exists():
        with Image.open(logo) as lg:
            lg = lg.convert("RGBA")
            lg.thumbnail((int(W * 0.55), 300), Image.LANCZOS)
            card.paste(lg, ((W - lg.width) // 2, y), lg)
            y += lg.height + 90
    else:
        brand_font = load_font(74)
        text = "THAT 1 PAINTER"
        draw.text(((W - draw.textlength(text, font=brand_font)) / 2, y), text, font=brand_font, fill=WHITE)
        y += 100
        tag_font = load_font(40)
        tag = "Best House Guests Ever."
        draw.text(((W - draw.textlength(tag, font=tag_font)) / 2, y), tag, font=tag_font, fill=BLUE_B)
        y += 170

    cta_font = load_font(108)
    text = "FREE ESTIMATE"
    draw.text(((W - draw.textlength(text, font=cta_font)) / 2, y), text, font=cta_font, fill=WHITE)
    y += 160

    city_font = load_font(66)
    text = f"{city}, OR"
    draw.text(((W - draw.textlength(text, font=city_font)) / 2, y), text, font=city_font, fill=BLUE_B)
    y += 170

    proof_font = load_font(52)
    text = f"★ {reviews} FIVE-STAR REVIEWS ★"
    draw.text(((W - draw.textlength(text, font=proof_font)) / 2, y), text, font=proof_font, fill=GOLD)
    y += 110

    ccb_font = load_font(44)
    text = f"CCB #{ccb}"
    draw.text(((W - draw.textlength(text, font=ccb_font)) / 2, y), text, font=ccb_font, fill=(148, 163, 184))

    card.save(dst)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{proc.stderr[-2000:]}")


def build(args: argparse.Namespace) -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH — install it first.")

    out = Path(args.out)
    beat, cta = args.beat, args.cta
    total = beat * 2 + cta

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fit_photo(Path(args.before), tmp / "before.png")
        fit_photo(Path(args.after), tmp / "after.png")
        make_chip("BEFORE", tmp / "chip_before.png")
        make_chip("AFTER", tmp / "chip_after.png")
        make_cta_card(
            args.city, str(args.reviews), args.ccb,
            Path(args.logo) if args.logo else None, tmp / "cta.png",
        )

        beat_frames = int(beat * FPS)
        cta_frames = int(cta * FPS)
        # Ken Burns: upscale 2x first so zoompan doesn't jitter, then slow
        # centered zoom — in on the before, out on the after, for contrast.
        upscale = f"scale={W * 2}:{H * 2}:flags=lanczos"
        zoom_in = (
            f"{upscale},zoompan=z='1+0.10*on/{beat_frames}':d={beat_frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}"
        )
        zoom_out = (
            f"{upscale},zoompan=z='1.10-0.10*on/{beat_frames}':d={beat_frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}"
        )
        cta_zoom = (
            f"{upscale},zoompan=z='1+0.04*on/{cta_frames}':d={cta_frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"fade=t=in:st=0:d=0.35"
        )
        # Chips fade in and slide up into the lower third.
        chip_anim = "format=rgba,fade=t=in:st=0.25:d=0.45:alpha=1"
        chip_pos = "x=(main_w-overlay_w)/2:y=main_h*0.70+40*max(0\\,1-t/0.7)"

        filters = (
            f"[0:v]{zoom_in}[b];[1:v]{zoom_out}[a];[2:v]{cta_zoom}[c];"
            f"[3:v]{chip_anim}[cb];[4:v]{chip_anim}[ca];"
            f"[b][cb]overlay={chip_pos}:shortest=1[bv];"
            f"[a][ca]overlay={chip_pos}:shortest=1[av];"
            f"[bv][av][c]concat=n=3:v=1:a=0[v]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(beat), "-i", str(tmp / "before.png"),
            "-loop", "1", "-t", str(beat), "-i", str(tmp / "after.png"),
            "-loop", "1", "-t", str(cta), "-i", str(tmp / "cta.png"),
            "-loop", "1", "-t", str(beat), "-i", str(tmp / "chip_before.png"),
            "-loop", "1", "-t", str(beat), "-i", str(tmp / "chip_after.png"),
        ]
        if args.music:
            cmd += ["-stream_loop", "-1", "-i", str(args.music)]
            filters += (
                f";[5:a]atrim=0:{total},afade=t=in:st=0:d=0.5,"
                f"afade=t=out:st={total - 0.8}:d=0.8[aud]"
            )
        cmd += ["-filter_complex", filters, "-map", "[v]"]
        if args.music:
            cmd += ["-map", "[aud]", "-c:a", "aac", "-b:a", "160k"]
        cmd += [
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-t", str(total), str(out),
        ]
        run(cmd)

    print(f"Built {out} — {total:.1f}s, {W}x{H}, "
          f"{'music bed' if args.music else 'SILENT'}")
    if not args.music:
        print("WARNING: no --music given. The v2 brand standard says never "
              "ship silent — add a music bed before posting.")
    print("QA next: score against the rubric in .claude/skills/rendering/SKILL.md")


def main() -> None:
    p = argparse.ArgumentParser(description="Build a That 1 Painter before/after reveal reel.")
    p.add_argument("--before", required=True, help="Before photo")
    p.add_argument("--after", required=True, help="After photo (matched angle)")
    p.add_argument("--city", required=True, help="Job city for the geo-anchored CTA")
    p.add_argument("--out", default="reveal.mp4")
    p.add_argument("--music", help="Music bed (mp3/m4a/wav) — required to ship")
    p.add_argument("--logo", help="Logo PNG for the CTA card (text fallback if omitted)")
    p.add_argument("--reviews", default="351", help="Five-star review count")
    p.add_argument("--ccb", default="249983", help="CCB license number")
    p.add_argument("--beat", type=float, default=4.0, help="Seconds per before/after beat")
    p.add_argument("--cta", type=float, default=2.5, help="Seconds for the CTA card")
    build(p.parse_args())


if __name__ == "__main__":
    main()
