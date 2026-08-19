#!/usr/bin/env python3
"""Generate icon.png (128x128) and logo.png (500x200) for the add-on.

Rendered at 4x and downscaled, so the edges stay smooth without any external
asset. Run from the repository root:  python tools/make_icons.py
"""

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 4  # supersampling factor

NAVY_TOP = (14, 48, 76)
NAVY_BOTTOM = (5, 18, 31)
CYAN = (34, 211, 238)
CYAN_DIM = (34, 211, 238, 150)
WHITE = (240, 249, 255)
SEA = (16, 120, 150)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.pardir, "ais_catcher_stats")


def vertical_gradient(size, top, bottom):
    width, height = size
    base = Image.new("RGB", (1, height))
    px = base.load()
    for y in range(height):
        t = y / max(1, height - 1)
        px[0, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
    return base.resize((width, height), Image.BICUBIC)


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                           radius=radius, fill=255)
    return mask


def draw_mark(draw, cx, cy, r):
    """Radar waves over a ship silhouette, centred on (cx, cy) within radius r."""
    # three signal arcs radiating from the mast head
    top = cy - r * 0.62
    for i, scale in enumerate((0.42, 0.68, 0.94)):
        rr = r * scale
        box = [cx - rr, top - rr * 0.78, cx + rr, top + rr * 0.78]
        width = max(1, int(r * 0.085))
        colour = CYAN if i == 0 else (*CYAN, 235 - i * 55)
        draw.arc(box, start=205, end=335, fill=colour, width=width)

    # mast
    mast_w = max(1, int(r * 0.075))
    draw.line([(cx, top + r * 0.05), (cx, cy + r * 0.16)], fill=WHITE, width=mast_w)

    # hull: a trapezoid with a rounded bottom
    hull_top = cy + r * 0.16
    hull_bot = cy + r * 0.50
    draw.polygon([
        (cx - r * 0.78, hull_top),
        (cx + r * 0.78, hull_top),
        (cx + r * 0.50, hull_bot),
        (cx - r * 0.50, hull_bot),
    ], fill=WHITE)
    draw.pieslice([cx - r * 0.50, hull_bot - r * 0.26,
                   cx + r * 0.50, hull_bot + r * 0.26], 0, 180, fill=WHITE)

    # superstructure
    draw.rectangle([cx - r * 0.24, cy - r * 0.14, cx + r * 0.24, hull_top],
                   fill=WHITE)

    # water line: one continuous wave under the hull
    wave_y = cy + r * 0.86
    width = max(1, int(r * 0.11))
    amp = r * 0.15
    step = r * 0.50
    for i in range(4):
        x0 = cx - r + i * step
        box = [x0, wave_y - amp, x0 + step, wave_y + amp]
        start, end = (0, 180) if i % 2 else (180, 360)
        draw.arc(box, start=start, end=end, fill=SEA, width=width)


def make_icon(path, size=128):
    big = size * S
    background = vertical_gradient((big, big), NAVY_TOP, NAVY_BOTTOM).convert("RGBA")

    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([big * 0.12, big * 0.02, big * 0.88, big * 0.72],
                                 fill=(34, 211, 238, 46))
    background = Image.alpha_composite(background, glow.filter(
        ImageFilter.GaussianBlur(big * 0.06)))

    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(layer), big / 2, big * 0.52, big * 0.33)
    image = Image.alpha_composite(background, layer)

    image.putalpha(rounded_mask((big, big), int(big * 0.22)))
    image.resize((size, size), Image.LANCZOS).save(path)
    return path


def load_font(size):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_logo(path, size=(500, 200)):
    big = (size[0] * S, size[1] * S)

    # The store shows the logo on a light or a dark card, so the logo brings
    # its own background instead of relying on transparency.
    image = vertical_gradient(big, NAVY_TOP, NAVY_BOTTOM).convert("RGBA")
    glow = Image.new("RGBA", big, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([-big[1] * 0.2, -big[1] * 0.5,
                                  big[1] * 1.1, big[1] * 0.9],
                                 fill=(34, 211, 238, 40))
    image = Image.alpha_composite(image, glow.filter(
        ImageFilter.GaussianBlur(big[1] * 0.12)))

    mark = Image.new("RGBA", big, (0, 0, 0, 0))
    mark_cx, mark_r = big[1] * 0.52, big[1] * 0.32
    draw_mark(ImageDraw.Draw(mark), mark_cx, big[1] * 0.50, mark_r)
    image = Image.alpha_composite(image, mark)

    draw = ImageDraw.Draw(image)
    tx = int(mark_cx + mark_r + big[1] * 0.22)
    available = big[0] - tx - int(big[1] * 0.10)

    def fit(text, start, minimum=8):
        """Largest font size at which `text` still fits the free width."""
        for pt in range(start, minimum, -2):
            font = load_font(pt)
            if draw.textlength(text, font=font) <= available:
                return font
        return load_font(minimum)

    title_text, subtitle_text = "AIS-catcher", "STATISTICS FOR HOME ASSISTANT"
    title = fit(title_text, int(big[1] * 0.26))
    subtitle = fit(subtitle_text, int(big[1] * 0.11))
    draw.text((tx, big[1] * 0.30), title_text, font=title, fill=WHITE)
    draw.text((tx + 2, big[1] * 0.58), subtitle_text, font=subtitle, fill=CYAN)

    image.putalpha(rounded_mask(big, int(big[1] * 0.10)))
    image.resize(size, Image.LANCZOS).save(path)
    return path


if __name__ == "__main__":
    print("wrote", make_icon(os.path.join(OUT, "icon.png")))
    print("wrote", make_logo(os.path.join(OUT, "logo.png")))
