"""Shared storage for the science layer: one JSON document per mechanism.

Everything the science layer records lives under ``.taos/science/``. Each
mechanism owns one document and never reads another's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .paths import Paths
from .store import atomic_write_json, read_json
from .util import TaosError


def science_dir(paths: Paths) -> Path:
    directory = paths.state / "science"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load(paths: Paths, name: str, key: str) -> Dict[str, Any]:
    data = read_json(science_dir(paths) / (name + ".json"))
    if not isinstance(data, dict) or key not in data:
        return {"schema": "TAOS_{0}_V1".format(name.upper()), key: []}
    return data


def save(paths: Paths, name: str, data: Dict[str, Any]) -> None:
    atomic_write_json(science_dir(paths) / (name + ".json"), data)


def find(items: List[Dict[str, Any]], item_id: str, what: str) -> Dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise TaosError("no {0} with id {1}".format(what, item_id))


def need(value: Any, what: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise TaosError("{0} is required".format(what))
    return text
