(() => {
  const $ = (id) => document.getElementById(id);
  const rawEl = $("raw");
  const refinedEl = $("refined");
  const provEl = $("provenance");
  const p2Pane = $("p2-pane");
  const paneP2 = $("pane-p2");
  const consoleEl = $("console");
  const badge = $("badge");
  const keyBadge = $("key-badge");
  const p2Badge = $("p2-badge");
  const speedEl = $("speed");
  const refineEl = $("refine-mode");
  const convoEl = $("conversation");
  const btnPlay = $("btn-play");
  const btnStop = $("btn-stop");
  const btnReset = $("btn-reset");

  // Provenance UI off for now (troubleshooting). Keep handlers commented/gated.
  const SHOW_PROVENANCE = false;

  const UI_DEFAULT_SPEED = "1";
  if (!speedEl.value || Number(speedEl.value) <= 0) {
    speedEl.value = UI_DEFAULT_SPEED;
  }

  let p2Score = 0;
  let p2Hits = [];
  let p2Review = null;
  let p2RefinePasses = [];
  let p2Breaker = { state: null, topic_score: null };
  let p2Tab = "refine";

  function append(el, html) {
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    const div = document.createElement("div");
    div.className = "row";
    div.innerHTML = html;
    el.appendChild(div);
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }

  function log(level, message) {
    const nearBottom =
      consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 48;
    const line = document.createElement("div");
    line.className = `console-line ${level || "INFO"}`;
    line.textContent = `[${level || "INFO"}] ${message}`;
    consoleEl.appendChild(line);
    if (nearBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function stickBottom(el) {
    el.scrollTop = el.scrollHeight;
  }

  function setBadge(state, llmMode) {
    const parts = [state || "idle"];
    if (llmMode && llmMode !== "unknown") parts.push(llmMode);
    badge.textContent = parts.join(" · ");
  }

  function setBusy(busy) {
    btnPlay.disabled = !!busy;
    btnReset.disabled = !!busy;
  }

  function setKeyBadge(present, hint) {
    if (present) {
      keyBadge.textContent = hint ? `Venice key: ${hint}` : "Venice key: yes";
    } else {
      keyBadge.textContent = "Venice key: no";
    }
    keyBadge.classList.toggle("ok", !!present);
    keyBadge.classList.toggle("muted", !present);
    const hintEl = $("key-hint");
    if (hintEl) {
      hintEl.textContent = present
        ? `Stored in DB as ${hint || "••••"}`
        : "No key in DB";
      hintEl.classList.toggle("ok", !!present);
      hintEl.classList.toggle("muted", !present);
    }
  }

  function setP2Badge(score, tripped, latched) {
    p2Score = Number(score) || 0;
    if (latched) {
      p2Badge.textContent = "P2: latched";
      p2Badge.classList.remove("muted", "p2-active", "p2-trip");
      p2Badge.classList.add("p2-latched");
      return;
    }
    p2Badge.classList.remove("p2-latched");
    p2Badge.textContent = tripped
      ? `P2: TRIP ${p2Score.toFixed(1)}`
      : `P2: ${p2Score.toFixed(1)}`;
    p2Badge.classList.toggle("muted", p2Score <= 0 && !tripped);
    p2Badge.classList.toggle("p2-active", p2Score > 0 && !tripped);
    p2Badge.classList.toggle("p2-trip", !!tripped);
  }

  function setBreakerBadge(state, topicScore) {
    const el = $("p2-breaker-badge");
    if (!el) return;
    if (!state) {
      el.textContent = "breaker: —";
      el.classList.remove("p2-breaker-on", "p2-breaker-off");
      return;
    }
    const ts = typeof topicScore === "number" ? ` ${topicScore.toFixed(2)}` : "";
    el.textContent = `breaker: ${state}${ts}`;
    el.classList.toggle("p2-breaker-on", state === "on");
    el.classList.toggle("p2-breaker-off", state === "off");
  }

  function setP2Tab(tab) {
    p2Tab = tab;
    const refineBtn = document.querySelector('.p2-tab[data-p2tab="refine"]');
    const reviewBtn = document.querySelector('.p2-tab[data-p2tab="review"]');
    if (refineBtn) refineBtn.classList.toggle("active", tab === "refine");
    if (reviewBtn) reviewBtn.classList.toggle("active", tab === "review");
    if (p2Pane) p2Pane.hidden = tab !== "refine";
    const reviewPane = $("p2-review-pane");
    if (reviewPane) reviewPane.hidden = tab !== "review";
    if (tab === "review") renderP2ReviewPane();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderP2ReviewPane() {
    const pane = $("p2-review-pane");
    if (!pane) return;
    if (!p2Review) {
      pane.innerHTML =
        '<p class="p2-idle muted">No review yet — after escalate, the trip receipt parks here.</p>';
      return;
    }
    const r = p2Review;
    const salient = ((r.evidence && r.evidence.salient_spans) || [])
      .map((s) => s.matched || s.rule_kind)
      .filter(Boolean)
      .slice(0, 12)
      .join(", ");
    const escalated = r.status === "escalated" || r.escalate === true;
    const declined = r.status === "declined" || r.escalate === false;
    let html = `<div class="p2-review-card">`;
    html += `<h3>Review #${r.id} · ${escapeHtml(r.status || "pending")}</h3>`;
    if (r.status === "pending") {
      html += `<p class="q">Evaluator running…</p>`;
    } else if (escalated) {
      html += `<p class="q p2-decision-yes">ESCALATE → P2 refine mode</p>`;
    } else if (declined) {
      html += `<p class="q p2-decision-no">DECLINE — stay on P1 path</p>`;
    }
    if (salient) {
      html += `<p class="p2-salient">Salient: ${escapeHtml(salient)}</p>`;
    }
    html += `<p class="p2-salient">Window segments: ${(r.window_raw_ids || r.window_segments || []).length} · score ${Number(r.running_score || 0).toFixed(1)}</p>`;
    const note = r.evaluator_rationale || r.decision_note;
    if (note) {
      html += `<p class="p2-salient">Evaluator: ${escapeHtml(note)}</p>`;
    }
    if (r.evaluator_mode) {
      html += `<p class="p2-salient muted">mode=${escapeHtml(r.evaluator_mode)}</p>`;
    }
    html += `</div>`;
    pane.innerHTML = html;
  }

  function renderP2Pane() {
    if (!p2Pane) return;
    // P2 refine mode: stream refine passes + breaker notes
    if (p2RefinePasses.length || (p2Breaker && p2Breaker.state)) {
      let html = "";
      if (p2Breaker && p2Breaker.state) {
        const cls = p2Breaker.state === "on" ? "p2-breaker-note-on" : "p2-breaker-note-off";
        const ts = typeof p2Breaker.topic_score === "number" ? ` · topic ${p2Breaker.topic_score.toFixed(2)}` : "";
        html += `<div class="p2-breaker-note ${cls}">Home-topic breaker: <strong>${escapeHtml(p2Breaker.state)}</strong>${ts}</div>`;
      }
      if (!p2RefinePasses.length) {
        html += '<p class="p2-idle muted">P2 mode on — refine passes every N turns appear here.</p>';
      }
      for (const p of p2RefinePasses.slice(-6).reverse()) {
        const meta = `pass #${p.pass_index || p.id} · mode=${p.mode || "?"} · topic=${p.topic_score == null ? "—" : Number(p.topic_score).toFixed(2)} · window ${p.window_start_raw_id}–${p.window_end_raw_id}`;
        html += `<div class="p2-refine-pass"><div class="p2-refine-meta">${escapeHtml(meta)}</div><div class="p2-refine-text">${escapeHtml(p.text || "")}</div></div>`;
      }
      p2Pane.innerHTML = html;
      paneP2.classList.remove("p2-tripped");
      return;
    }
    if (!p2Hits.length && !p2Review) {
      p2Pane.innerHTML =
        '<p class="p2-idle muted">Waiting for Play — filter factoids accumulate here; an internal evaluator auto-decides escalate.</p>';
      paneP2.classList.remove("p2-tripped");
      return;
    }
    let html = `<div class="p2-scoreline">Running score <strong>${p2Score.toFixed(2)}</strong> · hits ${p2Hits.length}</div>`;
    html += '<h3 class="p2-section">Factoids</h3>';
    html += '<ul class="p2-hit-list">';
    for (const h of p2Hits.slice(-40)) {
      const ev = h.evidence || {};
      const detail = ev.matched
        ? `“${escapeHtml(ev.matched)}”`
        : escapeHtml(JSON.stringify(ev).slice(0, 80));
      html += `<li><span class="p2-rule-kind">${escapeHtml(h.rule_kind || "?")}</span> +${Number(h.delta || 0).toFixed(1)} → ${Number(h.running_score || 0).toFixed(1)} <span class="muted">${detail}</span></li>`;
    }
    html += "</ul>";
    if (p2Review) {
      const r = p2Review;
      const pending = r.status === "pending";
      const escalated = r.status === "escalated" || r.escalate === true;
      const declined = r.status === "declined" || r.escalate === false;
      html += `<div class="p2-review-card">`;
      html += `<h3>Review #${r.id} · ${escapeHtml(r.status || "pending")}</h3>`;
      if (pending) {
        html += `<p class="q">Evaluator running…</p>`;
      } else if (escalated) {
        html += `<p class="q p2-decision-yes">ESCALATE → P2 refine (see Review tab)</p>`;
      } else if (declined) {
        html += `<p class="q p2-decision-no">DECLINE — stay on P1 path</p>`;
      }
      html += `</div>`;
      paneP2.classList.add("p2-tripped");
    } else {
      paneP2.classList.remove("p2-tripped");
    }
    p2Pane.innerHTML = html;
  }

  function applySettings(d) {
    const present = !!(d.venice_api_key_set || d.venice_key_present);
    setKeyBadge(present, d.venice_api_key_hint || "");
    const convos = d.conversations || [];
    if (convoEl && convos.length) {
      const prev = convoEl.value;
      const focused = document.activeElement === convoEl;
      const same =
        convoEl.options.length === convos.length &&
        Array.from(convoEl.options).every((opt, i) => opt.value === convos[i].id);
      if (!same) {
        convoEl.innerHTML = "";
        for (const c of convos) {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = c.exists === false ? `${c.label} (missing)` : c.label;
          opt.disabled = c.exists === false;
          convoEl.appendChild(opt);
        }
      }
      const want = d.conversation_id || prev;
      if (want && convos.some((c) => c.id === want && c.exists !== false)) {
        convoEl.value = want;
      } else if (!focused) {
        const first = convos.find((c) => c.exists !== false);
        if (first) convoEl.value = first.id;
      }
    }
    const modelSelect = $("venice-model");
    const opts = d.venice_model_options || [];
    if (modelSelect && opts.length) {
      const prev = modelSelect.value;
      modelSelect.innerHTML = "";
      for (const o of opts) {
        const opt = document.createElement("option");
        opt.value = o.id;
        opt.textContent = o.label;
        modelSelect.appendChild(opt);
      }
      const want = d.venice_model || prev;
      if (want && opts.some((o) => o.id === want)) modelSelect.value = want;
    }
    const meta = $("model-meta");
    const m = d.venice_model_meta;
    if (meta) {
      if (m) {
        meta.textContent =
          `Lab score ${m.pass_pct}% pass · mean Q ${m.mean_quality} · cost ${m.cost_rating} (${m.cost_rel}× vs cheapest whitelisted) · ~$${m.blended_usd_per_m}/1M blended`;
      } else {
        meta.textContent = "";
      }
    }
    if (d.p2 && typeof d.p2.running_score === "number") {
      setP2Badge(d.p2.running_score, !!d.p2.awaiting_review, !!d.p2.escalated_latched);
    }
  }

  function handle(ev) {
    if (ev.type === "raw" && ev.row) {
      const r = ev.row;
      append(
        rawEl,
        `<div class="meta">#${r.id} · ${r.speaker_name || "?"} · t=${r.start_time}</div>${escapeHtml(r.text)}`
      );
    } else if (ev.type === "refined" && ev.row) {
      const r = ev.row;
      append(
        refinedEl,
        `<div class="meta">#${r.id} · ${r.speaker_name || "?"} · mode=${r.mode || "?"}</div>${escapeHtml(r.text)}`
      );
    } else if (ev.type === "provenance" && ev.row) {
      // Hidden for now — leave code path for revive
      if (SHOW_PROVENANCE && provEl) {
        const r = ev.row;
        append(
          provEl,
          `<div class="meta">raw ${r.raw_segment_id} → refined ${r.refined_segment_id}</div>`
        );
      }
    } else if (ev.type === "p2_hit") {
      p2Hits.push(ev);
      setP2Badge(ev.running_score, false);
      renderP2Pane();
      const matched = (ev.evidence && ev.evidence.matched) || "";
      log(
        "P2",
        `+${Number(ev.delta || 0).toFixed(1)} ${ev.rule_kind || "?"} → score ${Number(ev.running_score || 0).toFixed(2)}${matched ? ` (${matched})` : ""}`
      );
    } else if (ev.type === "p2_trip") {
      setP2Badge(ev.running_score, true);
      log(
        "WARN",
        `P2 TRIP score=${Number(ev.running_score || 0).toFixed(2)} review=#${ev.review_id || "?"} — evaluator…`
      );
      renderP2Pane();
    } else if (ev.type === "p2_review") {
      p2Review = ev.review || p2Review;
      if (ev.decided) {
        setP2Badge(0, false, !!ev.escalate);
        renderP2Pane();
        renderP2ReviewPane();
        const esc = !!ev.escalate || (p2Review && p2Review.status === "escalated");
        log(
          "P2",
          `Review #${p2Review && p2Review.id} → ${esc ? "ESCALATE" : "DECLINE"}`
        );
        if (esc) setP2Tab("review");
      } else {
        setP2Badge((p2Review && p2Review.running_score) || p2Score, true, false);
        renderP2Pane();
        if (p2Review) {
          log("P2", `Review #${p2Review.id} factoids ready — evaluator deciding`);
        }
      }
    } else if (ev.type === "p2_refine" && ev.row) {
      p2RefinePasses.push(ev.row);
      renderP2Pane();
      log(
        "P2",
        `refine pass #${ev.row.pass_index || ev.row.id} mode=${ev.row.mode || "?"} topic=${ev.row.topic_score == null ? "—" : Number(ev.row.topic_score).toFixed(2)}`
      );
    } else if (ev.type === "p2_breaker") {
      p2Breaker = {
        state: ev.state || null,
        topic_score: typeof ev.topic_score === "number" ? ev.topic_score : null,
      };
      setBreakerBadge(p2Breaker.state, p2Breaker.topic_score);
      if (ev.flipped) {
        log("P2", `breaker → ${String(ev.state || "?").toUpperCase()} (${ev.reason || ""})`);
      }
      renderP2Pane();
    } else if (ev.type === "console") {
      log(ev.level, ev.message);
    } else if (ev.type === "snapshot") {
      renderSnapshot(ev);
    } else if (ev.type === "status") {
      setBadge(ev.state, ev.llm_mode);
      if (ev.state === "playing") setBusy(true);
      if (ev.state === "stopped" || ev.state === "idle" || ev.state === "done" || ev.state === "error") {
        setBusy(false);
      }
      if (typeof ev.venice_key_present === "boolean" || typeof ev.venice_api_key_set === "boolean") {
        applySettings(ev);
      }
      if (typeof ev.force_stub === "boolean" && document.activeElement !== refineEl) {
        refineEl.value = ev.force_stub ? "stub" : "venice";
      }
      if (ev.p2) {
        setP2Badge(
          ev.p2.running_score,
          !!ev.p2.awaiting_review,
          !!ev.p2.escalated_latched
        );
        if (ev.p2.breaker_state) {
          p2Breaker.state = ev.p2.breaker_state;
          if (typeof ev.p2.topic_score === "number") {
            p2Breaker.topic_score = ev.p2.topic_score;
          }
          setBreakerBadge(p2Breaker.state, p2Breaker.topic_score);
        }
      }
      if (ev.snapshot) {
        renderSnapshot(ev.snapshot);
      }
    }
  }

  function renderSnapshot(snap) {
    if (!snap) return;
    const raw = snap.raw_segments || [];
    const refined = snap.refined_segments || [];
    const usage = snap.segment_usage || [];
    rawEl.innerHTML = "";
    refinedEl.innerHTML = "";
    if (SHOW_PROVENANCE && provEl) provEl.innerHTML = "";
    for (const r of raw) {
      append(
        rawEl,
        `<div class="meta">#${r.id} · ${r.speaker_name || "?"} · t=${r.start_time}</div>${escapeHtml(r.text)}`
      );
    }
    for (const r of refined) {
      append(
        refinedEl,
        `<div class="meta">#${r.id} · ${r.speaker_name || "?"} · mode=${r.mode || "?"}</div>${escapeHtml(r.text)}`
      );
    }
    if (SHOW_PROVENANCE && provEl) {
      for (const r of usage) {
        append(
          provEl,
          `<div class="meta">raw ${r.raw_segment_id} → refined ${r.refined_segment_id}</div>`
        );
      }
      stickBottom(provEl);
    }
    stickBottom(rawEl);
    stickBottom(refinedEl);
  }

  function clearPanes() {
    rawEl.innerHTML = "";
    refinedEl.innerHTML = "";
    if (provEl) provEl.innerHTML = "";
    consoleEl.innerHTML = "";
    p2Hits = [];
    p2Review = null;
    p2RefinePasses = [];
    p2Breaker = { state: null, topic_score: null };
    setP2Badge(0, false, false);
    setBreakerBadge(null, null);
    setP2Tab("refine");
    renderP2Pane();
  }

  function playBody() {
    let speed = parseFloat(speedEl.value || UI_DEFAULT_SPEED);
    if (!Number.isFinite(speed) || speed <= 0 || speed > 1000) {
      speed = 1;
      speedEl.value = UI_DEFAULT_SPEED;
    }
    const force_stub = refineEl.value !== "venice";
    const conversation_id = convoEl.value || undefined;
    return { speed, force_stub, conversation_id };
  }

  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    try {
      handle(JSON.parse(m.data));
    } catch (e) {
      log("ERROR", String(e));
    }
  };
  es.onerror = () => log("WARN", "SSE reconnecting…");

  btnPlay.onclick = async () => {
    clearPanes();
    const body = playBody();
    setBusy(true);
    setBadge("playing");
    if (!body.force_stub && keyBadge.textContent.includes("no")) {
      log("WARN", "Venice selected but no API key on server — will fall back to stub on failure");
    }
    try {
      const res = await fetch("/api/play", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setBusy(false);
        setBadge(data.state || "error", data.llm_mode);
        log("ERROR", data.error || "Play failed");
        return;
      }
      setBadge(data.state, data.llm_mode);
      if (data.conversation_id && convoEl) convoEl.value = data.conversation_id;
      log(
        "INFO",
        `Play conversation=${body.conversation_id || "?"} speed=${body.speed} refine=${body.force_stub ? "stub" : "venice"}`
      );
      log("P2", "Filter armed — watching for evidence accumulation");
    } catch (e) {
      setBusy(false);
      log("ERROR", String(e));
    }
  };

  btnReset.onclick = async () => {
    clearPanes();
    setBusy(true);
    try {
      const res = await fetch("/api/reset", { method: "POST" });
      const data = await res.json();
      setBadge(data.state, data.llm_mode);
      speedEl.value = UI_DEFAULT_SPEED;
    } finally {
      setBusy(false);
    }
  };

  btnStop.onclick = async () => {
    setBadge("stopped");
    log("INFO", "Stopping…");
    try {
      const res = await fetch("/api/stop", { method: "POST" });
      const data = await res.json();
      setBadge(data.state, data.llm_mode);
      setBusy(false);
      if (data.snapshot) renderSnapshot(data.snapshot);
      log("INFO", "Stopped — DB kept; panes show progress so far");
    } catch (e) {
      setBusy(false);
      log("ERROR", `Stop failed: ${e}`);
    }
  };

  const veniceKeyEl = $("venice-key");
  const settingsDialog = $("settings-dialog");
  const btnMenu = $("btn-menu");

  function openSettings() {
    if (typeof settingsDialog.showModal === "function") {
      settingsDialog.showModal();
    } else {
      settingsDialog.setAttribute("open", "");
    }
    btnMenu.setAttribute("aria-expanded", "true");
    loadP2DoctorTab();
  }

  function closeSettings() {
    if (settingsDialog.open) settingsDialog.close();
    btnMenu.setAttribute("aria-expanded", "false");
  }

  btnMenu.onclick = () => {
    if (settingsDialog.open) closeSettings();
    else openSettings();
  };
  settingsDialog.addEventListener("close", () => {
    btnMenu.setAttribute("aria-expanded", "false");
  });
  $("btn-close-settings").onclick = () => closeSettings();

  // P2 pane tabs (Refine vs Review receipt)
  document.querySelectorAll(".p2-tab").forEach((tab) => {
    tab.onclick = () => setP2Tab(tab.getAttribute("data-p2tab") || "refine");
  });

  // Tabs
  document.querySelectorAll(".settings-tab").forEach((tab) => {
    tab.onclick = () => {
      const name = tab.getAttribute("data-tab");
      document.querySelectorAll(".settings-tab").forEach((t) => {
        const on = t === tab;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      $("tab-venice").hidden = name !== "venice";
      $("tab-p2").hidden = name !== "p2";
      if (name === "p2") loadP2DoctorTab();
    };
  });

  async function loadP2DoctorTab() {
    const list = $("p2-rules-list");
    try {
      const [sRes, pRes] = await Promise.all([
        fetch("/api/doctor/settings"),
        fetch("/api/doctor/filter-packs"),
      ]);
      const sData = await sRes.json();
      const pData = await pRes.json();
      const settings = sData.settings || {};
      $("p2-threshold").value = settings.trip_threshold || "7";
      $("p2-decay").value = settings.score_decay_per_segment || "0.15";
      $("p2-gate").textContent = settings.enrichment_gate_enabled_b ? "on" : "off";
      $("p2-auto").textContent = settings.p2_auto_evaluate_b === false ? "off" : "on";
      const modeEl = $("p2-eval-mode");
      if (modeEl) modeEl.value = settings.p2_evaluator_mode || "auto";
      const cardEl = $("p2-project-card");
      if (cardEl) cardEl.value = settings.p2_project_card || "";
      // P2 refine + breaker knobs
      const setVal = (id, v) => { const el = $(id); if (el) el.value = v; };
      setVal("p2-refine-every", settings.p2_refine_every_turns || "5");
      setVal("p2-refine-max", settings.p2_refine_max_segments || "80");
      setVal("p2-breaker-off", settings.p2_breaker_off_score || "0.18");
      setVal("p2-breaker-on", settings.p2_breaker_on_score || "0.34");
      setVal("p2-breaker-off-streak", settings.p2_breaker_off_streak || "3");
      setVal("p2-breaker-on-streak", settings.p2_breaker_on_streak || "2");
      const be = $("p2-breaker-enabled");
      if (be) be.textContent = settings.p2_breaker_enabled_b === false ? "off" : "on";
      const rm = $("p2-refine-model-label");
      if (rm) rm.textContent = settings.p2_refine_model || "(P1)";
      // Fill evaluator model options from Venice whitelist (same as P1)
      const evalModel = $("p2-eval-model");
      if (evalModel) {
        const prev = settings.p2_evaluator_model || evalModel.value || "";
        fetch("/api/settings")
          .then((r) => r.json())
          .then((sd) => {
            const opts = sd.venice_model_options || [];
            evalModel.innerHTML = '<option value="">(same as P1 refine)</option>';
            for (const o of opts) {
              const opt = document.createElement("option");
              opt.value = o.id;
              opt.textContent = o.label;
              evalModel.appendChild(opt);
            }
            if (prev && opts.some((o) => o.id === prev)) evalModel.value = prev;
          })
          .catch(() => {});
      }
      const packs = pData.packs || [];
      const activeSlug = settings.active_filter_pack_slug;
      const pack = packs.find((p) => p.slug === activeSlug) || packs[0];
      if (pack) {
        $("p2-pack-title").value = pack.title || pack.slug;
        $("p2-pack-slug").textContent = pack.slug;
        const rules = pack.rules || [];
        if (!rules.length) {
          list.textContent = "No rules in pack.";
        } else {
          list.innerHTML = rules
            .map(
              (r) =>
                `<div class="p2-rule-row"><span class="p2-rule-kind">${escapeHtml(r.kind)}</span><span>w=${Number(r.weight).toFixed(1)} · prio ${r.priority}${r.enabled ? "" : " · off"}</span></div>`
            )
            .join("");
        }
      } else {
        $("p2-pack-title").value = "(none)";
        $("p2-pack-slug").textContent = "—";
        list.textContent = "No filter packs — POST /api/doctor/seed";
      }
    } catch (e) {
      list.textContent = `Failed to load: ${e}`;
    }
  }

  $("btn-save-p2").onclick = async () => {
    const hint = $("p2-save-hint");
    try {
      const body = {
        trip_threshold: String($("p2-threshold").value || "7"),
        score_decay_per_segment: String($("p2-decay").value || "0.15"),
        p2_evaluator_mode: String(($("p2-eval-mode") && $("p2-eval-mode").value) || "auto"),
        p2_evaluator_model: String(($("p2-eval-model") && $("p2-eval-model").value) || ""),
        p2_project_card: String(($("p2-project-card") && $("p2-project-card").value) || ""),
        p2_refine_every_turns: String(($("p2-refine-every") && $("p2-refine-every").value) || "5"),
        p2_refine_max_segments: String(($("p2-refine-max") && $("p2-refine-max").value) || "80"),
        p2_breaker_off_score: String(($("p2-breaker-off") && $("p2-breaker-off").value) || "0.18"),
        p2_breaker_on_score: String(($("p2-breaker-on") && $("p2-breaker-on").value) || "0.34"),
        p2_breaker_off_streak: String(($("p2-breaker-off-streak") && $("p2-breaker-off-streak").value) || "3"),
        p2_breaker_on_streak: String(($("p2-breaker-on-streak") && $("p2-breaker-on-streak").value) || "2"),
      };
      const res = await fetch("/api/doctor/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (!res.ok) {
        hint.textContent = d.error || "save failed";
        return;
      }
      hint.textContent = "Saved";
      hint.classList.add("ok");
      log(
        "P2",
        `Doctor settings saved — threshold=${d.settings.trip_threshold} eval=${d.settings.p2_evaluator_mode} refine_every=${d.settings.p2_refine_every_turns}`
      );
    } catch (e) {
      hint.textContent = String(e);
    }
  };

  $("btn-reseed-p2").onclick = async () => {
    const hint = $("p2-save-hint");
    try {
      const res = await fetch("/api/doctor/seed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_rules: true }),
      });
      const d = await res.json();
      if (!res.ok) {
        hint.textContent = d.error || "seed failed";
        return;
      }
      hint.textContent = "Re-seeded";
      log("P2", `Re-seeded pack ${(d.pack && d.pack.slug) || "?"}`);
      loadP2DoctorTab();
    } catch (e) {
      hint.textContent = String(e);
    }
  };

  $("btn-save-settings").onclick = async (e) => {
    e.preventDefault();
    const body = {
      venice_model: $("venice-model").value,
    };
    const venice_api_key = veniceKeyEl.value;
    if (venice_api_key.trim()) body.venice_api_key = venice_api_key;
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await res.json();
    if (!res.ok) {
      log("ERROR", d.error || "Settings save failed");
      applySettings(d);
      return;
    }
    applySettings(d);
    veniceKeyEl.value = "";
    log(
      "INFO",
      `Settings saved — refine model=${d.venice_model}` +
        (body.venice_api_key ? "; API key updated" : "")
    );
    closeSettings();
  };

  $("btn-clear-key").onclick = async (e) => {
    e.preventDefault();
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ venice_api_key: "" }),
    });
    const d = await res.json();
    applySettings(d);
    veniceKeyEl.value = "";
    log("INFO", "Venice API key cleared from DB");
  };

  function hydrate() {
    return fetch("/api/status")
      .then((r) => r.json())
      .then((d) => {
        if (!speedEl.value) speedEl.value = UI_DEFAULT_SPEED;
        if (typeof d.force_stub === "boolean") {
          refineEl.value = d.force_stub ? "stub" : "venice";
        }
        setBadge(d.state, d.llm_mode);
        setBusy(d.state === "playing");
        applySettings(d);
        if (d.snapshot) renderSnapshot(d.snapshot);
        const n = (d.counts && d.counts.raw) || 0;
        if (n > 0) {
          log("INFO", `Hydrated ${n} raw / ${(d.counts && d.counts.refined) || 0} refined from DB`);
        }
        renderP2Pane();
      });
  }

  fetch("/api/settings")
    .then((r) => r.json())
    .then(applySettings)
    .catch(() => {});

  fetch("/api/controls")
    .then((r) => r.json())
    .then((d) => {
      speedEl.value = UI_DEFAULT_SPEED;
      refineEl.value = d.force_stub ? "stub" : "venice";
      setBadge(d.state, d.llm_mode);
      applySettings(d);
    })
    .catch(() => {})
    .finally(() => {
      hydrate().catch(() => {});
    });
})();
