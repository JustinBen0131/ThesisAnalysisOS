"""Describe the downloadable research records using Schema.org JSON-LD."""

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit
from zipfile import ZipFile


class Experiment(NamedTuple):
    record: str
    question: str
    method: str
    scope: str
    variables: Tuple[str, ...]
    evidence: str


EXPERIMENTS = (
    Experiment(
        "at_revision", "Which known failures does a later software revision still exhibit?",
        "Run the same {checks} regression tests against {earlier} earlier releases and the reference checkout, "
        "recording every test that fails or raises an error.",
        "The cases were selected because they exposed specific defects and cannot estimate an overall defect rate.",
        ("Number of tests run at each revision", "Number of failures or errors", "Names of tests that did not pass"),
        "evidence/#revision-comparison",
    ),
    Experiment(
        "mutations", "Do the tests detect the removal of a protection they are meant to check?",
        "Introduce one of {faults} specified faults at a time in a temporary copy and run the associated tests.",
        "Detection is measured only for the selected edits and their assigned tests.",
        ("Number of seeded faults", "Number detected by the tests", "Names of missed faults"),
        "evidence/#seeded-faults",
    ),
    Experiment(
        "reuse_frontier", "When does tracking the inputs to a check save work without reusing an obsolete result?",
        "Apply {edits} seeded file edits to a workspace with {checks} checks and compare execution logs "
        "against the folders each check actually read.",
        "The workload uses small file checks. Consultation and isolation timings describe the recorded machine and workload.",
        ("Check executions after the initial runs", "Reuses after an input changed",
         "Time spent checking inputs", "Paired time spent running a check in isolation"),
        "evidence/#reuse-full",
    ),
    Experiment(
        "measurement_audit", "When does an old passing check still support a revised numerical estimate?",
        "Perturb a pendulum fit to {readings} readings in {cases} cases, compare its saved status with a fresh fit "
        "and recompute the estimate and its standard error with 48-digit decimal arithmetic.",
        "The selected edits test one teaching dataset. The fit assumes small swings and a zero intercept. Its standard error measures scatter around that model.",
        ("Status of the earlier pass", "Gravity estimate (m/s²)", "Standard error of the estimate (m/s²)",
         "Fresh check exit code", "Agreement between two calculations of the same fit"),
        "evidence/pendulum/",
    ),
    Experiment(
        "model_evaluation", "Can pooled classifier results conceal a loss of sensitivity in one group?",
        "Apply {cases} specified perturbations to an instrument comparison, then count true and false classifications "
        "for each instrument and the combined readings using the known sample labels.",
        "The {readings} fictional readings provide a counterexample to relying on pooled performance alone. "
        "They cannot estimate how often the disagreement occurs.",
        ("True positives, false negatives, false positives and true negatives by instrument and pooled",
         "Direction of sensitivity change", "Executed and reused checks", "Group and pooled check outcomes"),
        "evidence/model-evaluation/",
    ),
    Experiment(
        "session_footprint", "What does a new session actually have to read?",
        "Construct the pendulum demo and collect its compact project status, one task brief and the generated instructions as {surfaces} separate texts. "
        "Count their UTF-8 bytes and lines after replacing temporary paths, the Python executable path and the status dates with fixed labels.",
        "One local demo. The host determines which instructions it loads. The recorded sizes describe the text the software returns.",
        ("UTF-8 bytes", "Text lines", "How the text reaches an assistant", "SHA-256 of the normalized text"),
        "evidence/#session-reading",
    ),
    Experiment(
        "handoff_audit", "Which earlier check can another task cite after the data changes or is restored?",
        "Follow {requests} requests from {tasks} task IDs in one pendulum analysis, recording whether each request "
        "runs the check again or cites an earlier execution.",
        "One scripted history retains earlier results under a fixed check definition and uses supplied actor labels.",
        ("Input file hashes", "Status before and after the request", "Execution or reuse",
         "Origin of the cited execution", "Check exit code"),
        "evidence/#handoff-audit",
    ),
)


