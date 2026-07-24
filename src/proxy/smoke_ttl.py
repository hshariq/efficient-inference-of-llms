#!/usr/bin/env python3
"""
Phase 5 smoke: exercise TTL headers via the live proxy.

Requires vLLM :8000 + proxy :9000 with admission hold on (and rewrite on).

  export OPTIMIZER_REWRITE_MODE=on
  export OPTIMIZER_TTL_MODE=on
  export OPTIMIZER_ADMISSION_HOLD_MS=50
  export OPTIMIZER_MAX_TTL_MS=200
  export OPTIMIZER_TTL_BATCH_PEERS=8
  bash src/proxy/start_proxy.sh

  PYTHONPATH=. python src/proxy/smoke_ttl.py
  # optional hard max_batch check (proxy peers must match):
  PYTHONPATH=. python src/proxy/smoke_ttl.py --max-batch-peers 8
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
import time

import httpx
from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
VALID_DISPOSITIONS = frozenset({"skip", "hold_window", "max_batch", "ttl_escape"})

SUMMARIZE_PROMPT = (
    "Please summarize the following in 3 bullets.\n\n"
    "Alpha Corp revenue rose 12% on cloud growth in Europe."
)
EXTRACT_PROMPT = (
    "Extract all named entities from the following text.\n\n"
    "Alice met Bob at Acme Corp in London on Tuesday."
)


def _one(
    base_url: str,
    prompt: str = SUMMARIZE_PROMPT,
) -> tuple[str, str, str, float]:
    t0 = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        r = client.post(
            "/chat/completions",
            headers={"Authorization": "Bearer EMPTY"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
                "temperature": 0,
                "stream": False,
            },
        )
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    return (
        r.headers.get("x-optimizer-ttl", ""),
        r.headers.get("x-optimizer-ttl-wait-ms", ""),
        r.headers.get("x-optimizer-task", ""),
        elapsed,
    )


def _parse_wait(wait: str) -> float:
    try:
        return float(wait)
    except (TypeError, ValueError):
        return -1.0


def _assert_disposition(disp: str, *, allowed: set[str] | frozenset[str]) -> None:
    if disp not in VALID_DISPOSITIONS:
        raise AssertionError(f"invalid TTL disposition {disp!r}")
    if disp not in allowed:
        raise AssertionError(f"expected one of {sorted(allowed)}, got {disp!r}")


def _assert_wait_bounded(wait: str, max_ttl_ms: float, slack_ms: float = 40.0) -> float:
    w = _parse_wait(wait)
    if w < 0:
        raise AssertionError(f"non-negative wait_ms required, got {wait!r}")
    if w > max_ttl_ms + slack_ms:
        raise AssertionError(
            f"wait_ms={w:.2f} exceeds MAX_TTL_MS={max_ttl_ms} + slack={slack_ms}"
        )
    return w


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:9000/v1")
    parser.add_argument(
        "--max-ttl-ms",
        type=float,
        default=float(os.environ.get("OPTIMIZER_MAX_TTL_MS", "200")),
        help="Hard wait ceiling used for assertions (must match proxy).",
    )
    parser.add_argument(
        "--hold-ms",
        type=float,
        default=float(os.environ.get("OPTIMIZER_ADMISSION_HOLD_MS", "50")),
        help="Expected hold window (must match proxy).",
    )
    parser.add_argument(
        "--max-batch-peers",
        type=int,
        default=0,
        help="If >0, fire N concurrent same-task requests and assert max_batch "
        "(proxy OPTIMIZER_TTL_BATCH_PEERS must equal N).",
    )
    parser.add_argument(
        "--expect-hold-off",
        action="store_true",
        help="Assert skip / ~0 wait only (control: OPTIMIZER_TTL_MODE=off). "
        "Intentionally does not assert X-Optimizer-Task — disposition/timing only.",
    )
    args = parser.parse_args()

    print(f"base_url={args.base_url}")
    print(
        f"expect hold_ms≈{args.hold_ms} max_ttl_ms={args.max_ttl_ms} "
        f"hold_off={args.expect_hold_off}"
    )

    if args.expect_hold_off:
        print("--- control: lonely (expect skip, wait≈0) ---")
        disp, wait, task, elapsed = _one(args.base_url)
        print(
            f"  TTL={disp!r} wait_ms={wait!r} task={task!r} wall_s={elapsed:.3f}"
        )
        _assert_disposition(disp, allowed={"skip"})
        w = _parse_wait(wait)
        if w < 0 or w > 5.0:
            raise AssertionError(f"hold-off wait_ms should be ≈0, got {wait!r}")
    else:
        print("--- lonely request (expect hold_window, wait≈hold_ms) ---")
        disp, wait, task, elapsed = _one(args.base_url)
        print(
            f"  TTL={disp!r} wait_ms={wait!r} task={task!r} wall_s={elapsed:.3f}"
        )
        _assert_disposition(disp, allowed={"hold_window", "ttl_escape"})
        w = _assert_wait_bounded(wait, args.max_ttl_ms)
        if disp == "hold_window" and w + 15 < args.hold_ms * 0.5:
            raise AssertionError(
                f"hold_window wait_ms={w:.2f} unexpectedly << hold_ms={args.hold_ms}"
            )
        if task and task != "summarize_3_bullets":
            print(f"  WARN: expected summarize_3_bullets, got task={task!r}")

        print("--- two concurrent same-task (expect hold_window together) ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(_one, args.base_url) for _ in range(2)]
            for i, fut in enumerate(futs, start=1):
                disp, wait, task, elapsed = fut.result()
                print(
                    f"  req{i}: TTL={disp!r} wait_ms={wait!r} "
                    f"task={task!r} wall_s={elapsed:.3f}"
                )
                _assert_disposition(disp, allowed={"hold_window", "max_batch"})
                _assert_wait_bounded(wait, args.max_ttl_ms)

        print(
            "--- starvation / independence: lonely off-task during same-task hold ---"
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            batch_futs = [pool.submit(_one, args.base_url) for _ in range(2)]
            time.sleep(0.01)
            lonely_fut = pool.submit(_one, args.base_url, EXTRACT_PROMPT)

            batch_tasks: list[str] = []
            for i, fut in enumerate(batch_futs, start=1):
                disp, wait, task, elapsed = fut.result()
                print(
                    f"  batch req{i}: TTL={disp!r} wait_ms={wait!r} "
                    f"task={task!r} wall_s={elapsed:.3f}"
                )
                _assert_disposition(disp, allowed={"hold_window", "max_batch"})
                _assert_wait_bounded(wait, args.max_ttl_ms)
                batch_tasks.append(task)

            disp, wait, task, elapsed = lonely_fut.result()
            print(
                f"  lonely (different task): TTL={disp!r} wait_ms={wait!r} "
                f"task={task!r} wall_s={elapsed:.3f}"
            )
            _assert_disposition(disp, allowed={"hold_window", "ttl_escape"})
            lonely_wait = _assert_wait_bounded(wait, args.max_ttl_ms)
            if task and any(t and t == task for t in batch_tasks):
                raise AssertionError(
                    f"lonely request should land in a different catalogue task; "
                    f"got task={task!r} batch_tasks={batch_tasks!r}"
                )
            # Dissertation proof: off-task wait is independently bounded, not
            # stuck behind the other group's batch size / peers.
            print(
                f"  ok: off-task wait_ms={lonely_wait:.2f} <= "
                f"MAX_TTL_MS+slack ({args.max_ttl_ms}+40)"
            )

        if args.max_batch_peers > 0:
            n = args.max_batch_peers
            print(f"--- max_batch: {n} concurrent same-task (expect max_batch) ---")
            with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
                futs = [pool.submit(_one, args.base_url) for _ in range(n)]
                for i, fut in enumerate(futs, start=1):
                    disp, wait, task, elapsed = fut.result()
                    print(
                        f"  req{i}: TTL={disp!r} wait_ms={wait!r} "
                        f"task={task!r} wall_s={elapsed:.3f}"
                    )
                    _assert_disposition(disp, allowed={"max_batch"})
                    _assert_wait_bounded(wait, args.max_ttl_ms)

    # Sanity OpenAI path still works
    client = OpenAI(base_url=args.base_url, api_key="EMPTY")
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": SUMMARIZE_PROMPT}],
        max_tokens=32,
        temperature=0,
    )
    print("--- openai client ok ---")
    print((r.choices[0].message.content or "")[:120])
    print("smoke_ttl: PASS")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"smoke_ttl: FAIL — {exc}", file=sys.stderr)
        sys.exit(1)
