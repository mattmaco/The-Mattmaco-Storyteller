"""Symbol rulebook: turns one display word into spoken tokens."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

TRAILING_PUNCT = ".,;:?!"
_OPENERS = "\"'([{“‘"
_CLOSERS = "\"')]}”’"
_PQ = re.compile(r"^(\d+)([pq]{2,3})$")
_EN_DASH = "–"
_EM_DASH = "—"


@dataclass
class Rules:
    patterns: list[tuple[re.Pattern[str], str]]
    chars: dict[str, str]
    unknown: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, overrides: dict[str, str] | None = None) -> "Rules":
        path = Path(__file__).with_name("symbols.toml")
        with path.open("rb") as f:
            data = tomllib.load(f)
        patterns = [(re.compile(p), t) for p, t in data["patterns"].items()]
        chars = dict(data["chars"])
        if overrides:
            chars.update(overrides)
        return cls(patterns, chars)


def _match_pattern(word: str, rules: Rules) -> list[str] | None:
    for regex, template in rules.patterns:
        m = regex.match(word)
        if m:
            text = re.sub(r"\{(\d+)\}", lambda g: m.group(int(g.group(1))), template)
            return text.split()
    return None


def _speak_chars(core: str, rules: Rules) -> str:
    out: list[str] = []
    for i, ch in enumerate(core):
        if ch in (_EN_DASH, _EM_DASH):
            before = core[i - 1] if i else ""
            after = core[i + 1] if i + 1 < len(core) else ""
            if ch == _EN_DASH and before.isdigit() and after.isdigit():
                out.append(" to ")
            else:
                # Pause: a comma on the preceding text; nothing if there is none.
                text = "".join(out).rstrip()
                out = [text + ", "] if text else []
            continue
        if ch in rules.chars:
            rep = rules.chars[ch]
            if any(c.isalnum() for c in rep):
                prev = "".join(out)[-1:] if out else ""
                nxt = core[i + 1] if i + 1 < len(core) else ""
                if prev.isalnum():
                    rep = " " + rep
                if nxt.isalnum():
                    rep = rep + " "
            out.append(rep)
        elif ch.isascii() or unicodedata.category(ch)[0] == "L":
            out.append(ch)
        else:
            rules.unknown.add(ch)
            out.append(" " + unicodedata.name(ch, f"u+{ord(ch):04x}").lower() + " ")
    return "".join(out)


def speak_word(text: str, rules: Rules) -> list[str]:
    """Spoken tokens for one display word (possibly empty, e.g. a bare ``★``)."""
    tokens = _match_pattern(text, rules)
    if tokens is not None:
        return tokens

    core = text
    # Peel trailing closers and sentence punctuation; remember the punctuation.
    trail = ""
    while core and core[-1] in _CLOSERS + TRAILING_PUNCT:
        ch = core[-1]
        core = core[:-1]
        if ch in TRAILING_PUNCT:
            trail = ch + trail
    core = core.lstrip(_OPENERS)
    if not core:
        return []

    tokens = _match_pattern(core, rules)
    if tokens is None:
        pq = _PQ.match(core)
        if pq:
            tokens = [pq.group(1), *pq.group(2)]
        else:
            tokens = _speak_chars(core, rules).split()
    if tokens and trail:
        tokens[-1] += trail
    return tokens
