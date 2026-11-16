"""Render the loading animations in assets/loading/, one is picked at random
per loading message:

- slice: the logo's cucumber slice read by a scanning arc and circuit pulses
- plate: a scan line sweeps a plate and brackets lock onto each portion
- rings: protein, carbs and fat rings fill around the logo's leaf
- bowl: ingredients drop into a bowl, then a sparkle marks it read

Each is a seamless 2.4 s loop of flat vector art drawn at 2x, downsampled.

    uv run --with pillow --with imageio-ffmpeg \
        python scripts/make_loading_animation.py [name]
"""

import math
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

W, H = 960, 540
SS = 2  # supersampling
FPS = 30
FRAMES = 72  # 2.4 s
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "loading"

BG = (247, 249, 242)
TRACK = (228, 234, 219)
RIND = (31, 90, 42)
RIND_EDGE = (62, 142, 58)
FLESH = (214, 236, 172)
CORE = (238, 247, 214)
SEED = (250, 252, 240)
SEED_EDGE = (176, 210, 120)
SCAN = (109, 179, 63)
NODE = (62, 142, 58)
PULSE = (140, 198, 63)
MACROS = ((47, 125, 50), (242, 181, 68), (63, 176, 160))  # protein, carbs, fat

CX, CY, R = 480, 236, 112


def ease_out(x: float) -> float:
    # Matches cubic-bezier(.23,1,.32,1) closely enough for a loop.
    return 1 - (1 - x) ** 4


def ease_io(x: float) -> float:
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def s(*v: float) -> list[float]:
    return [c * SS for c in v]


def mix(colour, target, k: float) -> tuple[int, ...]:
    return tuple(round(a + (b - a) * k) for a, b in zip(colour, target, strict=True))


def blob(img, cx, cy, w, h, angle, fill, outline=None, edge=2) -> None:
    """A rotated ellipse (seed, leaf, grain) pasted at (cx, cy)."""
    layer = Image.new("RGBA", (int((w + 4) * SS), int((h + 4) * SS)), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        s(2, 2, w + 2, h + 2), fill=fill, outline=outline, width=edge * SS
    )
    layer = layer.rotate(-angle, expand=True, resample=Image.BICUBIC)
    img.paste(
        layer, (int(cx * SS - layer.width / 2), int(cy * SS - layer.height / 2)), layer
    )


def ring(d: ImageDraw.ImageDraw, r: float, fill) -> None:
    d.ellipse(s(CX - r, CY - r, CX + r, CY + r), fill=fill)


def arc(d, r, start, end, colour, width, cx=CX, cy=CY) -> None:
    # PIL strokes inward from the box; pad it so the stroke centres on r.
    o = r + width / 2
    d.arc(s(cx - o, cy - o, cx + o, cy + o), start, end, fill=colour, width=width * SS)
    for a in (start, end):  # round caps
        x = cx + r * math.cos(math.radians(a))
        y = cy + r * math.sin(math.radians(a))
        hw = width / 2
        d.ellipse(s(x - hw, y - hw, x + hw, y + hw), fill=colour)


# Circuit traces from the logo: out from the slice, a 45° bend, a node.
TRACES = []
for side in (-1, 1):
    for dy, bend in ((-58, -1), (0, 0), (58, 1)):
        x0 = CX + side * (R + 46)
        y0 = CY + dy * 0.9
        x1 = x0 + side * 70
        x2 = x1 + side * 38
        y2 = y0 + bend * 38
        TRACES.append([(x0, y0), (x1, y0), (x2, y2), (x2 + side * 46, y2)])


def point_on(path, f):
    segs = list(zip(path, path[1:], strict=False))
    lengths = [math.dist(a, b) for a, b in segs]
    target = f * sum(lengths)
    for (a, b), length in zip(segs, lengths, strict=True):
        if target <= length:
            k = target / length
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        target -= length
    return path[-1]


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W * SS, H * SS), BG)
    return img, ImageDraw.Draw(img)


