"""Create tiny calendar/event icons for the firmware Apps menu."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / 'upcoming_events/assets'
OUT.mkdir(parents=True, exist_ok=True)


def icon(size, name):
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    white = (255, 255, 255, 255)
    accent = (255, 151, 38, 255)
    draw.rounded_rectangle((0, 1, size - 1, size - 1), radius=2, outline=white, width=1)
    draw.line((1, 3, size - 2, 3), fill=white, width=1)
    draw.point((size // 2, size // 2 + 1), fill=accent)
    if size >= 11:
        draw.rectangle((size // 2 - 1, size // 2, size // 2 + 1, size // 2 + 2), fill=accent)
    image.save(OUT / name)


icon(8, 'upcoming_front_8x8.png')
icon(11, 'upcoming_back_11x11.png')
