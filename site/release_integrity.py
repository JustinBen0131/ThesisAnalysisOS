"""Browser policy for generated pages and a byte inventory for the finished static site."""

import argparse
import base64
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit


BUILD_ORIGIN = "https://build.invalid"
BEACON_SCRIPT = "https://static.cloudflareinsights.com/beacon.min.js"
GITHUB_TREE = "https://api.github.com/repos/JustinBen0131/ThesisAnalysisOS/git/trees/"
READER_ENDPOINTS = ("https://whatstillholds-interactions.just0131.workers.dev/v1",
                    "https://cloudflareinsights.com/cdn-cgi/rum")
LOCAL_SCRIPTS = {"assets/site.js", "assets/mind.js", "assets/reuse.js", "assets/interactions.js"}
DATA_TYPES = {"application/json", "application/ld+json"}
CHARSET = '<meta charset="utf-8">'
MANIFEST = "release.json"


def script_hash(code):
    value = hashlib.sha256(code.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(value).decode("ascii") + "'"


class PageScripts(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.scripts = []
        self.attributes = []
        self._script = None
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        self.attributes.append((tag, fields))
        if tag == "script":
            self._script = []
            self.scripts.append((fields, self._script))

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self._script = None


def trusted_film_scripts():
    # Trust only the two repository-controlled templates. A new block in a rendered
    # contribution must never acquire permission merely because it appeared in the output.
    trusted = set()
    for name in ("film_player.html", "film_record.html"):
        page = PageScripts(Path(__file__).with_name(name).read_text(encoding="utf-8"))
        for fields, chunks in page.scripts:
            if not fields and chunks:
                trusted.add(script_hash("".join(chunks)))
    return trusted


def browser_policy(markup, relative, trusted, analytics):
    page = PageScripts(markup)
    base = BUILD_ORIGIN + "/" + relative
    sources, connections = set(), {"'self'"}
    for tag, fields in page.attributes:
        links = [fields.get(k) or "" for k in ("href", "src", "action", "formaction")]
        if (tag in {"base", "embed", "object", "iframe", "form"} or
                any(k.startswith("on") for k in fields) or
                any(urlsplit(link.strip()).scheme == "javascript" for link in links)):
            raise ValueError(f"Unexpected active markup in {relative}: {tag}")
        if tag == "meta" and fields.get("http-equiv", "").lower() in {"refresh", "content-security-policy"}:
            raise ValueError(f"Unexpected page redirect or second policy in {relative}")
        asset = fields.get("src") if tag in {"img", "source", "track", "video", "audio"} else None
        if tag == "link" and set((fields.get("rel") or "").lower().split()) & {"stylesheet", "icon", "preload", "modulepreload"}:
            asset = fields.get("href")
        if asset:
            target = urlsplit(urljoin(base, asset))
            if target.scheme != "https" or target.netloc != urlsplit(BUILD_ORIGIN).netloc:
                raise ValueError(f"Unexpected external page resource in {relative}: {asset}")
    for fields, chunks in page.scripts:
        source = fields.get("src")
        if fields.get("type", "").lower() in DATA_TYPES and source is None:
            continue
        if source is None:
            permitted = script_hash("".join(chunks))
            if relative != "index.html" or permitted not in trusted:
                raise ValueError(f"Unregistered inline script in {relative}")
            sources.add(permitted)
            continue
        if analytics and source == BEACON_SCRIPT:
            sources.add(BEACON_SCRIPT)
            connections.update(READER_ENDPOINTS)
            continue
        url = urlsplit(urljoin(base, source))
        path = url.path.lstrip("/")
        if (url.scheme != "https" or url.netloc != urlsplit(BUILD_ORIGIN).netloc or
                path not in LOCAL_SCRIPTS or url.query or url.fragment or
                (path == "assets/interactions.js" and not analytics)):
            raise ValueError(f"Unregistered script in {relative}: {source}")
        sources.add("'self'")
        if path == "assets/site.js":
            connections.add(GITHUB_TREE)
    allowed = " ".join(sorted(sources)) if sources else "'none'"
    directives = ["default-src 'none'", "base-uri 'none'", "object-src 'none'", "form-action 'none'",
                  "script-src " + allowed, "script-src-attr 'none'", "style-src 'self' 'unsafe-inline'",
                  "img-src 'self' data:", "media-src 'self'", "font-src 'self'",
                  "connect-src " + " ".join(sorted(connections))]
    return "; ".join(directives)


def protect_pages(root, *, private_film, analytics):
    trusted = trusted_film_scripts() if private_film else set()
    for path in sorted(root.rglob("*.html")):
        name = path.relative_to(root).as_posix()
        markup = path.read_text(encoding="utf-8")
        if markup.count(CHARSET) != 1 or not re.search(r"<head>\s*" + re.escape(CHARSET), markup, re.I):
            raise ValueError(f"Missing early charset in {name}")
        policy = browser_policy(markup, name, trusted, analytics)
        meta = '<meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">'
        meta += '\n<meta name="referrer" content="same-origin">'
        path.write_text(markup.replace(CHARSET, CHARSET + "\n" + meta, 1), encoding="utf-8")


def release_inventory(root, revision):
    rows = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"A served file must have its own bytes: {path}")
        if not path.is_file() or path == root / MANIFEST:
            continue
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        rows.append({"path": path.relative_to(root).as_posix(), "bytes": size, "sha256": digest.hexdigest()})
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"format": "taos-static-release/1", "revision": revision, "files_sha256": hashlib.sha256(canonical).hexdigest(),
            "files": rows}


def write_manifest(root, revision):
    data = release_inventory(root, revision)
    (root / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_manifest(root, expected=None):
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    revision = json.loads((root / "standing.json").read_text(encoding="utf-8"))["revision"]
    if manifest != release_inventory(root, revision):
        raise ValueError("The served files differ from release.json")
    if expected is not None and manifest["files_sha256"] != expected:
        raise ValueError("The release fingerprint differs from the one supplied")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify every file against a downloaded site's release.json.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-sha256", help="a release fingerprint saved from an independent trusted copy")
    args = parser.parse_args()
    receipt = verify_manifest(args.directory, args.expected_sha256)
    print(f"{len(receipt['files'])} files verified at {receipt['revision']}: {receipt['files_sha256']}")
