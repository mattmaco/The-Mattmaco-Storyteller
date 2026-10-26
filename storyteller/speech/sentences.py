"""Sentence boundaries on display words, and splitting of over-long spoken text."""

from __future__ import annotations

import re

from storyteller.model import SpokenWord, Word

_ENDERS = ".?!"
_CLOSERS = "\"')]}”’"
_OPENERS = "\"'([{“‘"
_QUOTES = "\"'“‘"
_ABBREVIATIONS = {
    "e.g.", "i.e.", "vs.", "etc.", "al.", "Fig.", "Figs.", "approx.", "cf.", "No.", "St.", "Dr.",
}
_INITIAL = re.compile(r"^[A-Z]\.$")
_MARKER = re.compile(r"^[A-Z]?\d+[a-z]?\.$")  # list numbers: "2.", "Q1.", "3a."
_SOFT_BREAKS = ";,—:"


def _is_abbreviation(core: str) -> bool:
    core = core.lstrip(_OPENERS)
    return core in _ABBREVIATIONS or bool(_INITIAL.match(core))


def _starts_sentence(word: Word) -> bool:
    first = word.text[:1]
    return first.isupper() or first.isdigit() or (first != "" and first in _QUOTES)


def split_sentences(words: list[Word]) -> list[list[Word]]:
    """Group display words into sentences.

    A boundary falls after a word ending in ``. ? !`` (optionally followed by a
    closing quote or bracket) when the next word starts with an uppercase
    letter, a digit or a quote; never after a known abbreviation or a single
    capital initial, never after list numbers (``2.``, ``Q1.``) that open a
    sentence, and never inside parentheses.
    """
    groups: list[list[Word]] = []
    current: list[Word] = []
    depth = 0
    for i, word in enumerate(words):
        current.append(word)
        depth = max(0, depth + word.text.count("(") - word.text.count(")"))
        if i + 1 == len(words) or depth:
            continue
        core = word.text.rstrip(_CLOSERS)
        if not core or core[-1] not in _ENDERS:
            continue
        if core.endswith(".") and _is_abbreviation(core):
            continue
        if all(_MARKER.match(w.text) for w in current):
            continue  # a list number opens its sentence, it does not end one
        if _starts_sentence(words[i + 1]):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _length(spoken: list[SpokenWord]) -> int:
    return sum(len(w.text) for w in spoken) + max(0, len(spoken) - 1)


def split_long(spoken: list[SpokenWord], limit: int = 300) -> list[list[SpokenWord]]:
    """Split spoken words into parts of at most ``limit`` characters (joined by spaces).

    Each cut goes after the last token ending in ``; , — :`` that keeps the
    part within the limit; failing that, at the last word boundary that does.
    A single token longer than the limit becomes a part of its own.
    """
    parts: list[list[SpokenWord]] = []
    rest = list(spoken)
    while rest:
        if _length(rest) <= limit:
            parts.append(rest)
            break
        fit = 0  # number of leading tokens that fit
        size = -1
        while fit < len(rest) and size + 1 + len(rest[fit].text) <= limit:
            size += 1 + len(rest[fit].text)
            fit += 1
        cut = max(fit, 1)
        for k in range(fit, 0, -1):
            if rest[k - 1].text[-1:] in _SOFT_BREAKS:
                cut = k
                break
        parts.append(rest[:cut])
        rest = rest[cut:]
    return parts
