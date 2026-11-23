"""Shared storage for the science layer: one JSON document per mechanism.

Everything the science layer records lives under ``.taos/science/``. Each
mechanism owns one document and never reads another's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from . import plain
from .paths import Paths
from .store import atomic_write_json, read_json
from .util import TaosError


# Where a person sees every item of a kind, for the answer to a name that does not exist.
EVERY = {"adjustment": "taos anchor list", "change": "taos change list", "lesson": "taos lesson repeats",
         "rule": "taos rule governing <scope>"}


def science_dir(paths: Paths) -> Path:
    directory = paths.state / "science"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load(paths: Paths, name: str, key: str) -> Dict[str, Any]:
    data = read_json(paths.state / "science" / (name + ".json"))
    if not isinstance(data, dict) or key not in data:
        return {"schema": "TAOS_{0}_V1".format(name.upper()), key: []}
    return data


def save(paths: Paths, name: str, data: Dict[str, Any]) -> None:
    atomic_write_json(science_dir(paths) / (name + ".json"), data)


def find(items: List[Dict[str, Any]], item_id: str, what: str) -> Dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise TaosError(plain.missing(what, str(item_id), [item.get("id") for item in items], EVERY.get(what, "taos --help")))


def need(value: Any, what: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise TaosError("{0} is required".format(what))
    return text
