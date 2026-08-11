(() => {
  const $ = (id) => document.getElementById(id);
  const rawEl = $("raw");
  const refinedEl = $("refined");
  const provEl = $("provenance");
  const consoleEl = $("console");
  const badge = $("badge");
  const keyBadge = $("key-badge");
  const speedEl = $("speed");
  const refineEl = $("refine-mode");

  function append(el, html) {
    const div = document.createElement("div");
    div.className = "row";
    div.innerHTML = html;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }

  function log(level, message) {
    const line = document.createElement("div");
    line.className = `console-line ${level || "INFO"}`;
    line.textContent = `[${level || "INFO"}] ${message}`;
    consoleEl.appendChild(line);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function setBadge(state, llmMode) {
    const parts = [state || "idle"];
    if (llmMode && llmMode !== "unknown") parts.push(llmMode);
    badge.textContent = parts.join(" · ");
  }

  function setKeyBadge(present) {
    keyBadge.textContent = present ? "Venice key: yes" : "Venice key: no";
    keyBadge.classList.toggle("ok", !!present);
    keyBadge.classList.toggle("muted", !present);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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
      const r = ev.row;
      append(
        provEl,
        `<div class="meta">raw ${r.raw_segment_id} → refined ${r.refined_segment_id}</div>`
      );
    } else if (ev.type === "console") {
      log(ev.level, ev.message);
    } else if (ev.type === "snapshot") {
      renderSnapshot(ev);
    } else if (ev.type === "status" || ev.state) {
      setBadge(ev.state, ev.llm_mode);
      if (typeof ev.venice_key_present === "boolean") {
        setKeyBadge(ev.venice_key_present);
      }
      if (typeof ev.force_stub === "boolean" && document.activeElement !== refineEl) {
        refineEl.value = ev.force_stub ? "stub" : "venice";
      }
      if (typeof ev.speed === "number" && document.activeElement !== speedEl) {
        speedEl.value = String(ev.speed);
      }
      // status payloads include snapshot — paint panes after reload / reconnect
      if (ev.snapshot) {
        renderSnapshot(ev.snapshot);
      } else if (ev.raw_segments || ev.refined_segments) {
        renderSnapshot(ev);
      }
    }
  }

  function renderSnapshot(snap) {
    if (!snap) return;
    const raw = snap.raw_segments || [];
    const refined = snap.refined_segments || [];
    const usage = snap.segment_usage || [];
    // Only replace panes when we have a full snapshot (reload / stop / done).
    // Avoid wiping mid-stream if an empty snapshot arrives by mistake.
    rawEl.innerHTML = "";
    refinedEl.innerHTML = "";
    provEl.innerHTML = "";
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
    for (const r of usage) {
      append(
        provEl,
        `<div class="meta">raw ${r.raw_segment_id} → refined ${r.refined_segment_id}</div>`
      );
    }
  }

  function clearPanes() {
    rawEl.innerHTML = "";
    refinedEl.innerHTML = "";
    provEl.innerHTML = "";
    consoleEl.innerHTML = "";
  }

  function playBody() {
    const speed = parseFloat(speedEl.value || "1");
    const force_stub = refineEl.value !== "venice";
    return { speed, force_stub };
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

  $("btn-play").onclick = async () => {
    clearPanes();
    const body = playBody();
    if (!body.force_stub && keyBadge.textContent.includes("no")) {
      log("WARN", "Venice selected but no API key on server — will fall back to stub on failure");
    }
    const res = await fetch("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    setBadge(data.state, data.llm_mode);
    log(
      "INFO",
      `Play speed=${body.speed} refine=${body.force_stub ? "stub" : "venice"}`
    );
  };

  $("btn-reset").onclick = async () => {
    clearPanes();
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    setBadge(data.state, data.llm_mode);
  };

  $("btn-stop").onclick = async () => {
    const res = await fetch("/api/stop", { method: "POST" });
    const data = await res.json();
    setBadge(data.state, data.llm_mode);
    if (data.snapshot) renderSnapshot(data.snapshot);
    log("INFO", "Stopped — DB kept; panes show progress so far");
  };

  function hydrate() {
    return fetch("/api/status")
      .then((r) => r.json())
      .then((d) => {
        if (typeof d.speed === "number") speedEl.value = String(d.speed);
        if (typeof d.force_stub === "boolean") {
          refineEl.value = d.force_stub ? "stub" : "venice";
        }
        setBadge(d.state, d.llm_mode);
        setKeyBadge(!!d.venice_key_present);
        if (d.snapshot) renderSnapshot(d.snapshot);
        const n = (d.counts && d.counts.raw) || 0;
        if (n > 0) {
          log("INFO", `Hydrated ${n} raw / ${(d.counts && d.counts.refined) || 0} refined from DB`);
        }
      });
  }

  fetch("/api/controls")
    .then((r) => r.json())
    .then((d) => {
      if (typeof d.speed === "number") speedEl.value = String(d.speed);
      refineEl.value = d.force_stub ? "stub" : "venice";
      setBadge(d.state, d.llm_mode);
      setKeyBadge(!!d.venice_key_present);
    })
    .catch(() => {})
    .finally(() => {
      hydrate().catch(() => {});
    });
})();
