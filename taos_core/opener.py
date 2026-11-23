"""Five terminal rows replay a recorded pendulum check before the static welcome."""

import math
from typing import Callable, List, Tuple

# The baseline, changed input and recheck are verified against the JSON from taos demo.
SAVED_PERIOD, NEW_PERIOD = 2.19, 2.21
SAVED_G, NEW_G, ERROR_G = 9.82, 9.75, 0.02
DURATION = 3.8
CHANGE, RECHECK = 0.29, 0.66
DOTS = ((1, 2, 4, 64), (8, 16, 32, 128))
Ink = Callable[[str, str], str]
Segment = Tuple[str, str]


def pendulum(at: float, ink: Ink, shade: str) -> List[str]:
    """Draw the pivot, arc, thread and bob on a 34 by 12 dot grid."""
    grid = [[0] * 17 for _ in range(3)]
    bob = [[0] * 17 for _ in range(3)]

    def dot(x: int, y: int, bright: bool = False) -> None:
        cell = bob if bright else grid
        cell[y // 4][x // 2] |= DOTS[x % 2][y % 4]

    def position(angle: float) -> Tuple[int, int]:
        return round(16 + 11 * math.sin(angle)), round(0.5 + 9 * math.cos(angle))

    # Keep the swing continuous when the period changes. The arc is illustrative.
    cycles = DURATION * (min(at, CHANGE) / SAVED_PERIOD + max(0.0, at - CHANGE) / NEW_PERIOD)
    x, y = position(0.78 * math.cos(2 * math.pi * cycles))
    for mark in range(-5, 6):
        dot(*position(mark * 0.155))
    for anchor in range(12, 21):
        dot(anchor, 0)
    for i in range(1, y + 1):
        dot(round(16 + (x - 16) * i / y), i, True)
    for dx, dy in ((-1, 0), (1, 0), (0, 1), (0, -1)):
        dot(x + dx, y + dy, True)
    rows = []
    for etched, lit in zip(grid, bob):
        row = []
        for background, foreground in zip(etched, lit):
            bits = background | foreground
            row.append(ink(shade if foreground else "2", chr(0x2800 + bits)) if bits else " ")
        rows.append("".join(row))
    return rows


def frame(at: float, ink: Ink, width: int = 80) -> List[str]:
    """Draw the recorded example. No project, subprocess or terminal state is read."""
    stage = 2 if at >= RECHECK else 1 if at >= CHANGE else 0
    answer, color = ("stale", "33") if stage == 1 else ("holds", "32")
    period = (f"{SAVED_PERIOD:.2f} s", f"{SAVED_PERIOD:.2f} → {NEW_PERIOD:.2f} s", f"{NEW_PERIOD:.2f} s")[stage]
    gravity = NEW_G if stage == 2 else SAVED_G
    note = ("The saved fit passed.", "The timing changed. Recheck the saved fit.",
            "The fit passed on the revised timing.")[stage]

    def rail(left: List[Segment], right: List[Segment]) -> str:
        count = sum(len(word) for _, word in left + right)
        return ("".join(ink(style, word) for style, word in left) + ink("2", "─" * (width - count))
                + "".join(ink(style, word) for style, word in right))

    top = rail([("2", "┌─ "), ("1", "TAOS"), ("2", " ── "), ("", "Pendulum replay"), ("2", " ")],
               [("2", " "), ("", "PEN-1 / fit"), ("2", " ─┐")])
    path = [("2", "└─ ")]
    for i, (name, done) in enumerate((("saved", "32"), ("input changed", "33"), ("rechecked", "32"))):
        if i:
            path.append(("2", " ─── "))
        path.append((done if i <= stage else "2", ("● " if i == stage else "· ") + name))
    path.append(("2", " "))
    foot = rail(path, [("2", "┘")])

    details = [
        [("1", "data/swings.csv"), ("2", "   ·   1.20 m pendulum")],
        [("2", "period  "), ("1", period.ljust(17)), ("2", "g  "),
         ("", f"{gravity:.2f} ± {ERROR_G:.2f} m/s²")],
        [("1;" + color, ("◆ " if stage == 1 else "● ") + answer), ("", "   " + note)],
    ]
    rows = [top]
    for picture, parts in zip(pendulum(at, ink, color), details):
        room = width - 22
        body = "".join(ink(style, word) for style, word in parts)
        pad = " " * (room - sum(len(word) for _, word in parts))
        rows.append(ink("2", "│") + picture + ink("2", "│") + "  " + body + pad + ink("2", "│"))
    return rows + [foot]
