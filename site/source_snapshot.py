"""Serve the generated site's referenced public files, with their build provenance."""

import hashlib
import html
import json
import posixpath
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit
from zipfile import ZipFile


HREF = re.compile(r"""(\bhref\s*=\s*["'])(https://[^"'<>]+)(["'])""", re.IGNORECASE)
URL = re.compile(r"""https://[^\s<>"'\]\)]+""")
LINE = re.compile(r"L([1-9][0-9]*)(?:-L[1-9][0-9]*)?")
HASH = re.compile(r"[0-9a-f]{7,64}")
CREDENTIAL_PATH = re.compile(
    r"(^|/)(?:\.git|\.taos|\.ssh|\.aws|\.env(?:\.[^/]+)?|"
    r"credentials(?:\.[^/]+)?|secrets(?:\.[^/]+)?|id_rsa|id_ed25519)(?:/|$)"
    r"|\.(?:key|pem|p12|pfx|jks|kdbx)$", re.IGNORECASE)
CREDENTIAL_VALUE = (
    r"^-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----"
    r"|gh[pousr]_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{60,}"
    r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}"
    r"|sk-(proj-|svcacct-)[0-9A-Za-z_-]{32,}|xox[baprs]-[0-9A-Za-z-]{16,}"
)
VALUE_CHECK = re.compile(CREDENTIAL_VALUE, re.MULTILINE)
INDEX = PurePosixPath("source/index.html")
MANIFEST = PurePosixPath("source/index.json")
LLMS = PurePosixPath("llms.txt")
RAW_SUFFIXES = {".md", ".markdown", ".py", ".txt", ".json", ".csv", ".tsv", ".yml", ".yaml", ".toml"}
PLAIN_MODES = {"100644", "100755"}
LEGAL_TEXT = {"LICENSE", "NOTICE"}
RAW_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\[\]\r\n]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))")
RAW_MARKDOWN_IMAGE = re.compile(r"!\[[^\]\r\n]*\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))")
RAW_INDEX_DIRECTORIES = {"evals/results", "examples/model_evaluation"}
RAW_LINK_DEPTH = 2
RAW_LINK_BUDGET = 64
CSS = """
:root{color-scheme:dark}body{max-width:76rem;margin:0 auto;padding:1.25rem 1rem;
background:#0b1510;color:#eaf4ee;font:1rem/1.55 system-ui,sans-serif}
a{color:#9be2c3;text-underline-offset:.17em}h1{line-height:1.2;overflow-wrap:anywhere}
nav{display:flex;gap:1.2rem;flex-wrap:wrap}code{font-family:ui-monospace,monospace}
p code,li>a code{overflow-wrap:anywhere}
ol{padding:0;list-style:none;margin:0}li{margin:.25rem 0}.listing{overflow:auto;
border:1px solid #3e5749;background:#0f1b14;padding:.4rem .6rem}
.listing li{display:grid;grid-template-columns:4ch 1fr;gap:.8rem;min-width:max-content;
margin:0;white-space:pre;min-height:1.55em}.listing li:target{background:#294a38}
.listing a{text-align:right;color:#a7c1b1}.checksum{overflow-wrap:anywhere}
"""


def _git(repo, *args):
    git = shutil.which("git") or "/usr/bin/git"
    return subprocess.run([git, *args], cwd=repo, capture_output=True)


def _tracked(repo):
    proc = _git(repo, "ls-files", "--stage", "-z")
    if proc.returncode:
        return {}
    files = {}
    for entry in proc.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not entry:
            continue
        info, path = entry.split("\t", 1)
        mode, _, stage = info.split()
        if stage == "0":
            files[path] = mode
    return files


def _html(title, content):
    safe = html.escape(title)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{safe}</title><style>{CSS}</style></head><body><main>{content}</main></body></html>\n')


def _href(origin, target):
    return quote(posixpath.relpath(str(target), str(origin.parent)), safe="/")


def _file_target(name):
    return PurePosixPath("source/files") / (name + ".html")


