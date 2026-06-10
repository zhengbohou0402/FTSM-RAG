from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


ROOT = Path(__file__).resolve().parent
DOCX_PATH = ROOT / "thesis.docx"


def iter_blocks(document: Document):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def paragraph_record(index: int, paragraph: Paragraph) -> dict:
    fmt = paragraph.paragraph_format
    return {
        "index": index,
        "style": paragraph.style.name if paragraph.style else "",
        "text": paragraph.text,
        "alignment": str(paragraph.alignment),
        "left_indent_pt": fmt.left_indent.pt if fmt.left_indent else None,
        "right_indent_pt": fmt.right_indent.pt if fmt.right_indent else None,
        "first_line_indent_pt": (
            fmt.first_line_indent.pt if fmt.first_line_indent else None
        ),
        "space_before_pt": fmt.space_before.pt if fmt.space_before else None,
        "space_after_pt": fmt.space_after.pt if fmt.space_after else None,
        "line_spacing": str(fmt.line_spacing) if fmt.line_spacing else None,
        "runs": [
            {
                "text": run.text,
                "bold": run.bold,
                "italic": run.italic,
                "underline": bool(run.underline),
                "font": run.font.name,
                "size_pt": run.font.size.pt if run.font.size else None,
            }
            for run in paragraph.runs
        ],
    }


def extract_docx() -> None:
    document = Document(DOCX_PATH)
    paragraphs = []
    tables = []
    blocks = []
    paragraph_index = 0
    table_index = 0

    for block in iter_blocks(document):
        if isinstance(block, Paragraph):
            record = paragraph_record(paragraph_index, block)
            paragraphs.append(record)
            blocks.append({"type": "paragraph", "index": paragraph_index})
            paragraph_index += 1
        else:
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            tables.append(
                {
                    "index": table_index,
                    "rows": rows,
                    "row_count": len(rows),
                    "column_count": max((len(row) for row in rows), default=0),
                }
            )
            blocks.append({"type": "table", "index": table_index})
            table_index += 1

    (ROOT / "paragraphs.json").write_text(
        json.dumps(paragraphs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "tables.json").write_text(
        json.dumps(tables, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "blocks.json").write_text(
        json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with (ROOT / "paragraphs.txt").open("w", encoding="utf-8") as output:
        for record in paragraphs:
            text = record["text"].replace("\n", " | ")
            output.write(
                f"P{record['index']:04d}\t[{record['style']}]\t{text}\n"
            )

    with (ROOT / "tables.txt").open("w", encoding="utf-8") as output:
        for table in tables:
            output.write(
                f"\n=== TABLE {table['index']} "
                f"({table['row_count']}x{table['column_count']}) ===\n"
            )
            for row in table["rows"]:
                output.write(" || ".join(cell.replace("\n", " | ") for cell in row))
                output.write("\n")


if __name__ == "__main__":
    extract_docx()
    print(
        json.dumps(
            {
                "paragraphs_file": str(ROOT / "paragraphs.txt"),
                "tables_file": str(ROOT / "tables.txt"),
            },
            ensure_ascii=False,
        )
    )
