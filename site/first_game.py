"""The homepage game and its text reading, from the same fictional scenarios."""

from html import escape


TITLE = "Play the game"
INTRO = "Your flight moved. Which plans need another look?"
VERDICTS = {
    "holds": ("✓", "The recorded conditions still match."),
    "stale": ("△", "Something the result depended on changed. Check it again."),
    "fails": ("×", "A check ran under the current conditions and did not pass."),
    "unknown": ("?", "There is too little recorded evidence to tell whether it holds."),
}

ROUNDS = (
    {
        "label": "The flight",
        "answer_view": "flight-results",
        "reveal": "Which plans still hold?",
        "title": "An AI agent planned your weekend.",
        "change": "Your Saturday flight now lands at 5:10 PM. The original arrival time was 2:10 PM.",
        "question": "Which plans would you check again?",
        "plans": (
            ("Airport pickup", "2:30 PM at arrivals", (), "stale", "Depended on the original arrival time."),
            ("Dinner table", "7:00 PM downtown", (), "stale", "Depended on arrival time and the drive downtown."),
            ("Hotel", "One night with late check-in", (), "holds", "The date and late check-in are the same."),
            ("Museum tickets", "Sunday at 10:00 AM", (), "holds", "The Sunday plan is unchanged."),
        ),
        "lesson": "A changed input puts both plans back in question. Check each one to find out whether it still works.",
        "correct": "Exactly. The pickup and dinner both depended on your arrival time.",
    },
    {
        "label": "The report",
        "answer_view": "report-results",
        "reveal": "The report after the correction",
        "title": "An AI agent wrote your sales report.",
        "change": "sales.csv was corrected. One order had been entered twice.",
        "question": "Which results use the corrected file?",
        "plans": (
            ("Total sales", "Headline number", ("sales.csv",), "stale", "The sum used the corrected sales file."),
            ("Monthly chart", "Sales by month", ("sales.csv", "colors.txt"), "stale",
             "The bars used the corrected sales file. The colors are unchanged."),
            ("Team list", "Names by region", ("team.txt",), "holds", "The team file is unchanged."),
            ("Growth figure", "“12%” from an old chat", (), "unknown",
             "Find a source and check it before using it."),
        ),
        "lesson": "The recorded inputs show which results need checking again. The growth figure needs its own evidence.",
        "correct": "Exactly. The total and the chart both use sales.csv.",
    },
)

RECHECKED = (
    ("Airport pickup", "2:30 PM at arrivals", (), "fails", "The pickup is now before you land. Move it."),
    ("Dinner table", "7:00 PM downtown", (), "holds",
     "Allow 45 minutes to leave the airport and 35 to drive. You still arrive by 6:30 PM."),
)
RECHECK_LESSON = "One plan has to change. The other still works after you check it with the new arrival time."
SCALE_TITLE = "Now imagine a month of work."
SCALE_SIZE = 400
SCALE_START = 4
SCALE_AFFECTED = 37
SCALE_INTRO = "You just checked four plans. What if you had 400 results to keep track of?"
SCALE_LESSON = ("In this fictional example, one corrected file affects 37 of 400 recorded results. "
                "A notebook that tracks their inputs would point you to those 37. "
                "The other 363 use unchanged inputs.")
ILLUSTRATION = "The stories and counts are fictional."


def _verdict(state):
    mark, _meaning = VERDICTS[state]
    return (f'<span class="first-game__verdict" data-verdict="{state}">'
            f'<span aria-hidden="true">{mark}</span> {state}</span>')


def _cards(plans, *, choose=False, show_inputs=False):
    cards = []
    for name, detail, inputs, state, reason in plans:
        source = ""
        if show_inputs:
            files = " ".join(f"<code>{escape(file)}</code>" for file in inputs)
            source = (f'<span class="first-game__inputs">Uses {files}</span>' if inputs else
                      '<span class="first-game__inputs">No source recorded</span>')
        description = (f'<span class="first-game__plan-title">{escape(name)}</span>'
                       f'<span class="first-game__plan-detail">{escape(detail)}</span>{source}')
        if choose:
            card = ('<label class="first-game__card first-game__choice">'
                    f'<input type="checkbox" name="plan" data-verdict="{state}">'
                    f'<span>{description}</span></label>')
        else:
            card = (f'<li class="first-game__card first-game__answer" data-verdict="{state}">'
                    f'<div class="first-game__answer-head"><div>{description}</div>{_verdict(state)}</div>'
                    f'<p>{escape(reason)}</p></li>')
        cards.append(card)
    joined = "".join(cards)
    if choose:
        return joined
    return f'<ul class="first-game__cards" role="list">{joined}</ul>'


def _round_header(round_, title):
    return (f'<p class="first-game__stage-label">{round_["label"]}</p>'
            f'<h2 tabindex="-1">{title}</h2>'
            f'<div class="first-game__change"><strong>Update</strong><p>{round_["change"]}</p></div>')


def _round(index, *, choose=False, feedback=False):
    round_ = ROUNDS[index]
    show_inputs = index == 1
    header = _round_header(round_, round_["reveal"] if feedback else round_["title"])
    if choose:
        return (f'{header}<div data-choice data-reveal="{round_["answer_view"]}" data-correct="{escape(round_["correct"], quote=True)}">'
                f'<fieldset><legend>{round_["question"]}</legend>'
                f'<div class="first-game__cards">{_cards(round_["plans"], choose=True, show_inputs=show_inputs)}</div>'
                '</fieldset><button type="button" class="button" data-reveal-choice>Reveal the answers</button></div>')
    response = ('<p class="first-game__feedback" data-game-feedback></p>' if feedback else
                f'<p>{round_["question"]}</p>')
    return (f'{header}{response}{_cards(round_["plans"], show_inputs=show_inputs)}'
            f'<p class="first-game__lesson">{round_["lesson"]}</p>')


