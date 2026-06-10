from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

parser = argparse.ArgumentParser()
parser.add_argument("start", type=int)
parser.add_argument("end", type=int)
args = parser.parse_args()

root = Path(__file__).resolve().parent
records = json.loads((root / "word_paragraph_pages.json").read_text(encoding="utf-8"))
for record in records:
    if args.start <= record["Page"] <= args.end:
        print(
            f"\n[PDF PAGE {record['Page']} | P{record['Index']:04d} | "
            f"{record['Style']}]\n{record['Text']}"
        )