def _raw_target(name):
    target = PurePosixPath("source/raw") / name
    if target.suffix.lower() in {".html", ".htm", ".xhtml"}:
        return None
    # Keep active formats off executable routes. A tracked file cannot also
    # be a directory, so this mapping cannot collide with another tracked path.
    return target if name in LEGAL_TEXT or target.suffix.lower() in RAW_SUFFIXES else target / "source.txt"


def _read_text(repo, name):
    path = repo / name
    if CREDENTIAL_PATH.search(name) or path.is_symlink() or path.resolve() != path:
        return None
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    if "\0" in text or VALUE_CHECK.search(text):
        return None
    return data, text


def _raw_markdown_target(document, href):
    try:
        url = urlsplit(href)
    except ValueError:
        return None
    path = unquote(url.path)
    if url.scheme or url.netloc or not path or path.startswith("/") or "\\" in path or "\0" in path:
        return None
    name = posixpath.normpath(posixpath.join(posixpath.dirname(document), path))
    return None if name in {".", ".."} or name.startswith("../") else name


def _extend_raw_navigation(repo, tracked, referenced):
    """Follow bounded relative text links without changing the original Markdown."""
    directories, inspected = set(), set()
    attempted = set(referenced)
    initial = len(attempted)
    for _ in range(RAW_LINK_DEPTH):
        candidates = set()
        for name, (_, text) in sorted(referenced.items()):
            if name in inspected or PurePosixPath(name).suffix.lower() not in {".md", ".markdown"}:
                continue
            inspected.add(name)
            for match in RAW_MARKDOWN_LINK.finditer(text):
                target = _raw_markdown_target(name, match[1] or match[2])
                if target in RAW_INDEX_DIRECTORIES:
                    if target not in directories:
                        directories.add(target)
                        candidates.update(path for path in tracked if posixpath.dirname(path) == target)
                elif target:
                    candidates.add(target)
        extra = {name for name in candidates - attempted
                 if tracked.get(name) in PLAIN_MODES
                 and (name in LEGAL_TEXT or PurePosixPath(name).suffix.lower() in RAW_SUFFIXES)}
        if len(attempted) - initial + len(extra) > RAW_LINK_BUDGET:
            raise ValueError("The raw Markdown source links exceed the snapshot's file budget.")
        attempted.update(extra)
        for name in sorted(extra):
            source = _read_text(repo, name)
            if source is not None:
                referenced[name] = source
    return directories


def _write_raw_directory_indexes(out, directories, referenced):
    for directory in sorted(directories):
        names = sorted(name for name in referenced if posixpath.dirname(name) == directory
                       and _raw_target(name) is not None)
        if not names:
            continue
        page = PurePosixPath("source/raw") / directory / "index.html"
        links = "".join(f'<li><a href="{_href(page, _raw_target(name))}">'
                        f'<code>{html.escape(PurePosixPath(name).name)}</code></a></li>' for name in names)
        body = (f'<nav aria-label="Source navigation"><a href="{_href(page, INDEX)}">Source index</a></nav>'
                f'<h1>{html.escape(directory)}/</h1><p>Tracked files available in this snapshot.</p><ul>{links}</ul>')
        (out / page).write_text(_html(directory, body), encoding="utf-8")


def _copy_markdown_images(out, tracked, referenced):
    """Preserve relative image links in byte-identical Markdown using the site's published raster assets."""
    images = set()
    for name, (_, text) in referenced.items():
        if PurePosixPath(name).suffix.lower() in {".md", ".markdown"}:
            for match in RAW_MARKDOWN_IMAGE.finditer(text):
                target = _raw_markdown_target(name, match[1] or match[2])
                if target and target.startswith("site/assets/") and PurePosixPath(target).suffix.lower() in {
                        ".png", ".jpg", ".jpeg", ".webp"}:
                    images.add(target)
    for name in sorted(images):
        asset = out / PurePosixPath(name).relative_to("site")
        if tracked.get(name) not in PLAIN_MODES or asset.is_symlink() or not asset.is_file():
            raise ValueError(f"Missing published image referenced by raw Markdown: {name}")
        target = out / "source/raw" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, target)


