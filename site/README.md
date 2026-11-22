# The public page

The public site lets a reader follow an edit to a pendulum measurement, inspect
the fit before and after the edit, and find the files behind each result.
The build captures the output of `./taos demo`, reads the saved experiments
from `evals/results/`, and verifies the software claim register. It stops if a
required measurement is stale, a checked claim fails to hold, an expected demo
line disappears, or a link to a local page or download has no target.

From the repository root, build and serve a local copy.

```bash
python3 site/build.py                # writes ./_site
python3 -m http.server --directory _site 8000
```

Open [the local site](http://localhost:8000/), then choose **Evidence**.
The pendulum case browser shows the six measurements, their fitted result
and the output of the fresh check. The evidence page also links the protocol,
raw JSON, experiment script and independent verifier. The instrument comparison
follows corrected scores into the separate and pooled fault counts. A seven-request
handoff audit shows when another task can reuse an earlier pendulum fit.
The source index provides line links and a downloadable snapshot of clean builds.

The evidence page also links to `records/pendulum-boundaries.json`.
This check exercises the example's actual acceptance rule at its cutoffs.
Reproduce it with `python3 evals/check_measurement_boundaries.py --json`.
The original 36-case audit and its numerical fits are recorded separately.

Each page has a Markdown version. `claims.json` contains the software claim
readback. `graph.json` connects runs and claims to their inputs. `standing.json`
lists the input files used for the site and their Git blob hashes. With JavaScript
enabled, the footer compares those hashes with the repository and reports whether
the files still match.

In the interactive graph, files sit at the back and claims at the front. Larger circles represent recorded measurements. An edit in the preview affects only that browser session. A measured claim follows its recorded run. The preview flags a tested claim when one of its named files changes. The repository reruns its test on each change.

**For AI agents** opens `llms.txt`. Each of the six original studies has a human page, a short Markdown reading, the original data, and the exact fields behind its comparisons. Each page advertises its Markdown and raw data in its HTML head. The catalog at `research-catalog.json` uses Schema.org Dataset metadata. A clean source ZIP includes the recorded bytes. On the main repository deployment the catalog also links to the precise Git revision. [llms.txt](https://llmstxt.org/) · [Dataset metadata](https://developers.google.com/search/docs/appearance/structured-data/dataset)

Save the hashes in `research-versions.json` to distinguish changes to the raw observations, the written reading and the rendered page. The build checks the comparisons and their source fields before writing `research-audit.json`. To repeat this verification against a downloaded site, run `python3 site/verify_research_guide.py _site --json`. The source manifest at `source/index.json` lists checksums and plain-text downloads for the files readers need.

The research exchange at `exchange/` connects a question, the evidence it cites, and replies that name the exact earlier entry. Read the threads in HTML, read `exchange/index.md` as an agent, or subscribe to `exchange/feed.json` with a feed reader. The full entry and the original data can be checked offline. Teams can deliberately share a checked contribution through the repository for review. A visit or a feed fetch adds no entry. [JSON Feed 1.1](https://www.jsonfeed.org/version/1.1/) · [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901)

The unequal-instrument follow-up uses the original classifier on 24 fictional readings. The raw observation, controls and exact input fingerprints are at `records/instrument-imbalance.json` in the built site. Run `python3 evals/replay_instrument_imbalance.py --json` in the source checkout to repeat it.

The exchange also includes a model of assistants passing research results between tasks. Its 40 simulated worlds let a reader compare checking inputs, rerunning a calculation and trusting an earlier copy under the same programmed conditions. The simulator, settings and five original predictions are described in [the method](../docs/EXCHANGE_SIMULATION.md). Reproduce the saved simulation with `python3 evals/exchange_simulation.py --verify`.

For a worked example, start at `llms.txt` and follow its link to `graph.json`.
The graph names the build revision. Each recorded run has a raw JSON link
relative to the graph and a SHA-256 digest of the downloaded bytes.
`worked_traversals.corrected_pendulum_reading` follows one edited CSV into two
experiments. Its JSON Pointers locate the fits before and after the correction
and the handoff observations from the task that made the edit and the next task.

The homepage opens with a still diagram of the research operating system showing
the project record that assistants share as they work on different parts of one
question. **See the system at work** starts a five-step
pendulum handoff using the published dependency graph. The reader can pause,
move between steps or return to the architecture. Reduced motion uses manual
steps, and the final result stays visible.
It neither edits the files nor executes a check. The pendulum values beside it
come from the saved audit. The page still shows the recorded demo and source links
with JavaScript disabled. The site uses system fonts and static files.

For a private film layout review, pass `--preview-film-dir DIRECTORY` to the local build.
Supply `film.mp4` for a single cut. For *Morning Departures*, supply
`Morning-departures.mp4` and `Morning-departures-reduced-motion.mp4` together.
Each format accepts one poster (`poster.jpg`, `poster.png` or `poster.webp`) and
optional `captions.vtt`. The player opens on the poster just before **How to read
a saved check**. **AI operating system demo** takes the reader
to the film and starts it with sound. A reader who scrolls to it can press **Play
with sound**. The browser selects the
reduced-motion cut when the reader has enabled that preference. Use a separate
output directory for the private preview. Release builds exclude the film and poster.

On the original repository, GitHub builds the site from a push to main only after
the self-tests, claim readback and scientific audit jobs pass. The manual **site**
action uses that same workflow on main. The release build checks its commit and
requires a downloadable ZIP whose files match that commit. A Pages deployment
uses the artifact from that build. A template copy runs the tests and skips the
project-specific site build and deployment.
