"""Push pipeline metrics to Grafana Cloud via Prometheus remote_write.

Callers build a list of {name, value, labels?} dicts and call push().
Push silently skips if GRAFANA_REMOTE_WRITE_URL is not set, so this is
safe in local/dev environments without any config changes.
"""

import json
import os
import struct
import time
from collections import Counter
from pathlib import Path

import httpx


# --- Protobuf encoding -------------------------------------------------------
# Implements just enough of the Prometheus remote_write proto to push gauges.
# WriteRequest > TimeSeries > (Label*, Sample)

def _varint(n: int) -> bytes:
    out = b''
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | 0x80 if n else b])
        if not n:
            break
    return out

def _f_varint(num: int, val: int) -> bytes: return _varint((num << 3) | 0) + _varint(val)
def _f_64bit(num: int, val: bytes) -> bytes: return _varint((num << 3) | 1) + val
def _f_bytes(num: int, data: bytes) -> bytes: return _varint((num << 3) | 2) + _varint(len(data)) + data
def _f_str(num: int, s: str) -> bytes:       return _f_bytes(num, s.encode())

def _label(k: str, v: str) -> bytes:
    return _f_str(1, k) + _f_str(2, v)

def _sample(val: float, ts_ms: int) -> bytes:
    return _f_64bit(1, struct.pack('<d', val)) + _f_varint(2, ts_ms)

def _timeseries(labels: dict, val: float, ts_ms: int) -> bytes:
    data = b''.join(_f_bytes(1, _label(k, v)) for k, v in sorted(labels.items()))
    return data + _f_bytes(2, _sample(val, ts_ms))

def _write_request(series: list[bytes]) -> bytes:
    return b''.join(_f_bytes(1, s) for s in series)


# --- Push --------------------------------------------------------------------

def push(metrics: list[dict], log_error=None, labels: dict | None = None) -> None:
    """Push a list of {name, value, labels?} metrics to Grafana Cloud.

    labels: base labels merged into every metric (e.g. {"run_id": "..."}).
    Per-metric labels take precedence over base labels.
    Silently skips if GRAFANA_REMOTE_WRITE_URL is unset.
    Errors are logged but never raise — metrics push must not break the pipeline.
    """
    url   = os.environ.get("GRAFANA_REMOTE_WRITE_URL")
    user  = os.environ.get("GRAFANA_STACK_ID", "")
    token = os.environ.get("GRAFANA_API_KEY", "")

    if not url:
        return

    try:
        import snappy
    except ImportError:
        _warn("python-snappy not installed — skipping metrics push", log_error)
        return

    base = labels or {}
    ts_ms = int(time.time() * 1000)
    series = [
        _timeseries(
            {"__name__": m["name"], "job": "builder-jobs-pipeline", **base, **m.get("labels", {})},
            float(m["value"]),
            ts_ms,
        )
        for m in metrics
    ]

    try:
        body = _write_request(series)
        compressed = snappy.compress(body)
        resp = httpx.post(
            url,
            content=compressed,
            headers={
                "Content-Type": "application/x-protobuf",
                "Content-Encoding": "snappy",
                "X-Prometheus-Remote-Write-Version": "0.1.0",
            },
            auth=(user, token),
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as e:
        _warn(f"metrics push failed: {e}", log_error)


def _warn(msg: str, log_error=None) -> None:
    if log_error:
        log_error(msg)
    else:
        print(f"WARNING: {msg}")


# --- Board state -------------------------------------------------------------

SUPPORTED_ATS = {
    "ashby", "greenhouse", "lever", "workday", "bamboo",
    "breezy", "workable", "smartrecruiters", "eightfold",
}

DATA_DIR = Path(__file__).parent.parent / "data"


def board_metrics() -> list[dict]:
    """Compute current board state metrics from data files."""
    classified: dict = {}
    raw_by_id: dict  = {}

    classified_file = DATA_DIR / "jobs_classified.json"
    raw_file        = DATA_DIR / "jobs_raw.json"
    companies_file  = DATA_DIR / "companies.json"
    patterns_file   = DATA_DIR / "job_title_skip_patterns.json"

    if classified_file.exists():
        classified = json.loads(classified_file.read_text())
    if raw_file.exists():
        raw_by_id = {j["id"]: j for j in json.loads(raw_file.read_text())}

    counts: Counter = Counter()
    active_companies: set = set()

    for jid, cl in classified.items():
        if cl.get("is_engineering") is not True:
            continue
        if cl.get("is_contract", False):
            continue
        if cl.get("region") not in ("us", "canada"):
            continue
        raw = raw_by_id.get(jid)
        if not raw:
            continue

        active_companies.add(raw.get("company", ""))
        dims = (
            ("ats",        raw.get("source", "unknown")),
            ("has_equity", str("Equity" in (cl.get("comp_extras") or [])).lower()),
            ("has_salary", str(bool(cl.get("comp"))).lower()),
            ("hybrid",     str(bool(cl.get("is_hybrid"))).lower()),
            ("level",      cl.get("level") or "unclear"),
            ("region",     cl.get("region", "unclear")),
            ("remote",     str(raw.get("remote") is True).lower()),
        )
        counts[dims] += 1

    metrics: list[dict] = []
    total = 0
    for dims, count in counts.items():
        metrics.append({"name": "builder_board_roles", "value": count, "labels": dict(dims)})
        total += count

    metrics.append({"name": "builder_board_roles_total",            "value": total})
    metrics.append({"name": "builder_board_companies_active",        "value": len(active_companies)})
    metrics.append({"name": "builder_board_classification_cache_size", "value": len(classified)})

    if companies_file.exists():
        companies = json.loads(companies_file.read_text())
        monitored = sum(1 for c in companies if c.get("status") == "active"
                        and c.get("ats") in SUPPORTED_ATS)
        metrics.append({"name": "builder_board_companies_monitored", "value": monitored})

    if patterns_file.exists():
        patterns = json.loads(patterns_file.read_text())
        metrics.append({"name": "builder_board_title_skip_patterns", "value": len(patterns)})

    return metrics
