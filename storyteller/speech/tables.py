"""Table linearisation: an announcement, then one spoken sentence per row."""

from __future__ import annotations

from storyteller.model import Table, Word

_TRAIL = ".,;:"


def _cell_tokens(cell: list[Word]) -> list[str]:
    return [w.text for w in cell]


def _header_name(cell: list[Word]) -> list[str]:
    tokens = _cell_tokens(cell)
    if tokens:
        tokens[-1] = tokens[-1].rstrip(_TRAIL)
        if not tokens[-1]:
            tokens.pop()
    return tokens


def _end_with(tokens: list[str], mark: str) -> None:
    """Close the last token with ``mark`` unless it already ends a sentence."""
    if not tokens or tokens[-1][-1:] in "?!":
        return
    tokens[-1] = tokens[-1].rstrip(_TRAIL) + mark


def linearise_table_mapped(table: Table) -> list[tuple[list[str], list[int], list[Word]]]:
    """Like :func:`linearise_table`, plus each token's index into the display words."""
    items: list[tuple[list[str], list[int], list[Word]]] = []
    names = [_header_name(cell) for cell in table.header]

    n = len(table.rows)
    tokens = ["Table,", str(n), "row" if n == 1 else "rows"]
    owners = [0, 0, 0]
    display: list[Word] = []
    named = [(name, cell) for name, cell in zip(names, table.header) if name]
    if named:
        tokens[-1] += ":"
    else:
        tokens[-1] += "."
    for k, (name, cell) in enumerate(named):
        start = len(display)
        display.extend(cell)
        part = list(name)
        _end_with(part, "." if k + 1 == len(named) else ",")
        tokens.extend(part)
        owners.extend(start + min(j, len(cell) - 1) for j in range(len(part)))
    if not display:
        display = [w for row in table.rows for cell in row for w in cell]
    if display:
        items.append((tokens, owners, display))

    for row in table.rows:
        tokens, owners, display = [], [], []
        for c, cell in enumerate(row):
            if not cell:
                continue
            start = len(display)
            display.extend(cell)
            name = list(names[c]) if c < len(names) else []
            if name:
                name[-1] += ":"
                tokens.extend(name)
                owners.extend([start] * len(name))
            part = _cell_tokens(cell)
            _end_with(part, ".")
            tokens.extend(part)
            owners.extend(range(start, start + len(part)))
        if tokens:
            items.append((tokens, owners, display))
    return items


def linearise_table(table: Table) -> list[tuple[list[str], list[Word]]]:
    """Announcement ``Table, {n} rows: {h1}, {h2}.`` then ``{header}: {cell}.`` per row.

    Tokens are display-word texts (symbol rules not yet applied); each item's
    words are what gets highlighted: the header words for the announcement,
    the row's words for each row.
    """
    return [(tokens, display) for tokens, _, display in linearise_table_mapped(table)]