def slice_frame(t: float) -> Image.Image:
    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)

    # Traces and their end nodes; a node lights while its pulse lands.
    for i, path in enumerate(TRACES):
        d.line(
            [c for p in path for c in s(*p)], fill=TRACK, width=4 * SS, joint="curve"
        )
        ex, ey = path[-1]
        lit = 0.82 <= (t + i * 0.37) % 1.0 < 0.97
        d.ellipse(s(ex - 7, ey - 7, ex + 7, ey + 7), fill=NODE)
        d.ellipse(s(ex - 3, ey - 3, ex + 3, ey + 3), fill=PULSE if lit else BG)

    # Pulses: one per trace, staggered, one trip per loop (seamless).
    for i, path in enumerate(TRACES):
        f = (t + i * 0.37) % 1.0
        if f > 0.82:
            continue  # absorbed into the node; reappears at the slice
        px, py = point_on(path, ease_io(f / 0.82))
        d.ellipse(s(px - 5, py - 5, px + 5, py + 5), fill=PULSE)

    # The slice: rind, flesh, core, rotating seed ring (8-fold, 45° per loop).
    ring(d, R, RIND)
    ring(d, R - 9, RIND_EDGE)
    ring(d, R - 13, FLESH)
    ring(d, R * 0.62, CORE)
    spin = 45 * t
    for k in range(8):
        a = math.radians(spin + k * 45)
        sx, sy = CX + 44 * math.cos(a), CY + 44 * math.sin(a)
        blob(img, sx, sy, 36, 20, math.degrees(a), SEED, SEED_EDGE)
    d = ImageDraw.Draw(img)

    # Scanning arc: head races, tail catches up; base turns 420° so it loops.
    base = 420 * t - 90
    head = base + 300 * ease_io(clamp(2 * t))
    tail = base + 300 * ease_io(clamp(2 * t - 1))
    arc(d, R + 22, tail - 14, head, SCAN, 7)

    # Macro bar: segments fill in turn, hold, then fade back to the track.
    bx, by, bw, bh = CX - 150, 432, 300, 12
    d.rounded_rectangle(s(bx, by, bx + bw, by + bh), radius=6 * SS, fill=TRACK)
    shares = (0.3, 0.45, 0.25)
    fade = ease_io(clamp((t - 0.82) / 0.18))
    x = bx
    for i, (share, colour) in enumerate(zip(shares, MACROS, strict=True)):
        grow = ease_out(clamp((t - 0.08 - i * 0.18) / 0.3))
        seg = bw * share * grow
        if seg > 1:
            c = mix(colour, TRACK, fade)
            d.rounded_rectangle(s(x, by, x + seg, by + bh), radius=6 * SS, fill=c)
        x += bw * share

    return img.resize((W, H), Image.LANCZOS)


# --- plate: scan line + detection brackets ----------------------------------

PX, PY, PR = 480, 262, 168
RICE = (243, 228, 186)
RICE_GRAIN = (252, 246, 226)
DAL = (233, 162, 59)
DAL_TOP = (244, 196, 98)
KATORI = (208, 212, 200)
GREENS = ((109, 179, 63), (62, 142, 58), (140, 198, 63))
# (centre x, centre y, half width, half height) of each portion's bracket box.
PORTIONS = ((424, 218, 54, 48), (552, 226, 48, 48), (474, 322, 64, 38))


def scan_x(t: float) -> float:
    """Left to right in the first half, back in the second (seamless)."""
    k = ease_io(t / 0.5) if t < 0.5 else 1 - ease_io((t - 0.5) / 0.5)
    return PX - PR * 0.92 + 2 * PR * 0.92 * k


# When the outbound sweep first crosses each portion, so its bracket locks then.
LOCK_AT = [
    next(i / 1000 for i in range(500) if scan_x(i / 1000) >= cx) for cx, *_ in PORTIONS
]


def brackets(d, cx, cy, hw, hh, colour, arm=16, width=4) -> None:
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * hw, cy + sy * hh
            d.line(s(x, y, x - sx * arm, y), fill=colour, width=width * SS)
            d.line(s(x, y, x, y - sy * arm), fill=colour, width=width * SS)


