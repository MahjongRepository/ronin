"""Stack a before and an after screenshot into one labelled collage, before on top.

uv run --no-project --with pillow python -I .claude/skills/app-browser/collage.py \\
    OUT.png BEFORE.png AFTER.png [--title "1440x900 laptop, dense replay"] [--width 1600]
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

LABEL_HEIGHT = 40
GAP = 12
INK = (20, 20, 20)
PAPER = (255, 255, 255)


def scaled(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image
    return image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)


def build_collage(before: Image.Image, after: Image.Image, title: str, width: int) -> Image.Image:
    shots = [scaled(before.convert("RGB"), width), scaled(after.convert("RGB"), width)]

    canvas_width = max(shot.width for shot in shots)
    canvas = Image.new("RGB", (canvas_width, sum(LABEL_HEIGHT + shot.height for shot in shots) + GAP), PAPER)
    draw = ImageDraw.Draw(canvas)
    top = 0
    for label, shot in zip(("before", "after"), shots, strict=True):
        draw.text((10, top + 8), f"{label} - {title}" if title else label, fill=INK, font_size=22)
        canvas.paste(shot, (0, top + LABEL_HEIGHT))
        top += LABEL_HEIGHT + shot.height + GAP

    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--title", default="")
    parser.add_argument("--width", type=int, default=1600, help="widest a shot is drawn (px); larger ones scale down")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    build_collage(Image.open(args.before), Image.open(args.after), args.title, args.width).save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
