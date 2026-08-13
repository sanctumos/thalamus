# Gold fixture — mortgage → Jim handoff (2026-08-11)

Evaluation target for P2 **review** + future conversational refinement.

**Feed:** `conversations/omi-live-webhook-mortgage-2026-08-11.ndjson`  
**Seam:** NDJSON event index **009** / raw wall time ~`t=626.5` — *“Hey, Chief, how's it going?”*  
**Prior:** events 000–008 — YouTube-style mortgage.buy / crypto pedagogy (ambient).  
**After:** SPEAKER_02 ops talk — upload columns, Cameron, Docket, Rocket Reach, modality.

Live Venice web_replay run (Aug 11): ~166 raw → ~103 refined, avg ~1.55 sources/group. That path is **P1 ASR cleanup** (same-speaker concat + silent cleanup prompt) — **not** P2.

---

## Seam timing (filter, not evaluator)

Do **not** trip on greeting alone (*“Hey, Chief…”* can be personal or business hello).
Accumulate structural + greeting score, then require **ops substance** (tasking /
project nouns like upload, Gmail, Docket) and score ≥ `trip_threshold` (default **12**).
On this feed that lands a few turns after the greeting (upload / columns / knock-out ask).

---

## Review + evaluator stage (what the card must show)

Enough for Thalamus’s **internal evaluation agent** (not HITL, not Sanctum) to answer
*Escalate this window to P2 conversational refinement?* without replaying audio:

1. Conversation window (P0 segments from epoch start through trip).
2. Factoids — why tripped (rule hits + weights + score).
3. Structural sketch (speaker counts, long vs short durations, gap before last).
4. Salient spans (Chief, upload, columns, Gmail, Cameron, Docket, …).
5. Project card (doctor-supplied tiny context).
6. Auto decision + short rationale (Venice or heuristic).

---

## Otto gold (rich context — social-sourcing / Docket / RocketReach / Mark↔Jim)

- **Phase A:** Disposable YouTube/crypto-mortgage ambient — no ops enrichment.
- **Phase B:** Mark↔Jim catch-up on imaging social-sourcing ops.
- **Speakers:** Mark ≈ SPEAKER_00 (greeting “Chief”, Gmail, Docket jazz-hands); Jim ≈ SPEAKER_02 (upload instructions, Cameron, Docket modality, RocketReach titles).
- **Beats:**
  1. Jim needs column-merge upload instructions emailed to Mark’s Gmail.
  2. Cameron impressed → second-client contact path; Mark stay slightly mysterious; Jim already showed Docket.
  3. Docket contact shape — phones/socials; modality missing → radiologist-technologist; RocketReach title cleanup; Mark’s team faster.
  4. “Jazz hands” Docket + Claude = later pitch, not blocking.
  5. Digressions (economics, family, AI parents, computers) = color, not ops.
- **Commitments:** Jim emails upload/column instructions to Gmail; Jim continues RocketReach title pass; Docket jazz-hands/Claude deferred.

---

## Tiny-context algo target (conversation + small project card)

Must **not** invent “Jim” unless the name appears in transcript.

**May see:** SPEAKER_00/02; nouns upload, columns, Gmail, Cameron, Docket, Rocket Reach, radiologist-technologist, modality, Claude.

**Project card example (doctor-supplied):**  
“Engagement: imaging social-sourcing; tools: Docket queue, RocketReach exports; operators: Mark + partner (name unknown unless in transcript).”

**Success:** recover beats + actions + phase split; label partner as `SPEAKER_02` / `partner` until named.

**Failure modes:** hallucinating Jim; treating video as ops; missing Gmail/Cameron/Docket actions; collapsing digression into commitments.

---

## P1 vs P2 (from live run)

| | Live Venice (P1-ish) | P2 after escalate |
|--|----------------------|-------------------|
| Unit | Same-speaker concat | Dialog beats / topic spans |
| Context | One fragment | Full review window (+ tiny card) |
| Output | Cleaned utterance | Cleaned turns + phase labels + optional actions |
| Identity | SPEAKER_N | Transcript-supported only unless card supplies aliases |

P2 v1 does **not** write CRM/Tasks or unbounded web search.