def plate_frame(t: float) -> Image.Image:
    img, d = canvas()
    d.ellipse(s(PX - PR, PY - PR + 8, PX + PR, PY + PR + 8), fill=TRACK)  # shadow
    d.ellipse(s(PX - PR, PY - PR, PX + PR, PY + PR), fill=(255, 255, 255))
    d.ellipse(
        s(PX - PR + 26, PY - PR + 26, PX + PR - 26, PY + PR - 26),
        outline=TRACK,
        width=2 * SS,
    )

    # Rice mound with grains.
    for dx, dy, r in ((-22, 6, 36), (18, 10, 34), (0, -14, 38), (-4, 20, 30)):
        d.ellipse(s(424 + dx - r, 218 + dy - r, 424 + dx + r, 218 + dy + r), fill=RICE)
    for k in range(14):
        a = k * 2.4
        rr = 10 + (k * 7) % 30
        blob(
            img,
            424 + rr * math.cos(a),
            220 + rr * math.sin(a) * 0.8,
            12,
            5,
            k * 47,
            RICE_GRAIN,
        )
    d = ImageDraw.Draw(img)
    # Dal in a katori.
    d.ellipse(s(548 - 46, 226 - 46, 548 + 46, 226 + 46), fill=KATORI)
    d.ellipse(s(548 - 38, 226 - 38, 548 + 38, 226 + 38), fill=DAL)
    d.ellipse(s(548 - 24, 226 - 28, 548 + 14, 226 + 4), fill=DAL_TOP)
    # Greens: overlapping leaves.
    for k, (dx, dy, ang) in enumerate(
        (
            (-40, 4, 20),
            (-14, -8, -30),
            (12, 6, 40),
            (38, -4, -15),
            (0, 14, 80),
            (-26, 16, -60),
            (26, 18, 10),
        )
    ):
        blob(img, 474 + dx, 322 + dy, 40, 22, ang, GREENS[k % 3])
    d = ImageDraw.Draw(img)

    # Scan line, clipped to the plate, with a soft trailing band.
    x = scan_x(t)
    half = math.sqrt(max(0.0, PR**2 - (x - PX) ** 2)) - 6
    d.line(s(x, PY - half, x, PY + half), fill=(226, 240, 208), width=16 * SS)
    d.line(s(x, PY - half, x, PY + half), fill=SCAN, width=3 * SS)

    # Brackets lock on as the sweep passes, then fade before the loop restarts.
    fade = ease_io(clamp((t - 0.84) / 0.14))
    for (cx, cy, hw, hh), at in zip(PORTIONS, LOCK_AT, strict=True):
        p = ease_out(clamp((t - at) / 0.14))
        if p <= 0:
            continue
        grow = (1 - p) * 14
        colour = mix(mix((255, 255, 255), SCAN, p), (255, 255, 255), fade)
        brackets(d, cx, cy, hw + grow, hh + grow, colour)
    return img.resize((W, H), Image.LANCZOS)


# --- rings: macro rings around the leaf -------------------------------------

RX, RY = 480, 262
RINGS = ((134, 0.78), (104, 0.62), (74, 0.86))  # radius, share filled
LEAF = (109, 179, 63)
LEAF_RIB = (62, 142, 58)


def rings_frame(t: float) -> Image.Image:
    img, d = canvas()
    shrink = ease_io(clamp((t - 0.78) / 0.2))
    for i, ((r, share), colour) in enumerate(zip(RINGS, MACROS, strict=True)):
        o = r + 9
        d.ellipse(s(RX - o, RY - o, RX + o, RY + o), outline=TRACK, width=18 * SS)
        v = share * ease_out(clamp((t - 0.04 - i * 0.1) / 0.45)) * (1 - shrink)
        if v > 0.005:
            arc(d, r, -90, -90 + 360 * v, colour, 18, RX, RY)

    # Two leaves from the logo, swaying gently (one cycle per loop).
    sway = 6 * math.sin(2 * math.pi * t)
    for lx, ly, w, h, ang in ((466, 272, 84, 38, -50), (500, 244, 58, 28, -10)):
        a = ang + sway
        blob(img, lx, ly, w, h, a, LEAF)
        d = ImageDraw.Draw(img)
        dx = math.cos(math.radians(a)) * w * 0.4
        dy = math.sin(math.radians(a)) * w * 0.4
        d.line(s(lx - dx, ly - dy, lx + dx, ly + dy), fill=LEAF_RIB, width=2 * SS)
    return img.resize((W, H), Image.LANCZOS)


# --- bowl: ingredients drop in ----------------------------------------------

BX, BRIM, BHW = 480, 318, 176
BOWL = (31, 90, 42)
BOWL_IN = (22, 64, 30)
TOMATO = (229, 83, 61)
CARROT = (240, 140, 50)
CARROT_IN = (248, 178, 104)
# (kind, rest x, rest y, drop delay, start spin)
ITEMS = (
    ("tomato", 424, 296, 0.04, 40),
    ("slice", 506, 300, 0.14, -60),
    ("leaf", 556, 288, 0.24, 90),
    ("carrot", 458, 304, 0.32, -30),
    ("leaf2", 400, 300, 0.40, -80),
)


