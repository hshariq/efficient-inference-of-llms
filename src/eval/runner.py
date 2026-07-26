"""Load workload, fire requests, write JSONL results."""

from __future__ import annotations

import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from src.eval.backends import make_backend, to_request_result
from src.eval.config import EvalConfig
from src.eval.schemas import RequestResult, WorkloadItem


def load_workload(path: Path) -> list[WorkloadItem]:
    items: list[WorkloadItem] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(WorkloadItem.from_dict(json.loads(line)))
    return items


def fetch_proxy_metrics(url: str) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.json()
    except Exception:  # noqa: BLE001
        return None


def reset_proxy_metrics(url: str) -> None:
    base = url.rstrip("/")
    for reset_url in (f"{base}/reset", base.replace("/metrics", "/metrics/reset")):
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.post(reset_url)
                if r.status_code < 400:
                    return
        except Exception:  # noqa: BLE001
            continue


def detect_server_capabilities(base_url: str, *, model: str) -> dict[str, Any]:
    """
    Probe upstream for audit trail (vanilla vs APC is otherwise trust-based).

    Strategy: identical short prompt twice; if cached_tokens appears on #2,
    prefix caching is effectively on. Also record /models payload keys.
    """
    from src.eval.backends import _extract_cached_tokens

    info: dict[str, Any] = {
        "base_url": base_url,
        "models_ok": False,
        "apc_probe": "unknown",
        "cached_tokens_call1": None,
        "cached_tokens_call2": None,
        "usage_call2_raw": None,
    }
    root = base_url.rstrip("/")
    prompt = (
        "APC capability probe. Summarize in one sentence: Leeds campus has libraries."
    )
    try:
        with httpx.Client(base_url=root, timeout=60.0) as client:
            try:
                mr = client.get("/models")
                info["models_ok"] = mr.status_code == 200
                if mr.status_code == 200:
                    info["models_ids"] = [
                        m.get("id") for m in (mr.json().get("data") or [])[:5]
                    ]
            except Exception as exc:  # noqa: BLE001
                info["models_error"] = str(exc)[:200]

            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16,
                "temperature": 0,
                "stream": False,
            }
            u1 = (client.post("/chat/completions", json=body).json()).get("usage") or {}
            u2 = (client.post("/chat/completions", json=body).json()).get("usage") or {}
            c1 = _extract_cached_tokens(u1)
            c2 = _extract_cached_tokens(u2)
            info["cached_tokens_call1"] = c1
            info["cached_tokens_call2"] = c2
            info["usage_call2_raw"] = u2
            if c2 > 0:
                info["apc_probe"] = "likely_enabled"
            elif "prompt_tokens_details" in u2 or "cached_tokens" in u2:
                info["apc_probe"] = "field_present_but_zero"
            else:
                info["apc_probe"] = "no_cached_tokens_field_or_zero"
    except Exception as exc:  # noqa: BLE001
        info["apc_probe"] = "probe_failed"
        info["probe_error"] = str(exc)[:300]
    return info


def _percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def summarize_results(results: list[RequestResult]) -> dict[str, Any]:
    ok = [r for r in results if r.disposition not in ("error",)]
    processed = sum(r.prompt_tokens for r in ok)
    saved = sum(r.cached_tokens for r in ok)
    lat = [r.latency_ms for r in ok]
    ttft = [r.ttft_ms for r in ok]
    hits = sum(1 for r in ok if r.hit)
    gen_tokens = sum(r.completion_tokens for r in ok)
    total_s = sum(r.latency_ms for r in ok) / 1000.0 if ok else 0.0

    # One spread value per best_of_n group (not per member duplicate)
    bon_by_group: dict[str, float] = {}
    for r in ok:
        if r.tier != "best_of_n" or r.bon_group_spread_ms is None:
            continue
        gid = r.best_of_n_group or r.req_id
        bon_by_group[gid] = float(r.bon_group_spread_ms)
    bon_spreads = list(bon_by_group.values())

    out: dict[str, Any] = {
        "n": len(results),
        "n_ok": len(ok),
        "prompt_tokens": processed,
        "cached_tokens": saved,
        "tsr": (saved / processed) if processed else 0.0,
        "hit_rate": (hits / len(ok)) if ok else 0.0,
        "mean_ttft_ms": statistics.mean(ttft) if ttft else 0.0,
        "p50_latency_ms": _percentile(lat, 50),
        "p90_latency_ms": _percentile(lat, 90),
        "p99_latency_ms": _percentile(lat, 99),
        "throughput_gen_tok_s": (gen_tokens / total_s) if total_s > 0 else 0.0,
    }
    if bon_spreads:
        out["best_of_n_spread_ms"] = {
            "n_groups": len(bon_spreads),
            "mean": statistics.mean(bon_spreads),
            "min": min(bon_spreads),
            "max": max(bon_spreads),
            "p50": _percentile(bon_spreads, 50),
            "p90": _percentile(bon_spreads, 90),
            "p99": _percentile(bon_spreads, 99),
            "values_ms": sorted(bon_spreads),
        }
    return out


