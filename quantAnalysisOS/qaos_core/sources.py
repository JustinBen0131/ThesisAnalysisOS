"""Where data comes from, and proof of what came.

Every fetch keeps the raw bytes' hash and where they were fetched from, so a
dataset can say what it stands on. Three kinds of source:

    pypi      a file inside a pinned release of an open-source package. The
              bytes are fixed by the release, so the pull is reproducible and
              is checked against a recorded hash. Works wherever pip does.
    vendor    daily prices from a public endpoint (Yahoo, FRED; Stooq has
              asked for a key since 2026). Needs the network to allow that
              host, and vendors revise history.
    file      a CSV you already have.

Nothing here needs an account or a key, and nothing here sends anything but a
symbol name.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import store
from .data import Dataset, align, carry_forward, rf_from_yield, to_dates

USER_AGENT = "Mozilla/5.0 (compatible; research-script)"  # some vendors refuse a client they do not recognise


class SourceError(Exception):
    """A source could not be read. The message names the host or file and the reason."""


# --------------------------------------------------------------------- http

def http_get(url: str, timeout: float = 45.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    host = url.split("/")[2] if "://" in url else url
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise SourceError("{0} answered HTTP {1}".format(host, error.code))
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise SourceError("{0} could not be reached ({1}). If this machine restricts outbound hosts, that host is not allowed.".format(host, reason))


# ------------------------------------------------------------------ parsing

def _date(text: str) -> np.datetime64:
    text = text.strip()
    if "/" in text:                       # M/D/YYYY
        month, day, year = text.split("/")
        return np.datetime64("{0:04d}-{1:02d}-{2:02d}".format(int(year), int(month), int(day)), "D")
    if len(text) == 6 and text.isdigit():  # YYYYMM: the month's last day
        month = np.datetime64("{0}-{1}".format(text[:4], text[4:]), "M")
        return (month + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    return np.datetime64(text[:10], "D")


def read_table(text: str, columns: Optional[Sequence[str]] = None) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """A CSV with a date in the first column. Returns dates, column names, values (NaN where blank)."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header = [cell.strip() for cell in rows[0]]
    names = header[1:] if columns is None else list(columns)
    index = [header.index(name) for name in names]
    dates, values = [], []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        try:
            dates.append(_date(row[0]))
        except (ValueError, IndexError):
            continue
        cells = []
        for column in index:
            cell = row[column].strip() if column < len(row) else ""
            try:
                cells.append(float(cell))
            except ValueError:
                cells.append(float("nan"))
        values.append(cells)
    order = np.argsort(np.asarray(dates, dtype="datetime64[D]"), kind="stable")
    return np.asarray(dates, dtype="datetime64[D]")[order], names, np.asarray(values, dtype=float).reshape(len(dates), len(names))[order]


def parse_stooq(raw: bytes) -> Tuple[np.ndarray, np.ndarray]:
    text = raw.decode("utf-8", "replace")
    if not text.lower().startswith("date"):
        raise SourceError("stooq did not return a price table (it said: {0!r})".format(text[:60]))
    dates, _, values = read_table(text, ["Close"])
    return dates, values[:, 0]


