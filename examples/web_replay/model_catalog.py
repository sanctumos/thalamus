#!/usr/bin/env python3
"""
Whitelisted Venice refine models (≥ lab pass_pct threshold).

Copyright (C) 2025-2026 Mark "Rizzn" Hopkins, Athena Vernal, John Casaretto
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
WHITELIST_PATH = ROOT / "lab_out" / "refine_model_whitelist.json"
PASS_PCT_MIN = 85.0


def load_whitelist(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path or WHITELIST_PATH)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data.get("models"), list):
        raise ValueError("whitelist missing models[]")
    return data


def whitelisted_models(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    data = load_whitelist(path)
    floor = float(data.get("pass_pct_min", PASS_PCT_MIN))
    out = []
    for m in data["models"]:
        if float(m.get("pass_pct", 0)) >= floor:
            out.append(m)
    return out


def whitelist_ids(path: Optional[Path] = None) -> List[str]:
    return [m["id"] for m in whitelisted_models(path)]


def default_model_id(path: Optional[Path] = None) -> str:
    data = load_whitelist(path)
    did = data.get("default_model_id")
    ids = set(whitelist_ids(path))
    if did and did in ids:
        return str(did)
    models = whitelisted_models(path)
    if not models:
        return "mistral-small-3-2-24b-instruct"
    # cheapest by cost_rel
    return sorted(models, key=lambda m: float(m.get("cost_rel", 99)))[0]["id"]


def get_model_meta(model_id: str, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    for m in whitelisted_models(path):
        if m["id"] == model_id:
            return m
    return None


def is_whitelisted(model_id: str, path: Optional[Path] = None) -> bool:
    return model_id in set(whitelist_ids(path))


def option_label(m: Dict[str, Any]) -> str:
    """Dropdown label: name · score% · cost rating."""
    name = m.get("label") or m["id"]
    score = m.get("pass_pct", 0)
    rating = m.get("cost_rating", "?")
    rel = m.get("cost_rel", 1)
    return f"{name} · {score:.0f}% lab · {rating} ({rel:.1f}×)"


def settings_models_payload(selected: str) -> Dict[str, Any]:
    models = whitelisted_models()
    return {
        "venice_model": selected,
        "venice_model_options": [
            {
                "id": m["id"],
                "label": option_label(m),
                "pass_pct": m.get("pass_pct"),
                "mean_quality": m.get("mean_quality"),
                "cost_rating": m.get("cost_rating"),
                "cost_rel": m.get("cost_rel"),
                "blended_usd_per_m": m.get("blended_usd_per_m"),
            }
            for m in models
        ],
        "venice_model_meta": get_model_meta(selected),
        "pass_pct_min": PASS_PCT_MIN,
    }


def write_whitelist_from_lab_summaries(
    summaries: List[Dict[str, Any]],
    *,
    lab_date: str,
    path: Optional[Path] = None,
    pass_pct_min: float = PASS_PCT_MIN,
) -> Dict[str, Any]:
    """Build whitelist JSON from lab_model_ladder summaries (≥ threshold)."""
    rows = []
    for s in summaries:
        if float(s.get("pass_pct", 0)) < pass_pct_min:
            continue
        price = s.get("price") or {}
        pin = float(price.get("input_usd_per_m") or 0)
        pout = float(price.get("output_usd_per_m") or 0)
        blended = (pin + pout) / 2.0 if (pin or pout) else 0.0
        rows.append(
            {
                "id": s["model"],
                "pass_pct": float(s["pass_pct"]),
                "mean_quality": float(s.get("mean_quality") or 0),
                "hard_fails": int(s.get("hard_fails") or 0),
                "mean_latency_ms": s.get("mean_latency_ms"),
                "price": {
                    "input_usd_per_m": pin,
                    "output_usd_per_m": pout,
                },
                "blended_usd_per_m": blended,
                "label": s["model"],
            }
        )
    if not rows:
        raise ValueError("no models met pass_pct_min")
    min_blend = min(r["blended_usd_per_m"] for r in rows) or 1.0
    for r in rows:
        rel = r["blended_usd_per_m"] / min_blend
        r["cost_rel"] = round(rel, 2)
        if rel <= 1.25:
            r["cost_rating"] = "$"
        elif rel <= 3.0:
            r["cost_rating"] = "$$"
        else:
            r["cost_rating"] = "$$$"
    rows.sort(key=lambda r: r["cost_rel"])
    # Prefer prior default if still present; else cheapest
    default = rows[0]["id"]
    for prefer in ("mistral-small-3-2-24b-instruct", "llama-3.3-70b"):
        if any(r["id"] == prefer for r in rows):
            default = prefer
            break
    data = {
        "version": 1,
        "pass_pct_min": pass_pct_min,
        "lab_date": lab_date,
        "source_report": "lab_out/model_ladder_report.json",
        "fragment_source": "examples/raw_data_log.json",
        "notes": (
            "Whitelist for Settings refine-model dropdown. "
            "Regenerated by: PYTHONPATH=examples python3 -m web_replay.lab_model_ladder"
        ),
        "models": rows,
        "default_model_id": default,
    }
    out = Path(path or WHITELIST_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
