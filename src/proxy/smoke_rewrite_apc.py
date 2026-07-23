#!/usr/bin/env python3
"""
Phase 4e smoke: shared-instruction / different-data APC via the proxy.

Sends two summarize requests with *different* documents through :9000.
With OPTIMIZER_REWRITE_MODE=on, both get the same block-aligned system prefix.

Examples (GPU node, vLLM :8000 + proxy :9000):
  PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py
  PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --long --warmup
  PYTHONPATH=. python src/proxy/smoke_rewrite_apc.py --rag-scale --warmup \\
    2>&1 | tee results/phase4/smoke_apc_ragscale_on.txt

Match smoke-shell OPTIMIZER_REWRITE_MODE to the proxy process (on|off).
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any, Literal

from openai import OpenAI

MODEL = "meta-llama/Llama-3.1-8B-Instruct"
DocScale = Literal["short", "long", "rag"]

DOC_A_SHORT = (
    "Alpha Corp reported quarterly revenue of $4.2B, up 12% year over year, "
    "driven by cloud services in Europe and a new enterprise contract with "
    "Nordic Bank. Operating margin improved to 28%."
)
DOC_B_SHORT = (
    "The City of Leeds approved a zoning ordinance for the waterfront district, "
    "allowing mixed-use towers up to 18 storeys and requiring 20% affordable "
    "housing units. Construction is expected to begin in 2027."
)

# Longer, distinct bodies so prefill cost is visible after GPU warmup.
DOC_A_LONG = """
Alpha Corp (NYSE: ALPH) reported fiscal Q2 results on Tuesday. Quarterly revenue
reached $4.2 billion, up 12% year over year, driven primarily by cloud services
growth in Europe and a multi-year enterprise contract with Nordic Bank valued at
approximately $180 million in total contract value. Operating margin improved to
28%, compared with 24% in the year-ago quarter, reflecting higher software mix and
lower hosting unit costs after the Frankfurt region capacity expansion.

Management highlighted three operational themes. First, cloud ARR grew 19% with
net retention of 118% among the top 200 accounts. Second, professional services
revenue declined 3% as the company shifted toward partner-led deployments.
Third, free cash flow was $910 million after capex of $220 million for additional
GPU clusters reserved for inference workloads. The board authorized a further
$1.0 billion share repurchase and raised the quarterly dividend by $0.04.

Risk factors disclosed in the 10-Q include currency headwinds in the Nordic
region, elevated customer concentration (top ten accounts = 31% of ARR), and
ongoing antitrust inquiries related to bundling of cloud credits with software
licenses. Guidance for Q3 calls for revenue of $4.3–4.4 billion and operating
margin of 27–29%. Analysts on the call pressed for more detail on AI attach rates;
CFO Jane Okonkwo stated that generative-AI add-ons contributed under 4% of ARR
but are expected to reach high single digits by year end if enterprise pilots
convert. The company also noted a one-time $45 million restructuring charge
tied to consolidating three legacy data centres in North America.
""".strip()

DOC_B_LONG = """
The City of Leeds Cabinet approved a comprehensive zoning ordinance for the
South Bank waterfront district after an eighteen-month consultation involving
resident associations, transport planners, and affordable-housing advocates.
The ordinance permits mixed-use towers up to 18 storeys along the riverside
corridor, with a hard cap of 14 storeys on streets backing onto Victorian
terraces. Developers must deliver at least 20% affordable housing by unit count,
or an equivalent financial contribution indexed to local median rents, and must
fund upgrades to two pedestrian bridges linking the district to the city centre.

Construction on the first phase is expected to begin in 2027, contingent on
Environment Agency flood-defence sign-off and National Grid reinforcement for
an estimated additional 40 MW of peak load. The transport assessment projects
6,200 additional weekday trips and mandates a mobility hub with e-bike parking,
bus layover bays, and a contribution toward the proposed tram spur. Heritage
officers secured conditions preserving sightlines to the Parish Church spire and
requiring brick-and-stone facade materials on river-facing elevations.

