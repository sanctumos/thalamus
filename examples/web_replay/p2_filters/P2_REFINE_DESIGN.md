# P2 refine engine + home-topic breaker — design (2026-08-11)

Goal: after the filter **escalates once**, stop filter work and start **P2 conversational refinement** — periodic whole-window passes that re-analyze in greater context (punctuation, turns, topic). A separate **breaker** turns P2 refine **off** when talk drifts from the home topic and **back on** when it returns — with hysteresis so it does not thrash.

## Roles (keep clean)

| Piece | Job | LLM? |
|-------|-----|------|
| **P2 filter** | Cheap accumulating rules → one escalate | No |
| **Evaluator** | Gate escalate (auto, internal) | Optional Venice |
| **P2 refine engine** | Every N turns: re-analyze window in context | Venice (stub fallback) |
| **Breaker** | On/off latch vs **home topic** (hysteresis) | No (lexical + cues) |

## Data model

- **`p2_refine_passes`** (runtime, wiped on Play/Reset): `id, pass_index, window_start_raw_id, window_end_raw_id, status ('on'|'off'), mode ('venice'|'stub'), text, topic_score, home_overlap_json, created_at`.
- **`p2_topic_state`** (runtime, one row per Play): `id, state ('on'|'off'), home_text, home_terms_json, on_streak, off_streak, last_pass_raw_id, updated_at`.
- Settings in `thalamus_settings` (survive Play/Reset) — see config hooks.

## Refine cadence

- After escalate, P2 mode starts with `state='on'`, home topic seeded from the escalate window (salient + window text).
- Every **`p2_refine_every_turns`** raw segments (default **5**) **and** breaker `on`: run one refine pass over the **current window** (escalate anchor → latest).
- Window is capped by **`p2_refine_max_segments`** (default 80) so Venice stays cheap; oldest turns drop out of the prompt but stay in P0/P1 panes.
- Output: cleaned turns with better punctuation / speaker labels / light topic note — **not** CRM/Tasks writes.

## Home topic + breaker (hysteresis)

- **Home topic** = terms from the last **on** refine pass (top content terms, minus stopwords) + project card nouns. Updated only on successful `on` passes (slow drift, not per-turn).
- **Topic score** per new segment batch: weighted overlap of content terms vs home terms + optional closing-cue penalty.
- **Off:** require **`p2_breaker_off_streak`** (default 3) consecutive batches with score < **`p2_breaker_off_score`** (default 0.18) → flip to `off`, stop refine passes, keep ingesting.
- **On:** while `off`, require **`p2_breaker_on_streak`** (default 2) consecutive batches with score ≥ **`p2_breaker_on_score`** (default 0.34) → flip to `on`, resume refine.
- **Closing cues** (e.g. wrap-up phrases) add a small penalty but never flip alone — same “don’t tip on hi alone” discipline.

## Config hooks (`thalamus_settings`)

| Key | Default | Meaning |
|-----|---------|---------|
| `p2_refine_every_turns` | `5` | Turns between refine passes |
| `p2_refine_max_segments` | `80` | Max window size sent to refine |
| `p2_refine_model` | `""` | Empty → P1 Venice model |
| `p2_breaker_enabled` | `true` | Master switch for breaker |
| `p2_breaker_off_score` | `0.18` | Below this counts as off-topic batch |
| `p2_breaker_on_score` | `0.34` | Above this counts as on-topic batch |
| `p2_breaker_off_streak` | `3` | Consecutive low batches to flip off |
| `p2_breaker_on_streak` | `2` | Consecutive high batches to flip on |
| `p2_breaker_closing_penalty` | `0.08` | Weak wrap-up cue penalty |

## SSE / UI

- `p2_refine` — new refine pass (text + mode + topic_score).
- `p2_breaker` — `{state: 'on'|'off', topic_score, reason}` on flips.
- Review card moves to a **tab/receipt**; P2 pane becomes the refine stream with breaker state badge.

## Not in this slice

- No CRM/Tasks writes, no web search, no Sanctum agent.
- Home-topic similarity is lexical (no embeddings service yet) — swappable later.