def parse_yahoo(raw: bytes) -> Tuple[np.ndarray, np.ndarray]:
    try:
        result = json.loads(raw.decode("utf-8"))["chart"]["result"][0]
        stamps = np.asarray(result["timestamp"], dtype="int64")
        adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise SourceError("yahoo did not return an adjusted-close series ({0})".format(error))
    offset = int(result.get("meta", {}).get("gmtoffset", 0))
    dates = ((stamps + offset) // 86400).astype("datetime64[D]")
    values = np.asarray([float("nan") if value is None else float(value) for value in adjusted], dtype=float)
    keep = np.concatenate([dates[1:] != dates[:-1], [True]])  # an intraday last row repeats the date
    return dates[keep], values[keep]


def parse_fred(raw: bytes) -> Tuple[np.ndarray, np.ndarray]:
    text = raw.decode("utf-8", "replace")
    if "," not in text.split("\n", 1)[0]:
        raise SourceError("fred did not return a CSV")
    dates, _, values = read_table(text)
    return dates, values[:, 0]


VENDORS = {
    "stooq": (lambda symbol: "https://stooq.com/q/d/l/?s={0}&i=d".format(symbol.lower()), parse_stooq),
    "yahoo": (lambda symbol: "https://query1.finance.yahoo.com/v8/finance/chart/{0}?period1=0&period2=9999999999&interval=1d&events=div%2Csplits".format(symbol.upper()), parse_yahoo),
    "fred": (lambda symbol: "https://fred.stlouisfed.org/graph/fredgraph.csv?id={0}".format(symbol.upper()), parse_fred),
}


def vendor_series(vendor: str, symbol: str) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    if vendor not in VENDORS:
        raise SourceError("unknown vendor '{0}'. Known: {1}".format(vendor, ", ".join(sorted(VENDORS))))
    make_url, parse = VENDORS[vendor]
    url = make_url(symbol)
    raw = http_get(url)
    dates, values = parse(raw)
    keep = np.isfinite(values)
    if not keep.any():
        raise SourceError("{0} returned no prices for {1}".format(vendor, symbol))
    return dates[keep], values[keep], {"vendor": vendor, "symbol": symbol, "url": url.split("?")[0],
                                         "sha256": store.sha256_bytes(raw), "bytes": len(raw),
                                         "fetched_at": store.now_iso(), "rows": int(keep.sum())}


def vendor_dataset(name: str, symbols: Sequence[str], vendor: str = "yahoo", rf_series: Optional[str] = "DTB3",
                   start: Optional[str] = None) -> Dataset:
    """Daily total-return prices for `symbols` on their shared calendar, with a T-bill risk-free rate.

    Adjusted closes fold dividends into the price, which is what makes this a
    total-return series, and also why history is rewritten after each dividend.
    """
    series: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    provenance = []
    for symbol in symbols:
        dates, values, record = vendor_series(vendor, symbol)
        series[symbol.upper()] = (dates, values)
        provenance.append(record)
    dates, names, table = align(series, how="inner")
    rf = np.zeros(dates.shape[0])
    if rf_series:
        rf_dates, rf_values, record = vendor_series("fred", rf_series)
        provenance.append(record)
        rf = rf_from_yield(dates, carry_forward(dates, rf_dates, rf_values))
    dataset = Dataset(name, dates, names, table, 252.0, rf, {
        "kind": "vendor", "provenance": provenance,
        "note": "adjusted closes; vendors revise them after every dividend, so the fingerprint is expected to change over time",
    })
    return dataset.window(start=start) if start else dataset


# --------------------------------------------------------------------- pypi

# name -> (package, pinned version, file inside its wheel, sha256 of that file, what it is)
PYPI_MEMBERS = {
    "us_market": ("arch", "9.0.0", "arch/data/frenchdata/frenchdata.csv.gz",
                  "f23436727b01d879e1372e3ee277514b0962a23d2b158f1aee6a402a90994f52",
                  "US stock market total return and one-month T-bill, monthly, July 1926 on "
                  "(Kenneth R. French Data Library market factor, as shipped in arch)"),
    "french": ("arch", "9.0.0", "arch/data/frenchdata/frenchdata.csv.gz",
               "f23436727b01d879e1372e3ee277514b0962a23d2b158f1aee6a402a90994f52",
               "Fama-French research factors (market, size, value), monthly, July 1926 on "
               "(Kenneth R. French Data Library, as shipped in arch)"),
    "sp500_daily": ("skfolio", "1.14.6", "skfolio/datasets/data/sp500_index.csv.gz",
                    "894c34431c284f86aa64a467e176e2a3c9b697c857eb9ab35006c2dd55d3fdf2",
                    "S&P 500 price index, daily, 1990 on (as shipped in skfolio). No dividends, no risk-free rate."),
    "factor_etfs": ("skfolio", "1.14.6", "skfolio/datasets/data/factors_dataset.csv.gz",
                    "6eb089953db90c9a38d3283582751701a90db6f59965847fd64b0578de497161",
                    "Five US equity factor ETFs, adjusted daily closes, 2014 on (as shipped in skfolio)"),
    "stocks20": ("skfolio", "1.14.6", "skfolio/datasets/data/sp500_dataset.csv.gz",
                 "ee21cac28befb1d0a739a9ceb22184f995394726aa0cfde9a21941d1ac04ac0d",
                 "Twenty large US stocks, adjusted daily closes, 1990 on (as shipped in skfolio). "
                 "Chosen with hindsight: survivors only."),
}


def pypi_member(package: str, version: str, member: str, wheel_dir: Optional[Path] = None) -> Tuple[bytes, Dict[str, Any]]:
    """Read one file out of a pinned package release, downloading the wheel if needed (no install)."""
    def find(directory: Path) -> Optional[Path]:
        hits = sorted(directory.glob("{0}-{1}-*.whl".format(package.replace("-", "_"), version)))
        return hits[0] if hits else None

    holder = None
    wheel = find(Path(wheel_dir)) if wheel_dir else None
    if wheel is None:
        holder = tempfile.TemporaryDirectory(prefix="qaos-pypi-")
        command = [sys.executable, "-m", "pip", "download", "{0}=={1}".format(package, version), "--no-deps",
                   "--only-binary", ":all:", "-d", holder.name, "-q", "--disable-pip-version-check"]
        done = subprocess.run(command, capture_output=True, text=True)
        wheel = find(Path(holder.name))
        if done.returncode != 0 or wheel is None:
            raise SourceError("pip could not download {0}=={1}: {2}".format(package, version, (done.stderr or done.stdout).strip()[-300:]))
    try:
        with zipfile.ZipFile(wheel) as archive:
            raw = archive.read(member)
    except KeyError:
        raise SourceError("{0} has no member {1}".format(wheel.name, member))
    finally:
        if holder is not None:
            holder.cleanup()
    record = {"kind": "pypi", "package": package, "version": version, "member": member,
              "sha256": store.sha256_bytes(raw), "bytes": len(raw)}
    return raw, record


def _text(raw: bytes, member: str) -> str:
    return (gzip.decompress(raw) if member.endswith(".gz") else raw).decode("utf-8", "replace")


def french_dataset(text: str, provenance: Optional[Dict[str, Any]] = None) -> Dataset:
    """US market total return and T-bill rate, monthly, from the Fama-French factor file.

    MKT is an index of the market's total return (Mkt-RF + RF). SMB and HML
    are indices of a fully collateralised long-short factor (RF + factor).
    Returns are month-end to month-end, so nothing is averaged within a month.
    """
    dates, names, values = read_table(text, ["Mkt-RF", "SMB", "HML", "RF"])
    values = values / 100.0
    rf = values[:, 3]
    lead = dates[0].astype("datetime64[M]").astype("datetime64[D]") - np.timedelta64(1, "D")  # the month-end before the first return
    grown = np.cumprod(1.0 + values[:, :3] + rf[:, None], axis=0)
    prices = np.vstack([np.ones((1, 3)), grown]) * 100.0
    return Dataset("french", np.concatenate([[lead], dates]), ["MKT", "SMB", "HML"], prices, 12.0,
                   np.concatenate([[0.0], rf]),
                   {"kind": "pypi", "provenance": [provenance] if provenance else [],
                    "note": "MKT = total return of the US market (CRSP value-weighted); rf = one-month T-bill"})


def price_table_dataset(name: str, text: str, periods_per_year: float = 252.0,
                        provenance: Optional[Dict[str, Any]] = None, note: str = "") -> Dataset:
    dates, names, values = read_table(text)
    return Dataset(name, dates, names, values, periods_per_year, None,
                   {"kind": "pypi" if provenance else "file", "provenance": [provenance] if provenance else [], "note": note})


def pull(name: str, wheel_dir: Optional[Path] = None) -> Dataset:
    """Build one of the reproducible datasets named in PYPI_MEMBERS.

    The file's hash is checked against the one recorded here, so the same name
    is the same numbers on every machine, or the pull is refused.
    """
    if name not in PYPI_MEMBERS:
        raise SourceError("unknown dataset '{0}'. Known: {1}".format(name, ", ".join(sorted(PYPI_MEMBERS))))
    package, version, member, expected, description = PYPI_MEMBERS[name]
    raw, record = pypi_member(package, version, member, wheel_dir)
    if record["sha256"] != expected:
        raise SourceError("{0} {1}: {2} is not the file this dataset was defined on (hash {3}..., expected {4}...)".format(
            package, version, member, record["sha256"][:12], expected[:12]))
    record["description"] = description
    text = _text(raw, member)
    if name in ("french", "us_market"):
        dataset = french_dataset(text, record)
        if name == "us_market":
            dataset = dataset.select(["MKT"])
            dataset.name = "us_market"
        return dataset
    dataset = price_table_dataset(name, text, 252.0, record, description)
    return dataset
