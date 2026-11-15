"""Shared dataclasses for extraction, speech scripts and the server."""
from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class Word:
    text: str
    page: int  # 0-based
    bbox: BBox

    def to_dict(self) -> dict:
        return {"text": self.text, "page": self.page, "bbox": list(self.bbox)}

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(d["text"], d["page"], tuple(d["bbox"]))


@dataclass
class Table:
    header: list[list[Word]]
    rows: list[list[list[Word]]]

    def to_dict(self) -> dict:
        return {
            "header": [[w.to_dict() for w in cell] for cell in self.header],
            "rows": [[[w.to_dict() for w in cell] for cell in row] for row in self.rows],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Table":
        return cls(
            header=[[Word.from_dict(w) for w in cell] for cell in d["header"]],
            rows=[[[Word.from_dict(w) for w in cell] for cell in row] for row in d["rows"]],
        )


@dataclass
class Block:
    id: str  # f"b{page:03d}_{n:03d}"
    role: str  # heading1|heading2|heading3|body|box_label|table
    words: list[Word]
    page: int
    lead: str | None = None
    box_kind: str | None = None
    table: Table | None = None
    flagged: bool = False  # chunk heading carrying the "★ Likely tested" flag

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "words": [w.to_dict() for w in self.words],
            "page": self.page,
            "lead": self.lead,
            "box_kind": self.box_kind,
            "table": self.table.to_dict() if self.table else None,
            "flagged": self.flagged,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        return cls(
            id=d["id"],
            role=d["role"],
            words=[Word.from_dict(w) for w in d["words"]],
            page=d["page"],
            lead=d.get("lead"),
            box_kind=d.get("box_kind"),
            table=Table.from_dict(d["table"]) if d.get("table") else None,
            flagged=d.get("flagged", False),
        )


@dataclass
class OutlineEntry:
    level: int
    title: str
    page: int
    y: float
    sentence_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "title": self.title,
            "page": self.page,
            "y": self.y,
            "sentence_id": self.sentence_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OutlineEntry":
        return cls(d["level"], d["title"], d["page"], d["y"], d.get("sentence_id"))


@dataclass
class Document:
    profile: str  # studypack|besteffort
    page_count: int
    blocks: list[Block]
    outline: list[OutlineEntry]
    title: str

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "page_count": self.page_count,
            "blocks": [b.to_dict() for b in self.blocks],
            "outline": [o.to_dict() for o in self.outline],
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        return cls(
            profile=d["profile"],
            page_count=d["page_count"],
            blocks=[Block.from_dict(b) for b in d["blocks"]],
            outline=[OutlineEntry.from_dict(o) for o in d["outline"]],
            title=d["title"],
        )


@dataclass
class SpokenWord:
    text: str
    word_index: int  # index into the owning sentence's `display`

    def to_dict(self) -> dict:
        return {"text": self.text, "word_index": self.word_index}

    @classmethod
    def from_dict(cls, d: dict) -> "SpokenWord":
        return cls(d["text"], d["word_index"])


@dataclass
class Sentence:
    id: str  # f"s{n:05d}"
    block_id: str
    spoken: list[SpokenWord]
    display: list[Word]
    pause_after_ms: int
    kind: str  # heading|body|table|box_label

    @property
    def spoken_text(self) -> str:
        return " ".join(w.text for w in self.spoken)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "block_id": self.block_id,
            "spoken": [w.to_dict() for w in self.spoken],
            "display": [w.to_dict() for w in self.display],
            "pause_after_ms": self.pause_after_ms,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sentence":
        return cls(
            id=d["id"],
            block_id=d["block_id"],
            spoken=[SpokenWord.from_dict(w) for w in d["spoken"]],
            display=[Word.from_dict(w) for w in d["display"]],
            pause_after_ms=d["pause_after_ms"],
            kind=d["kind"],
        )


@dataclass
class Script:
    pack_id: str
    profile: str
    title: str
    sentences: list[Sentence]
    outline: list[OutlineEntry]
    page_count: int

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "profile": self.profile,
            "title": self.title,
            "sentences": [s.to_dict() for s in self.sentences],
            "outline": [o.to_dict() for o in self.outline],
            "page_count": self.page_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        return cls(
            pack_id=d["pack_id"],
            profile=d["profile"],
            title=d["title"],
            sentences=[Sentence.from_dict(s) for s in d["sentences"]],
            outline=[OutlineEntry.from_dict(o) for o in d["outline"]],
            page_count=d["page_count"],
        )
