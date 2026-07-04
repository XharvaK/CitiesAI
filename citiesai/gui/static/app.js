const POLL_MS = 10000;
const ASK_SUBMIT_LABEL = "Send";

const ONBOARDING_STEPS = [
  {
    title: "Welcome to CitiesAI",
    html: `<p>Your read-only advisor for <strong>Cities: Skylines II</strong>. See live city stats and ask grounded questions. We never touch your save.</p>`,
  },
  {
    title: "Detect your game",
    html: `<p>We'll look for CS2 on Steam or Game Pass and set paths automatically.</p><p id="onboard-detect" class="muted">Detecting…</p>`,
    onEnter: detectGame,
  },
  {
    title: "Install data export mod",
    html: `<p>A tiny mod writes a snapshot of your city every ~10 seconds while you play. Close CS2 if install fails.</p><p id="onboard-mod" class="muted"></p>`,
    onEnter: checkMod,
  },
  {
    title: "Load a city in-game",
    html: `<p>Launch CS2, enable <strong>CS2 Data Export</strong>, and load your city. We'll wait for the first snapshot.</p><p id="onboard-export" class="muted">Waiting…</p>`,
    onEnter: waitForExport,
    autoAdvance: true,
  },
  {
    title: "AI answers (optional)",
    html: `<p>Stats work without AI. For answers, get a free key at <a href="https://console.mistral.ai" target="_blank" rel="noopener">console.mistral.ai</a> and paste below. Stored only on your PC.</p>
      <label>API key<input id="onboard-key" type="password" placeholder="Optional" /></label>`,
  },
  {
    title: "You're ready",
    html: `<p>Dashboard refreshes automatically. Use <strong>Ask</strong> for advice and <strong>Feedback</strong> to report issues during beta.</p>`,
  },
];

const FEEDBACK_PLACEHOLDERS = {
  bug: "Describe what broke, what you clicked, and what you expected…",
  ux: "What felt confusing or hard to use?",
  "wrong-answer": "Paste the question and what was wrong in the answer…",
  feature: "What would you like CitiesAI to do?",
  general: "Anything else on your mind…",
};

let onboardingStep = 0;
let onboardingDismissed = false;
let exportPollTimer = null;
let dashboardTimer = null;
let lastStatus = null;
let lastIssues = [];
let llmConfigured = false;
let refreshInFlight = false;
let statusRefreshInFlight = false;
let lastDashboardData = null;
let metricModalReturnFocus = null;
let diagnosticsModalReturnFocus = null;

