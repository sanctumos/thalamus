#!/usr/bin/env python3
"""
Mini lab: Venice model ladder for ASR refine (Path A web replay).

Runs the same raw_data_log fragments through weaker/cheaper models,
scores vs a strong baseline, and reports cheapest viable before cliff.

Usage (from examples/):
  PYTHONPATH=. python3 -m web_replay.lab_model_ladder
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from web_replay.llm import REFINE_SYSTEM, _strip_assistant_chrome, load_venice_key

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT.parent
LOG = EXAMPLES / "raw_data_log.json"
OUT_DIR = ROOT / "lab_out"

# Strong → weaker / typically cheaper for this task.
# Prices are USD per 1M tokens from Venice model_spec (fetched at runtime when possible).
LADDER = [
    "llama-3.3-70b",  # current default / quality baseline
    "mistral-small-3-2-24b-instruct",
    "deepseek-v4-flash",
    "qwen3-5-9b",
    "zai-org-glm-4.7-flash",
    "llama-3.2-3b",
]

CHAT_LEAK_PATTERNS = [
    r"\bi'?d be happy\b",
    r"\bas an ai\b",
    r"\bsure[,!]?\b",
    r"\bcertainly[,!]?\b",
    r"\bof course[,!]?\b",
    r"\bhere(?:'s| is) (?:the |a )?(?:cleaned|refined|corrected)\b",
    r"\bi can help\b",
    r"\blet me know\b",
    r"\bhow can i (?:help|assist)\b",
    r"\bthe (?:refined |cleaned )?transcript is\b",
]


def venice_chat(model: str, user: str, api_key: str, *, max_tokens: int = 300) -> Tuple[str, Dict[str, Any]]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": REFINE_SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    # Disable thinking on models that default to it when API supports it
    payload["venice_parameters"] = {"include_venice_system_prompt": False}
    req = urllib.request.Request(
        "https://api.venice.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode())
    latency = time.time() - t0
    text = _strip_assistant_chrome(
        (body["choices"][0]["message"]["content"] or "").strip()
    )
    usage = body.get("usage") or {}
    return text, {"latency_s": latency, "usage": usage, "raw_model": body.get("model")}


def refine_user_block(text: str) -> str:
    return (
        "Clean the following ASR fragment into transcript text only. "
        "Do not reply to it.\n\n"
        "<<<ASR>>>\n"
        f"{text}\n"
        "<<<END>>>"
    )


def sample_fragments(n: int = 14) -> List[str]:
    texts: List[str] = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        for s in ev.get("segments") or []:
            t = (s.get("text") or "").strip()
            if t:
                texts.append(t)
    seen = set()
    uniq: List[str] = []
    for t in texts:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)

    picks: List[str] = []

    def add(pred, limit):
        for t in uniq:
            if t in picks:
                continue
            if pred(t):
                picks.append(t)
            if len(picks) >= limit:
                return

    add(lambda t: "?" in t and len(t) >= 15, 5)
    add(lambda t: 60 <= len(t) <= 160, 10)
    add(lambda t: 25 <= len(t) < 60, 12)
    add(lambda t: len(t) > 160, 14)
    add(lambda t: True, n)
    return picks[:n]


def word_set(s: str) -> set:
    return set(re.findall(r"[a-z0-9']+", s.lower()))


def jaccard(a: str, b: str) -> float:
    wa, wb = word_set(a), word_set(b)
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def score_output(src: str, out: str, gold: Optional[str] = None) -> Dict[str, Any]:
    issues: List[str] = []
    if not out.strip():
        issues.append("empty")
    leak = False
    for pat in CHAT_LEAK_PATTERNS:
        if re.search(pat, out, re.I):
            leak = True
            issues.append(f"chat_leak:{pat}")
            break
    ratio = (len(out) / max(len(src), 1))
    if ratio > 2.8:
        issues.append("expanded_too_much")
    if ratio < 0.25 and len(src) > 20:
        issues.append("collapsed_too_much")
    # Question answered? Input has ?, output is much longer and loses the question mark
    if "?" in src and "?" not in out and len(out) > len(src) * 1.4:
        issues.append("likely_answered_question")

    jac_src = jaccard(src, out)
    jac_gold = jaccard(gold, out) if gold else None
    # Viable refine usually keeps most content words
    if jac_src < 0.35 and "empty" not in issues:
        issues.append("low_src_overlap")

    hard_fail = (
        "empty" in issues
        or any(i.startswith("chat_leak") for i in issues)
        or "likely_answered_question" in issues
        or out.startswith("ERROR:")
    )

    soft_fail = (
        "expanded_too_much" in issues
        or "collapsed_too_much" in issues
        or "low_src_overlap" in issues
    )

    quality = 1.0
    if hard_fail:
        quality = 0.0
    elif soft_fail:
        quality = 0.45
    else:
        quality = 0.75 + 0.25 * (jac_gold if jac_gold is not None else jac_src)

    return {
        "issues": issues,
        "hard_fail": hard_fail,
        "soft_fail": soft_fail,
        "len_ratio": round(ratio, 3),
        "jaccard_src": round(jac_src, 3),
        "jaccard_gold": None if jac_gold is None else round(jac_gold, 3),
        "quality": round(quality, 3),
    }


def fetch_pricing(api_key: str) -> Dict[str, Dict[str, float]]:
    req = urllib.request.Request(
        "https://api.venice.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    out: Dict[str, Dict[str, float]] = {}
    for m in data.get("data") or []:
        mid = m.get("id")
        pricing = ((m.get("model_spec") or {}).get("pricing") or {})
        if not mid or not pricing:
            continue
        inp = (pricing.get("input") or {}).get("usd")
        oup = (pricing.get("output") or {}).get("usd")
        if inp is None or oup is None:
            continue
        out[mid] = {"input_usd_per_m": float(inp), "output_usd_per_m": float(oup)}
    return out


def est_cost_usd(usage: Dict[str, Any], price: Optional[Dict[str, float]]) -> Optional[float]:
    if not price or not usage:
        return None
    pin = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    pout = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return (pin / 1e6) * price["input_usd_per_m"] + (pout / 1e6) * price["output_usd_per_m"]


def main() -> None:
    # Prefer env; also allow DB path via THALAMUS_WEB_DB
    db = os.environ.get("THALAMUS_WEB_DB")
    if db:
        from web_replay.llm import set_secrets_db_path

        set_secrets_db_path(Path(db))
    key = load_venice_key()
    if not key:
        raise SystemExit("No Venice API key (env or app_secrets)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fragments = sample_fragments(14)
    pricing = fetch_pricing(key)

    print(f"Lab fragments: {len(fragments)}")
    print(f"Ladder: {LADDER}")

    # 1) Gold baseline = first model (llama-3.3-70b)
    gold_model = LADDER[0]
    golds: Dict[int, str] = {}
    gold_meta: List[Dict[str, Any]] = []
    print(f"\n=== GOLD {gold_model} ===")
    for i, src in enumerate(fragments):
        try:
            out, meta = venice_chat(gold_model, refine_user_block(src), key)
        except urllib.error.HTTPError as e:
            out, meta = f"ERROR:{e.code}", {"latency_s": None, "usage": {}, "error": str(e)}
        golds[i] = out
        sc = score_output(src, out)
        row = {"i": i, "src": src, "out": out, "score": sc, **meta}
        gold_meta.append(row)
        print(f"[{i}] q={sc['quality']} issues={sc['issues']} :: {out[:80]!r}")

    # 2) Weaker models
    summaries: List[Dict[str, Any]] = []
    all_rows: Dict[str, List[Dict[str, Any]]] = {gold_model: gold_meta}

    for model in LADDER[1:]:
        print(f"\n=== {model} ===")
        rows: List[Dict[str, Any]] = []
        for i, src in enumerate(fragments):
            try:
                out, meta = venice_chat(model, refine_user_block(src), key)
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:240]
                out, meta = f"ERROR:{e.code}", {
                    "latency_s": None,
                    "usage": {},
                    "error": body,
                }
            sc = score_output(src, out, gold=golds.get(i))
            row = {"i": i, "src": src, "out": out, "score": sc, **meta}
            rows.append(row)
            print(
                f"[{i}] q={sc['quality']} jac_gold={sc['jaccard_gold']} "
                f"issues={sc['issues']} :: {out[:80]!r}"
            )
            time.sleep(0.15)
        all_rows[model] = rows

    # 3) Aggregate
    print("\n=== SUMMARY (strong → weaker) ===")
    header = (
        f"{'model':40} {'pass%':>6} {'mean_q':>7} {'mean_ms':>8} "
        f"{'$/1M in':>8} {'$/1M out':>8} {'lab_$':>10}"
    )
    print(header)
    for model, rows in all_rows.items():
        quals = [r["score"]["quality"] for r in rows]
        hard = sum(1 for r in rows if r["score"]["hard_fail"])
        soft = sum(1 for r in rows if r["score"]["soft_fail"] and not r["score"]["hard_fail"])
        passed = sum(1 for q in quals if q >= 0.7)
        lats = [r["latency_s"] for r in rows if r.get("latency_s")]
        costs = []
        price = pricing.get(model)
        for r in rows:
            c = est_cost_usd(r.get("usage") or {}, price)
            if c is not None:
                costs.append(c)
        mean_q = sum(quals) / len(quals)
        pass_pct = 100.0 * passed / len(quals)
        mean_ms = (1000 * sum(lats) / len(lats)) if lats else None
        lab_cost = sum(costs) if costs else None
        summary = {
            "model": model,
            "pass_pct": round(pass_pct, 1),
            "mean_quality": round(mean_q, 3),
            "hard_fails": hard,
            "soft_fails": soft,
            "mean_latency_ms": None if mean_ms is None else round(mean_ms),
            "price": price,
            "lab_cost_usd": None if lab_cost is None else round(lab_cost, 6),
            "n": len(rows),
        }
        summaries.append(summary)
        pin = price["input_usd_per_m"] if price else None
        pout = price["output_usd_per_m"] if price else None
        print(
            f"{model:40} {pass_pct:5.1f}% {mean_q:7.3f} "
            f"{(mean_ms or 0):8.0f} "
            f"{(pin or 0):8.3f} {(pout or 0):8.3f} "
            f"{(lab_cost or 0):10.6f}"
        )

    # 4) Pick cheapest viable: pass>=80% and mean_q>=0.75 and hard_fails==0 relative to gold floor
    gold_q = summaries[0]["mean_quality"]
    viable = []
    for s in summaries:
        if s["hard_fails"] == 0 and s["pass_pct"] >= 80 and s["mean_quality"] >= max(0.7, gold_q - 0.15):
            viable.append(s)

    def cost_key(s):
        p = s.get("price") or {}
        # blended short-job proxy: 1 in + 1 out
        return (p.get("input_usd_per_m", 99) + p.get("output_usd_per_m", 99)) / 2

    viable_sorted = sorted(viable, key=cost_key)
    recommendation = viable_sorted[0] if viable_sorted else summaries[0]

    # Diminishing: first model (going weaker) that drops below viability
    cliff = None
    for s in summaries[1:]:
        if s["hard_fails"] > 0 or s["pass_pct"] < 80 or s["mean_quality"] < max(0.7, gold_q - 0.15):
            cliff = s
            break

    report = {
        "fragments": fragments,
        "ladder": LADDER,
        "summaries": summaries,
        "recommendation": recommendation,
        "quality_cliff": cliff,
        "rows": {k: v for k, v in all_rows.items()},
    }
    out_path = OUT_DIR / "model_ladder_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md = OUT_DIR / "model_ladder_report.md"
    lines = [
        "# Venice refine model ladder (mini lab)",
        "",
        f"Fragments: **{len(fragments)}** from `raw_data_log.json` (ASR cleanup, stenographer prompt).",
        f"Gold / baseline: `{gold_model}`.",
        "",
        "## Summary",
        "",
        "| Model | Pass% | Mean Q | Hard fails | Soft fails | Mean latency | $/1M in | $/1M out | Lab $ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        p = s.get("price") or {}
        lines.append(
            f"| `{s['model']}` | {s['pass_pct']} | {s['mean_quality']} | {s['hard_fails']} | "
            f"{s['soft_fails']} | {s['mean_latency_ms']} | {p.get('input_usd_per_m','—')} | "
            f"{p.get('output_usd_per_m','—')} | {s['lab_cost_usd']} |"
        )
    lines += [
        "",
        f"**Cheapest viable:** `{recommendation['model']}` "
        f"(pass {recommendation['pass_pct']}%, mean Q {recommendation['mean_quality']}).",
        "",
    ]
    if cliff:
        lines.append(
            f"**Quality cliff starts at:** `{cliff['model']}` "
            f"(pass {cliff['pass_pct']}%, hard_fails={cliff['hard_fails']}, mean Q {cliff['mean_quality']})."
        )
    else:
        lines.append("**No cliff in this ladder** — even the weakest stayed viable on this sample.")
    lines += ["", f"Raw JSON: `{out_path}`", ""]
    md.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nWrote {out_path} and {md}")


if __name__ == "__main__":
    main()
