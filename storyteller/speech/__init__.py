"""Speech preparation: symbol rulebook, pronunciations, listening script."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from storyteller.model import Block, Document, OutlineEntry, Script, Sentence, SpokenWord, Word
from storyteller.speech.pronounce import apply_pronunciations
from storyteller.speech.sentences import CLOSERS, split_long, split_sentences
from storyteller.speech.symbols import TRAILING_PUNCT, Rules, speak_word
from storyteller.speech.tables import linearise_table_mapped

__all__ = ["BOX_KINDS", "ScriptOptions", "build_script"]

BOX_KINDS = (
    "chain", "figure", "note", "gap", "background", "reading_aid", "analogy", "key", "kit", "traps",
)
BADGES = {"Stated", "Follows"}
SPOKEN_LIMIT = 300
_KIND = {"heading1": "heading", "heading2": "heading", "heading3": "heading",
         "box_label": "box_label", "table": "table"}

# A sentence before speaking: (display-word text or lead token, index into display).
_Item = tuple[str, int]


@dataclass
class ScriptOptions:
    pauses: dict[str, int] = field(
        default_factory=lambda: {"sentence": 250, "block": 600, "section": 1000}
    )
    read_boxes: dict[str, bool] = field(default_factory=lambda: {k: True for k in BOX_KINDS})
    read_badges: bool = True
    read_flags: bool = False
    pronunciations: dict[str, str] = field(default_factory=dict)


def _trailing_punct(text: str) -> str:
    core = text.rstrip(CLOSERS + TRAILING_PUNCT)
    return "".join(c for c in text[len(core):] if c in TRAILING_PUNCT)


def _speak(items: list[_Item], rules: Rules, lexicon: dict[str, str]) -> list[SpokenWord]:
    spoken: list[SpokenWord] = []
    for text, index in items:
        tokens = [t for t in apply_pronunciations(speak_word(text, rules), lexicon) if t.strip()]
        if tokens:
            spoken.extend(SpokenWord(t, index) for t in tokens)
            continue
        # Punctuation-only word (e.g. "★."): keep its sentence punctuation.
        trail = _trailing_punct(text)
        if trail and spoken:
            spoken[-1].text = spoken[-1].text.rstrip(TRAILING_PUNCT) + trail
    return spoken


def _lead_tokens(lead: str | None, read_badges: bool) -> list[str]:
    if not lead:
        return []
    tokens = lead.split()
    if not read_badges:
        kept = [t for t in tokens if t.rstrip(":") not in BADGES]
        if kept and tokens[-1].endswith(":") and not kept[-1].endswith(":"):
            kept[-1] += ":"
        tokens = kept
    return tokens


def _block_groups(block: Block, opts: ScriptOptions) -> list[tuple[list[_Item], list[Word]]]:
    """Unspoken sentences of one block: items to speak and the words they display."""
    groups: list[tuple[list[_Item], list[Word]]]
    if block.role == "table" and block.table is not None:
        groups = [
            (list(zip(tokens, owners)), display)
            for tokens, owners, display in linearise_table_mapped(block.table)
        ]
    elif block.role in _KIND and block.role != "table":  # headings and box labels
        groups = [([(w.text, i) for i, w in enumerate(block.words)], block.words)] if block.words else []
    else:
        groups = [([(w.text, i) for i, w in enumerate(g)], g) for g in split_sentences(block.words)]
    lead = _lead_tokens(block.lead, opts.read_badges)
    if lead and groups:
        groups[0] = ([(t, 0) for t in lead] + groups[0][0], groups[0][1])
    if opts.read_flags and block.flagged and block.words:
        groups.append(([("Likely", 0), ("tested.", 0)], block.words))
    return groups


def _parts(spoken: list[SpokenWord], display: list[Word]) -> list[tuple[list[SpokenWord], list[Word]]]:
    """Split an over-long sentence; each part displays the words its tokens cover."""
    if len(" ".join(w.text for w in spoken)) <= SPOKEN_LIMIT:
        return [(spoken, display)]
    pieces = split_long(spoken, SPOKEN_LIMIT)
    out = []
    for k, piece in enumerate(pieces):
        start = 0 if k == 0 else piece[0].word_index
        if k + 1 == len(pieces):
            end = len(display)
        else:
            end = max(piece[-1].word_index + 1, pieces[k + 1][0].word_index)
        out.append(
            ([SpokenWord(w.text, w.word_index - start) for w in piece], display[start:end])
        )
    return out


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def _titled_heading(entry: OutlineEntry, sentences: list[Sentence]) -> str | None:
    """First heading sentence on the entry's page whose text starts with its title."""
    title = _normalise(entry.title)
    if not title:
        return None
    for s in sentences:
        if s.kind != "heading" or s.display[0].page != entry.page:
            continue
        text = _normalise(" ".join(w.text for w in s.display))
        if text.startswith(title) and not text[len(title) : len(title) + 1].isalnum():
            return s.id
    return None


def _assign_outline(doc: Document, sentences: list[Sentence]) -> list[OutlineEntry]:
    # Prefer the heading that carries the entry's title: pages laid out in
    # columns put later entries beside, not below, earlier text. Otherwise take
    # the first sentence at or after (page, y); a heading's top (y0) sits a few
    # points above its outline y, so compare the first word's bottom (y1).
    keys = [(s.display[0].page, s.display[0].bbox[3]) for s in sentences]
    outline = []
    for entry in doc.outline:
        sid = _titled_heading(entry, sentences) or next(
            (s.id for s, (page, bottom) in zip(sentences, keys)
             if page > entry.page or (page == entry.page and bottom > entry.y)),
            sentences[-1].id if sentences else None,
        )
        outline.append(replace(entry, sentence_id=sid))
    return outline


def build_script(
    doc: Document, pack_id: str, opts: ScriptOptions | None = None, rules: Rules | None = None
) -> Script:
    """Turn an extracted Document into the listening Script.

    ``rules`` defaults to a fresh :meth:`Rules.load`; pass one in to read the
    symbols it did not know (``rules.unknown``) afterwards.
    """
    opts = opts or ScriptOptions()
    rules = rules or Rules.load()
    sentences: list[Sentence] = []
    for block in doc.blocks:
        if block.box_kind and not opts.read_boxes.get(block.box_kind, True):
            continue
        kind = _KIND.get(block.role, "body")
        made: list[Sentence] = []
        for items, display in _block_groups(block, opts):
            spoken = _speak(items, rules, opts.pronunciations)
            if not spoken or not display:
                continue
            for part, shown in _parts(spoken, display):
                made.append(Sentence("", block.id, part, shown, opts.pauses["sentence"], kind))
        for n, s in enumerate(made):
            if kind == "heading":
                s.pause_after_ms = opts.pauses["section"]
            elif n + 1 == len(made):
                s.pause_after_ms = opts.pauses["block"]
        sentences.extend(made)
    for n, s in enumerate(sentences):
        s.id = f"s{n:05d}"
    return Script(
        pack_id=pack_id,
        profile=doc.profile,
        title=doc.title,
        sentences=sentences,
        outline=_assign_outline(doc, sentences),
        page_count=doc.page_count,
    )