def _loud(msg: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{msg}\n{bar}\n", flush=True)


def run_eval(cfg: EvalConfig) -> dict[str, Any]:
    from src.eval.cached_tokens_gate import check_cached_tokens_gate

    gate_skipped = bool(getattr(cfg, "skip_cached_tokens_gate", False))
    if gate_skipped:
        _loud(
            "GATE SKIPPED (--skip-cached-tokens-gate)\n"
            "  TSR numbers from this run are UNVERIFIED.\n"
            "  Do NOT cite in dissertation tables/charts without a real probe pass."
        )

    # Hard gate BEFORE any workload work (prevents silent TSR=0 scale runs)
    gate_marker = check_cached_tokens_gate(
        system=cfg.system,
        base_url=cfg.base_url,
        skip=gate_skipped,
    )

    items = load_workload(cfg.workload_path)
    backend = make_backend(cfg.system, cfg.base_url, timeout_s=cfg.timeout_s)
    cfg.out_path.parent.mkdir(parents=True, exist_ok=True)

    # Audit trail: which APC mode did we actually hit?
    server_caps = detect_server_capabilities(cfg.base_url, model=cfg.model)
    expected_apc = cfg.system in ("apc", "optimizer", "optimizer_hold", "gptcache")
    mode_mismatch = False
    if cfg.system == "vanilla" and server_caps.get("apc_probe") == "likely_enabled":
        mode_mismatch = True
        _loud(
            "MODE MISMATCH — DO NOT CITE THIS RUN AS VANILLA\n"
            "  --system vanilla but live probe saw cached_tokens > 0.\n"
            "  Restart vLLM WITHOUT --enable-prefix-caching, then re-run.\n"
            f"  apc_probe={server_caps.get('apc_probe')!r} "
            f"cached_tokens_call2={server_caps.get('cached_tokens_call2')!r}"
        )
    if expected_apc and server_caps.get("apc_probe") in (
        "no_cached_tokens_field_or_zero",
        "field_present_but_zero",
        "probe_failed",
    ):
        mode_mismatch = True
        _loud(
            "MODE / SCHEMA MISMATCH — DO NOT CITE TSR FROM THIS RUN\n"
            "  Expected prefix-cache signal but live probe did not confirm it.\n"
            "  Run: PYTHONPATH=. python -m src.eval.probe_cached_tokens\n"
            f"  apc_probe={server_caps.get('apc_probe')!r} "
            f"usage_call2={server_caps.get('usage_call2_raw')!r}"
        )

    if cfg.proxy_metrics_url:
        reset_proxy_metrics(cfg.proxy_metrics_url)

    results: list[RequestResult] = []

    def _one(item: WorkloadItem) -> RequestResult:
        br = backend.complete(item, model=cfg.model, max_tokens=cfg.max_tokens)
        return to_request_result(item, cfg.system, br)

    groups: dict[str, list[WorkloadItem]] = {}
    solo: list[WorkloadItem] = []
    for it in items:
        if it.tier == "best_of_n" and it.best_of_n_group:
            groups.setdefault(it.best_of_n_group, []).append(it)
        else:
            solo.append(it)

    with cfg.out_path.open("w", encoding="utf-8") as out_f:

        def _write(res: RequestResult) -> None:
            results.append(res)
            out_f.write(json.dumps(res.to_dict(), ensure_ascii=False) + "\n")
            out_f.flush()

        if cfg.concurrency <= 1:
            for it in solo:
                _write(_one(it))
        else:
            with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
                futs = {pool.submit(_one, it): it for it in solo}
                for fut in as_completed(futs):
                    _write(fut.result())

        # Best-of-N: concurrent dispatch; log observed send-timestamp spread
        for _gid, members in groups.items():
            with ThreadPoolExecutor(max_workers=len(members)) as pool:
                futs = [pool.submit(_one, m) for m in members]
                group_res = [fut.result() for fut in futs]
            sends = [r.client_send_ts for r in group_res if r.client_send_ts is not None]
            spread_ms = (
                (max(sends) - min(sends)) * 1000.0 if len(sends) >= 2 else 0.0
            )
            for r in group_res:
                r.bon_group_spread_ms = spread_ms
                _write(r)

    summary = summarize_results(results)
    summary["system"] = cfg.system
    summary["workload"] = str(cfg.workload_path)
    summary["out"] = str(cfg.out_path)
    summary["concurrency"] = cfg.concurrency
    summary["server_capabilities"] = server_caps
    summary["expected_apc"] = expected_apc
    summary["mode_mismatch"] = mode_mismatch
    summary["cached_tokens_gate_skipped"] = gate_skipped
    summary["cached_tokens_gate_marker"] = (
        {k: gate_marker.get(k) for k in ("ts_iso", "upstream_vllm", "cached_tokens_call2", "slurm_job_id")}
        if isinstance(gate_marker, dict) and not gate_marker.get("skipped")
        else gate_marker
    )
    if gate_skipped:
        summary["cite_warning"] = (
            "cached_tokens gate SKIPPED — TSR UNVERIFIED; do not cite"
        )
    if mode_mismatch:
        summary["cite_warning"] = (
            "MODE MISMATCH — do not cite this run's system label / TSR without fix"
        )
        _loud(
            "RUN COMPLETED WITH mode_mismatch=true — "
            "summary flagged cite_warning; do not use in dissertation tables as-is."
        )

    if cfg.proxy_metrics_url:
        proxy_m = fetch_proxy_metrics(cfg.proxy_metrics_url)
        summary["proxy_metrics"] = proxy_m

    summary_path = cfg.out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