def _write_viewer(out, name, text, note, raw):
    location = _file_target(name)
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        lines.append(f'<li id="L{number}"><a href="#L{number}" aria-label="Line {number}">{number}</a>'
                     f'<code>{html.escape(line)}</code></li>')
    index = _href(location, INDEX)
    raw_link = f'<a href="{_href(location, raw)}">Raw source</a>' if raw else ""
    body = (f'<nav aria-label="Source navigation"><a href="{index}">Source index</a>'
            f'{raw_link}</nav>'
            f'<h1>{html.escape(name)}</h1><p>{note}</p>'
            '<div class="listing" tabindex="0" role="region" aria-label="Source listing">'
            '<ol>' + "".join(lines) + '</ol></div>')
    target = out / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_html(name, body), encoding="utf-8")


def _blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _archive(out, repo, revision, tracked, referenced):
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    head = _git(repo, "rev-parse", "HEAD")
    if (not HASH.fullmatch(revision) or status.returncode or status.stdout
            or head.returncode or head.stdout.decode().strip() != revision):
        return None, "This preview uses files in the local workspace. It has no matching clean-commit archive."
    if not tracked or any(mode not in PLAIN_MODES or CREDENTIAL_PATH.search(path) for path, mode in tracked.items()):
        return None, "The commit contains a path outside the source archive’s allowed file types."
    if _git(repo, "grep", "-I", "-q", "-E", CREDENTIAL_VALUE, revision, "--").returncode != 1:
        return None, "The tracked commit did not pass the credential check."

    tree_run = _git(repo, "ls-tree", "-rz", revision)
    tree = {}
    for entry in tree_run.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if entry:
            info, path = entry.split("\t", 1)
            tree[path] = info.split()[-1]
    standing = out / "standing.json"
    manifest = json.loads(standing.read_text()) if standing.is_file() else {}
    if manifest.get("revision") != revision:
        return None, "The page source manifest names a different revision."
    expected = {row["path"]: row["blob"] for row in manifest["stands_on"]}
    for name, (data, _) in referenced.items():
        expected[name] = _blob_id(data)
    if (tree_run.returncode or tree.keys() != tracked.keys()
            or any(tree.get(name) != blob for name, blob in expected.items())):
        return None, "Some files used by the build do not match the committed snapshot."
    short = revision[:12]
    target = out / "source" / f"thesisanalysisos-{short}.zip"
    prefix = f"ThesisAnalysisOS-{short}/"
    result = _git(repo, "archive", "--format=zip", f"--prefix={prefix}", f"--output={target}", revision)
    if result.returncode:
        raise RuntimeError("Git could not create the source archive.")
    with ZipFile(target) as zipped:
        files = {entry.filename[len(prefix):]: entry for entry in zipped.infolist() if not entry.is_dir()}
        exact = (zipped.comment.decode("ascii") == revision and files.keys() == tree.keys()
                 and all(_blob_id(zipped.read(entry)) == tree[name] for name, entry in files.items()))
    if not exact:
        target.unlink()
        return None, "Git archive export settings would change the committed source snapshot."
    return target, "The archive contains the tracked files from this exact Git commit."


