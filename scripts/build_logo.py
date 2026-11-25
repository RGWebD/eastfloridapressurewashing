#!/usr/bin/env python3
"""Build outlined-path logo SVGs and raster PNGs for East Florida Pressure Washing.

Text is converted to glyph outlines (no live <text>). Every glyph is checked for
finite coordinates, a real drawn shape, and counters (holes) on letters that need them.
"""

from __future__ import annotations

import math
import re
import subprocess
import json
from pathlib import Path

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = ROOT / "assets" / "logo"
GEO = Path("/tmp/fl.json")
BOLD = Path("/usr/share/fonts/truetype/macos/Inter-Bold.ttf")
SEMI = Path("/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf")

NAVY = "#071E33"
NAVY_DEEP = "#041520"
AQUA = "#2FE0F0"
AQUA_DEEP = "#14B4C6"
GREEN = "#3DDC7C"
GREEN_DEEP = "#14924F"
INK = "#071E33"
WHITE = "#FFFFFF"
SUB_LIGHT = "#0B6E62"  # teal on white, checked for contrast
SUB_DARK = "#7EFAFF"

HOLE_LETTERS = set("ADOPR")
NUM_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][-+]?\d+)?")


def chaikin(pts, ratio=0.2):
    n = len(pts)
    out = []
    for i in range(n):
        p = pts[i]
        q = pts[(i + 1) % n]
        out.append((p[0] * (1 - ratio) + q[0] * ratio, p[1] * (1 - ratio) + q[1] * ratio))
        out.append((p[0] * ratio + q[0] * (1 - ratio), p[1] * ratio + q[1] * (1 - ratio)))
    return out


