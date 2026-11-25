#!/usr/bin/env python3
"""Resize and compress selected job photos. Originals stay in source-assets/."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source-assets"
OUT = ROOT / "assets" / "img"
MAX_SIDE = 1800
MAX_BYTES = 290_000


def prepare(path: Path, max_side=MAX_SIDE) -> Image.Image:
    im = ImageOps.exif_transpose(Image.open(path))
    im = im.convert("RGB")
    w, h = im.size
    scale = max_side / max(w, h)
    if scale < 1:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
    return im


def save_webp(im: Image.Image, path: Path, max_bytes=MAX_BYTES) -> tuple[int, tuple[int, int], int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    working = im
    for _ in range(4):
        for q in (78, 70, 62, 54, 46):
            buf = io.BytesIO()
            working.save(buf, format="WEBP", quality=q, method=6)
            if buf.tell() <= max_bytes:
                path.write_bytes(buf.getvalue())
                return buf.tell(), working.size, q
        w, h = working.size
        working = working.resize((max(1, int(w * 0.85)), max(1, int(h * 0.85))), Image.Resampling.LANCZOS)
    path.write_bytes(buf.getvalue())
    return path.stat().st_size, working.size, q


def split_horizontal(path: Path, trim=2):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    w, h = im.size
    mid = h // 2
    top = im.crop((0, 0, w, mid - trim))
    bot = im.crop((0, mid + trim, w, h))
    return top, bot


def cover(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.convert("RGB")
    scale = max(w / im.width, h / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def build_og():
    W, H = 1200, 630
    photo = cover(Image.open(OUT / "hero.webp").convert("RGB"), W, H)
    photo = ImageEnhance.Brightness(photo).enhance(0.62)
    photo = ImageEnhance.Color(photo).enhance(0.9)
    base = photo.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(W):
        if x < 560:
            a = 242
        else:
            a = max(30, int(242 - (x - 560) / 640 * 200))
        draw.line([(x, 0), (x, H)], fill=(7, 30, 51, a))
    base = Image.alpha_composite(base, overlay)
    icon = Image.open(ROOT / "assets" / "logo" / "icon-512.png").convert("RGBA")
    icon = icon.resize((168, 168), Image.Resampling.LANCZOS)
    base.alpha_composite(icon, (72, 150))
    text = ImageDraw.Draw(base)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/macos/Inter-Bold.ttf", 58)
    semi = ImageFont.truetype("/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf", 22)
    med = ImageFont.truetype("/usr/share/fonts/truetype/macos/Inter-Medium.ttf", 26)
    text.text((268, 168), "EAST FLORIDA", font=bold, fill=(255, 255, 255))
    text.text((268, 238), "PRESSURE WASHING", font=semi, fill=(126, 250, 255))
    text.rectangle((268, 292, 392, 296), fill=(47, 224, 240))
    text.text((268, 324), "Jacksonville, FL", font=med, fill=(232, 246, 250))
    text.text((268, 366), "(904) 240-8705", font=med, fill=(255, 255, 255))
    text.text((72, 540), "House · Roof · Driveway · Soft washing", font=semi, fill=(186, 230, 236))
    out = base.convert("RGB")
    dest = ROOT / "assets" / "og.jpg"
    out.save(dest, format="JPEG", quality=82, optimize=True)
    print(f"og {dest.stat().st_size} {out.size}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []

    def export(im, rel):
        size, dims, q = save_webp(im if im.mode == "RGB" else im.convert("RGB"), OUT / rel)
        report.append((rel, size, dims, q))
        print(f"{rel:40} {dims[0]}x{dims[1]} q={q} {size/1024:.0f}KB")

    # Hero and gallery singles.
    singles = {
        "hero.webp": SRC / "photos" / "photo15.jpg",
        "gallery/trailer.webp": SRC / "gbp" / "gbp01.jpg",
        "gallery/driveway-line.webp": SRC / "gbp" / "gbp02.jpg",
        "gallery/pavers-progress.webp": SRC / "gbp" / "gbp05.jpg",
        "gallery/metal-roof.webp": SRC / "gbp" / "gbp07.jpg",
        "gallery/fence.webp": SRC / "gbp" / "gbp08.jpg",
        "gallery/window.webp": SRC / "photos" / "photo01.jpg",
        "gallery/roof-equipment.webp": SRC / "photos" / "photo06.jpg",
        "gallery/driveway-house.webp": SRC / "photos" / "photo07.jpg",
        "gallery/paver-driveway.webp": SRC / "photos" / "photo09.jpg",
        "gallery/surface-cleaner.webp": SRC / "photos" / "photo12.jpg",
        "gallery/paver-steps.webp": SRC / "photos" / "photo13.jpg",
        "gallery/gray-house.webp": SRC / "photos" / "photo14.jpg",
    }
    for rel, path in singles.items():
        export(prepare(path), rel)

    # Stacked before/after composites, split on the midpoint.
    # gbp10 house: top before (darker roof, ladder), bottom after
    top, bot = split_horizontal(SRC / "gbp" / "gbp10.jpg")
    export(prepare_image(top), "ba/house-before.webp")
    export(prepare_image(bot), "ba/house-after.webp")

    # gbp09 roof: top before, bottom after
    top, bot = split_horizontal(SRC / "gbp" / "gbp09.jpg")
    export(prepare_image(top), "ba/roof-before.webp")
    export(prepare_image(bot), "ba/roof-after.webp")

    # gbp04 soffit: top before, bottom after
    top, bot = split_horizontal(SRC / "gbp" / "gbp04.jpg")
    export(prepare_image(top), "ba/soffit-before.webp")
    export(prepare_image(bot), "ba/soffit-after.webp")

    # gbp03 concrete: bottom is the stained wall (before), top is cleaned (after)
    top, bot = split_horizontal(SRC / "gbp" / "gbp03.jpg")
    export(prepare_image(bot), "ba/concrete-before.webp")
    export(prepare_image(top), "ba/concrete-after.webp")

    # Separate photo pairs.
    export(prepare(SRC / "photos" / "photo03.jpg"), "ba/brick-before.webp")
    export(prepare(SRC / "photos" / "photo02.jpg"), "ba/brick-after.webp")
    export(prepare(SRC / "photos" / "photo04.jpg"), "ba/foundation-before.webp")
    export(prepare(SRC / "photos" / "photo05.jpg"), "ba/foundation-after.webp")

    # photo08 is a stacked patio comparison with a "2026" title across the seam.
    # Crop that band out so the slider photos are the work itself.
    patio = ImageOps.exif_transpose(Image.open(SRC / "photos" / "photo08.jpg")).convert("RGB")
    pw, ph = patio.size
    mid = ph // 2
    before = patio.crop((0, 0, pw, mid - 52))
    after = patio.crop((0, mid + 52, pw, ph))
    export(prepare_image(before), "ba/patio-before.webp")
    export(prepare_image(after), "ba/patio-after.webp")
    export(prepare_image(after), "gallery/patio.webp")

    over = [r for r in report if r[1] > MAX_BYTES]
    if over:
        raise SystemExit(f"oversize: {over}")
    print(f"files {len(report)} total_kb {sum(r[1] for r in report)/1024:.0f}")
    build_og()


def prepare_image(im: Image.Image, max_side=MAX_SIDE) -> Image.Image:
    im = im.convert("RGB")
    w, h = im.size
    scale = max_side / max(w, h)
    if scale < 1:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.LANCZOS)
    return im


if __name__ == "__main__":
    main()