def write_source_snapshot(out, repo, github, ref, revision, evidence_files=()):
    """Write public source views and raw bytes, with an optional exact archive."""
    out, repo = Path(out).resolve(), Path(repo).resolve()
    site = urlsplit(github.rstrip("/"))
    origin = site.path
    tracked = _tracked(repo)
    if not tracked:
        return {"files": 0, "archive": None}

    refs = {"main", revision}
    if ref and (ref == revision or not HASH.fullmatch(ref)):
        current_ref = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
        if ref == "main" or current_ref.returncode or current_ref.stdout.decode().strip() == revision:
            refs.add(ref)
    prefixes = [origin + f"/blob/{name}/" for name in sorted(refs, key=len, reverse=True) if name]
    referenced = {}
    for name in sorted(set(evidence_files)):
        source = _read_text(repo, name) if tracked.get(name) in PLAIN_MODES else None
        if source is None:
            raise ValueError(f"Cannot publish the cited source document: {name}")
        referenced[name] = source

    def link(value, doc):
        parts = urlsplit(html.unescape(value))
        if parts.scheme != site.scheme or parts.netloc.lower() != site.netloc.lower():
            return value
        path = unquote(parts.path)
        if revision != "unknown" and path == origin + f"/commit/{revision}":
            return _href(doc, INDEX)
        prefix = next((item for item in prefixes if path.startswith(item)), None)
        if not prefix:
            return value
        name = path[len(prefix):]
        if tracked.get(name) not in PLAIN_MODES:
            return value
        if name not in referenced:
            source = _read_text(repo, name)
            if source is None:
                return value
            referenced[name] = source
        marker = LINE.fullmatch(parts.fragment)
        suffix = f"#L{marker.group(1)}" if marker else ""
        raw = _raw_target(name) if doc == LLMS and not marker else None
        return _href(doc, raw or _file_target(name)) + suffix

    pages = sorted(set(out.rglob("*.html")) | set(out.rglob("*.md")) | {out / LLMS})
    for path in pages:
        if not path.is_file() or path.relative_to(out).parts[0] == "source":
            continue
        doc = PurePosixPath(path.relative_to(out).as_posix())
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            def rewrite(mark):
                url = link(mark[2], doc)
                if url == mark[2]:
                    return mark[0]
                return mark[1] + html.escape(url, quote=True) + mark[3]
            rewritten = HREF.sub(rewrite, text)
        else:
            def rewrite(mark):
                url = mark[0]
                trimmed = url.rstrip(".,;")
                relative = link(trimmed, doc)
                if relative == trimmed:
                    return url
                previous = text[mark.start() - 1:mark.start()] if mark.start() else ""
                if previous != "(":
                    file_label = unquote(urlsplit(trimmed).path.rsplit("/", 1)[-1])
                    relative = f"[{file_label}]({relative})"
                return relative + url[len(trimmed):]
            rewritten = URL.sub(rewrite, text)
        if text != rewritten:
            path.write_text(rewritten, encoding="utf-8")

    directories = _extend_raw_navigation(repo, tracked, referenced)
    (out / "source").mkdir(parents=True, exist_ok=True)
    archive, archive_note = _archive(out, repo, revision, tracked, referenced)
    revision_text = html.escape(revision)
    note = (f"Source bytes used to build this page from Git commit <code>{revision_text}</code>."
            if archive else f"Source bytes from the workspace used for this build at <code>{revision_text}</code>.")
    files = []
    for name, (data, text) in sorted(referenced.items()):
        raw = _raw_target(name)
        if raw:
            destination = out / raw
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        _write_viewer(out, name, text, note, raw)
        files.append({"path": name, "raw_url": _href(MANIFEST, raw) if raw else None,
                      "viewer_url": _href(MANIFEST, _file_target(name)),
                      "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    _write_raw_directory_indexes(out, directories, referenced)
    _copy_markdown_images(out, tracked, referenced)
    manifest = {"schema": "source-snapshot/1", "revision": revision,
                "provenance": "commit" if archive else "workspace", "files": files}
    (out / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    links = "".join(f'<li><a href="{_href(INDEX, _file_target(name))}"><code>{html.escape(name)}</code></a></li>'
                    for name in sorted(referenced))
    download = ""
    if archive:
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        download = (f'<p><a href="{quote(archive.name)}" download>Download the source ZIP</a></p>'
                    f'<p class="checksum">ZIP SHA-256 <code>{digest}</code></p>')
    body = ('<nav aria-label="Source navigation"><a href="../index.html">Home</a>'
            '<a href="../evidence/index.html">Evidence</a></nav><h1>Source for this build</h1>'
            f'<p>{note} {html.escape(archive_note)}</p>{download}'
            '<h2>Reproduce the published checks</h2><p>The evidence pages list the commands and their saved observations. '
            'Run them from the extracted repository root. The historical revision comparison requires a Git checkout '
            'that retains the earlier commits listed in its method.</p>'
            f'<h2>Referenced source files</h2><p><a href="{_href(INDEX, MANIFEST)}">Source manifest (JSON)</a></p>'
            f'<ul>{links}</ul>')
    (out / INDEX).write_text(_html("Source for this build", body), encoding="utf-8")
    return {"files": len(referenced), "archive": archive.name if archive else None}