def florida_points():
    g = json.loads(GEO.read_text())
    raw = g["coordinates"][0]
    if raw[0] == raw[-1]:
        raw = raw[:-1]
    midlat = sum(p[1] for p in raw) / len(raw)
    cos = math.cos(math.radians(midlat))
    pts = [(lon * cos, -lat) for lon, lat in raw]
    # One smoothing pass keeps the panhandle, peninsula, and keys, and drops the jagged coast.
    pts = chaikin(pts, 0.18)
    minx = min(p[0] for p in pts)
    maxx = max(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    maxy = max(p[1] for p in pts)
    return pts, (minx, miny, maxx, maxy)


def fit_florida(box):
    """Map Florida into (x, y, w, h). Returns SVG path d and the fitted points."""
    pts, (minx, miny, maxx, maxy) = florida_points()
    x, y, w, h = box
    s = min(w / (maxx - minx), h / (maxy - miny))
    dw = w - (maxx - minx) * s
    dh = h - (maxy - miny) * s
    ox = x + dw / 2
    oy = y + dh / 2
    fitted = []
    for px, py in pts:
        fitted.append((ox + (px - minx) * s, oy + (py - miny) * s))
    d = path_from_points(fitted)
    return d, fitted


def path_from_points(pts):
    parts = [f"M{pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for x, y in pts[1:]:
        parts.append(f"L{x:.2f} {y:.2f}")
    parts.append("Z")
    return "".join(parts)


PATH_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def tokenize_path(d):
    return PATH_TOKEN.findall(d)


def parse_path(d):
    """Absolute SVG path parser. Extra pairs after M are implicit linetos."""
    tokens = tokenize_path(d)
    i = 0
    cmd = None
    segs = []
    while i < len(tokens):
        t = tokens[i]
        if re.fullmatch(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd.upper() == "Z":
                segs.append(("Z", []))
                cmd = None
                continue
        if cmd is None:
            raise SystemExit(f"path started without a command: {d[:80]}")
        if cmd.islower():
            raise SystemExit(f"relative path command {cmd} is not expected")
        n = PATH_ARITY[cmd.upper()]
        if i + n > len(tokens):
            raise SystemExit(f"short path data for {cmd}: {d[:80]}")
        vals = []
        for _ in range(n):
            if re.fullmatch(r"[A-Za-z]", tokens[i]):
                raise SystemExit(f"missing numbers for {cmd}")
            vals.append(float(tokens[i]))
            i += 1
        if any(not math.isfinite(v) for v in vals):
            raise SystemExit("non-finite path coordinate")
        segs.append((cmd, vals))
        if cmd == "M":
            cmd = "L"
    return segs


def emit_path(segs):
    parts = []
    for cmd, vals in segs:
        if cmd == "Z":
            parts.append("Z")
        else:
            nums = " ".join(_fmt(v) for v in vals)
            parts.append(cmd + nums)
    return "".join(parts)


def _fmt(v):
    if not math.isfinite(v):
        raise SystemExit("non-finite coordinate while emitting path")
    s = f"{v:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0",):
        s = "0"
    return s


def subpath_count(d):
    return sum(1 for cmd, _ in parse_path(d) if cmd == "M")


def droplet_path(cx, cy, scale):
    """Teardrop with the tip up. Local origin is the visual center of the body."""
    raw = (
        "M0 -48"
        "C2 -40 16 -22 22 -6"
        "C30 14 22 36 0 44"
        "C-22 36 -30 14 -22 -6"
        "C-16 -22 -2 -40 0 -48Z"
    )
    segs = []
    for cmd, vals in parse_path(raw):
        if cmd == "Z":
            segs.append(("Z", []))
            continue
        mapped = []
        # Pairwise x,y except we only use C and M here.
        if len(vals) % 2 != 0:
            raise SystemExit("droplet path has an odd coordinate")
        for k in range(0, len(vals), 2):
            mapped.append(vals[k] * scale + cx)
            mapped.append(vals[k + 1] * scale + cy)
        segs.append((cmd, mapped))
    return emit_path(segs)


def sanitize_path(d: str) -> str:
    def repl(m):
        v = float(m.group(0))
        if not math.isfinite(v):
            raise SystemExit(f"non-finite coordinate in path: {m.group(0)}")
        s = f"{v:.2f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if s in ("-0", "-0.0"):
            s = "0"
        return s

    cleaned = NUM_RE.sub(repl, d)
    if "nan" in cleaned.lower() or "inf" in cleaned.lower():
        raise SystemExit("NaN/Inf survived sanitizing")
    return cleaned


def glyph_path(font, glyph_name, transform):
    gs = font.getGlyphSet()
    svg = SVGPathPen(gs)
    pen = TransformPen(svg, transform)
    gs[glyph_name].draw(pen)
    d = svg.getCommands()
    if not d or not d.strip():
        raise SystemExit(f"empty outline for {glyph_name}")
    return sanitize_path(d)


def glyph_bounds(font, glyph_name, transform):
    gs = font.getGlyphSet()
    bp = BoundsPen(gs)
    pen = TransformPen(bp, transform)
    gs[glyph_name].draw(pen)
    if bp.bounds is None:
        raise SystemExit(f"no bounds for {glyph_name}")
    return bp.bounds


def load_font(path):
    font = TTFont(str(path))
    cmap = font.getBestCmap()
    upem = font["head"].unitsPerEm
    cap = font["OS/2"].sCapHeight or int(upem * 0.7)
    return font, cmap, upem, cap


def layout_line(font_path, text, size, tracking_em, fill, id_prefix):
    font, cmap, upem, cap = load_font(font_path)
    scale = size / upem
    tracking = tracking_em * size
    glyphs = []
    x = 0.0
    for index, ch in enumerate(text):
        if ch == " ":
            # Use the space advance so word spacing stays typographic.
            name = cmap.get(ord(" "))
            adv = font.getGlyphSet()[name].width * scale if name else size * 0.33
            x += adv + tracking
            continue
        name = cmap.get(ord(ch))
        if not name:
            raise SystemExit(f"missing glyph for {ch!r}")
        adv = font.getGlyphSet()[name].width * scale
        # Baseline at y=0, y grows down. Font y grows up, so scaleY is negative
        # and we translate by the baseline later. Here baseline is 0.
        transform = Transform(scale, 0, 0, -scale, x, 0)
        d = glyph_path(font, name, transform)
        xmin, ymin, xmax, ymax = glyph_bounds(font, name, transform)
        width = xmax - xmin
        height = ymax - ymin
        if width < size * (0.08 if ch == "I" else 0.18):
            raise SystemExit(f"{ch} width looks broken: {width:.2f} at size {size}")
        if height < size * 0.45:
            raise SystemExit(f"{ch} height looks broken: {height:.2f} at size {size}")
        m_count = subpath_count(d)
        if ch in HOLE_LETTERS and m_count < 2:
            raise SystemExit(f"{ch} is missing its counter (subpaths={m_count})")
        if m_count < 1:
            raise SystemExit(f"{ch} has no subpath")
        glyphs.append(
            {
                "ch": ch,
                "id": f"{id_prefix}-{ch}-{index}",
                "d": d,
                "fill": fill,
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
            }
        )
        x += adv + tracking
    if not glyphs:
        raise SystemExit("no glyphs")
    minx = min(g["xmin"] for g in glyphs)
    miny = min(g["ymin"] for g in glyphs)
    maxx = max(g["xmax"] for g in glyphs)
    maxy = max(g["ymax"] for g in glyphs)
    return glyphs, (minx, miny, maxx, maxy), x


def shift_glyphs(glyphs, dx, dy):
    out = []
    for g in glyphs:
        d = translate_path(g["d"], dx, dy)
        ng = dict(g)
        ng["d"] = d
        ng["xmin"] += dx
        ng["xmax"] += dx
        ng["ymin"] += dy
        ng["ymax"] += dy
        out.append(ng)
    return out


def translate_path(d, dx, dy):
    segs = []
    for cmd, vals in parse_path(d):
        if cmd == "Z":
            segs.append(("Z", []))
            continue
        u = cmd.upper()
        mapped = list(vals)
        if u in ("M", "L", "T", "Q", "C", "S"):
            for k in range(0, len(mapped), 2):
                mapped[k] += dx
                mapped[k + 1] += dy
        elif u == "H":
            mapped[0] += dx
        elif u == "V":
            mapped[0] += dy
        elif u == "A":
            mapped[5] += dx
            mapped[6] += dy
        else:
            raise SystemExit(f"cannot translate {cmd}")
        segs.append((cmd, mapped))
    return emit_path(segs)


def badge_defs():
    return f"""
  <defs>
    <radialGradient id="badgeBg" cx="38%" cy="28%" r="75%">
      <stop offset="0%" stop-color="#123A56"/>
      <stop offset="58%" stop-color="{NAVY}"/>
      <stop offset="100%" stop-color="{NAVY_DEEP}"/>
    </radialGradient>
    <linearGradient id="flFill" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#5BE892"/>
      <stop offset="55%" stop-color="{GREEN}"/>
      <stop offset="100%" stop-color="{GREEN_DEEP}"/>
    </linearGradient>
    <linearGradient id="dropFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#F4FEFF"/>
      <stop offset="42%" stop-color="#7EF3FF"/>
      <stop offset="100%" stop-color="#0E9AAB"/>
    </linearGradient>
    <linearGradient id="dropFill2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#E9FDFF"/>
      <stop offset="100%" stop-color="#18C3D4"/>
    </linearGradient>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1.2" stdDeviation="1.2" flood-color="#04202C" flood-opacity="0.28"/>
    </filter>
  </defs>"""


def badge_body(vb=512):
    """Inner mark. viewBox is 0 0 vb vb. Ids are unprefixed; callers wrap unique ids if needed."""
    # Florida sits right-of-center so the Gulf (lower left) stays open for the spray.
    fl_d, fl_pts = fit_florida((118, 96, 318, 318))
    # Droplets live in the Gulf negative space, kissing the west coast.
    drops = [
        (168, 318, 1.22, "dropFill"),
        (124, 262, 0.62, "dropFill2"),
        (206, 246, 0.40, "dropFill2"),
        (108, 338, 0.28, "dropFill2"),
    ]
    dots = [(150, 214, 7), (98, 292, 5), (214, 292, 4.5), (132, 372, 4)]
    drop_markup = []
    for i, (cx, cy, sc, fill) in enumerate(drops):
        d = droplet_path(cx, cy, sc)
        drop_markup.append(f'<path id="droplet-{i}" fill="url(#{fill})" d="{d}"/>')
        # Specular highlight, a small tilted ellipse near the upper-left of the body.
        hx = cx - 7 * sc
        hy = cy - 6 * sc
        drop_markup.append(
            f'<ellipse id="highlight-{i}" cx="{hx:.2f}" cy="{hy:.2f}" rx="{7.5 * sc:.2f}" ry="{11 * sc:.2f}" '
            f'transform="rotate(-28 {hx:.2f} {hy:.2f})" fill="#FFFFFF" opacity="0.88"/>'
        )
    dot_markup = []
    for i, (cx, cy, r) in enumerate(dots):
        dot_markup.append(f'<circle id="spray-{i}" cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{AQUA}"/>')
    c = vb / 2
    return f"""
  <circle cx="{c}" cy="{c}" r="{c - 8}" fill="url(#badgeBg)"/>
  <circle cx="{c}" cy="{c}" r="{c - 14}" fill="none" stroke="{AQUA}" stroke-width="7" opacity="0.95"/>
  <circle cx="{c}" cy="{c}" r="{c - 28}" fill="none" stroke="{AQUA}" stroke-width="1.5" opacity="0.35"/>
  <path id="florida" d="{fl_d}" fill="url(#flFill)" stroke="{GREEN_DEEP}" stroke-width="6" stroke-linejoin="round"/>
  <g id="spray" filter="url(#soft)">
    {''.join(drop_markup)}
    {''.join(dot_markup)}
  </g>
"""


def svg_doc(body, viewbox, title, desc, width=None, height=None):
    w_attr = f' width="{width}"' if width else ""
    h_attr = f' height="{height}"' if height else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}"{w_attr}{h_attr} role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{desc}</desc>
{body}
</svg>
'''


def glyphs_to_svg(glyphs):
    parts = []
    for g in glyphs:
        parts.append(
            f'<path id="{g["id"]}" data-letter="{g["ch"]}" fill="{g["fill"]}" fill-rule="evenodd" d="{g["d"]}"/>'
        )
    return "\n    ".join(parts)


def build_wordmark(fill_main, fill_sub, main_size=78, sub_size=18):
    main, mb, _ = layout_line(BOLD, "EAST FLORIDA", main_size, -0.02, fill_main, "main")
    sub, sb, _ = layout_line(SEMI, "PRESSURE WASHING", sub_size, 0.22, fill_sub, "sub")
    # Normalize each line so its left edge is 0 and cap-top is 0.
    main = shift_glyphs(main, -mb[0], -mb[1])
    sub = shift_glyphs(sub, -sb[0], -sb[1])
    main_w = max(g["xmax"] for g in main) - min(g["xmin"] for g in main)
    main_h = max(g["ymax"] for g in main) - min(g["ymin"] for g in main)
    sub_w = max(g["xmax"] for g in sub) - min(g["xmin"] for g in sub)
    sub_h = max(g["ymax"] for g in sub) - min(g["ymin"] for g in sub)
    # Center the shorter line under/over the wider one. Main is wider.
    block_w = max(main_w, sub_w)
    gap = main_size * 0.16
    rule_h = max(2.0, main_size * 0.035)
    sub_dx = (block_w - sub_w) / 2
    sub = shift_glyphs(sub, sub_dx, main_h + gap + rule_h + gap)
    rule = {
        "x": (block_w - sub_w * 0.42) / 2,
        "y": main_h + gap,
        "w": sub_w * 0.42,
        "h": rule_h,
    }
    block_h = main_h + gap + rule_h + gap + sub_h
    return main, sub, rule, block_w, block_h


def compose_horizontal(theme):
    if theme == "light":
        fill, subfill, bg = INK, SUB_LIGHT, None
    else:
        fill, subfill, bg = WHITE, SUB_DARK, None
    main, sub, rule, tw, th = build_wordmark(fill, subfill, 84, 18.5)
    badge = 168
    gap = 28
    pad_x = 8
    pad_y = 10
    # Vertically center the badge against the wordmark.
    height = max(badge, th) + pad_y * 2
    width = pad_x + badge + gap + tw + pad_x
    badge_y = (height - badge) / 2
    text_y = (height - th) / 2
    text_x = pad_x + badge + gap
    main = shift_glyphs(main, text_x, text_y)
    sub = shift_glyphs(sub, text_x, text_y)
    rule_x = text_x + rule["x"]
    rule_y = text_y + rule["y"]
    # Scale badge group from 512 space into `badge` px.
    s = badge / 512
    body = f"""
  <g id="badge" transform="translate({pad_x:.2f} {badge_y:.2f}) scale({s:.6f})">
    {badge_defs()}
    {badge_body()}
  </g>
  <g id="wordmark" fill-rule="evenodd">
    {glyphs_to_svg(main)}
    <rect id="rule" x="{rule_x:.2f}" y="{rule_y:.2f}" width="{rule['w']:.2f}" height="{rule['h']:.2f}" rx="{rule['h']/2:.2f}" fill="{subfill}"/>
    {glyphs_to_svg(sub)}
  </g>
"""
    title = "East Florida Pressure Washing"
    desc = f"Horizontal logo lockup for {theme} backgrounds. Lettering is outlined, not live text."
    return svg_doc(body, f"0 0 {width:.2f} {height:.2f}", title, desc), width, height


def compose_stacked(theme):
    if theme == "light":
        fill, subfill = INK, SUB_LIGHT
    else:
        fill, subfill = WHITE, SUB_DARK
    main, sub, rule, tw, th = build_wordmark(fill, subfill, 78, 17)
    badge = 300
    gap = 28
    pad = 16
    width = max(badge, tw) + pad * 2
    height = pad + badge + gap + th + pad
    badge_x = (width - badge) / 2
    text_x = (width - tw) / 2
    text_y = pad + badge + gap
    main = shift_glyphs(main, text_x, text_y)
    sub = shift_glyphs(sub, text_x, text_y)
    rule_x = text_x + rule["x"]
    rule_y = text_y + rule["y"]
    s = badge / 512
    body = f"""
  <g id="badge" transform="translate({badge_x:.2f} {pad:.2f}) scale({s:.6f})">
    {badge_defs()}
    {badge_body()}
  </g>
  <g id="wordmark" fill-rule="evenodd">
    {glyphs_to_svg(main)}
    <rect id="rule" x="{rule_x:.2f}" y="{rule_y:.2f}" width="{rule['w']:.2f}" height="{rule['h']:.2f}" rx="{rule['h']/2:.2f}" fill="{subfill}"/>
    {glyphs_to_svg(sub)}
  </g>
"""
    title = "East Florida Pressure Washing"
    desc = f"Stacked logo lockup for {theme} backgrounds. Lettering is outlined, not live text."
    return svg_doc(body, f"0 0 {width:.2f} {height:.2f}", title, desc), width, height


def badge_svg():
    body = badge_defs() + badge_body()
    return svg_doc(
        body,
        "0 0 512 512",
        "East Florida Pressure Washing mark",
        "Circular badge with a green Florida silhouette and an aqua water-spray motif.",
    )


def rasterize(svg_text, png_path, w, h, background=None):
    """Render an SVG to PNG with headless Chrome. background '#hex' or None for transparent."""
    html_path = Path("/tmp/efpw-raster.html")
    bg = "transparent" if background is None else background
    html_path.write_text(
        f"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:{bg};overflow:hidden;width:{w}px;height:{h}px}}
svg{{display:block;width:{w}px;height:{h}px}}
</style></head><body>{svg_text}</body></html>""",
        encoding="utf-8",
    )
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "timeout", "30",
        "google-chrome",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--screenshot={png_path}",
        f"--window-size={w},{h}",
        "--default-background-color=00000000",
        html_path.as_uri(),
    ]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not png_path.exists():
        raise SystemExit(f"Chrome did not write {png_path}")
    im = Image.open(png_path)
    if im.size != (w, h):
        im = im.resize((w, h), Image.Resampling.LANCZOS)
        im.save(png_path)
    return im


def assert_png(im, label, min_coverage=0.02):
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    alpha = im.getchannel("A")
    hist = alpha.histogram()
    opaque = sum(hist[16:])
    coverage = opaque / (im.size[0] * im.size[1])
    if coverage < min_coverage:
        raise SystemExit(f"{label} looks blank (coverage {coverage:.3f})")
    return coverage


def qa_svg_text(svg_text, expected_phrase):
    """Confirm every letter of the phrase exists as a complete outline."""
    letters = [ch for ch in expected_phrase if ch != " "]
    ids = re.findall(r'data-letter="([A-Z])"', svg_text)
    # Wordmark letters only (florida path has no data-letter).
    if ids != letters and ids != letters + letters:
        # horizontal/stacked have one wordmark. If mismatch, show what we got.
        if "".join(ids) != "".join(letters):
            raise SystemExit(f"glyph sequence mismatch\n expected {''.join(letters)}\n got      {''.join(ids)}")
    if "NaN" in svg_text or "nan" in svg_text or "Infinity" in svg_text:
        raise SystemExit("NaN/Infinity found in SVG")
    # Every data-letter path must contain a draw command and finite numbers.
    for m in re.finditer(r'<path id="([^"]+)" data-letter="([A-Z])"[^>]*d="([^"]+)"', svg_text):
        pid, letter, d = m.group(1), m.group(2), m.group(3)
        if len(d) < 20:
            raise SystemExit(f"{pid} path too short")
        nums = [float(n) for n in NUM_RE.findall(d)]
        if not nums or any(not math.isfinite(n) for n in nums):
            raise SystemExit(f"{pid} has a bad coordinate")
        if letter in HOLE_LETTERS and subpath_count(d) < 2:
            raise SystemExit(f"{pid} counter missing")


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    qa_svg_text(text, "EAST FLORIDAPRESSURE WASHING") if "data-letter" in text else None
    if "NaN" in text or "Infinity" in text:
        raise SystemExit(f"bad number in {path}")


def main():
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    badge = badge_svg()
    write(LOGO_DIR / "badge.svg", badge)

    h_light, hw, hh = compose_horizontal("light")
    h_dark, _, _ = compose_horizontal("dark")
    s_light, sw, sh = compose_stacked("light")
    s_dark, _, _ = compose_stacked("dark")
    write(LOGO_DIR / "lockup-horizontal-light.svg", h_light)
    write(LOGO_DIR / "lockup-horizontal-dark.svg", h_dark)
    write(LOGO_DIR / "lockup-stacked-light.svg", s_light)
    write(LOGO_DIR / "lockup-stacked-dark.svg", s_dark)

    # Raster primary assets.
    icon = rasterize(badge, LOGO_DIR / "icon-512.png", 512, 512)
    assert_png(icon, "icon-512")
    # logo 1024: horizontal lockup, width 1024, proportional height.
    logo_h = max(1, round(1024 * hh / hw))
    logo = rasterize(h_light, ROOT / "assets" / "logo" / "logo-1024.png", 1024, logo_h)
    assert_png(logo, "logo-1024")

    fav = rasterize(badge, ROOT / "favicon-32.png", 32, 32)
    assert_png(fav, "favicon", min_coverage=0.05)
    # Apple touch: opaque navy field, badge inset so iOS corner mask still shows the ring.
    apple_svg = svg_doc(
        f'<rect width="180" height="180" fill="{NAVY}"/>'
        + f'<g transform="translate(6 6) scale({168/512:.6f})">'
        + badge_defs()
        + badge_body()
        + "</g>",
        "0 0 180 180",
        "East Florida Pressure Washing",
        "Apple touch icon",
        180,
        180,
    )
    apple = rasterize(apple_svg, ROOT / "apple-touch-icon.png", 180, 180, background=NAVY)
    assert_png(apple, "apple-touch", min_coverage=0.5)

    # QA sheet: each letter large, on white, plus full words.
    qa_glyphs = []
    line, bounds, _ = layout_line(BOLD, "EAST FLORIDA", 140, 0.01, INK, "qa")
    line2, bounds2, _ = layout_line(SEMI, "PRESSURE WASHING", 90, 0.08, INK, "qa2")
    line = shift_glyphs(line, 20 - bounds[0], 30 - bounds[1])
    y2 = 30 - bounds[1] + (bounds[3] - bounds[1]) + 40
    line2 = shift_glyphs(line2, 20 - bounds2[0], y2 - bounds2[1])
    maxx = max(max(g["xmax"] for g in line), max(g["xmax"] for g in line2)) + 20
    maxy = max(g["ymax"] for g in line2) + 30
    qa_svg = svg_doc(
        f'<rect width="100%" height="100%" fill="#FFFFFF"/>{glyphs_to_svg(line)}{glyphs_to_svg(line2)}',
        f"0 0 {maxx:.0f} {maxy:.0f}",
        "Glyph QA",
        "Outlined letters for visual inspection",
    )
    write(Path("/tmp/glyph-qa.svg"), qa_svg)
    qa_w = min(1600, int(maxx))
    qa_h = max(1, round(qa_w * maxy / maxx))
    rasterize(qa_svg, "/tmp/glyph-qa.png", qa_w, qa_h, background="#FFFFFF")

    # Dark word QA
    dline, db, _ = layout_line(BOLD, "EAST FLORIDA", 140, 0.01, WHITE, "qad")
    dline2, db2, _ = layout_line(SEMI, "PRESSURE WASHING", 90, 0.08, SUB_DARK, "qad2")
    dline = shift_glyphs(dline, 20 - db[0], 30 - db[1])
    y2 = 30 - db[1] + (db[3] - db[1]) + 40
    dline2 = shift_glyphs(dline2, 20 - db2[0], y2 - db2[1])
    qa_dark = svg_doc(
        f'<rect width="100%" height="100%" fill="{NAVY}"/>{glyphs_to_svg(dline)}{glyphs_to_svg(dline2)}',
        f"0 0 {maxx:.0f} {maxy:.0f}",
        "Glyph QA dark",
        "Outlined letters on navy",
    )
    rasterize(qa_dark, "/tmp/glyph-qa-dark.png", qa_w, qa_h, background=NAVY)

    # Badge preview and a scaled-up favicon for inspection.
    rasterize(badge, "/tmp/badge-preview.png", 640, 640)
    big_fav = Image.open(ROOT / "favicon-32.png").resize((256, 256), Image.Resampling.NEAREST)
    big_fav.save("/tmp/favicon-nearest.png")

    print("badge", "ok")
    print(f"horizontal {hw:.1f}x{hh:.1f}")
    print(f"stacked {sw:.1f}x{sh:.1f}")
    print("wrote", LOGO_DIR)


if __name__ == "__main__":
    main()
