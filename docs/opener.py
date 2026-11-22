"""Draw the opener of `./taos demo` as a picture: docs/opener.svg, the banner at the top of README.md.

The picture is made from the opener itself, so it cannot show something the
program does not print. Words are set on the terminal's grid. The box and the
mark are drawn as strokes, not as the letters of a font, so every reader sees
the same lines whatever fonts they have.

    python3 docs/opener.py --write     draw the picture again
    python3 docs/opener.py --verify    fail if the saved picture is not what the opener prints now
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from html import escape
from itertools import groupby
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from taos_core.page import WIDTH, Page  # noqa: E402

PICTURE = REPO / "docs" / "opener.svg"
COMMAND = "$ ./taos demo"
SAYS = ("The opener of ./taos demo: the name TAOS in a box, its four letters shaded as the four answers "
        "a result can get: holds, stale, fails and unknown.")
PAPER, EDGE = "#0b1510", "#22332b"
INK = {"": "#dbe7e0", "1": "#ffffff", "2": "#7d8f86", "32": "#6fd3a0", "33": "#f2a23a", "31": "#ef8f80"}
FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', 'DejaVu Sans Mono', monospace"
SIZE, CELL, ROW, SIDE, TOP = 15, 9.0, 20.0, 28.0, 22.0             # letter size, one column, one row, the margins
STROKE = {False: 1.3, True: 3.2}                                    # a light line and a heavy one
# A box-drawing character is the arms it reaches from the middle of its cell: left, right, up, down. Capitals are heavy.
ARMS = {"─": "lr", "│": "ud", "┌": "rd", "┐": "ld", "└": "ru", "┘": "lu",
        "━": "LR", "┃": "UD", "┏": "RD", "┓": "LD", "┗": "RU", "┛": "LU", "┣": "UDR", "┫": "UDL", "┳": "LRD",
        "╺": "R", "╸": "L", "╹": "U", "╻": "D"}

Cell = Tuple[str, str]                                              # a character and its shade


def cells(line: str) -> List[Cell]:
    """A printed line as one (character, shade) for each column."""
    out, shade = [], ""                                             # type: Tuple[List[Cell], str]
    for piece in re.split(r"(\x1b\[\d+m)", line):
        code = re.fullmatch(r"\x1b\[(\d+)m", piece)
        if code:
            shade = "" if code.group(1) == "0" else code.group(1)
        else:
            out.extend((char, shade) for char in piece)
    return out


def words(row: List[Cell]) -> Iterator[Tuple[int, str, str]]:
    """Each stretch of words in one shade, with the column it starts in. A single space does not end a stretch."""
    column = 0
    for shade, group in groupby(row, key=lambda cell: None if cell[0] in ARMS else cell[1]):
        text = "".join(char for char, _ in group)
        if shade is not None:
            for found in re.finditer(r"\S+(?: \S+)*", text):
                yield column + found.start(), shade, found.group(0)
        column += len(text)


def strokes(rows: List[List[Cell]]) -> Dict[Tuple[str, bool, bool], List[Tuple[float, float, float]]]:
    """Every arm of every box-drawing character as (the line it lies on, from, to), kept by shade, weight and direction."""
    spans = {}                                                      # type: Dict[Tuple[str, bool, bool], List[Tuple[float, float, float]]]
    for down, row in enumerate(rows):
        for along, (char, shade) in enumerate(row):
            arms = ARMS.get(char, "")
            heavy, arms = arms.isupper(), arms.lower()
            x, y = SIDE + CELL * (along + 0.5), TOP + ROW * (down + 0.5)
            corner = STROKE[heavy] / 2 if set(arms) & set("lr") and set(arms) & set("ud") else 0.0    # square where it turns
            for arm in arms:
                across = arm in "lr"
                middle, reach = (x, CELL / 2) if across else (y, ROW / 2)
                start, end = (middle - reach, middle + corner) if arm in "lu" else (middle - corner, middle + reach)
                spans.setdefault((shade, heavy, across), []).append((y if across else x, start, end))
    return spans


def joined(spans: List[Tuple[float, float, float]]) -> List[List[float]]:
    """Spans on one line that touch become one span, so a border is one stroke and not eighty."""
    out = []                                                        # type: List[List[float]]
    for line, start, end in sorted((round(line, 2), round(start, 2), round(end, 2)) for line, start, end in spans):
        if out and out[-1][0] == line and start <= out[-1][2]:
            out[-1][2] = max(out[-1][2], end)
        else:
            out.append([line, start, end])
    return out


def number(value: float) -> str:
    return "{0:.2f}".format(value).rstrip("0").rstrip(".")


def picture() -> str:
    """The opener as it prints on a terminal, under the command that prints it, as an SVG."""
    printed = io.StringIO()
    Page(printed, WIDTH, True).opener()
    rows = [[(char, "2") for char in COMMAND], []] + [cells(line) for line in printed.getvalue().splitlines()]
    wide, high = SIDE * 2 + CELL * WIDTH, TOP * 2 + ROW * len(rows)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 0 {0} {1}" role="img" '
           'aria-label="{2}">'.format(number(wide), number(high), escape(SAYS)),
           "<title>{0}</title>".format(escape(SAYS)),
           '<rect x="0.5" y="0.5" width="{0}" height="{1}" rx="12" fill="{2}" stroke="{3}"/>'.format(
               number(wide - 1), number(high - 1), PAPER, EDGE),
           '<g fill="none">']
    for (shade, heavy, across), spans in sorted(strokes(rows).items()):
        drawn = "".join(("M{1} {0}H{2}" if across else "M{0} {1}V{2}").format(*map(number, span)) for span in joined(spans))
        out.append('<path stroke="{0}" stroke-width="{1}" d="{2}"/>'.format(INK[shade], number(STROKE[heavy]), drawn))
    out += ["</g>", '<g font-family="{0}" font-size="{1}">'.format(FONT, SIZE)]
    for down, row in enumerate(rows):
        for column, shade, text in words(row):
            out.append('<text x="{0}" y="{1}" textLength="{2}" fill="{3}"{4}>{5}</text>'.format(
                number(SIDE + CELL * column), number(TOP + ROW * (down + 0.5) + SIZE * 0.34), number(CELL * len(text)),
                INK[shade], ' font-weight="700"' if shade == "1" else "", escape(text)))
    return "\n".join(out + ["</g>", "</svg>"]) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Draw the opener of ./taos demo as docs/opener.svg.")
    how = parser.add_mutually_exclusive_group(required=True)
    how.add_argument("--write", action="store_true", help="draw the picture again")
    how.add_argument("--verify", action="store_true", help="fail if the saved picture is not what the opener prints now")
    args = parser.parse_args(argv)
    drawn = picture()
    if args.write:
        PICTURE.write_text(drawn, encoding="utf-8")
        print("wrote docs/opener.svg")
        return 0
    if not PICTURE.exists() or PICTURE.read_text(encoding="utf-8") != drawn:
        print("docs/opener.svg is not what the opener prints now. Draw it again: python3 docs/opener.py --write", file=sys.stderr)
        return 1
    print("docs/opener.svg is what the opener prints now.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
