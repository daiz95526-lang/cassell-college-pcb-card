"""Render flat gallery images directly from the published Gerber regions."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from PIL import Image, ImageDraw, ImageFont
from export_public_gerber import parse_regions, LAYER_FILES, OUT

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "images"
SCALE = 17.5
UPSCALE = 2
W, H, R = 85.6, 54.0, 3.18
GOLD = (197, 163, 91, 255)
MASK = (14, 16, 20, 255)
BACKDROP = (26, 28, 34, 255)


def draw_ring(draw, ring, left, top, side, scale):
    pts = []
    for x, y in ring.coords:
        # Gerber y is negative down. Bottom is viewed from the outside once.
        sx = x if side == "front" else W - x
        sy = -y
        pts.append((left + sx * scale, top + sy * scale))
    draw.polygon(pts, fill=GOLD)


def render(side):
    art_name = LAYER_FILES[1 if side == "front" else 2]
    regions = parse_regions((OUT / art_name).read_bytes())
    w, h = 1800 * UPSCALE, 1160 * UPSCALE
    scale = SCALE * UPSCALE
    card_w, card_h = round(W * scale), round(H * scale)
    left, top = (w - card_w) // 2, 115 * UPSCALE
    img = Image.new("RGBA", (w, h), BACKDROP)
    draw = ImageDraw.Draw(img)
    radius = round(R * scale)
    draw.rounded_rectangle((left + 8 * UPSCALE, top + 12 * UPSCALE,
                            left + card_w + 8 * UPSCALE, top + card_h + 12 * UPSCALE),
                           radius=radius, fill=(5, 6, 8, 255))
    draw.rounded_rectangle((left, top, left + card_w, top + card_h),
                           radius=radius, fill=MASK, outline=(100, 81, 47, 255), width=2 * UPSCALE)
    for poly in regions:
        draw_ring(draw, poly.exterior, left, top, side, scale)
        for hole in poly.interiors:
            pts = []
            for x, y in hole.coords:
                sx = x if side == "front" else W - x
                pts.append((left + sx * scale, top - y * scale))
            draw.polygon(pts, fill=MASK)
    try:
        titlefont = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24 * UPSCALE)
        capfont = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15 * UPSCALE)
    except OSError:
        titlefont = capfont = ImageFont.load_default()
    title = "FRONT" if side == "front" else "BACK"
    draw.text((left, 47 * UPSCALE), title, font=titlefont, fill=(244, 241, 232, 255))
    caption = "GERBER-DERIVED FLAT PREVIEW  |  NOT A PHOTOGRAPH OR MATERIAL SAMPLE"
    box = draw.textbbox((0, 0), caption, font=capfont)
    draw.text(((w - (box[2] - box[0])) / 2, (top + card_h + 42 * UPSCALE)),
              caption, font=capfont, fill=(190, 191, 194, 255))
    img = img.resize((w // UPSCALE, h // UPSCALE), Image.Resampling.LANCZOS)
    IMAGES.mkdir(exist_ok=True)
    img.convert("RGB").save(IMAGES / f"{side}.png", optimize=True)


if __name__ == "__main__":
    render("front")
    render("back")
