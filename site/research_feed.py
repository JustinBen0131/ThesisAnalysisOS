"""Publish reviewed exchange entries as a JSON Feed 1.1 subscription."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def write_feed(out: Path, exchange_index: dict, base_url: str = "") -> None:
    entries = exchange_index["entries"]
    by_id = {entry["id"]: entry for entry in entries}
    if len(by_id) != len(entries) or any(not re.fullmatch(r"[0-9a-f]{64}", key) for key in by_id):
        raise ValueError("Feed items require unique exchange entry SHA-256 IDs.")
    base = ""
    if base_url:
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Use the site's absolute HTTP(S) base URL without a query or fragment.")
        base = base_url.rstrip("/") + "/"
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "ThesisAnalysisOS research exchange",
        "description": "Reviewed questions and replies about the published research records.",
        "items": [],
    }
    if base:
        feed["home_page_url"] = urljoin(base, "exchange/")
        feed["feed_url"] = urljoin(base, "exchange/feed.json")

    # The exchange supplies content addresses, not publication dates.
    for key in sorted(by_id):
        entry = by_id[key]
        root = entry
        seen = {key}
        while root["replies_to"] in by_id:
            parent_id = root["replies_to"]
            if parent_id in seen:
                raise ValueError("A research exchange entry cannot reply to itself or its descendants.")
            seen.add(parent_id)
            root = by_id[parent_id]
        title = root["proposal"].split(". ", 1)[0].strip()
        if entry["replies_to"]:
            title = f"{entry['stance'].capitalize()} · {title}"
        status = {field: entry[field] for field in ("standing", "citation", "thread", "prediction") if field in entry}
        prediction = entry.get("prediction", {})
        lines = [entry["proposal"], "", f"Overall standing is {entry['standing']}.",
                 f"Citation check: {entry.get('citation', 'not reported separately')}.",
                 f"Parent thread: {entry.get('thread', 'not reported separately')}.",
                 f"Prediction: {prediction.get('status', 'not reported')}."]
        for run in prediction.get("runs", []):
            lines.append(f"Reply {run['id']} reports {run['outcome'].replace('_', ' ')} (citation {run['citation']}).")
        lines.extend([f"{entry['study']} at {entry['pointer']}", f"Record SHA-256 {entry['sha256']}"])
        item = {"id": key, "title": title, "content_text": "\n".join(lines), "_taos": status}
        if base:
            item["url"] = urljoin(base, "exchange/#e-" + key[:12])
            status["about"] = urljoin(base, "exchange/index.md")
            status["entry_url"] = urljoin(base, entry["entry"])
            if entry.get("page"):
                status["markdown_url"] = urljoin(base, entry["page"])
        feed["items"].append(item)
    folder = Path(out) / "exchange"
    folder.mkdir(exist_ok=True)
    (folder / "feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