def _rechecked():
    return ('<h2 tabindex="-1">What happened when you checked again?</h2>'
            f'{_cards(RECHECKED)}<p class="first-game__lesson">{RECHECK_LESSON}</p>')


def _verdicts():
    items = "".join(f'<div><dt>{_verdict(state)}</dt><dd>{meaning}</dd></div>'
                    for state, (_mark, meaning) in VERDICTS.items())
    return f'<dl class="first-game__definitions">{items}</dl>'


def _after_game(lesson_href):
    return f'<a class="button" href="{escape(lesson_href, quote=True)}">Try the pendulum demo</a>'


def _scale(lesson_href):
    # 137 and 400 are coprime, so these 37 fictional flags cannot repeat.
    affected = {index * 137 % SCALE_SIZE for index in range(SCALE_AFFECTED)}
    dots = "".join(
        '<span class="first-game__dot'
        + (" first-game__dot--initial" if index < SCALE_START else "")
        + (" first-game__dot--affected" if index in affected else "")
        + '"></span>' for index in range(SCALE_SIZE)
    )
    return (
        f'<h2 tabindex="-1">{SCALE_TITLE}</h2><p>{SCALE_INTRO}</p>'
        '<div class="first-game__scale">'
        f'<div class="first-game__field" data-field data-phase="start" aria-hidden="true">{dots}</div>'
        '<div class="first-game__scale-copy">'
        f'<p class="first-game__scale-label" data-scale-label>{SCALE_START} results</p>'
        '<p class="first-game__fiction">Fictional illustration</p>'
        '<button type="button" class="button" data-action="grow">A month later</button>'
        '<button type="button" class="button" data-action="correct" hidden>Correct one file</button>'
        f'<p class="first-game__lesson" data-scale-lesson hidden>{SCALE_LESSON}</p>'
        '</div></div>'
        f'<div data-game-end hidden>{_verdicts()}<div class="first-game__actions">{_after_game(lesson_href)}'
        '<button type="button" class="button ghost" data-action="flight">Play again</button></div></div>'
    )


def _answer_round(index, action, button):
    return (f'{_round(index, feedback=True)}'
            f'<button type="button" class="button" data-action="{action}">{button}</button>')


def render_game(lesson_href="#run"):
    """Return one self-contained disclosure, ready for the home page."""
    views = {
        "flight": _round(0, choose=True),
        "flight-results": _answer_round(0, "recheck", "Check the two again"),
        "recheck": _rechecked() + '<button type="button" class="button" data-action="report">Next: the sales report</button>',
        "report": _round(1, choose=True),
        "report-results": _answer_round(1, "scale", "Now try a month of work"),
        "scale": _scale(lesson_href),
    }
    templates = "".join(f'<template data-game-view="{name}">{body}</template>' for name, body in views.items())
    fallback = (
        f'<p class="first-game__fiction">{ILLUSTRATION}</p>'
        f'<div class="first-game__reading-block">{_round(0)}{_rechecked()}</div>'
        f'<div class="first-game__reading-block">{_round(1)}</div>'
        f'<div class="first-game__reading-block"><h2>{SCALE_TITLE}</h2><p>{SCALE_LESSON}</p>{_verdicts()}</div>'
        f'{_after_game(lesson_href)}'
    )
    return (
        '<div class="first-game-wrap"><details class="first-game" id="first-game" data-first-game>'
        '<summary><span class="first-game__summary-text">'
        f'<strong>{TITLE}</strong><span>{INTRO}</span></span>'
        '<span class="first-game__chevron" aria-hidden="true"></span></summary>'
        f'<div class="first-game__reading" data-game-reading>{fallback}</div>'
        '<div class="first-game__content" data-game-content hidden>'
        f'<p class="first-game__fiction">{ILLUSTRATION}</p><div data-game-stage></div>'
        '<p class="first-game__live" role="status" aria-atomic="true" data-game-live></p></div>'
        f'{templates}</details></div>'
    )


def _plain_cards(plans, *, show_inputs=False):
    lines = []
    for name, detail, inputs, state, reason in plans:
        source = ""
        if show_inputs:
            files = ", ".join(f"`{file}`" for file in inputs)
            source = f" Uses {files}." if inputs else " No source recorded."
        lines.append(f"- **{name}** ({detail}). **{state}**. {reason}{source}")
    return "\n".join(lines)


def game_markdown(lesson_href="./#run"):
    """Return the same scenarios, answers and terms for readers of index.md."""
    parts = [f"## {TITLE}\n\n{INTRO} {ILLUSTRATION}"]
    for index, round_ in enumerate(ROUNDS):
        parts.append(f"### {round_['label']}\n\n{round_['title']} {round_['change']} {round_['question']}"
                     f"\n\n{_plain_cards(round_['plans'], show_inputs=index == 1)}\n\n{round_['lesson']}")
        if index == 0:
            parts.append(f"**What happened when you checked again?**\n\n{_plain_cards(RECHECKED)}\n\n{RECHECK_LESSON}")
    meanings = "\n".join(f"- **{state}**. {meaning}" for state, (_mark, meaning) in VERDICTS.items())
    parts.append(f"### {SCALE_TITLE}\n\n{SCALE_INTRO}\n\n{SCALE_LESSON}\n\n{meanings}"
                 f"\n\n[Try the pendulum demo]({lesson_href})")
    return "\n\n".join(parts) + "\n"