Opposition councillors argued that 20% affordability is insufficient given
median house prices in LS1/LS11, and tabled an amendment for 30% which was
defeated 5–4. Supporters cited independent modelling that higher mandates would
render several plots unviable under current build-cost inflation. The ordinance
also creates a Community Infrastructure Levy schedule for schools and GP capacity,
with first receipts ring-fenced for a new primary school site near Holbeck.
A monitoring report is due every 24 months, covering housing delivery, flood
resilience works, and air-quality sensors along the A61 corridor.
""".strip()


def _expand_doc(seed: str, *, tag: str, target_chars: int) -> str:
    """Pad a seed with unique numbered paragraphs until ~target_chars (≈ tokens/4)."""
    parts = [seed.strip(), ""]
    n = 0
    while sum(len(p) for p in parts) < target_chars:
        n += 1
        parts.append(
            f"[{tag} section {n}] Additional context unique to document {tag}: "
            f"metric_{n}={n * 17 % 97}, stakeholder_{n % 11}, site_code={tag}-{n:04d}. "
            f"Narrative filler elaborates operational detail {n} without repeating the "
            f"peer document's entities, so user-body LCP stays low while the shared "
            f"catalogue system prefix (under rewrite-on) remains the APC candidate. "
            f"Clause {n} records timestamps, owners, and residual risk notes for audit."
        )
        parts.append("")
    return "\n".join(parts).strip()


# ~5k tokens ≈ 20k chars of English-ish text (thesis RAG scale).
_RAG_TARGET_CHARS = 20_000
DOC_A_RAG = _expand_doc(DOC_A_LONG, tag="ALPHA", target_chars=_RAG_TARGET_CHARS)
DOC_B_RAG = _expand_doc(DOC_B_LONG, tag="LEEDS", target_chars=_RAG_TARGET_CHARS)


def _prompts(*, scale: DocScale) -> tuple[str, str]:
    if scale == "rag":
        doc_a, doc_b = DOC_A_RAG, DOC_B_RAG
    elif scale == "long":
        doc_a, doc_b = DOC_A_LONG, DOC_B_LONG
    else:
        doc_a, doc_b = DOC_A_SHORT, DOC_B_SHORT
    prompt_a = f"Please summarize the following in 3 bullets.\n\n{doc_a}"
    prompt_b = f"Summarise this document in three bullet points:\n\n{doc_b}"
    return prompt_a, prompt_b


def _usage_fields(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None, "cached_tokens": None}
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    cached = None
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None)
    # Some vLLM builds expose this directly on usage.
    if cached is None:
        cached = getattr(usage, "cached_tokens", None)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "cached_tokens": cached}


def one_stream(
    client: OpenAI, prompt: str
) -> tuple[float, float, str, dict[str, int | None]]:
    t0 = time.perf_counter()
    ttft: float | None = None
    chunks: list[str] = []
    usage_info: dict[str, int | None] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "cached_tokens": None,
    }
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=128,
        temperature=0.0,
    )
    for event in stream:
        if getattr(event, "usage", None) is not None:
            usage_info = _usage_fields(event.usage)
        if not event.choices:
            continue
        piece = event.choices[0].delta.content or ""
        if not piece:
            continue
        if ttft is None:
            ttft = time.perf_counter() - t0
        chunks.append(piece)
    total = time.perf_counter() - t0
    if ttft is None:
        raise RuntimeError("no content tokens received")
    return ttft, total, "".join(chunks), usage_info


def warmup(client: OpenAI) -> None:
    client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "Say only: ping"}],
        max_tokens=5,
        temperature=0.0,
    )
    print("Warmup (unrelated ping) done — burns cold CUDA/engine start.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:9000/v1",
        help="Proxy OpenAI base URL (default :9000)",
    )
    parser.add_argument(
        "--long",
        action="store_true",
        help="Use ~1.5–2k char docs (still often under TTFT floor on L40S)",
    )
    parser.add_argument(
        "--rag-scale",
        action="store_true",
        help="Use ~5k-token-scale distinct docs (thesis RAG size; preferred APC check)",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Send an unrelated ping before A/B (recommended for fair on vs off)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="Seconds to sleep between A and B (default 0.5)",
    )
    args = parser.parse_args()

    if args.rag_scale:
        scale: DocScale = "rag"
    elif args.long:
        scale = "long"
    else:
        scale = "short"

    prompt_a, prompt_b = _prompts(scale=scale)
    mode = os.environ.get("OPTIMIZER_REWRITE_MODE", "on").strip().lower()

    client = OpenAI(base_url=args.base_url, api_key="EMPTY")
    print(f"base_url={args.base_url}")
    print(f"smoke_shell OPTIMIZER_REWRITE_MODE={mode!r} (must match proxy process)")
    print(f"docs={scale}  warmup={args.warmup}")
    print("Case: shared instruction (paraphrased) + DIFFERENT documents")
    print("---")
    print(f"INPUT A chars={len(prompt_a)}:")
    print(prompt_a[:240] + ("…" if len(prompt_a) > 240 else ""))
    print("---")
    print(f"INPUT B chars={len(prompt_b)}:")
    print(prompt_b[:240] + ("…" if len(prompt_b) > 240 else ""))
    print("---")

    from src.proxy.rewrite.pipeline import rewrite_request

    for label, prompt in (("A", prompt_a), ("B", prompt_b)):
        body, decision = rewrite_request(
            {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
        )
        print(
            f"REWRITE {label}: action={decision.action} reason={decision.reason} "
            f"task={decision.catalogue_task}"
        )
        if decision.action == "rewrite":
            sys_msg = body["messages"][0]["content"]
            usr_msg = body["messages"][1]["content"]
            print(f"  system[:160]={sys_msg[:160]!r}")
            print(f"  user[:160]={usr_msg[:160]!r}")
    print("---")

    if args.warmup:
        warmup(client)
        print("---")

    ttft_a, total_a, text_a, use_a = one_stream(client, prompt_a)
    print(f"Doc A  ttft={ttft_a:.3f}s total={total_a:.3f}s")
    print(
        f"  usage prompt={use_a['prompt_tokens']} completion={use_a['completion_tokens']} "
        f"cached={use_a['cached_tokens']}"
    )
    print(f"  LLM output (full):\n{text_a}")
    print("---")

    time.sleep(args.pause)

    ttft_b, total_b, text_b, use_b = one_stream(client, prompt_b)
    print(f"Doc B  ttft={ttft_b:.3f}s total={total_b:.3f}s")
    print(
        f"  usage prompt={use_b['prompt_tokens']} completion={use_b['completion_tokens']} "
        f"cached={use_b['cached_tokens']}"
    )
    print(f"  LLM output (full):\n{text_b}")

    ratio = ttft_a / ttft_b if ttft_b > 0 else float("inf")
    print("---")
    print(f"TTFT A/B ratio = {ratio:.2f}x  (>1 means B faster)")
    if use_a["cached_tokens"] is not None or use_b["cached_tokens"] is not None:
        print(
            f"Cached tokens A={use_a['cached_tokens']} B={use_b['cached_tokens']} "
            "(B >> A under rewrite-on + APC is the strong signal)"
        )
    else:
        print(
            "cached_tokens not reported by this vLLM build — rely on TTFT + rewrite logs."
        )
    print(
        "Read: at short/long scale, identical on/off A/B means perf unverified. "
        "At rag-scale, on should show lower B TTFT (or higher B cached) than off if APC helps."
    )
    print("Proxy headers: X-Optimizer-Rewrite should match action above.")


if __name__ == "__main__":
    main()
