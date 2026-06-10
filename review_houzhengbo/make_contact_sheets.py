from __future__ import annotations

from pathlib import Path
import argparse

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--source", default=str(ROOT / "layout_pages"))
parser.add_argument("--output", default=str(ROOT / "contact_sheets"))
args = parser.parse_args()
SOURCE = Path(args.source)
OUTPUT = Path(args.output)
OUTPUT.mkdir(exist_ok=True)

thumb_width = 640
thumb_height = 360
label_height = 28
columns = 2
rows = 3
per_sheet = columns * rows
font = ImageFont.load_default(size=18)

page_files = sorted(SOURCE.glob("page-*.png"))
for sheet_index in range(0, len(page_files), per_sheet):
    batch = page_files[sheet_index : sheet_index + per_sheet]
    sheet = Image.new(
        "RGB",
        (columns * thumb_width, rows * (thumb_height + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for item_index, page_file in enumerate(batch):
        image = Image.open(page_file).convert("RGB")
        image = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        column = item_index % columns
        row = item_index // columns
        x = column * thumb_width
        y = row * (thumb_height + label_height)
        sheet.paste(image, (x, y))
        draw.rectangle(
            (x, y + thumb_height, x + thumb_width, y + thumb_height + label_height),
            fill="white",
        )
        draw.text(
            (x + 10, y + thumb_height + 4),
            f"PDF {page_file.stem.removeprefix('page-')}",
            fill="black",
            font=font,
        )
    first_page = sheet_index + 1
    last_page = sheet_index + len(batch)
    sheet.save(OUTPUT / f"pages-{first_page:02d}-{last_page:02d}.png")

print(f"Created {len(list(OUTPUT.glob('*.png')))} contact sheets")
