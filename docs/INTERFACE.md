# The interface, in six rules

Everything a person sees from this system follows the same six rules: the
command line, the demo, the pictures and the website. They are short on
purpose. A rule that needs a paragraph to defend it is not one of these.

## 1. The answer comes first

A result gets one of four answers, and the answer is the first word of its
row. The reason follows on the same line.

```text
  holds    the fit passes its check, on the files as they are now
  stale    one swing was measured again: data/swings.csv changed
  fails    the check ran and did not pass
  unknown  nothing recorded says either way
```

A person scanning the left edge of a screen reads the state of the work
without reading a sentence.

## 2. Four words, and they keep their meaning

`holds`, `stale`, `fails`, `unknown`. Nothing else is an answer, and none of
them is used loosely. *Stale* never means old; it means something the result
stood on has changed. *Unknown* is an answer, not an error. The system
answers about itself in the same words: each row of `taos doctor` is led by
`holds` or `fails`, and a caution that is not an answer is marked `warn` and
takes no shade.

## 3. A shade carries meaning or it is not used

On a terminal the four answers are green, amber, red and gray, and the four
letters of the mark carry the same four shades, so the mark is the legend.
Nothing else is colored. Every screen reads the same with color off: a pipe
gets plain text, and `NO_COLOR` is honored.

## 4. One screen first, everything on request

What a command prints by default fits one screen. The full account is one
flag away (`taos demo --full`, `taos status --full`, `taos why <task>`),
never the default. The help keeps the same order: the core commands come
first, and every group after them is marked optional.

## 5. One run, three readers

The same run is written for a person at a terminal, for a pipe, and for a
program (`--json`). The three never disagree, because they are written from
one record.

## 6. Plain words, and a way forward

A message says what happened in words a newcomer knows, and ends with the
command to run next. On a terminal that command is written the way you
started taos (`./taos status` in a fresh clone), so it can be pasted as
shown. A mistyped command is answered with the nearest real
one. Asked nothing, `taos` says who it is and where to start.

## Where each rule is kept

| Rule | Kept by |
|---|---|
| The answer comes first; four words | `taos_core/page.py` (`ANSWERS`, `SHADE`), `tests/test_demo.py` |
| Shades | `page.Shaded`, `page.shades`, `tests/test_first_minute.py` |
| One screen | `tests/test_demo.py` (the short page fits one screen and matches `README.md`), `tests/test_first_minute.py` (`taos status` fits one screen and one width) |
| One run, three readers | `taos_core/demo.py` (`play` makes the record; `page.write` and `--json` read it) |
| Plain words, a way forward | `taos_core/cli.py` (`START`, `FRESH`, `GROUPS`, `LAYERS`, the answer to a mistyped command), `taos_core/page.py` (`launcher`, `commands`), `tests/test_first_minute.py` |
| The picture cannot drift | `docs/opener.py --verify`, run by every check job |