function $(id) {
  return document.getElementById(id);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    throw new Error("Invalid server response");
  }
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function toast(message, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function formatNum(n, options = {}) {
  if (n == null || Number.isNaN(n)) return "n/a";
  const decimals = options.decimals ?? 0;
  const rounded = decimals > 0 ? Number(n) : Math.round(Number(n));
  return rounded.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatSignedNum(n, options = {}) {
  if (n == null || Number.isNaN(n)) return "n/a";
  const decimals = options.decimals ?? 0;
  const rounded = decimals > 0 ? Number(n) : Math.round(Number(n));
  const body = Math.abs(rounded).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (rounded > 0) return `+${body}`;
  if (rounded < 0) return `-${body}`;
  return body;
}

function formatDelta(delta, options = {}) {
  if (delta == null || Number.isNaN(delta)) return "";
  const decimals = options.decimals ?? 0;
  const rounded = decimals > 0 ? Number(delta) : Math.round(Number(delta));
  if (rounded === 0) return "";
  const signed = formatSignedNum(rounded, options);
  if (!options.currency || signed === "n/a") return signed;
  if (signed.startsWith("+")) return `+¢${signed.slice(1)}`;
  if (signed.startsWith("-")) return `-¢${signed.slice(1)}`;
  return `¢${signed}`;
}

function formatMetricValue(val, def) {
  const formatOpts = { decimals: def.decimals ?? 0 };
  const formatted = formatNum(val, formatOpts);
  if (def.currency) {
    return formatted === "n/a" ? formatted : `¢${formatted}`;
  }
  return `${formatted}${def.suffix || ""}`;
}

function formatHourlyRate(value, options = {}) {
  if (value == null || Number.isNaN(value)) return "";
  const decimals = options.decimals ?? 0;
  const rounded = decimals > 0 ? Number(value) : Math.round(Number(value));
  if (rounded === 0) return "";
  const body = Math.abs(rounded).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  const sign = rounded > 0 ? "+" : rounded < 0 ? "-" : "";
  const prefix = options.currency ? `${sign}¢` : sign;
  return `${prefix}${body} /h`;
}

function hourlyRateClass(value) {
  if (value == null || Number.isNaN(value) || value === 0) return "";
  return value > 0 ? "up" : "down";
}

function formatAge(seconds) {
  if (seconds == null) return "unknown";
  if (seconds < 120) return `${Math.round(seconds)}s ago`;
  return `${(seconds / 60).toFixed(1)}m ago`;
}

function freshnessCountdown(ageSeconds) {
  if (ageSeconds == null) return null;
  return Math.max(0, 30 - ageSeconds);
}

function drawSparkline(svg, values) {
  const nums = (values || []).filter((v) => typeof v === "number");
  if (nums.length < 2) return;
  const w = 160;
  const h = 28;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const pts = nums.map((v, i) => {
    const x = (i / (nums.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  });
  svg.innerHTML = `<polyline fill="none" stroke="currentColor" stroke-width="1.5" points="${pts.join(" ")}" />`;
}

function formatHistoryDuration(seconds) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 1) return "";
  if (seconds < 120) return `~${Math.round(seconds)}s`;
  return `~${Math.round(seconds / 60)} min`;
}

function drawDetailChart(svg, { timestamps, values, suffix = "" }) {
  const nums = (values || []).filter((v) => typeof v === "number");
  if (!svg || nums.length < 2) {
    if (svg) svg.innerHTML = "";
    return false;
  }

  const width = 560;
  const height = 220;
  const pad = { top: 16, right: 16, bottom: 28, left: 52 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;

  const points = nums.map((v, i) => {
    const x = pad.left + (i / (nums.length - 1)) * plotW;
    const y = pad.top + plotH - ((v - min) / range) * plotH;
    return { x, y, v };
  });

  const yTicks = [min, min + range / 2, max];
  const yTickLines = yTicks
    .map((tick) => {
      const y = pad.top + plotH - ((tick - min) / range) * plotH;
      const label = `${formatNum(tick, { decimals: suffix === "%" ? 1 : 0 })}${suffix}`;
      return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="chart-grid" />
        <text x="${pad.left - 8}" y="${y + 4}" class="chart-axis" text-anchor="end">${label}</text>`;
    })
    .join("");

  const ts = timestamps || [];
  const xLabels = [];
  if (ts.length >= 2) {
    const first = ts[0];
    const last = ts[ts.length - 1];
    const midIdx = Math.floor((ts.length - 1) / 2);
    const slots = [
      { idx: 0, label: formatHistoryDuration(last - first) + " ago" },
      { idx: midIdx, label: formatHistoryDuration(last - ts[midIdx]) + " ago" },
      { idx: ts.length - 1, label: "now" },
    ];
    for (const slot of slots) {
      const x = pad.left + (slot.idx / (nums.length - 1)) * plotW;
      xLabels.push(`<text x="${x}" y="${height - 8}" class="chart-axis" text-anchor="middle">${slot.label}</text>`);
    }
  }

  const poly = points.map((p) => `${p.x},${p.y}`).join(" ");
  const area = `${pad.left},${pad.top + plotH} ${poly} ${pad.left + plotW},${pad.top + plotH}`;
  const last = points[points.length - 1];

  svg.innerHTML = `
    ${yTickLines}
    ${xLabels.join("")}
    <polygon class="chart-area" points="${area}" />
    <polyline class="chart-line" fill="none" points="${poly}" />
    <circle class="chart-dot" cx="${last.x}" cy="${last.y}" r="3.5" />
  `;
  return true;
}

function renderInlineMarkdown(text) {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(text) {
  const lines = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .split("\n");
  const out = [];
  let inOl = false;
  let inUl = false;

  const closeLists = () => {
    if (inUl) {
      out.push("</ul>");
      inUl = false;
    }
    if (inOl) {
      out.push("</ol>");
      inOl = false;
    }
  };

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      continue;
    }

    const olMatch = trimmed.match(/^\d+\.\s*(.*)$/);
    const ulMatch = trimmed.match(/^-\s+(.*)$/);

    if (olMatch) {
      const content = olMatch[1].trim();
      if (!content) {
        continue;
      }
      if (!inOl) {
        closeLists();
        out.push("<ol>");
        inOl = true;
      }
      out.push(`<li>${renderInlineMarkdown(content)}</li>`);
      continue;
    }

    if (ulMatch) {
      if (!inUl) {
        closeLists();
        out.push("<ul>");
        inUl = true;
      }
      out.push(`<li>${renderInlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }

    closeLists();
    if (/^### (.+)$/.test(trimmed)) {
      out.push(`<h4>${renderInlineMarkdown(trimmed.replace(/^### /, ""))}</h4>`);
    } else if (/^## (.+)$/.test(trimmed)) {
      out.push(`<h3>${renderInlineMarkdown(trimmed.replace(/^## /, ""))}</h3>`);
    } else if (/^# (.+)$/.test(trimmed)) {
      out.push(`<h2>${renderInlineMarkdown(trimmed.replace(/^# /, ""))}</h2>`);
    } else {
      out.push(`<p>${renderInlineMarkdown(trimmed)}</p>`);
    }
  }

  closeLists();
  return out.join("");
}

function typingIndicatorHtml() {
  return '<span class="typing-indicator"><span></span><span></span><span></span></span>';
}

function autoGrowTextarea(el) {
  el.style.height = "auto";
  const maxRows = 6;
  const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 22;
  const maxHeight = lineHeight * maxRows;
  el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
}

let feedbackContextIssueId = "";

function switchView(name, options = {}) {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    const active = btn.dataset.view === name;
    btn.classList.toggle("active", active);
    if (active) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  });
  document.querySelectorAll(".view").forEach((panel) => {
    const active = panel.id === `view-${name}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  if (name === "ask") {
    renderSuggestions();
    updateAskHelper();
    updateAskWelcome();
    $("question").focus();
  }
  if (name === "settings") void loadSettings();
  if (name === "issues") refreshIssues({ toastOnError: true });
  if (name === "feedback") {
    if (!options.issueId) feedbackContextIssueId = "";
    if (options.category) setFeedbackCategory(options.category);
    if (options.message) $("feedback-message").value = options.message;
    if (options.issueId) feedbackContextIssueId = options.issueId;
    updateFeedbackIssuesLink();
  }
}

function blockingIssueCount(issues) {
  return issues.filter((i) => i.severity === "error" || i.severity === "warn").length;
}

function applyIssuesData(data) {
  lastIssues = data.issues || [];
  const blocking = data.blocking_count ?? blockingIssueCount(lastIssues);
  if ($("view-issues").classList.contains("active")) {
    renderIssues(lastIssues);
  }
  if (lastStatus) {
    renderHealthStrip(lastStatus, blocking);
  }
  updateFeedbackIssuesLink();
}

const PATH_LABELS = {
  game_dir: "Game folder",
  locale_cok: "Locale file",
  export_path: "Export file",
};

/** Fallback when an older CitiesAI build has no /api/issues route. */
function synthesizeIssuesFromStatus(status) {
  const issues = [];
  for (const [key, entry] of Object.entries(status.paths || {})) {
    if (entry.ok) continue;
    const label = PATH_LABELS[key] || key;
    const missing = entry.error === "path does not exist";
    issues.push({
      id: `path_${key}`,
      severity: "error",
      title: missing ? `${label} not found` : `${label} not configured`,
      detail: entry.path || `No ${label.toLowerCase()} is set yet.`,
      hint: missing
        ? "Use Settings to re-detect paths or set them manually."
        : "Use Settings to detect your game installation.",
      report_category: "bug",
      action_view: "settings",
    });
  }
  if (!status.mod_installed) {
    issues.push({
      id: "mod_missing",
      severity: "warn",
      title: "Data export mod not installed",
      detail: "CitiesAI needs the CS2 Data Export mod to read your city.",
      hint: "Close CS2, then install the mod from Settings.",
      report_category: "bug",
      action_view: "settings",
    });
  }
  const exportBlock = status.export;
  if (!exportBlock) {
    issues.push({
      id: "export_missing",
      severity: "warn",
      title: "No city export yet",
      detail: "Load a city in CS2 with the Data Export mod enabled.",
      hint: "After loading, wait a few seconds for the first snapshot.",
      ask_prompt: "Why is my city export missing and how do I fix it?",
      report_category: "bug",
    });
  } else if (exportBlock.corrupt) {
    issues.push({
      id: "export_corrupt",
      severity: "error",
      title: "City export file is unreadable",
      detail: String(exportBlock.error || "The latest.json file could not be parsed."),
      hint: "Re-load your city in CS2 or wait for a new snapshot.",
      report_category: "bug",
      action_view: "settings",
    });
  }
  const knowledge = status.knowledge || {};
  const enc = knowledge.encyclopedia || {};
  if (knowledge.error) {
    issues.push({
      id: "knowledge_error",
      severity: "error",
      title: "Knowledge sources unavailable",
      detail: String(knowledge.error),
      hint: "Reinstall CitiesAI or report this in Feedback.",
      report_category: "bug",
    });
  } else if (!enc.available) {
    issues.push({
      id: "encyclopedia_missing",
      severity: "warn",
      title: "Game encyclopedia unavailable",
      detail: "Wiki-style answers may be limited until encyclopedia data loads.",
      hint: "Check that your game Locale.cok path is correct in Settings.",
      report_category: "bug",
      action_view: "settings",
    });
  }
  if (!status.llm?.configured) {
    issues.push({
      id: "llm_optional",
      severity: "info",
      title: "AI answers not configured",
      detail: "Dashboard stats work without an API key.",
      hint: "Add a free Mistral key in Settings for grounded answers.",
      action_view: "settings",
    });
  }
  return issues;
}

function issueCountLabel(count) {
  return count === 1 ? "1 issue" : `${count} issues`;
}

function infoIssueCount(issues) {
  return issues.filter((i) => i.severity === "info").length;
}

function renderHealthStrip(status, blockingCount = 0) {
  const el = $("health-strip");
  el.classList.remove("ok", "warn", "bad", "clickable");
  el.onclick = null;
  el.removeAttribute("aria-disabled");

  if (!status) {
    el.textContent = "Status unavailable";
    el.classList.add("warn", "clickable");
    el.onclick = () => switchView("issues");
    return;
  }

  const exportReady = Boolean(status.export && !status.export.corrupt);
  const encOk = status.knowledge?.encyclopedia?.available;
  const notes = infoIssueCount(lastIssues);

  if (status.ok && blockingCount === 0 && notes === 0) {
    el.textContent = "All systems ready";
    el.classList.add("ok");
    el.setAttribute("aria-disabled", "true");
    return;
  }

  el.classList.add("clickable");
  el.onclick = () => switchView("issues");

  if (!exportReady && !encOk && blockingCount > 0) {
    el.textContent = "Setup needed";
    el.classList.add("bad");
    return;
  }

  if (blockingCount > 0) {
    el.textContent = issueCountLabel(blockingCount);
    el.classList.add("warn");
    return;
  }

  if (notes > 0) {
    el.textContent = notes === 1 ? "Ready · 1 note in Issues" : `Ready · ${notes} notes in Issues`;
    el.classList.add("ok");
    return;
  }

  el.textContent = "All systems ready";
  el.classList.add("ok");
  el.setAttribute("aria-disabled", "true");
}

function updateAskHelper() {
  const el = $("ask-helper");
  if (!el) return;
  if (llmConfigured) {
    el.textContent =
      "Ask anything about your city. Answers combine your live export with Cities Wiki knowledge.";
  } else {
    el.textContent =
      "Stats work without AI. Add a Mistral API key in Settings for answers grounded in your city data and the Cities Wiki.";
  }
}

const METRIC_DEFS = [
  {
    key: "population",
    label: "Population",
    group: "city",
    description: "Official resident count (excludes commuters and tourists).",
    hourlyKey: "population_change_per_hour",
  },
  {
    key: "treasury",
    label: "Treasury",
    group: "economy",
    description: "City cash on hand from official finance statistics.",
    hourlyKey: "treasury_net_per_hour",
    hourlyCurrency: true,
    currency: true,
  },
  {
    key: "income",
    label: "Income",
    group: "economy",
    description: "Total monthly income across all revenue sources.",
    currency: true,
  },
  {
    key: "expense",
    label: "Expense",
    group: "economy",
    description: "Total monthly spending across all expense sources.",
    currency: true,
  },
  {
    key: "health",
    label: "Health",
    group: "social",
    decimals: 1,
    description: "Average citizen health index (0–100).",
  },
  {
    key: "traffic_volume",
    label: "Road / transit ratio",
    group: "mobility",
    decimals: 1,
    description: "Road vehicles per transit vehicle — not congestion.",
  },
  {
    key: "employment_percent",
    label: "Employment",
    group: "social",
    suffix: "%",
    description: "Share of working-age citizens with jobs.",
  },
  {
    key: "wellbeing",
    label: "Wellbeing",
    group: "social",
    decimals: 1,
    description: "Average citizen wellbeing index (0–100).",
  },
];

function metricDefByKey(key) {
  return METRIC_DEFS.find((def) => def.key === key);
}

function buildMetricCardHtml(def, m, deltas, series) {
  const val = m[def.key];
  const delta = deltas[def.key];
  const formatOpts = { decimals: def.decimals ?? 0 };
  const roundedDelta =
    delta == null || Number.isNaN(delta)
      ? null
      : formatOpts.decimals > 0
        ? Number(delta)
        : Math.round(Number(delta));
  const deltaCls = roundedDelta > 0 ? "up" : roundedDelta < 0 ? "down" : "";
  const historyValues = series[def.key] || [];
  const hasSparkline = historyValues.filter((v) => typeof v === "number").length >= 2;
  const deltaOpts = { decimals: def.decimals ?? 0, currency: Boolean(def.currency) };

  let hourlyHtml = "";
  if (def.hourlyKey) {
    const hourlyVal = m[def.hourlyKey];
    const hourlyText = formatHourlyRate(hourlyVal, {
      decimals: formatOpts.decimals,
      currency: Boolean(def.hourlyCurrency),
    });
    if (hourlyText) {
      hourlyHtml = `<span class="metric-hourly ${hourlyRateClass(hourlyVal)}">${hourlyText}</span>`;
    }
  }

  return `<button type="button" class="metric-card metric-group-${def.group}" data-metric-key="${def.key}" aria-label="View ${def.label} trend">
    <div class="metric-card-head">
      <span class="metric-label">${def.label}</span>
      <span class="metric-trend-hint" aria-hidden="true">›</span>
    </div>
    <div class="metric-value-row">
      <span class="metric-value">${formatMetricValue(val, def)}</span>
      ${hourlyHtml}
    </div>
    <div class="metric-delta ${deltaCls}">${formatDelta(delta, deltaOpts)}</div>
    <div class="metric-spark-wrap">
      <svg class="sparkline" viewBox="0 0 160 28" data-key="${def.key}" aria-hidden="true"></svg>
      ${hasSparkline ? "" : `<span class="sparkline-empty muted small">Collecting…</span>`}
    </div>
  </button>`;
}

function bindMetricCards() {
  $("metric-grid").querySelectorAll(".metric-card").forEach((card) => {
    card.addEventListener("click", () => openMetricModal(card.dataset.metricKey, card));
  });
}

function openMetricModal(key, returnFocusEl) {
  const def = metricDefByKey(key);
  if (!def || !lastDashboardData?.ok) return;

  metricModalReturnFocus = returnFocusEl || null;
  const m = lastDashboardData.metrics;
  const history = lastDashboardData.history || {};
  const series = history.series || {};
  const deltas = history.deltas || {};
  const values = series[key] || [];
  const timestamps = history.timestamps || [];
  const formatOpts = { decimals: def.decimals ?? 0 };
  const suffix = def.suffix || "";

  $("metric-modal-title").textContent = def.label;
  $("metric-modal-desc").textContent = def.description || "";

  let valueRow = `<span class="metric-modal-value">${formatMetricValue(m[def.key], def)}</span>`;
  if (def.hourlyKey) {
    const hourlyText = formatHourlyRate(m[def.hourlyKey], {
      decimals: formatOpts.decimals,
      currency: Boolean(def.hourlyCurrency || def.currency),
    });
    if (hourlyText) {
      valueRow += `<span class="metric-hourly ${hourlyRateClass(m[def.hourlyKey])}">${hourlyText}</span>`;
    }
  }
  const deltaOpts = { decimals: formatOpts.decimals, currency: Boolean(def.currency) };
  const deltaText = formatDelta(deltas[key], deltaOpts);
  if (deltaText) {
    const deltaCls = deltas[key] > 0 ? "up" : deltas[key] < 0 ? "down" : "";
    valueRow += `<span class="metric-modal-session-delta ${deltaCls}">${deltaText} since last export</span>`;
  }
  $("metric-modal-values").innerHTML = valueRow;

  const chart = $("metric-modal-chart");
  const drew = drawDetailChart(chart, { timestamps, values, suffix });
  chart.hidden = !drew;

  const count = history.count ?? 0;
  const span =
    timestamps.length >= 2 ? formatHistoryDuration(timestamps[timestamps.length - 1] - timestamps[0]) : "";
  const metaParts = [`Session history · ${count} point${count === 1 ? "" : "s"}`];
  if (span) metaParts.push(span);
  if (!drew) metaParts.push("waiting for more exports");
  $("metric-modal-meta").textContent = metaParts.join(" · ");

  $("metric-modal").removeAttribute("hidden");
  $("metric-modal-close").focus();
}

function closeMetricModal() {
  const modal = $("metric-modal");
  if (modal.hasAttribute("hidden")) return;
  modal.setAttribute("hidden", "");
  if (metricModalReturnFocus) {
    metricModalReturnFocus.focus();
    metricModalReturnFocus = null;
  }
}

function openDiagnosticsModal(returnFocusEl) {
  diagnosticsModalReturnFocus = returnFocusEl || $("open-diagnostics");
  const brief = lastDashboardData?.brief || "";
  $("brief-technical").textContent = brief || "No snapshot loaded yet. Load a city in CS2 with the export mod enabled.";
  $("diagnostics-modal").removeAttribute("hidden");
  $("diagnostics-modal-close").focus();
}

function closeDiagnosticsModal() {
  const modal = $("diagnostics-modal");
  if (modal.hasAttribute("hidden")) return;
  modal.setAttribute("hidden", "");
  if (diagnosticsModalReturnFocus) {
    diagnosticsModalReturnFocus.focus();
    diagnosticsModalReturnFocus = null;
  }
}

function renderDashboard(data) {
  const grid = $("metric-grid");
  if (!data.ok) {
    lastDashboardData = data;
    $("hero-title").textContent = "No city data yet";
    $("hero-sub").textContent = data.hint || data.error || "";
    $("freshness-pill").textContent = "No export";
    $("freshness-pill").className = "pill missing";
    grid.innerHTML = `<div class="skeleton"></div>`.repeat(METRIC_DEFS.length);
    $("brief-technical").textContent = "";
    return;
  }

  lastDashboardData = data;
  const m = data.metrics;
  const meta = data.meta;
  $("hero-title").textContent = m.city_name || "Your city";
  const date =
    m.game_year != null ? `Year ${m.game_year}, month ${m.game_month ?? "?"}` : "In-game date unknown";
  $("hero-sub").textContent = `${date} · ${m.buildings ?? "n/a"} buildings`;

  const pill = $("freshness-pill");
  if (meta.stale) {
    pill.textContent = `Stale · ${formatAge(meta.age_seconds)}`;
    pill.className = "pill stale";
  } else {
    const cd = freshnessCountdown(meta.age_seconds);
    pill.textContent = cd != null ? `Fresh · next ~${Math.round(cd)}s` : "Fresh";
    pill.className = "pill fresh";
  }

  const deltas = (data.history && data.history.deltas) || {};
  const series = (data.history && data.history.series) || {};
  grid.innerHTML = METRIC_DEFS.map((def) => buildMetricCardHtml(def, m, deltas, series)).join("");

  grid.querySelectorAll(".sparkline").forEach((svg) => {
    drawSparkline(svg, series[svg.dataset.key]);
  });
  bindMetricCards();

  $("brief-technical").textContent = data.brief || "";

  if (!$("metric-modal").hasAttribute("hidden") && metricModalReturnFocus) {
    openMetricModal(metricModalReturnFocus.dataset.metricKey, metricModalReturnFocus);
  }
}

function renderIssueCard(issue) {
  const actions = [];
  if (issue.ask_prompt) {
    actions.push(
      `<button type="button" class="btn secondary btn-sm issue-ask" data-prompt="${escapeAttr(issue.ask_prompt)}">Ask about this</button>`
    );
  }
  if (issue.action_view === "settings") {
    actions.push(`<button type="button" class="btn secondary btn-sm issue-settings">Open Settings</button>`);
  }
  actions.push(
    `<button type="button" class="btn ghost btn-sm issue-report" data-category="${escapeAttr(issue.report_category || "general")}" data-title="${escapeAttr(issue.title)}" data-issue-id="${escapeAttr(issue.id)}">Report</button>`
  );

  const severityLabel =
    issue.severity === "error" ? "Error" : issue.severity === "warn" ? "Warning" : "Note";
  const hintHtml = issue.hint
    ? `<p class="issue-hint muted small">${escapeHtml(issue.hint)}</p>`
    : "";

  return `<article class="issue-card severity-${issue.severity}">
    <div class="issue-stripe"></div>
    <div class="issue-body">
      <p class="issue-severity muted small">${severityLabel}</p>
      <h3>${escapeHtml(issue.title)}</h3>
      <p>${escapeHtml(issue.detail)}</p>
      ${hintHtml}
      ${actions.length ? `<div class="issue-actions">${actions.join("")}</div>` : ""}
    </div>
  </article>`;
}

function renderIssues(issues) {
  const list = $("issues-list");
  if (!issues.length) {
    list.innerHTML = `<div class="issues-empty">
      <span class="issues-empty-icon">✓</span>
      <p>No issues right now.</p>
    </div>`;
    return;
  }

  const cityIssues = issues.filter((issue) => issue.kind === "city");
  const setupIssues = issues.filter((issue) => issue.kind !== "city");
  const sections = [];

  if (cityIssues.length) {
    sections.push(
      `<div class="issues-section"><h2 class="issues-section-title">Your city</h2>${cityIssues.map((issue) => renderIssueCard(issue)).join("")}</div>`
    );
  }
  if (setupIssues.length) {
    sections.push(
      `<div class="issues-section"><h2 class="issues-section-title">Setup &amp; app</h2>${setupIssues.map((issue) => renderIssueCard(issue)).join("")}</div>`
    );
  }

  list.innerHTML = sections.join("");

  list.querySelectorAll(".issue-ask").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("question").value = btn.dataset.prompt;
      switchView("ask");
      $("question").focus();
    });
  });
  list.querySelectorAll(".issue-settings").forEach((btn) => {
    btn.addEventListener("click", () => switchView("settings"));
  });
  list.querySelectorAll(".issue-report").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchView("feedback", {
        category: btn.dataset.category,
        message: `Issue: ${btn.dataset.title}\n\n`,
        issueId: btn.dataset.issueId,
      });
    });
  });
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;");
}

async function refreshIssues({ toastOnError = false } = {}) {
  try {
    const data = await fetchJson("/api/issues");
    applyIssuesData(data);
    return data;
  } catch {
    try {
      const status = lastStatus || (await fetchJson("/api/status"));
      lastStatus = status;
      const issues =
        Array.isArray(status.issues) && status.issues.length
          ? status.issues
          : synthesizeIssuesFromStatus(status);
      const data = {
        issues,
        blocking_count: status.blocking_count ?? blockingIssueCount(issues),
      };
      applyIssuesData(data);
      return data;
    } catch (err) {
      if ($("view-issues").classList.contains("active")) {
        $("issues-list").innerHTML = `<div class="issues-error">
          <p>Could not load issues. Restart CitiesAI and try again.</p>
        </div>`;
      }
      if (toastOnError) toast(String(err.message || err), "err");
      return null;
    }
  }
}

async function loadDashboard() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const data = await fetchJson("/api/dashboard");
    renderDashboard(data);
    await refreshIssues();
    await renderSuggestions();
  } catch (err) {
    renderDashboard({
      ok: false,
      error: "Could not refresh dashboard",
      hint: String(err.message || err),
    });
    toast(String(err.message || err), "err");
  } finally {
    refreshInFlight = false;
  }
}

async function loadStatus({ promptOnboarding = false } = {}) {
  if (statusRefreshInFlight) return lastStatus;
  statusRefreshInFlight = true;
  try {
    const status = await fetchJson("/api/status");
    lastStatus = status;
    llmConfigured = Boolean(status.llm?.configured);
    updateAskHelper();

    if (Array.isArray(status.issues)) {
      lastIssues = status.issues;
      if ($("view-issues").classList.contains("active")) {
        renderIssues(lastIssues);
      }
    }
    const blocking = status.blocking_count ?? blockingIssueCount(lastIssues);
    renderHealthStrip(status, blocking);
    updateFeedbackIssuesLink();

    if (promptOnboarding && !onboardingDismissed && !status.onboarding_complete) {
      showOnboarding();
    }
    return status;
  } catch (err) {
    renderHealthStrip(null);
    toast(String(err.message || err), "err");
    return null;
  } finally {
    statusRefreshInFlight = false;
  }
}

async function renderSuggestions() {
  const container = $("suggestions");
  try {
    const data = await fetchJson("/api/suggestions");
    llmConfigured = Boolean(data.llm_configured);
    updateAskHelper();
    const items = data.suggestions || [];
    container.innerHTML = items
      .map(
        (q) =>
          `<button type="button" class="suggestion" data-q="${escapeAttr(q)}">${escapeHtml(q)}</button>`
      )
      .join("");
  } catch {
    container.innerHTML = "";
  }

  container.querySelectorAll(".suggestion").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("question").value = btn.dataset.q;
      $("question").focus();
    });
  });
}

function updateAskWelcome() {
  const hasChat = $("chat-log").children.length > 0;
  const welcome = $("ask-welcome");
  const suggestions = $("suggestions");
  if (welcome) welcome.classList.toggle("hidden", hasChat);
  if (suggestions) suggestions.classList.toggle("hidden", hasChat);
}

function appendBubble(role, html) {
  const log = $("chat-log");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.innerHTML = html;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  updateAskWelcome();
  return div;
}

function loadChatHistory() {
  try {
    const raw = localStorage.getItem("citiesai-chat");
    if (!raw) return;
    JSON.parse(raw).forEach((entry) => {
      appendBubble("user", entry.q);
      if (entry.a) appendBubble("assistant", renderMarkdown(entry.a));
    });
    updateAskWelcome();
  } catch {
    /* ignore */
  }
}

function saveChatEntry(q, a) {
  try {
    const raw = localStorage.getItem("citiesai-chat");
    const list = raw ? JSON.parse(raw) : [];
    list.push({ q, a, t: Date.now() });
    localStorage.setItem("citiesai-chat", JSON.stringify(list.slice(-40)));
  } catch {
    /* ignore */
  }
}

function processSsePart(part, handlers) {
  const lines = part.split("\n");
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (!data) return;
  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }
  handlers.onEvent(event, payload);
}

function drainSseBuffer(buffer, handlers) {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() || "";
  for (const part of parts) {
    if (part.trim()) processSsePart(part, handlers);
  }
  return remainder;
}

function askFetchSignal(timeoutMs = 180000) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(timeoutMs);
  }
  const controller = new AbortController();
  setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), timeoutMs);
  return controller.signal;
}

function resetAskSubmit() {
  const submitBtn = $("ask-submit");
  const askForm = $("ask-form");
  submitBtn.disabled = false;
  submitBtn.textContent = ASK_SUBMIT_LABEL;
  askForm.setAttribute("aria-busy", "false");
}

async function askStream(question) {
  appendBubble("user", escapeHtml(question));
  const assistant = appendBubble("assistant", typingIndicatorHtml());
  let answer = "";
  let streamFailed = false;
  let streamFinished = false;
  let bodyReader = null;
  const submitBtn = $("ask-submit");
  submitBtn.disabled = true;
  submitBtn.textContent = "Sending…";
  $("ask-form").setAttribute("aria-busy", "true");

  const finishStream = () => {
    if (streamFinished) return;
    streamFinished = true;
    resetAskSubmit();
    if (bodyReader && typeof bodyReader.cancel === "function") {
      bodyReader.cancel().catch(() => {});
    }
  };

  const handlers = {
    onEvent(event, payload) {
      if (event === "token") {
        answer += payload.text || "";
        assistant.innerHTML = renderMarkdown(answer);
        $("chat-log").scrollTop = $("chat-log").scrollHeight;
      }
      if (event === "error") {
        streamFailed = true;
        answer = "";
        const hint = payload.hint ? `<p class="muted small">${escapeHtml(payload.hint)}</p>` : "";
        assistant.innerHTML = `<span class="muted">${escapeHtml(payload.error || "Ask failed")}</span>${hint}`;
        if (payload.mode === "bundle" && payload.bundle) {
          assistant.innerHTML += `<details><summary>Retrieval bundle</summary><pre class="mono-block">${escapeHtml(payload.bundle)}</pre></details>`;
        }
        finishStream();
      }
      if (event === "done") {
        if (!answer.trim()) {
          streamFailed = true;
          assistant.innerHTML =
            `<span class="muted">No answer returned. Check Settings for your API key or try again.</span>`;
        }
        finishStream();
      }
    },
  };

  try {
    const response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, use_llm: true }),
      signal: askFetchSignal(),
    });
    if (!response.ok) {
      let message = "Ask failed";
      try {
        const errBody = await response.json();
        message = errBody.error || message;
      } catch {
        /* ignore */
      }
      throw new Error(message);
    }

    if (!response.body || typeof response.body.getReader !== "function") {
      drainSseBuffer(await response.text(), handlers);
    } else {
      bodyReader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!streamFinished) {
        const { done, value } = await bodyReader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          buffer = drainSseBuffer(buffer, handlers);
        }
        if (done || streamFinished) {
          if (!streamFinished && buffer) {
            buffer += decoder.decode();
            drainSseBuffer(buffer, handlers);
          }
          break;
        }
      }
    }

    if (!streamFailed && answer.trim()) {
      saveChatEntry(question, answer);
    }
  } catch (err) {
    streamFailed = true;
    const message =
      err.name === "TimeoutError"
        ? "Ask timed out. Check your connection or API key and try again."
        : String(err.message || err);
    assistant.innerHTML = `<span class="muted">${escapeHtml(message)}</span>`;
  } finally {
    finishStream();
  }
}

async function loadSettings() {
  try {
    const data = await fetchJson("/api/setup");
    const setPathTitle = (el, value) => {
      el.value = value || "";
      el.title = value || "";
    };
    $("setup-source").value = data.source || "";
    setPathTitle($("setup-game"), data.game_dir);
    setPathTitle($("setup-locale"), data.locale_cok);
    setPathTitle($("setup-export"), data.export_path);
    $("setup-model").value = data.llm_model || "mistral-medium-latest";
    const modBadge = $("mod-status");
    modBadge.textContent = data.mod_installed ? "Installed" : "Not installed";
    modBadge.className = `status-badge ${data.mod_installed ? "ok" : "missing"}`;
    const keyLine = $("key-status");
    if (data.llm_configured) {
      keyLine.textContent = "API key configured";
      keyLine.className = "key-status-pill ok";
    } else {
      keyLine.textContent = "No API key saved";
      keyLine.className = "key-status-pill muted";
    }
  } catch (err) {
    toast(String(err.message || err), "err");
  }
}

function setFeedbackCategory(category) {
  $("feedback-category").value = category;
  document.querySelectorAll(".segment").forEach((btn) => {
    const active = btn.dataset.category === category;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const placeholder = FEEDBACK_PLACEHOLDERS[category] || FEEDBACK_PLACEHOLDERS.general;
  $("feedback-message").placeholder = placeholder;
}

function updateFeedbackIssuesLink() {
  const link = $("feedback-issues-link");
  const blocking = lastIssues.filter((i) => i.severity === "error" || i.severity === "warn");
  link.hidden = blocking.length === 0;
}

async function detectGame() {
  const el = $("onboard-detect");
  if (!el) return;
  try {
    const data = await fetchJson("/api/setup");
    await fetchJson("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    el.textContent = data.game_dir
      ? `Found: ${data.game_dir}`
      : "Game not found. Set paths in Settings later.";
  } catch (err) {
    el.textContent = String(err.message || err);
  }
}

async function checkMod() {
  const el = $("onboard-mod");
  if (!el) return;
  try {
    const data = await fetchJson("/api/status");
    if (data.mod_installed) {
      el.textContent = "Mod already installed.";
      return;
    }
    el.textContent = "Click Continue to install the mod.";
  } catch (err) {
    el.textContent = String(err.message || err);
  }
}

async function waitForExport() {
  const el = $("onboard-export");
  if (!el) return;
  clearInterval(exportPollTimer);
  exportPollTimer = setInterval(async () => {
    try {
      const dash = await fetchJson("/api/dashboard");
      if (dash.ok && !dash.meta.stale) {
        el.textContent = "Export received!";
        clearInterval(exportPollTimer);
      } else if (dash.ok) {
        el.textContent = "Export found but stale. Load your city in CS2.";
      } else {
        el.textContent = "Still waiting… load a city with the mod enabled.";
      }
    } catch {
      el.textContent = "Still waiting…";
    }
  }, 3000);
}

function showOnboarding() {
  onboardingStep = 0;
  $("onboarding").removeAttribute("hidden");
  renderOnboardingStep();
  $("onboarding-next").focus();
}

function renderOnboardingStep() {
  if (onboardingStep !== 3) {
    clearInterval(exportPollTimer);
    exportPollTimer = null;
  }
  const step = ONBOARDING_STEPS[onboardingStep];
  const total = ONBOARDING_STEPS.length;
  $("onboarding-bar").style.width = `${((onboardingStep + 1) / total) * 100}%`;
  $("onboarding-body").innerHTML = `<h2 id="onboarding-title">${step.title}</h2>${step.html}`;
  $("onboarding-back").hidden = onboardingStep === 0;
  $("onboarding-next").textContent = onboardingStep === total - 1 ? "Open dashboard" : "Continue";
  if (step.onEnter) step.onEnter();
}

function hideOnboarding() {
  onboardingDismissed = true;
  $("onboarding").setAttribute("hidden", "");
  clearInterval(exportPollTimer);
}

async function completeOnboarding() {
  hideOnboarding();
  try {
    const keyInput = $("onboard-key");
    if (keyInput && keyInput.value.trim()) {
      await fetchJson("/api/settings/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: keyInput.value.trim() }),
      });
    }
    await fetchJson("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    toast("Setup complete", "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
  loadDashboard();
  await loadStatus();
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

document.querySelectorAll("[data-view-jump]").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.viewJump));
});

$("refresh-dashboard").addEventListener("click", loadDashboard);

$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("question");
  const q = input.value.trim();
  if (!q) return;
  const btn = $("ask-submit");
  if (btn.disabled) return;

  input.value = "";
  autoGrowTextarea(input);

  try {
    await askStream(q);
  } catch (err) {
    toast(String(err.message || err), "err");
    if (!input.value.trim()) {
      input.value = q;
      autoGrowTextarea(input);
    }
  }
});

$("question").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.shiftKey) return;
  e.preventDefault();
  if ($("ask-submit").disabled) return;
  $("ask-form").requestSubmit();
});

$("question").addEventListener("input", () => {
  autoGrowTextarea($("question"));
});

$("clear-chat").addEventListener("click", () => {
  $("chat-log").innerHTML = "";
  localStorage.removeItem("citiesai-chat");
  updateAskWelcome();
});

$("save-setup").addEventListener("click", async () => {
  try {
    const data = await fetchJson("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        game_dir: $("setup-game").value.trim(),
        locale_cok: $("setup-locale").value.trim(),
        export_path: $("setup-export").value.trim(),
        llm_model: $("setup-model").value.trim(),
      }),
    });
    toast(`Saved ${data.config_path}`, "ok");
    loadStatus();
    refreshIssues();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("redetect-paths").addEventListener("click", loadSettings);

$("install-mod").addEventListener("click", async () => {
  try {
    const data = await fetchJson("/api/install-mod", { method: "POST", body: "{}" });
    if (!data.ok) throw new Error(data.error);
    toast(`Mod installed to ${data.installed_to}`, "ok");
    const modBadge = $("mod-status");
    modBadge.textContent = "Installed";
    modBadge.className = "status-badge ok";
    loadStatus();
    refreshIssues();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("save-key").addEventListener("click", async () => {
  try {
    await fetchJson("/api/settings/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: $("api-key").value.trim() }),
    });
    toast("API key saved locally", "ok");
    $("key-status").textContent = "API key saved — use Test key to verify";
    $("key-status").className = "key-status-pill muted";
    $("api-key").value = "";
    await loadStatus();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("test-key").addEventListener("click", async () => {
  const key = $("api-key").value.trim();
  if (key) {
    await fetchJson("/api/settings/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
  }
  try {
    const data = await fetchJson("/api/settings/key/test");
    if (!data.ok) throw new Error(data.error);
    toast(`Key OK (${data.model})`, "ok");
    $("key-status").textContent = "API key verified";
    $("key-status").className = "key-status-pill ok";
    llmConfigured = true;
    updateAskHelper();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

document.querySelectorAll(".segment").forEach((btn) => {
  btn.addEventListener("click", () => setFeedbackCategory(btn.dataset.category));
});

$("feedback-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const success = $("feedback-success");
  success.hidden = true;
  try {
    const data = await fetchJson("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: $("feedback-category").value,
        message: $("feedback-message").value,
        contact: $("feedback-contact").value,
        attach_system_info: $("feedback-system").checked,
        context_issue_id: feedbackContextIssueId || undefined,
      }),
    });
    const msg =
      data.mode === "discord"
        ? "Thanks! Your feedback was sent to the beta channel."
        : data.hint
          ? `${data.hint} Local copy: ${data.saved_to}`
          : `Thanks! Saved locally at ${data.saved_to}`;
    if (data.warning) {
      toast(String(data.warning), "err");
    } else if (data.hint && data.mode === "local") {
      toast(String(data.hint), "err");
    }
    success.hidden = false;
    success.innerHTML = `<span class="feedback-success-icon">✓</span><p>${escapeHtml(msg)}</p>`;
    $("feedback-message").value = "";
    $("feedback-contact").value = "";
    feedbackContextIssueId = "";
    toast("Feedback sent", "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("onboarding-skip").addEventListener("click", () => {
  void completeOnboarding();
});

$("onboarding-back").addEventListener("click", () => {
  if (onboardingStep > 0) {
    onboardingStep -= 1;
    renderOnboardingStep();
  }
});

$("onboarding-next").addEventListener("click", async () => {
  if (onboardingStep === 2) {
    try {
      const data = await fetchJson("/api/install-mod", { method: "POST", body: "{}" });
      if (!data.ok) toast(data.error, "err");
      else toast("Mod installed", "ok");
    } catch (err) {
      toast(String(err.message || err), "err");
    }
  }
  if (onboardingStep >= ONBOARDING_STEPS.length - 1) {
    await completeOnboarding();
    return;
  }
  onboardingStep += 1;
  renderOnboardingStep();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const metricModal = $("metric-modal");
  if (!metricModal.hasAttribute("hidden")) {
    closeMetricModal();
    return;
  }
  const diagnosticsModal = $("diagnostics-modal");
  if (!diagnosticsModal.hasAttribute("hidden")) {
    closeDiagnosticsModal();
    return;
  }
  const onboarding = $("onboarding");
  if (!onboarding.hasAttribute("hidden")) {
    void completeOnboarding();
  }
});

$("metric-modal-close").addEventListener("click", closeMetricModal);
$("metric-modal").querySelectorAll("[data-close-metric-modal]").forEach((el) => {
  el.addEventListener("click", closeMetricModal);
});

$("diagnostics-modal-close").addEventListener("click", closeDiagnosticsModal);
$("diagnostics-modal").querySelectorAll("[data-close-diagnostics-modal]").forEach((el) => {
  el.addEventListener("click", closeDiagnosticsModal);
});

$("open-diagnostics").addEventListener("click", () => {
  openDiagnosticsModal($("open-diagnostics"));
});

async function init() {
  try {
    const ver = await fetchJson("/api/version");
    $("app-version").textContent = `v${ver.version}`;
  } catch {
    /* ignore */
  }
  loadChatHistory();
  updateAskHelper();
  setFeedbackCategory($("feedback-category").value);
  await loadStatus({ promptOnboarding: true });
  await loadDashboard();
  dashboardTimer = setInterval(async () => {
    await loadDashboard();
    await loadStatus();
  }, POLL_MS);
}

init();
