# The public page

`build.py` writes the site from the repository's own records. Nothing on it is
typed in twice: the run it steps through is the output of `./taos demo`, the
numbers come from `evals/results/`, and the claims from `docs/CLAIMS.md` with
the standing `evals/claims.py` gives them. The build stops if a recorded run
no longer stands, if a claim does not hold, if the demo stops printing a line
the page explains, or if a link inside the page leads nowhere.

```bash
python3 site/build.py                # writes ./_site
python3 -m http.server --directory _site 8000
```

Each page is written for two readers from one source: HTML for a person, and
Markdown, `llms.txt`, `claims.json` and `standing.json` for an agent.
`standing.json` lists the files the page was built from, by git blob hash.
In a browser the page asks the repository whether those files are still the
same, and answers `holds`, `stale` or `unknown` in its last line.

There is no framework and nothing to install. `assets/style.css` uses system
fonts, and `assets/site.js` does two things: it shows the run one moment at a
time, and it asks that question. Without scripts every step is still shown.

If you made your own repository from this template, delete this folder and
`.github/workflows/pages.yml`. They describe this project, not yours.
