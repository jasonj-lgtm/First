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
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
FPS = 30

REPO = Path(__file__).resolve().parent.parent
MUSIC_DIR = REPO / "assets" / "music" / "licensed"


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# Brand tokens come from render_core/brand.json (the single brand source);
# hardcoded values below are only the fallback if that file is missing.
try:
    _B = json.loads((REPO / "render_core" / "brand.json").read_text())
    _C = _B["colors"]
    NAVY, BLUE_A, BLUE_B = _hex(_C["navy"]), _hex(_C["cobalt"]), _hex(_C["azure"])
    TEAL = _hex(_C.get("teal", "#33BBCE"))
    GOLD = _hex(_C["gold"])
    FONT_CANDIDATES = list(_B["font"]["files"])
except Exception:
    NAVY = (11, 25, 48)
    BLUE_A = (30, 111, 224)
    BLUE_B = (74, 168, 255)
    TEAL = (51, 187, 206)
    GOLD = (255, 200, 64)
    FONT_CANDIDATES = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
WHITE = (255, 255, 255)


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


def make_chip(text: str, dst: Path, diameter: int = 260) -> None:
    """Corporate circular badge ('BEFORE' / 'AFTER'): teal->azure gradient
    circle with bold white uppercase text — the mark the national T1P
    pages stamp on every before/after composite. Transparent PNG."""
    d = diameter
    margin = 26
    size = d + margin * 2
    chip = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Soft drop shadow.
    shadow = Image.new("RGBA", chip.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        (margin, margin + 8, margin + d, margin + d + 8), fill=(0, 0, 0, 120))
    chip.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))

    # Vertical teal -> azure gradient masked to the circle.
    gradient = Image.new("RGB", (d, d))
    for y in range(d):
        t = y / max(d - 1, 1)
        gradient.paste(
            tuple(int(a + (b - a) * t) for a, b in zip(TEAL, BLUE_B)),
            (0, y, d, y + 1),
        )
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    chip.paste(gradient, (margin, margin), mask)

    # Size the text to sit comfortably inside the circle.
    fsize = 60
    font = load_font(fsize)
    while font.getlength(text) > d * 0.78 and fsize > 30:
        fsize -= 2
        font = load_font(fsize)
    draw = ImageDraw.Draw(chip)
    tw = draw.textlength(text, font=font)
    draw.text((margin + (d - tw) / 2, margin + d / 2 - font.size * 0.62),
              text, font=font, fill=WHITE)
    chip.save(dst)


