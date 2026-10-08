from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5")

MOJIBAKE_MARKERS = (
    "锛",
    "鐨",
    "璇",
    "绋",
    "鈹",
    "鉁",
    "�",
)


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    mojibake_score: int


def mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


def decode_text_bytes(data: bytes) -> DecodedText:
    best: DecodedText | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        decoded = DecodedText(
            text=text,
            encoding=encoding,
            mojibake_score=mojibake_score(text),
        )
        if best is None or decoded.mojibake_score < best.mojibake_score:
            best = decoded
        if decoded.mojibake_score == 0:
            return decoded

    if best is not None:
        return best

    text = data.decode("utf-8", errors="replace")
    return DecodedText(
        text=text,
        encoding="utf-8-replace",
        mojibake_score=mojibake_score(text),
    )


def read_text_safely(path: str | Path) -> DecodedText:
    return decode_text_bytes(Path(path).read_bytes())