def _study_sizes(stem: str, raw: dict) -> dict:
    if stem == "at_revision":
        checks = raw["here"]["ran"]
        if any(row["ran"] != checks for row in raw["revisions"].values()):
            raise ValueError("The revisions have different test counts.")
        return {"checks": checks, "earlier": len(raw["revisions"])}
    if stem == "mutations":
        return {"faults": raw["faults"]}
    if stem == "reuse_frontier":
        return {"edits": raw["edits"], "checks": raw["checks"]}
    if stem == "measurement_audit":
        return {"readings": len(raw["baseline_rows"]), "cases": len(raw["cases"])}
    if stem == "model_evaluation":
        return {"readings": sum(raw["baseline_counts"]["pooled"]), "cases": len(raw["cases"])}
    if stem == "session_footprint":
        return {"surfaces": len(raw["surfaces"])}
    observations = raw["observations"]
    return {"requests": len(observations), "tasks": len({row["task"] for row in observations})}


def _archive_hashes(root: Path, source_archive: str, revision: str) -> dict:
    reference = urlsplit(source_archive)
    path = PurePosixPath(unquote(reference.path))
    if (reference.scheme or reference.netloc or reference.query or reference.fragment or path.is_absolute()
            or ".." in path.parts or "\\" in str(path)):
        raise ValueError("The source ZIP reference must be a path relative to the site root.")
    prefix = f"ThesisAnalysisOS-{revision[:12]}/evals/results/"
    with ZipFile(root / path) as archive:
        if archive.comment != revision.encode("ascii"):
            raise ValueError("The source ZIP identifies a different Git revision.")
        return {e.record: hashlib.sha256(archive.read(prefix + e.record + ".json")).hexdigest()
                for e in EXPERIMENTS}


def research_catalog(records_dir: Path, base_url: str, revision: Optional[str] = None,
                     *, source_archive: Optional[str] = None) -> dict:
    """Cite the verified source ZIP when provided, otherwise describe the downloadable observations alone."""
    if (revision is None) != (source_archive is None):
        raise ValueError("A revision and its source ZIP must be supplied together.")
    archived = {}
    if revision is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or not source_archive:
            raise ValueError("A source citation requires a full Git commit hash and its source ZIP.")
        archived = _archive_hashes(records_dir.parent, source_archive, revision)
    base = base_url.rstrip("/") + "/" if base_url else ""
    catalog_id = urljoin(base, "research-catalog.json")
    catalog = {
        "@context": "https://schema.org",
        "@type": "DataCatalog",
        "@id": catalog_id,
        "name": "ThesisAnalysisOS research experiments",
        "dataset": [],
    }
    if revision:
        catalog["version"] = revision
    for experiment in EXPERIMENTS:
        filename = experiment.record + ".json"
        identifier = "evals/results/" + filename
        raw = (records_dir / filename).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if revision and digest != archived[experiment.record]:
            raise ValueError(f"The downloaded record {identifier} differs from its source archive.")
        sizes = _study_sizes(experiment.record, json.loads(raw))
        dataset = {
            "@type": "Dataset",
            "@id": catalog_id + "#" + experiment.record,
            "identifier": identifier,
            "version": "sha256:" + digest,
            "name": experiment.question,
            "url": urljoin(base, experiment.evidence),
            "measurementTechnique": experiment.method.format(**sizes),
            "description": experiment.scope.format(**sizes),
            "variableMeasured": list(experiment.variables),
            "distribution": {
                "@type": "DataDownload",
                "contentUrl": urljoin(base, "records/" + filename),
                "encodingFormat": "application/json",
                "sha256": digest,
            },
        }
        if revision and source_archive:
            dataset["isPartOf"] = {
                "@type": "CreativeWork",
                "name": f"ThesisAnalysisOS source at Git revision {revision}",
                "description": f"This source archive contains the observations in {identifier}.",
                "url": urljoin(base, source_archive),
            }
        catalog["dataset"].append(dataset)
    return catalog