def make_cta_card(city: str, reviews: str, ccb: str, logo: Path | None, dst: Path) -> None:
    """Full-frame CTA/proof card in the corporate style: azure->cobalt
    gradient, white logo, 'FREE' on a white brushstroke swash."""
    card = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(card)

    # Corporate gradient: azure up top falling into cobalt.
    for y in range(H):
        t = y / (H - 1)
        draw.line([(0, y), (W, y)],
                  fill=tuple(int(a + (b - a) * t) for a, b in zip(BLUE_B, BLUE_A)))

    y = int(H * 0.18)
    if logo and logo.exists():
        with Image.open(logo) as lg:
            lg = lg.convert("RGBA")
            lg.thumbnail((int(W * 0.55), 300), Image.LANCZOS)
            # All-white logo on blue, per the corporate cards.
            white_lg = Image.new("RGBA", lg.size, WHITE + (255,))
            white_lg.putalpha(lg.getchannel("A"))
            card.paste(white_lg, ((W - lg.width) // 2, y), white_lg)
            y += lg.height + 90
    else:
        brand_font = load_font(74)
        text = "THAT 1 PAINTER"
        draw.text(((W - draw.textlength(text, font=brand_font)) / 2, y), text, font=brand_font, fill=WHITE)
        y += 100
        tag_font = load_font(40)
        tag = "Best House Guests Ever."
        draw.text(((W - draw.textlength(tag, font=tag_font)) / 2, y), tag, font=tag_font, fill=WHITE)
        y += 170

    # "GET YOUR" lead-in, then FREE on a white brushstroke swash,
    # then ESTIMATE — echoing the corporate 'Get your FREE estimate' card.
    lead_font = load_font(56)
    text = "GET YOUR"
    draw.text(((W - draw.textlength(text, font=lead_font)) / 2, y), text, font=lead_font, fill=WHITE)
    y += 110

    free_font = load_font(150)
    text = "FREE"
    tw = draw.textlength(text, font=free_font)
    bx0, bx1 = (W - tw) / 2 - 60, (W + tw) / 2 + 60
    by0, by1 = y - 14, y + free_font.size + 10
    # Brushstroke swash: clean rounded band with flared ends, like the
    # corporate 'FREE estimate' card.
    draw.rounded_rectangle((bx0, by0, bx1, by1), radius=30, fill=WHITE)
    mid = (by0 + by1) / 2
    draw.ellipse((bx0 - 28, mid - 40, bx0 + 34, mid + 40), fill=WHITE)
    draw.ellipse((bx1 - 34, mid - 40, bx1 + 28, mid + 40), fill=WHITE)
    draw.text(((W - tw) / 2, y - free_font.size * 0.12), text, font=free_font, fill=BLUE_A)
    y += free_font.size + 60

    cta_font = load_font(96)
    text = "ESTIMATE"
    draw.text(((W - draw.textlength(text, font=cta_font)) / 2, y), text, font=cta_font, fill=WHITE)
    y += 160

    city_font = load_font(66)
    text = f"{city}, OR"
    draw.text(((W - draw.textlength(text, font=city_font)) / 2, y), text, font=city_font, fill=WHITE)
    y += 170

    proof_font = load_font(52)
    text = f"{reviews} FIVE-STAR REVIEWS"
    tw = draw.textlength(text, font=proof_font)
    star_r, gap = 24, 26
    tx = (W - tw) / 2
    draw.text((tx, y), text, font=proof_font, fill=GOLD)

    def star(cx: float, cy: float, r: float) -> None:
        import math
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.42
            ang = -math.pi / 2 + i * math.pi / 5
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        draw.polygon(pts, fill=GOLD)

    cy = y + proof_font.size * 0.55
    star(tx - gap - star_r, cy, star_r)
    star(tx + tw + gap + star_r, cy, star_r)
    y += 110

    ccb_font = load_font(44)
    text = f"CCB #{ccb}"
    draw.text(((W - draw.textlength(text, font=ccb_font)) / 2, y), text, font=ccb_font, fill=(214, 228, 245))

    card.save(dst)


def make_hook_card(text: str, dst: Path) -> None:
    """Hook line burned into the first 1.5s (azure accent bar + bold line),
    rendered as a transparent full-width PNG to avoid drawtext escaping."""
    font = load_font(72)
    pad = 36
    max_w = W - 120
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    lh = int(font.size * 1.22)
    ch = pad * 2 + lh * len(lines)
    card = Image.new("RGBA", (W, ch + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((40, 0, W - 40, ch), radius=26, fill=NAVY + (215,))
    d.rectangle((40, 0, 52, ch), fill=BLUE_B + (255,))
    y = pad - 4
    for ln in lines:
        d.text((90, y), ln, font=font, fill=WHITE)
        y += lh
    card.save(dst)


def make_composite(before: Path, after: Path, chip_b: Image.Image,
                   chip_a: Image.Image, dst: Path) -> None:
    """Corporate-style stacked before/after still (4:5): BEFORE badge on a
    white corner blob top-left, AFTER bottom-right, thin white divider —
    the format the national T1P pages post alongside reels."""
    CW, CH = 1080, 1350
    half = CH // 2
    card = Image.new("RGB", (CW, CH), WHITE)

    def fit(p: Path) -> Image.Image:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            return ImageOps.fit(im, (CW, half), Image.LANCZOS)

    card.paste(fit(before), (0, 0))
    card.paste(fit(after), (0, CH - half))
    d = ImageDraw.Draw(card)
    d.rectangle((0, half - 6, CW, half + 6), fill=WHITE)

    # White organic corner blobs under the badges, like the corporate posts —
    # sized to hug the badge, not eat the photo.
    d.ellipse((-140, -140, 235, 235), fill=WHITE)
    d.ellipse((CW - 235, CH - 235, CW + 140, CH + 140), fill=WHITE)
    b = chip_b.resize((190, 190), Image.LANCZOS)
    a = chip_a.resize((190, 190), Image.LANCZOS)
    card.paste(b, (4, 4), b)
    card.paste(a, (CW - a.width - 4, CH - a.height - 4), a)
    card.save(dst, quality=90)


def pick_music(music_arg: str | None) -> str | None:
    """Explicit --music wins; otherwise pick from assets/music/licensed/.
    Never reuse audio lifted from past reels."""
    if music_arg:
        return music_arg
    if MUSIC_DIR.is_dir():
        tracks = [p for p in MUSIC_DIR.iterdir()
                  if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac")]
        if tracks:
            return str(random.choice(tracks))
    return None


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{proc.stderr[-2000:]}")


def build(args: argparse.Namespace) -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH — install it first.")

    out = Path(args.out)
    beat, cta = args.beat, args.cta
    swipe = args.transition == "swipe"
    xd = 0.45 if swipe else 0.0
    total = beat * 2 + cta - xd
    music = pick_music(args.music)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Pre-render stills at 1.3x so zoom crops never upscale source pixels.
        BW, BH = int(W * 1.3) // 2 * 2, int(H * 1.3) // 2 * 2

        def fit_big(p: Path) -> Image.Image:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                return ImageOps.fit(im, (BW, BH), Image.LANCZOS)

        before_big = fit_big(Path(args.before))
        after_big = fit_big(Path(args.after))
        # 170px badge ≈ 18% of frame width incl. shadow — corporate proportion;
        # bigger covers too much of the photo (Jason, 2026-10-17).
        make_chip(args.label_before.upper(), tmp / "cb.png", diameter=170)
        make_chip(args.label_after.upper(), tmp / "ca.png", diameter=170)
        chip_b = Image.open(tmp / "cb.png").convert("RGBA")
        chip_a = Image.open(tmp / "ca.png").convert("RGBA")
        hook_im = None
        if args.hook:
            make_hook_card(args.hook, tmp / "hk.png")
            hook_im = Image.open(tmp / "hk.png").convert("RGBA")
        make_cta_card(args.city, str(args.reviews), args.ccb,
                      Path(args.logo) if args.logo else None, tmp / "cta.png")
        cta_big = Image.open(tmp / "cta.png").convert("RGB").resize((BW, BH), Image.LANCZOS)

        def zoom_frame(big: Image.Image, z: float) -> Image.Image:
            cw, ch = int(BW / z), int(BH / z)
            x0, y0 = (BW - cw) // 2, (BH - ch) // 2
            # BILINEAR: this runs per frame at 30fps — LANCZOS here cost more
            # CPU than the x264 encode and blew the 900s cap on free workers.
            return big.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)

        def paste_anim(frame: Image.Image, overlay: Image.Image, t: float,
                       y_frac: float, fade_in=(0.25, 0.45), fade_out=None,
                       x: int | None = None) -> None:
            alpha = 1.0
            s, d = fade_in
            if t < s:
                alpha = 0.0
            elif t < s + d:
                alpha = (t - s) / d
            if fade_out:
                fs, fd = fade_out
                if t >= fs + fd:
                    alpha = 0.0
                elif t >= fs:
                    alpha = min(alpha, 1 - (t - fs) / fd)
            if alpha <= 0:
                return
            ov = overlay
            if alpha < 1:
                ov = overlay.copy()
                ov.putalpha(ov.getchannel("A").point(lambda v: int(v * alpha)))
            rise = int(40 * max(0.0, 1 - t / 0.7))
            px = (W - ov.width) // 2 if x is None else x
            frame.paste(ov, (px, int(H * y_frac) + rise), ov)

        def beat1_frame(t: float) -> Image.Image:
            f = zoom_frame(before_big, 1 + 0.10 * t / beat)
            if hook_im is not None and t < 1.5:
                a = hook_im if t < 1.2 else None
                if a is None:
                    ov = hook_im.copy()
                    ov.putalpha(ov.getchannel("A").point(
                        lambda v: int(v * max(0.0, 1 - (t - 1.2) / 0.3))))
                    f.paste(ov, (0, int(H * 0.12)), ov)
                else:
                    f.paste(hook_im, (0, int(H * 0.12)), hook_im)
            paste_anim(f, chip_b, t, 0.76, x=36)  # corporate corner: BEFORE lower-left
            return f

        def beat2_frame(t: float) -> Image.Image:
            f = zoom_frame(after_big, 1.10 - 0.10 * t / beat)
            paste_anim(f, chip_a, t, 0.76, x=W - chip_a.width - 36)  # AFTER lower-right
            return f

        def cta_frame(t: float) -> Image.Image:
            f = zoom_frame(cta_big, 1 + 0.04 * t / cta)
            if t < 0.35:  # fade in from black
                k = t / 0.35
                f = Image.eval(f, (lambda v, k=k: int(v * k)))
            return f

        def frames():
            n1 = int((beat - xd) * FPS)          # before beat (minus overlap)
            nx = int(xd * FPS)                   # swipe
            n2 = int(beat * FPS)                 # after beat
            nc = int(total * FPS) - n1 - nx - n2 # cta fills the remainder
            for i in range(n1):
                yield beat1_frame(i / FPS)
            for i in range(nx):
                p = (i + 1) / (nx + 1)
                a = beat1_frame(beat - xd + i / FPS)
                b = beat2_frame(i / FPS)
                col = int(W * (1 - p))
                a.paste(b.crop((col, 0, W, H)), (col, 0))
                yield a
            for i in range(n2):
                yield beat2_frame(xd + i / FPS if swipe else i / FPS)
            for i in range(nc):
                yield cta_frame(i / FPS)

        cmd = ["ffmpeg", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-"]
        filters = []
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music)]
            filters = ["-filter_complex",
                       f"[1:a]atrim=0:{total},afade=t=in:st=0:d=0.5,"
                       f"afade=t=out:st={total - 0.8}:d=0.8[aud]",
                       "-map", "0:v", "-map", "[aud]", "-c:a", "aac", "-b:a", "160k"]
        cmd += filters + ["-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                          "-x264-params", "rc-lookahead=10:ref=1:bframes=1",
                          "-pix_fmt", "yuv420p", "-t", str(total), str(out)]
        # stderr goes to a FILE, not a pipe: nobody drains a pipe while we
        # feed stdin, so ffmpeg's progress chatter fills 64KB and deadlocks
        # both processes (the "stalled render" on slow workers).
        errlog = tmp / "ffmpeg.err"
        with open(errlog, "wb") as ef:
            proc = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats",
                                     "-loglevel", "error"] + cmd[1:],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=ef)
            try:
                for fr in frames():
                    proc.stdin.write(fr.tobytes())
                proc.stdin.close()
            except BrokenPipeError:
                pass
            proc.wait()

        comp = out.with_name(out.stem + "_composite.jpg")
        make_composite(Path(args.before), Path(args.after), chip_b, chip_a, comp)
        if proc.returncode != 0:
            sys.exit("ffmpeg failed:\n" + errlog.read_text()[-2000:])

    print(f"Built {out} — {total:.1f}s, {W}x{H}, "
          f"{'music bed' if music else 'SILENT'}"
          f"{', hook burned in' if args.hook else ''}"
          f"{', swipe transition' if swipe else ''}")
    if not music:
        print("WARNING: no music found (none passed, nothing in "
              f"{MUSIC_DIR}). The v2 brand standard says never ship silent.")
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
    p.add_argument("--label-before", default="BEFORE", help="Chip text for the first beat")
    p.add_argument("--label-after", default="AFTER", help="Chip text for the second beat")
    p.add_argument("--hook", help="Hook line burned in for the first 1.5s (max ~7 words)")
    p.add_argument("--transition", choices=["swipe", "cut"], default="swipe",
                   help="Before->after transition (swipe = ffmpeg wipeleft, default)")
    p.add_argument("--beat", type=float, default=4.0, help="Seconds per before/after beat")
    p.add_argument("--cta", type=float, default=2.5, help="Seconds for the CTA card")
    build(p.parse_args())


if __name__ == "__main__":
    main()
