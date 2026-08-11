(() => {
  const $ = (id) => document.getElementById(id);
  const rawEl = $("raw");
  const refinedEl = $("refined");
  const provEl = $("provenance");
  const consoleEl = $("console");
  const badge = $("badge");

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

  function setBadge(state) {
    badge.textContent = state || "idle";
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
    } else if (ev.type === "status" || ev.state) {
      setBadge(ev.state);
    }
  }

  function clearPanes() {
    rawEl.innerHTML = "";
    refinedEl.innerHTML = "";
    provEl.innerHTML = "";
    consoleEl.innerHTML = "";
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
    const speed = parseFloat($("speed").value || "20");
    const res = await fetch("/api/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed, force_stub: true }),
    });
    const data = await res.json();
    setBadge(data.state);
    log("INFO", `Play requested speed=${speed}`);
  };

  $("btn-reset").onclick = async () => {
    clearPanes();
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    setBadge(data.state);
  };

  $("btn-stop").onclick = async () => {
    const res = await fetch("/api/stop", { method: "POST" });
    const data = await res.json();
    setBadge(data.state);
  };

  fetch("/api/status")
    .then((r) => r.json())
    .then((d) => setBadge(d.state))
    .catch(() => {});
})();
