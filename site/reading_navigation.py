"""Navigation for the research pages and their browsable source files."""
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from string import Template

_HEADER = Template(Path(__file__).with_name("visitor_header.html").read_text(encoding="utf-8"))
THEME_INTEGRITY = "sha256-" + b64encode(sha256((Path(__file__).parent / "assets/theme.js").read_bytes()).digest()).decode("ascii")
APPEARANCE = ('<label class="reader-appearance" hidden>Appearance '
              '<select id="reader-appearance"><option value="system">System</option>'
              '<option value="light">Light</option><option value="dark">Dark</option></select></label>')


def header(root, path):
    return _HEADER.substitute(home=root if path else "", root=root,
                              current_hpc=' aria-current="page"' if path == "hpc/" else "")
