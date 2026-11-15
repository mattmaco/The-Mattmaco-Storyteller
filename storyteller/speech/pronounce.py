"""User pronunciation list: whole-token, case-insensitive replacement."""

from __future__ import annotations

TRAILING = ".,;:?!"


def apply_pronunciations(tokens: list[str], lexicon: dict[str, str]) -> list[str]:
    """Replace tokens found in ``lexicon`` (case-insensitive).

    Trailing sentence punctuation stays attached to the replacement. Values are
    passed through unchanged, so Kokoro inline phonemes ``[word](/phonemes/)``
    work as well as plain respellings.
    """
    if not lexicon:
        return list(tokens)
    folded = {k.casefold(): v for k, v in lexicon.items()}
    out: list[str] = []
    for token in tokens:
        core = token.rstrip(TRAILING)
        trail = token[len(core):]
        replacement = folded.get(core.casefold()) if core else None
        out.append(token if replacement is None else replacement + trail)
    return out