def drop_y(rest: float, p: float) -> float:
    if p < 0.7:  # falling under gravity
        return -60 + (rest + 60) * (p / 0.7) ** 2
    q = (p - 0.7) / 0.3  # one damped bounce, then rest
    return rest - 16 * math.sin(math.pi * q) * (1 - q)


def draw_item(img, kind, x, y, spin) -> None:
    d = ImageDraw.Draw(img)
    if kind == "tomato":
        d.ellipse(s(x - 30, y - 30, x + 30, y + 30), fill=TOMATO)
        for k in range(5):
            blob(img, x, y - 26, 16, 6, spin + k * 72, LEAF_RIB)
    elif kind == "slice":
        d.ellipse(s(x - 28, y - 28, x + 28, y + 28), fill=RIND)
        d.ellipse(s(x - 23, y - 23, x + 23, y + 23), fill=FLESH)
        d.ellipse(s(x - 14, y - 14, x + 14, y + 14), fill=CORE)
        for k in range(6):
            a = math.radians(spin + k * 60)
            blob(
                img,
                x + 9 * math.cos(a),
                y + 9 * math.sin(a),
                8,
                4,
                math.degrees(a),
                SEED_EDGE,
            )
    elif kind == "carrot":
        d.ellipse(s(x - 22, y - 22, x + 22, y + 22), fill=CARROT)
        d.ellipse(s(x - 12, y - 12, x + 12, y + 12), fill=CARROT_IN)
    else:
        w, h = (58, 26) if kind == "leaf" else (46, 22)
        blob(img, x, y, w, h, spin - 30, LEAF if kind == "leaf" else GREENS[2])


def sparkle(d, x, y, r, colour) -> None:
    k = r * 0.28
    d.polygon(
        s(
            x,
            y - r,
            x + k,
            y - k,
            x + r,
            y,
            x + k,
            y + k,
            x,
            y + r,
            x - k,
            y + k,
            x - r,
            y,
            x - k,
            y - k,
        ),
        fill=colour,
    )


def bowl_frame(t: float) -> Image.Image:
    img, d = canvas()
    d.ellipse(s(BX - BHW, BRIM - 26, BX + BHW, BRIM + 26), fill=BOWL_IN)
    sink = 110 * ease_io(clamp((t - 0.82) / 0.16))
    for kind, x, rest, delay, spin in ITEMS:
        p = clamp((t - delay) / 0.24)
        if p <= 0:
            continue
        draw_item(img, kind, x, drop_y(rest, p) + sink, spin * (1 - p))
    d = ImageDraw.Draw(img)
    d.pieslice(s(BX - BHW, BRIM - 150, BX + BHW, BRIM + 150), 0, 180, fill=BOWL)
    o = BHW
    d.arc(s(BX - o, BRIM - 26, BX + o, BRIM + 26), 0, 180, fill=RIND_EDGE, width=5 * SS)
    d.ellipse(s(BX - 70, BRIM + 160, BX + 70, BRIM + 170), fill=TRACK)  # shadow

    # A sparkle pops once everything has landed: the meal has been read.
    p = ease_out(clamp((t - 0.62) / 0.14)) * (1 - ease_io(clamp((t - 0.8) / 0.1)))
    if p > 0.02:
        sparkle(d, 610, 214, 22 * p, SCAN)
        sparkle(d, 640, 250, 11 * p, PULSE)
    return img.resize((W, H), Image.LANCZOS)


VARIANTS = {
    "slice": slice_frame,
    "plate": plate_frame,
    "rings": rings_frame,
    "bowl": bowl_frame,
}


def render(name: str) -> Path:
    out = OUT_DIR / f"{name}.mp4"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(FRAMES):
            VARIANTS[name](i / FRAMES).save(f"{tmp}/{i:03d}.png")
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                f"{tmp}/%03d.png",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
                "-preset",
                "slow",
                "-movflags",
                "+faststart",
                "-an",
                str(out),
            ],
            check=True,
        )
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return out


def main() -> None:
    for name in sys.argv[1:] or VARIANTS:
        render(name)


if __name__ == "__main__":
    main()
