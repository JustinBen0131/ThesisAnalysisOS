@AGENTS.md

# Claude Code notes

`AGENTS.md` above is the contract for work inside `quantAnalysisOS/`. It applies
to every agent the same way.

- Run `./qaos` from this folder. It needs Python 3.9 or newer and numpy.
- The record is the repository. A cloud session is thrown away when it ends, so
  anything worth keeping is in `book/` and committed before you stop.
- Vendor data (Yahoo, Stooq, FRED) needs the environment's network policy to
  allow those hosts. If a fetch is refused, say which host, and carry on with
  what does not depend on it. Do not stand in for missing prices with made-up ones.
