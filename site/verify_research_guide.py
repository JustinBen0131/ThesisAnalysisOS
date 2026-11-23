"""Verify the generated research guide and its evidence without network access."""

import argparse
import ast
from base64 import b64encode
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from hashlib import sha256
from html.parser import HTMLParser
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
from xml.etree import ElementTree
from urllib.parse import unquote, urljoin, urlsplit
from zipfile import BadZipFile, ZipFile


STUDIES = {
    "at_revision", "mutations", "reuse_frontier", "measurement_audit",
    "model_evaluation", "handoff_audit", "session_footprint",
}
DECISION_FIXTURES = {
    "approval": ("taos_core/tasks.py", ("TaskStore.accept",),
                 "tests/test_standing.py", "TestWhy.test_acceptance_is_of_one_version_and_does_not_carry_over"),
    "instruction": ("taos_core/rules.py", ("governing", "_governing", "displaced_by", "in_force", "covers"),
                    "tests/test_counterexamples.py",
                    "TestInstructionsKeepTheirTime.test_a_later_replacement_does_not_erase_the_earlier_answer"),
    "control": ("taos_core/changes.py", ("score",), "tests/test_science.py",
                "TestChanges.test_confirmed_refuted_and_control_moved"),
}
DETAIL_ROUTES = {
    "at_revision": "evidence/#revision-comparison",
    "mutations": "evidence/#seeded-faults",
    "reuse_frontier": "evidence/#reuse-full",
    "handoff_audit": "evidence/#handoff-audit",
    "session_footprint": "evidence/#session-reading",
    "measurement_audit": "evidence/pendulum/",
    "model_evaluation": "evidence/model-evaluation/",
}
RAW_TEXT = {".md", ".markdown", ".py", ".txt", ".json", ".csv", ".tsv", ".yml", ".yaml", ".toml"}
DIGEST = re.compile(r"[a-f0-9]{64}")
INDEX = re.compile(r"0|[1-9][0-9]*")
JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
MD_LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")
REPORT = "research-audit.json"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def unique(mapping):
    result = {}
    for key, value in mapping:
        require(key not in result, f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def invalid_number(value):
    raise ValueError(f"Invalid JSON number {value}")


def load(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_number)


def hash_bytes(data):
    return sha256(data).hexdigest()


class Page(HTMLParser):
    def __init__(self, data):
        super().__init__()
        self.links, self.metadata, self.rows, self.ids = [], [], [], set()
        self.source_lines = {}
        self.scripts = []
        self._script = self._row = self._cell = None
        self._source_line = self._source_text = None
        self.feed(data.decode("utf-8"))
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag in {"link", "a"} and "href" in attrs:
            self.links.append((tag, attrs))
        if tag == "script":
            self.scripts.append(attrs)
            if attrs.get("type") == "application/ld+json":
                self._script = []
        if tag == "tr":
            self._row = []
        if tag in {"th", "td"} and self._row is not None:
            self._cell = []
        if tag == "li" and re.fullmatch(r"L[1-9][0-9]*", attrs.get("id", "")):
            self._source_line = int(attrs["id"][1:])
        if tag == "code" and self._source_line is not None:
            self._source_text = []

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._source_text is not None:
            self._source_text.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.metadata.append(load("".join(self._script)))
            self._script = None
        if tag in {"th", "td"} and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        if tag == "code" and self._source_text is not None:
            require(self._source_line not in self.source_lines, f"Repeated source line {self._source_line}")
            self.source_lines[self._source_line] = "".join(self._source_text)
            self._source_text = None
        if tag == "li":
            self._source_line = None

    def described(self, relation, mime=None):
        return [d["href"] for tag, d in self.links if tag == "link"
                and relation in d.get("rel", "").split() and (mime is None or d.get("type") == mime)]


class Site:
    def __init__(self, root):
        self.root = root.resolve()
        self.versioned_paths = set()
        self.home = Page((self.root / "index.html").read_bytes())
        canonicals = self.home.described("canonical")
        require(len(canonicals) <= 1, "Homepage has competing canonical URLs")
        self.hosted = bool(canonicals)
        self.base = urlsplit(canonicals[0] if canonicals else "https://offline.invalid/")
        require(self.base.scheme in {"http", "https"} and bool(self.base.netloc)
                and self.base.path.endswith("/") and not self.base.query and not self.base.fragment,
                "Homepage canonical URL must be a site base")

    def url(self, reference, document="index.html"):
        return urlsplit(urljoin(urljoin(self.base.geturl(), document), reference))

    def path(self, reference, document="index.html", *, check=True):
        url = self.url(reference, document)
        prefix, target = unquote(self.base.path), unquote(url.path)
        require((url.scheme, url.netloc) == (self.base.scheme, self.base.netloc)
                and target.startswith(prefix), f"External or out-of-site link {reference!r} in {document}")
        suffix = target[len(prefix):]
        require(not suffix.startswith("/") and "\\" not in suffix and "\0" not in suffix
                and ".." not in PurePosixPath(suffix).parts, f"Unsafe site path {reference!r}")
        path = self.root / suffix
        if target.endswith("/") or path.is_dir():
            path /= "index.html"
        require(path.resolve().is_relative_to(self.root), f"Path escapes the built site: {reference!r}")
        if check:
            require(path.is_file(), f"Broken link {reference!r} in {document}")
            if url.fragment and path.suffix == ".html":
                require(unquote(url.fragment) in Page(path.read_bytes()).ids,
                        f"Missing anchor {reference!r} in {document}")
        return path

    def has_link(self, page, relation, mime, wanted, document):
        targets = page.described(relation, mime)
        require(any(self.path(href, document) == wanted for href in targets),
                f"{document} lacks the {relation} link for {wanted.name}")

    def hash_item(self, item, expected):
        path = self.path(item["href"])
        require(path == self.root / expected, f"Expected {expected} in the study version manifest")
        data = path.read_bytes()
        require(item["sha256"] == hash_bytes(data), f"Version hash mismatch for {expected}")
        self.versioned_paths.add(path)
        return data

    def markdown_links(self, document, data, *, writing_report=False):
        references = []
        for href in MD_LINK.findall(data.decode("utf-8")):
            url = self.url(href, document)
            if (url.scheme, url.netloc) == (self.base.scheme, self.base.netloc):
                path = self.path(href, document, check=False)
                pending = (writing_report and document == "llms.txt" and path in {self.root / REPORT, self.root / "release.json"}
                           and not url.query and not url.fragment)
                if not pending:
                    self.path(href, document)
                references.append(path)
        return references


def pointer(document, address):
    """Resolve RFC 6901 syntax and the nearest named array row."""
    require(isinstance(address, str) and (not address or address.startswith("/")) and not re.search(r"~(?![01])", address),
            f"Invalid observation JSON Pointer: {address!r}")
    value, identity = document, {}
    for token in address[1:].split("/") if address else ():
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            require(INDEX.fullmatch(key) and int(key) < len(value), f"Invalid array index at {address}")
            value = value[int(key)]
            if isinstance(value, dict):
                name = next((field for field in ("id", "policy") if field in value), None)
                if name:
                    identity = {name: value[name]}
        else:
            require(isinstance(value, dict) and key in value, f"No value at {address}")
            value = value[key]
    return value, identity


def locate(record, array, identity, key="id"):
    matches = [(index, row) for index, row in enumerate(record[array]) if row[key] == identity]
    require(len(matches) == 1, f"Expected one {identity!r} in /{array}")
    index, row = matches[0]
    return row, f"/{array}/{index}"


def fields(prefix, *names):
    return [prefix + "/" + name for name in names]


def verdict(code):
    return "passed" if code == 0 else "failed"


def expected_observations(stem, raw):
    """Independent expectations keyed by evidence fields, without using page-generation code."""
    expectations = {}

    def expect(addresses, text):
        key = frozenset(addresses)
        require(key not in expectations, f"Duplicate expected observation fields in {stem}")
        expectations[key] = text

    if stem == "at_revision":
        subjects = [(f"/revisions/{key}", row) for key, row in raw["revisions"].items()]
        subjects += [("/here", raw["here"])]
        require(len(subjects) == 3, "The revision comparison must have two historical controls")
        for address, row in subjects:
            ran, failed = row["ran"], row["did_not_pass"]
            require(len(row["names"]) == failed <= ran, f"Inconsistent regression counts in {address}")
            expect(fields(address, "ran", "did_not_pass", "names"), f"{failed} of {ran} failed or raised an error")
    elif stem == "mutations":
        names, missed = raw["names"], raw["missed"]
        require(len(names) == len(set(names)) == raw["faults"]
                and set(missed).issubset(names) and raw["caught"] + len(set(missed)) == raw["faults"],
                "Inconsistent seeded fault counts")
        lease = "leases: a lapsed lease can be revived"
        expect(["/caught", "/faults"], f"{raw['caught']} of {raw['faults']} seeded faults")
        expect(["/missed"], ", ".join(missed) or "None")
        expect([f"/names/{names.index(lease)}", "/missed"], "Missed" if lease in missed else "Detected")
    elif stem == "reuse_frontier":
        expect(["/relied_on"], str(raw["relied_on"]))
        for policy in ("rerun everything", "TAOS, 12 domain(s) declared",
                       "oracle (knows what every check reads)", "TAOS, each check hides one folder it reads"):
            row, address = locate(raw, "rows", policy, "policy")
            expect(fields(address, "policy", "executions", "wrong"),
                   f"{row['executions']} executions, {row['wrong']} outdated reuses")
    elif stem == "measurement_audit":
        periods, period_addresses = [], []
        for identity in ("baseline", "row-6-1.05", "omission-1.02", "style"):
            row, address = locate(raw, "cases", identity)
            if identity in {"baseline", "row-6-1.05"}:
                matching = [(i, reading[1]) for i, reading in enumerate(row["rows"]) if Decimal(reading[0]) == Decimal("1.20")]
                require(len(matching) == 1, f"Expected one 1.20 m reading at {address}")
                i, period = matching[0]
                periods.append(period)
                period_addresses.append(f"{address}/rows/{i}")
            expect(fields(address, "id", "g", "se", "retained", "fresh_exit"),
                   f"{row['g']:.4f} ± {row['se']:.4f} m/s² (statistical SE). "
                   f"Earlier pass {row['retained']}, fresh check {verdict(row['fresh_exit'])}.")
        expect(period_addresses, " to ".join(periods) + " s")
    elif stem == "model_evaluation":
        corrected, address = locate(raw, "cases", "offsetting-score-corrections")
        order = raw["cell_order"]
        require(len(order) == 4 and set(order) == {"tp", "fn", "fp", "tn"}, "Invalid confusion table")
        for instrument in ("A", "B", "pooled"):
            before = dict(zip(order, raw["baseline_counts"][instrument]))
            after = corrected["counts"][instrument]
            b = Fraction(before["tp"], before["tp"] + before["fn"])
            a = Fraction(after["tp"], after["tp"] + after["fn"])
            shift = (a - b) * 100
            shift_text = f"{float(shift):+g}" if shift else "0"
            expect([address + "/id", "/cell_order", f"/baseline_counts/{instrument}/{order.index('tp')}",
                    f"/baseline_counts/{instrument}/{order.index('fn')}", f"{address}/counts/{instrument}/tp",
                    f"{address}/counts/{instrument}/fn", f"{address}/result_after_consultation/{instrument}"],
                   f"{before['tp']}/{before['tp'] + before['fn']} to {after['tp']}/{after['tp'] + after['fn']} "
                   f"known faults detected ({shift_text} percentage points). "
                   f"Check status: {corrected['result_after_consultation'][instrument]}.")
        row, address = locate(raw, "cases", "figure-caption")
        expect(fields(address, "id", "executed", "reused"),
               f"{len(row['executed'])} checks executed, {len(row['reused'])} reused")
    elif stem == "session_footprint":
        require(raw["schema"] == "taos-session-footprint-v1", "Unknown session reading record")
        require(set(raw["surfaces"]) == {"compact_status", "task_capsule", "agents_md"}, "Unexpected session reading surfaces")
        for name, row in raw["surfaces"].items():
            text = row["text"].encode("utf-8")
            require((len(text), len(row["text"].splitlines()), hash_bytes(text)) ==
                    (row["bytes"], row["lines"], row["sha256"]), f"Session text disagrees with its recorded size or digest: {name}")
            expect(fields("/surfaces/" + name, "lines", "bytes", "delivery"),
                   f"{row['lines']} lines, {row['bytes']:,} UTF-8 bytes. {row['delivery']}")
    elif stem == "handoff_audit":
        rows = raw["observations"]
        counts = raw["counts"]
        reused = sum(row["execution"] == "reuse" for row in rows)
        executed = sum(row["execution"] == "execute" for row in rows)
        require((len(rows), executed, reused) == (counts["gate_requests"], counts["executions"], counts["reused"]),
                "Handoff totals do not match the recorded chronological rows")
        expect(fields("/counts", "gate_requests", "executions", "reused"),
               f"{len(rows)} requests, {executed} executions, {reused} reuses")
        for row in rows:
            _, address = locate(raw, "observations", row["id"])
            request = {"execute": "executed", "reuse": "reused"}[row["execution"]]
            expect(fields(address, "id", "task", "execution", "exit", "before", "after", "execution_origin"),
                   f"{row['task']} {request} the check ({verdict(row['exit'])}). Status {row['before']} → {row['after']}. "
                   f"The cited run was {row['execution_origin']}.")
    return expectations


def verify_observations(stem, document, raw):
    expected = expected_observations(stem, raw)
    labels, observed, sources = set(), set(), 0
    rows = document["observations"]
    for row in rows:
        label = row["label"]
        require(isinstance(label, str) and label.strip() and label not in labels,
                f"Missing or repeated observation label in {stem}")
        labels.add(label)
        addresses = [ref["pointer"] for ref in row["sources"]]
        key = frozenset(addresses)
        require(bool(key) and len(addresses) == len(key) and key not in observed,
                f"Missing or repeated observation sources in {stem}: {label}")
        require(key in expected and row["value"] == expected[key], f"Wrong observation or raw fields in {stem}: {label}")
        for ref in row["sources"]:
            _, identity = pointer(raw, ref["pointer"])
            require(ref.get("row", {}) == identity,
                    f"Wrong semantic row identity in {stem} at {ref['pointer']}")
        sources += len(addresses)
        observed.add(key)
    require(observed == expected.keys(), f"Incomplete published observations for {stem}")
    return len(rows), sources


def verify_terminal_image(data):
    """The README's generated diagram uses only text, geometry and solid colors."""
    require(b"<?" not in data and b"<!" not in data, "Unexpected markup in the terminal image")
    namespace = "{http://www.w3.org/2000/svg}"
    tags = {namespace + name for name in ("svg", "g", "title", "rect", "text", "path")}
    attrs = {"aria-label", "d", "fill", "font-family", "font-size", "font-weight", "height", "role", "rx",
             "stroke", "stroke-width", "textLength", "viewBox", "width", "x", "y"}
    root = ElementTree.fromstring(data)
    require(root.tag == namespace + "svg", "The terminal image is missing its SVG root")
    for node in root.iter():
        require(node.tag in tags and node.attrib.keys() <= attrs, "Unexpected element or attribute in the terminal image")
        for attr in ("fill", "stroke"):
            if attr in node.attrib:
                require(re.fullmatch(r"none|#[0-9a-fA-F]{6}", node.attrib[attr]), "Unexpected paint in the terminal image")


def verify_sources(site, revision):
    path = site.root / "source/index.json"
    manifest = load(path.read_bytes())
    require(manifest["schema"] == "source-snapshot/1" and manifest["revision"] == revision,
            "Source snapshot belongs to a different build revision")
    manifest_files, raw_paths = {}, set()
    theme = (site.root / "assets/theme.js").read_bytes()
    integrity = "sha256-" + b64encode(sha256(theme).digest()).decode("ascii")
    for entry in manifest["files"]:
        name = entry["path"]
        original = PurePosixPath(name)
        require(not original.is_absolute() and ".." not in original.parts and name not in manifest_files,
                f"Unsafe or repeated source name: {name}")
        require(DIGEST.fullmatch(entry["sha256"]) and entry["bytes"] >= 0, f"Invalid source fingerprint: {name}")
        manifest_files[name] = entry
        viewer = site.path(entry["viewer_url"], "source/index.json")
        require(viewer.is_relative_to(site.root / "source/files"), f"Invalid viewer route: {name}")
        viewer_page = Page(viewer.read_bytes())
        theme_url = posixpath.relpath("assets/theme.js", viewer.relative_to(site.root).parent.as_posix())
        require(viewer_page.scripts == [{"src": theme_url + "?v=" + hash_bytes(theme)[:16], "integrity": integrity}]
                and (entry["bytes"] == 0 or "L1" in viewer_page.ids),
                f"Invalid line-numbered source viewer: {name}")
        link = entry["raw_url"]
        if link is None:
            require(original.suffix.lower() in {".html", ".htm", ".xhtml"}, f"Missing safe raw route: {name}")
            continue
        raw = site.path(link, "source/index.json")
        legal_file = name in {"LICENSE", "NOTICE"} and raw == site.root / "source/raw" / name
        opener = name == "docs/opener.svg" and raw == site.root / "source/raw/docs/opener.svg"
        require(raw.is_relative_to(site.root / "source/raw") and (raw.suffix.lower() in RAW_TEXT or legal_file or opener)
                and raw not in raw_paths and original.suffix.lower() not in {".html", ".htm", ".xhtml"},
                f"Unsafe raw-source route: {link}")
        raw_paths.add(raw)
        data = raw.read_bytes()
        if opener:
            verify_terminal_image(data)
        require(len(data) == entry["bytes"] and hash_bytes(data) == entry["sha256"], f"Changed raw source: {name}")
        route = viewer.relative_to(site.root).as_posix()
        raw_links = [attr["href"] for tag, attr in viewer_page.links
                     if tag == "a" and attr.get("data-raw-source") == "true"]
        require(len(raw_links) == 1 and site.path(raw_links[0], route) == raw,
                f"Viewer does not link its raw source: {name}")
    return manifest_files, len(raw_paths)


def verify_saved_handoff(site, source_files, guide_links):
    handoff = site.root / "workflows/transit/handoff.txt"
    if handoff.exists() or handoff in guide_links:
        source = source_files["examples/transit/workflow.json"]["raw_url"]
        recorded = load(site.path(source, "source/index.json").read_bytes())["observations"]["handoff"]
        require(handoff in guide_links and handoff.read_bytes() == recorded.encode("utf-8"),
                "The plain-text handoff must match the recorded note and be linked from the agent guide")


def verify_decision_source(site, document, entry, expected_path, symbol, sources):
    require(entry["path"] == expected_path and entry["symbol"] == symbol,
            f"Wrong source or symbol in {document}: expected {expected_path}:{symbol}")
    manifest = sources[expected_path]
    raw = site.path(entry["raw_url"], document)
    plain_url = site.url(entry["raw_url"], document)
    require(raw == site.path(manifest["raw_url"], "source/index.json") and not plain_url.query
            and not plain_url.fragment and entry["sha256"] == manifest["sha256"],
            f"Decision source does not match the verified raw file for {symbol}")
    file = raw.read_bytes().decode("utf-8")
    module = ast.parse(file)
    scope = module.body
    owner, separator, name = symbol.rpartition(".")
    if separator:
        matches = [node for node in scope if type(node) is ast.ClassDef and node.name == owner]
        require(len(matches) == 1, f"Expected exactly one class {owner} in {expected_path}")
        scope = matches[0].body
    matches = [node for node in scope if type(node) in {ast.FunctionDef, ast.AsyncFunctionDef} and node.name == name]
    require(len(matches) == 1, f"Expected exactly one function {symbol} in {expected_path}")
    function = matches[0]
    start = min([function.lineno] + [decorator.lineno for decorator in function.decorator_list])
    end = function.end_lineno
    whole_lines = file.splitlines(keepends=True)[start - 1:end]
    require(entry["start_line"] == start and entry["end_line"] == end and entry["text"] == "".join(whole_lines),
            f"Decision source is not the complete span for {symbol}")
    viewer_url = site.url(entry["viewer_url"], document)
    viewer = site.path(entry["viewer_url"], document)
    require(viewer == site.path(manifest["viewer_url"], "source/index.json") and not viewer_url.query
            and viewer_url.fragment == f"L{start}", f"Wrong viewer link for {symbol}")
    shown = Page(viewer.read_bytes()).source_lines
    require([shown.get(line) for line in range(start, end + 1)] == [line.splitlines()[0] for line in whole_lines],
            f"Viewer and quoted source differ for {symbol}")
    return viewer_url


def verify_decisions(site, sources, guide_links):
    reading_path = site.root / "studies/decisions.md"
    require(reading_path in guide_links, "The guide does not link the decision reading")
    reading = reading_path.read_bytes()
    reading_document = "studies/decisions.md"
    reading_links = site.markdown_links(reading_document, reading)
    home_links = {site.url(attrs["href"]) for tag, attrs in site.home.links if tag == "a"}
    home_text = (site.root / "index.md").read_text(encoding="utf-8")
    home_md_links = {site.url(href, "index.md") for href in MD_LINK.findall(home_text)}
    reading_targets = {site.url(href, reading_document) for href in MD_LINK.findall(reading.decode("utf-8"))}
    excerpts = 0
    for slug, (code_path, symbols, test_path, test) in DECISION_FIXTURES.items():
        document = f"studies/decisions/{slug}.json"
        packet_path = site.root / document
        require(packet_path in guide_links and packet_path in reading_links,
                f"Decision source packet is not directly discoverable: {slug}")
        packet = load(packet_path.read_bytes())
        require(packet["schema"] == "decision-source/1" and packet["id"] == slug
                and f"## {packet['question']}\n" in reading.decode("utf-8"), f"Wrong source packet for {slug}")
        require(len(packet["implementation"]) == len(symbols), f"Wrong implementation list for {slug}")
        code_targets = [verify_decision_source(site, document, entry, code_path, symbol, sources)
                        for entry, symbol in zip(packet["implementation"], symbols)]
        test_target = verify_decision_source(site, document, packet["test"], test_path, test, sources)
        for target in (code_targets[0], test_target):
            require(target in home_links and target in home_md_links and target in reading_targets,
                    f"The public reading is missing the verified source line for {slug}: {target.geturl()}")
        excerpts += len(symbols) + 1
    return excerpts


def citation_value_matches(selected, quote, data, address):
    if isinstance(quote, dict) and quote.keys() == {"decimal"} and type(selected) in (int, float):
        number = quote["decimal"]
        if not isinstance(number, str) or not JSON_NUMBER.fullmatch(number):
            return False
        try:
            exact, _ = pointer(json.loads(data, object_pairs_hook=unique, parse_float=Decimal,
                                          parse_constant=invalid_number), address)
            return exact == Decimal(number)
        except InvalidOperation:
            return False
    return json.dumps(selected, sort_keys=True, allow_nan=False) == json.dumps(quote, sort_keys=True, allow_nan=False)


def verify_notes(site, records, digests, raw_bytes):
    guide = site.root / "research-notes/index.md"
    references = site.markdown_links("research-notes/index.md", guide.read_bytes())
    checker = site.root / "research-notes/check_note.py"
    require(checker.is_file() and checker in references, "Research notes have no linked offline checker")
    files = sorted(guide.parent.glob("*.json"))
    require(len(files) >= 2, "Missing research-note examples")
    for path in files:
        require(path in references, f"Unlinked research note: {path.name}")
        note = load(path.read_bytes())
        require(set(note) == {"format", "kind", "proposal", "scope", "prediction", "control", "evidence"}
                and note["format"] == "taos-research-note/1" and note["kind"] in {"follow-up", "correction"},
                f"Unknown research note format: {path.name}")
        for field in ("proposal", "scope", "prediction", "control"):
            require(isinstance(note[field], str) and note[field].strip(), f"Missing {field} in {path.name}")
        reference = note["evidence"]
        keys = {"study", "sha256", "pointer", "observed"}
        require(set(reference) in (keys, keys | {"row_id"}), f"Unexpected note evidence fields: {path.name}")
        study = reference["study"]
        require(study in records and reference["sha256"] == digests[study], f"Wrong record version in {path.name}")
        require(reference["pointer"], f"A note must cite an observation: {path.name}")
        selected, row = pointer(records[study], reference["pointer"])
        require(row.get("id") == reference.get("row_id") and
                citation_value_matches(selected, reference["observed"], raw_bytes[study], reference["pointer"]),
                f"Note omits or changes its cited observation: {path.name}")
    return len(files)


def verify_archive(site, paths, revision, raw_bytes):
    if not paths:
        return 0
    require(len(paths) == len(STUDIES) and len(set(paths)) == 1, "Datasets disagree about the source archive")
    path = paths[0]
    require(path.is_relative_to(site.root / "source") and path.suffix == ".zip", "Unexpected source archive route")
    with ZipFile(path) as archive:
        require(archive.comment == revision.encode("ascii"), "Source ZIP is from a different revision")
        for identifier, data in raw_bytes.items():
            members = [item for item in archive.infolist()
                       if not item.is_dir() and item.filename.partition("/")[2] == identifier]
            require(len(members) == 1 and members[0].file_size == len(data)
                    and archive.read(members[0]) == data, f"Source ZIP omits or changes {identifier}")
    return len(raw_bytes)


def verify(root: Path, *, writing_report: bool = False) -> dict:
    """Return a local build verification receipt or raise ValueError on mismatch."""
    site = Site(root)
    versions = load((site.root / "research-versions.json").read_bytes())
    require(versions["format"] == 1 and versions["algorithm"] == "sha256", "Unknown research version manifest")
    require(set(versions["studies"]) == STUDIES, "Research version manifest differs from the expected study set")
    revision = versions["build_revision"]
    require(load((site.root / "standing.json").read_bytes())["revision"] == revision,
            "Site and research versions disagree about the revision")
    site.hash_item(versions["home"], "index.html")
    guide = site.hash_item(versions["guide"], "llms.txt")
    decisions = versions.get("decisions", {})
    require(set(decisions) == {"guide", "packets"} and set(decisions["packets"]) == set(DECISION_FIXTURES),
            "Research version manifest must identify the decision guide and all three packets")
    site.hash_item(decisions["guide"], "studies/decisions.md")
    for slug in DECISION_FIXTURES:
        site.hash_item(decisions["packets"][slug], f"studies/decisions/{slug}.json")
    site.has_link(site.home, "describedby", "text/plain", site.root / "llms.txt", "index.html")
    root_markdown = site.root / "index.md"
    site.has_link(site.home, "alternate", "text/markdown", root_markdown, "index.html")
    require(any(tag == "a" and site.path(link["href"], check=False) == site.root / "llms.txt"
                for tag, link in site.home.links
                if not urlsplit(link["href"]).netloc), "Homepage has no visible route to llms.txt")
    guide_links = site.markdown_links("llms.txt", guide, writing_report=writing_report)
    report_path = site.root / REPORT
    if writing_report:
        require(report_path in guide_links, "The machine guide has no audit receipt link")
    catalog_path = site.root / "research-catalog.json"
    catalog = load(catalog_path.read_bytes())
    require(catalog["@type"] == "DataCatalog", "Invalid research catalog")
    require(catalog.get("version", revision) == revision, "Catalog names a different build revision")
    site.has_link(site.home, "describedby", "application/json", catalog_path, "index.html")
    require(catalog in site.home.metadata, "Homepage dataset catalog differs from the JSON download")
    datasets = catalog["dataset"]
    wanted = {f"evals/results/{stem}.json" for stem in STUDIES}
    require(len(datasets) == len(STUDIES) and {d["identifier"] for d in datasets} == wanted
            and len({d["@id"] for d in datasets}) == len(STUDIES), "Catalog identifiers differ from the expected distinct datasets")
    graph = load((site.root / "graph.json").read_bytes())
    run_nodes = [node for node in graph["nodes"] if node["k"] == "r"]
    graph_runs = {node["l"]: node["sha256"] for node in run_nodes}
    require(graph["revision"] == revision and len(run_nodes) == len(STUDIES) and set(graph_runs) == wanted,
            "Graph and catalog describe different records or revisions")
    records, raw_bytes, digests, archives = {}, {}, {}, []
    rows, references = 0, 0
    for dataset in datasets:
        identifier = dataset["identifier"]
        stem = Path(identifier).stem
        version = versions["studies"][stem]
        require(version["identifier"] == identifier, f"Wrong version identifier for {stem}")
        require(site.path(dataset["@id"]) == catalog_path and site.url(dataset["@id"]).fragment == stem,
                f"Dataset identifier does not resolve to its catalog entry for {stem}")
        folder = "studies/" + stem.replace("_", "-") + "/"
        document = folder + "index.html"
        raw_path = site.root / "records" / (stem + ".json")
        data = site.hash_item(version["observations"], f"records/{stem}.json")
        raw = load(data)
        digest = hash_bytes(data)
        require(graph_runs[identifier] == digest, f"Wrong graph record digest for {stem}")
        records[identifier], raw_bytes[identifier], digests[identifier] = raw, data, digest
        require(dataset["@type"] == "Dataset" and dataset["version"] == "sha256:" + digest,
                f"Wrong Dataset version for {stem}")
        distribution = dataset["distribution"]
        require(distribution["@type"] == "DataDownload" and distribution["encodingFormat"] == "application/json"
                and distribution["sha256"] == digest and site.path(distribution["contentUrl"]) == raw_path,
                f"Invalid Dataset download for {stem}")
        if "isPartOf" in dataset:
            archives.append(site.path(dataset["isPartOf"]["url"]))
        markdown = site.hash_item(version["reading"], folder + "index.md")
        markdown_path = site.root / (folder + "index.md")
        require(markdown_path in guide_links and site.path(dataset["subjectOf"]["url"]) == markdown_path,
                f"Study Markdown is missing from the guide or Dataset for {stem}")
        page = Page(site.hash_item(version["page"], document))
        require(site.path(dataset["url"]) == site.root / document, f"Wrong Dataset page for {stem}")
        if site.hosted:
            canonical = urljoin(site.base.geturl(), folder)
            require(page.described("canonical") == [canonical]
                    and site.url(dataset["url"]).geturl() == canonical, f"Wrong canonical Dataset page for {stem}")
        site.has_link(page, "item", "application/json", raw_path, document)
        site.has_link(page, "alternate", "text/markdown", markdown_path, document)
        details_path = site.root / folder / "observations.json"
        site.has_link(page, "describedby", "application/json", details_path, document)
        metadata = [d for d in page.metadata if d.get("@type") == "Dataset"]
        require(len(metadata) == 1 and {k: v for k, v in metadata[0].items() if k != "@context"} == dataset,
                f"Embedded Dataset metadata differs from the catalog for {stem}")
        context = metadata[0]["@context"]
        require(isinstance(context, list) and len(context) == 2 and context[0] == "https://schema.org"
                and site.url(context[1]["@base"], document) == site.base,
                f"Dataset links resolve against the wrong site base for {stem}")
        detail = DETAIL_ROUTES[stem]
        detail_url = "../../" + detail
        require(version["detail"]["href"] == detail
                and f"[Detailed evidence]({detail_url})" in markdown.decode("utf-8")
                and any(tag == "a" and attrs["href"] == detail_url for tag, attrs in page.links),
                f"Full evidence page is not the hashed detail route for {stem}")
        detail_path = site.path(detail).relative_to(site.root).as_posix()
        site.hash_item(version["detail"], detail_path)
        details = load(site.hash_item(version["selected"], folder + "observations.json"))
        require(details["study"] == identifier and details["record"]["sha256"] == digest
                and site.path(details["record"]["href"], document) == raw_path, f"Wrong selected record for {stem}")
        count, count_refs = verify_observations(stem, details, raw)
        rows += count
        references += count_refs
        table = [[row["label"], row["value"]] for row in details["observations"]]
        require(page.rows == [["Comparison", "Recorded result"], *table], f"HTML observation table differs for {stem}")
        text = markdown.decode("utf-8")
        for row in details["observations"]:
            prefix = f"- **{row['label']}** — "
            candidates = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
            value = row["value"]
            statement = value if value.endswith((".", "!", "?")) else value + "."
            require(len(candidates) == 1 and candidates[0].startswith(statement)
                    and all(f"`{ref['pointer']}`" in candidates[0] for ref in row["sources"]),
                    f"Markdown observation differs from its selected raw evidence for {stem}: {row['label']}")
        site.markdown_links(folder + "index.md", markdown)
    source_files, downloads = verify_sources(site, revision)
    verify_saved_handoff(site, source_files, guide_links)
    excerpts = verify_decisions(site, source_files, guide_links)
    notes = verify_notes(site, records, digests, raw_bytes)
    archived = verify_archive(site, archives, revision, raw_bytes)
    receipt = {"schema": "research-guide-audit/1", "build_revision": revision, "passed": True,
               "counts": {"studies": len(STUDIES), "versioned_artifacts": len(site.versioned_paths),
                          "observations": rows, "json_pointers": references, "source_viewers": len(source_files),
                          "raw_source_downloads": downloads, "decision_packets": len(DECISION_FIXTURES),
                          "decision_source_excerpts": excerpts, "archive_records": archived, "note_examples": notes}}
    if not writing_report and report_path.exists():
        require(load(report_path.read_bytes()) == receipt, "Audit receipt disagrees with recalculated checks")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="directory containing the generated site")
    parser.add_argument("--json", action="store_true", help="print the verification receipt as JSON")
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, IndexError, BadZipFile) as error:
        parser.exit(1, f"Research guide check failed: {error}\n")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Verified " + ", ".join(f"{count} {name.replace('_', ' ')}" for name, count in result["counts"].items()) + ".")


if __name__ == "__main__":
    main()
