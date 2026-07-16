const POLL_MS = 10000;
const STALE_AFTER_SECONDS = 30;
const ASK_TIMEOUT_MS = 480000;
let activeAskAbort = null;
let activeAskGeneration = 0;
const STATUS_POLL_INTERVALS = 6;
const ASK_SUBMIT_LABEL = "Send";

let statusPollCounter = 0;
let pollErrorActive = false;
let watchToggleTouched = false;
let lastIssuesFingerprint = "";

const ONBOARDING_STEPS = [
  {
    title: "Welcome to CitiesAI",
    html: `<p>Your read-only advisor for <strong>Cities: Skylines II</strong>. See live city stats and ask grounded questions. We never touch your save.</p>
      <p class="muted small">Choose how CitiesAI should talk to you. You can change this later in Settings.</p>
      <div class="onboarding-style-grid style-picker" role="radiogroup" aria-label="Advisor style">
        <label class="style-option"><input type="radio" name="onboard-advisor-style" value="civic" checked /><span class="style-option-card"><strong>Civic</strong><span class="muted small">Calm, direct, concise municipal guidance.</span></span></label>
        <label class="style-option"><input type="radio" name="onboard-advisor-style" value="conversational" /><span class="style-option-card"><strong>Conversational</strong><span class="muted small">Warm, game-native co-mayor voice.</span></span></label>
        <label class="style-option"><input type="radio" name="onboard-advisor-style" value="analyst" /><span class="style-option-card"><strong>Analyst</strong><span class="muted small">Technical, metric-heavy detail.</span></span></label>
      </div>`,
  },
  {
    title: "Detect game & install mod",
    html: `<p>We'll look for CS2 and install the tiny data export mod that writes a snapshot every few seconds.</p>
      <p id="onboard-detect" class="muted">Detecting…</p>
      <p id="onboard-mod" class="muted"></p>`,
    onEnter: async () => { await detectGame(); await checkMod(); },
  },
  {
    title: "Load a city in-game",
    html: `<p>Launch CS2, enable <strong>CS2 Data Export</strong>, and load your city. We'll wait for the first snapshot.</p><p id="onboard-export" class="muted">Waiting…</p>`,
    onEnter: waitForExport,
  },
  {
    title: "Optional AI key",
    html: `<p>Stats work without AI. For answers, get a free key at <a href="https://console.mistral.ai" target="_blank" rel="noopener">console.mistral.ai</a> and paste below.</p>
      <label class="field"><span class="field-label">API key</span><input id="onboard-key" class="control" type="password" placeholder="Optional" /></label>
      <p class="muted small">Continue finishes setup. Escape closes this wizard for now without marking setup complete.</p>`,
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
let lastApiKeyEnv = "MISTRAL_API_KEY";
let llmPresets = {};
let apiKeyReplacing = false;
let lastKeyUiState = { configured: false, suffix: null, provider: "mistral" };
let refreshInFlight = false;
let statusRefreshInFlight = false;
let lastDashboardData = null;
let metricModalReturnFocus = null;
let diagnosticsModalReturnFocus = null;
let lastActiveCity = null;
let lastUpdateInfo = null;
let updateCheckInFlight = false;
let advisorStyle = "civic";
let selectedIssueId = null;
let pendingIssueId = null;
/** Stable issue id order while the Issues view is open (avoids poll re-rank flicker). */
let issuesDisplayOrder = [];

function $(id) {
  return document.getElementById(id);
}

function sessionToken() {
  return document.querySelector('meta[name="citiesai-token"]')?.content || "";
}

async function fetchJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method && options.method !== "GET") {
    headers["X-CitiesAI-Token"] = sessionToken();
  }
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, { ...options, headers });
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
  const root = $("toast-root");
  if (kind === "err" && pollErrorActive && root?.dataset.lastErr === message) return;
  if (kind === "err") {
    pollErrorActive = true;
    if (root) root.dataset.lastErr = message;
  } else if (kind === "ok") {
    pollErrorActive = false;
    if (root) delete root.dataset.lastErr;
  }
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  root.appendChild(el);
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

function metricDeltaClass(delta, invert = false) {
  if (delta == null || Number.isNaN(delta) || delta === 0) return "";
  const up = delta > 0;
  if (invert) return up ? "down" : "up";
  return up ? "up" : "down";
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
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  const totalMinutes = Math.floor(seconds / 60);
  if (totalMinutes < 60) return `${totalMinutes}m ago`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (minutes === 0) return `${hours}h ago`;
  return `${hours}h ${minutes}m ago`;
}

function freshnessCountdown(ageSeconds) {
  if (ageSeconds == null) return null;
  return Math.max(0, STALE_AFTER_SECONDS - ageSeconds);
}

function safeHttpUrl(url) {
  try {
    const parsed = new URL(String(url));
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch {
    /* ignore */
  }
  return null;
}

function issuesFingerprint(issues) {
  return JSON.stringify((issues || []).map((i) => `${i.id}:${i.severity}`));
}

function stabilizeIssueOrder(issues, previousOrder) {
  const byId = new Map((issues || []).map((issue) => [String(issue.id), issue]));
  const ordered = [];
  const seen = new Set();
  for (const id of previousOrder || []) {
    const row = byId.get(String(id));
    if (!row) continue;
    ordered.push(row);
    seen.add(String(id));
  }
  for (const issue of issues || []) {
    const id = String(issue.id);
    if (seen.has(id)) continue;
    ordered.push(issue);
    seen.add(id);
  }
  return ordered;
}

function drawSparkline(svg, values, projected) {
  const nums = (values || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  const proj = (projected || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (nums.length < 2) return;
  const combined = proj.length ? [...nums, ...proj] : nums;
  const w = 160;
  const h = 20;
  const min = Math.min(...combined);
  const max = Math.max(...combined);
  const range = max - min || 1;
  const toPoint = (v, i, total) => {
    const x = (i / (total - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  };
  const solidPts = nums.map((v, i) => toPoint(v, i, combined.length));
  let html = `<polyline fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" points="${solidPts.join(" ")}" />`;
  if (proj.length) {
    const dashedPts = [
      toPoint(nums[nums.length - 1], nums.length - 1, combined.length),
      ...proj.map((v, i) => toPoint(v, nums.length + i, combined.length)),
    ];
    html += `<polyline fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="4 3" opacity="0.55" points="${dashedPts.join(" ")}" />`;
  }
  svg.innerHTML = html;
}

function formatHistoryDuration(seconds) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 1) return "";
  if (seconds < 120) return `~${Math.round(seconds)}s`;
  if (seconds < 7200) return `~${Math.round(seconds / 60)} min`;
  return `~${(seconds / 3600).toFixed(1)}h`;
}

function parseHistoryTs(iso) {
  if (iso == null) return null;
  const ms = Date.parse(String(iso));
  return Number.isFinite(ms) ? ms : null;
}

function historySpanSeconds(timestamps) {
  const parsed = (timestamps || []).map(parseHistoryTs).filter((t) => t != null);
  if (parsed.length < 2) return null;
  return (parsed[parsed.length - 1] - parsed[0]) / 1000;
}

function historyOffsetSeconds(timestamps, index) {
  const parsed = (timestamps || []).map(parseHistoryTs);
  const last = parsed[parsed.length - 1];
  const at = parsed[index];
  if (last == null || at == null) return null;
  return (last - at) / 1000;
}

function formatAxisTick(n, options = {}) {
  const { currency = false, decimals = 0, compact = true, suffix = "" } = options;
  if (n == null || Number.isNaN(n)) return "n/a";
  const abs = Math.abs(Number(n));
  let body;
  if (compact && abs >= 1_000_000) {
    body = `${(Number(n) / 1_000_000).toFixed(1)}M`;
  } else if (compact && abs >= 10_000) {
    body = `${(Number(n) / 1_000).toFixed(1)}K`;
  } else {
    body = formatNum(n, { decimals });
  }
  if (currency) return `¢${body}`;
  return `${body}${suffix}`;
}

function drawDetailChart(svg, { timestamps, values, suffix = "", currency = false }) {
  const nums = (values || []).filter((v) => typeof v === "number" && Number.isFinite(v));
  if (!svg || nums.length < 2) {
    if (svg) svg.innerHTML = "";
    return false;
  }

  const width = 560;
  const height = 220;
  const axisDecimals = suffix === "%" ? 1 : 0;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const yTicks = [min, min + range / 2, max];
  const tickLabels = yTicks.map((tick) =>
    formatAxisTick(tick, { currency, decimals: axisDecimals, compact: true, suffix: currency ? "" : suffix })
  );
  const pad = {
    top: 16,
    right: 16,
    bottom: 28,
    left: Math.min(88, Math.max(52, Math.max(...tickLabels.map((l) => l.length)) * 6 + 12)),
  };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const points = nums.map((v, i) => {
    const x = pad.left + (i / (nums.length - 1)) * plotW;
    const y = pad.top + plotH - ((v - min) / range) * plotH;
    return { x, y, v };
  });

  const yTickLines = yTicks
    .map((tick, i) => {
      const y = pad.top + plotH - ((tick - min) / range) * plotH;
      const label = tickLabels[i];
      return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="chart-grid" />
        <text x="${pad.left - 6}" y="${y + 4}" class="chart-axis" text-anchor="end">${label}</text>`;
    })
    .join("");

  const ts = timestamps || [];
  const xLabels = [];
  if (ts.length >= 2) {
    const midIdx = Math.floor((ts.length - 1) / 2);
    const spanSec = historySpanSeconds(ts);
    const midSec = historyOffsetSeconds(ts, midIdx);
    const slots = [
      { idx: 0, label: spanSec != null ? `${formatHistoryDuration(spanSec)} ago` : "" },
      { idx: midIdx, label: midSec != null ? `${formatHistoryDuration(midSec)} ago` : "" },
      { idx: ts.length - 1, label: "now" },
    ];
    for (const slot of slots) {
      if (!slot.label) continue;
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

function typingIndicatorHtml(statusText = "") {
  const status = statusText
    ? `<div class="ask-status muted small">${escapeHtml(statusText)}</div>`
    : "";
  return `${status}<span class="typing-indicator"><span></span><span></span><span></span></span>`;
}

function autoGrowTextarea(el) {
  el.style.height = "auto";
  const maxRows = 6;
  const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 22;
  const maxHeight = lineHeight * maxRows;
  el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
}

function scrollChatToBottom(behavior = "auto") {
  const log = $("chat-log");
  if (!log) return;
  requestAnimationFrame(() => {
    log.scrollTo({ top: log.scrollHeight, behavior });
    const last = log.lastElementChild;
    if (last) last.scrollIntoView({ block: "end", behavior });
  });
}

function askFromPrompt(prompt) {
  if (!llmConfigured) {
    toast("Add an API key in Settings for AI answers", "err");
    switchView("settings");
    openSettingsSection("ai");
    return;
  }
  $("question").value = prompt;
  autoGrowTextarea($("question"));
  switchView("ask");
  scrollChatToBottom();
  $("ask-form").requestSubmit();
}

function gradeClass(grade) {
  const safe = String(grade || "NA").replace(/[^A-Za-z0-9/-]/g, "");
  if (safe === "NA" || safe === "N/A") return "grade-NA";
  return `grade-${safe}`;
}

function renderGradeBadge(grade, options = {}) {
  const label = String(grade || "—");
  const cls = gradeClass(label);
  const sizeCls = options.size === "lg" ? " grade-badge-lg" : "";
  const aria = options.ariaLabel || `Grade ${label}`;
  return `<span class="grade-badge${sizeCls} ${cls}" aria-label="${escapeAttr(aria)}">${escapeHtml(label)}</span>`;
}

const modalTrapCleanups = new WeakMap();

function bindModalFocusTrap(modalEl, onClose) {
  const prev = modalTrapCleanups.get(modalEl);
  if (prev) prev();

  const selector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const nodes = [...modalEl.querySelectorAll(selector)].filter((el) => el.offsetParent !== null);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  modalEl.addEventListener("keydown", onKeyDown);
  const cleanup = () => modalEl.removeEventListener("keydown", onKeyDown);
  modalTrapCleanups.set(modalEl, cleanup);
  return cleanup;
}

function switchView(name, options = {}) {
  document.querySelectorAll(".nav-item[data-view], .nav-icon-btn[data-view]").forEach((btn) => {
    const active = btn.dataset.view === name;
    btn.classList.toggle("active", active);
    if (active) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
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
    renderAskContextRail();
    $("question")?.focus();
  }
  if (name === "settings") {
    void loadSettings().then(() => {
      if (options.section) openSettingsSection(options.section);
      if (lastUpdateInfo) renderUpdateSettings(lastUpdateInfo);
    });
    void refreshUpdateUi({ force: false });
  }
  if (name === "insights") void loadInsights();
  if (name === "issues") {
    if (options.issueId) pendingIssueId = String(options.issueId);
    // Fresh entry without a sticky selection: allow ranked order + top auto-select.
    if (!selectedIssueId && !pendingIssueId) {
      issuesDisplayOrder = [];
    }
    const preserve = Boolean(selectedIssueId || pendingIssueId);
    void refreshIssues({ toastOnError: true, preserveSelection: preserve });
  }
  if (name === "feedback") {
    if (options.category) setFeedbackCategory(options.category);
    if (options.message) $("feedback-message").value = options.message;
  }
}

function blockingIssueCount(issues) {
  return issues.filter((i) => i.severity === "error" || i.severity === "warn").length;
}

function applyIssuesData(data, options = {}) {
  const next = data.issues || [];
  const fp = issuesFingerprint(next);
  const changed = fp !== lastIssuesFingerprint;
  lastIssues = next;
  lastIssuesFingerprint = fp;
  updateIssuesNavLabel(lastIssues);
  if ($("view-issues").classList.contains("active")) {
    // Hard sticky: never follow Co-Mayor / re-rank while reading.
    const preserve =
      Boolean(options.preserveSelection) ||
      Boolean(selectedIssueId) ||
      Boolean(pendingIssueId) ||
      issueInspectorBusy();
    if (changed || options.force || !document.querySelector(".issue-item-btn")) {
      renderIssues(lastIssues, { preserveSelection: preserve });
    }
  } else {
    issuesDisplayOrder = [];
  }
  if (lastStatus) {
    renderHealthStrip(lastStatus);
  }
}

const PATH_LABELS = {
  game_dir: "Game folder",
  locale_cok: "Locale file",
  export_path: "Snapshot file",
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
      action_view: "settings",
    });
  }
  const exportBlock = status.export;
  if (!exportBlock) {
    issues.push({
      id: "export_missing",
      severity: "warn",
      title: "No city snapshot yet",
      detail: "Load a city in CS2 with the Data Export mod enabled.",
      hint: "After loading, wait a few seconds for the first snapshot.",
      ask_prompt: "Why is my city snapshot missing and how do I fix it?",
    });
  } else if (exportBlock.corrupt) {
    issues.push({
      id: "export_corrupt",
      severity: "error",
      title: "City snapshot file is unreadable",
      detail: String(exportBlock.error || "The latest.json file could not be parsed."),
      hint: "Re-load your city in CS2 or wait for a new snapshot.",
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
    });
  } else if (!enc.available) {
    issues.push({
      id: "encyclopedia_missing",
      severity: "warn",
      title: "Game encyclopedia unavailable",
      detail: "Wiki-style answers may be limited until encyclopedia data loads.",
      hint: "Check that your game Locale.cok path is correct in Settings.",
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

function updateIssuesNavLabel(issues) {
  const btn = $("nav-issues");
  if (!btn) return;
  const count = (issues || []).length;
  btn.textContent = count > 0 ? `Issues (${count})` : "Issues";
  btn.classList.toggle("has-issues", count > 0);
  btn.setAttribute("aria-label", count > 0 ? `Issues, ${issueCountLabel(count)}` : "Issues");
}

function renderHealthStrip(status) {
  const el = $("health-strip");
  if (!el) return;
  if (!status) {
    el.textContent = "Signal unavailable";
    return;
  }
  const exportReady = Boolean(status.export && !status.export.corrupt);
  const needsSetup = !status.mod_installed || !exportReady;
  const stale = Boolean(status.export?.stale);
  if (needsSetup) {
    el.textContent = "Signal: setup needed";
    return;
  }
  if (stale) {
    el.textContent = "Signal: stale";
    return;
  }
  el.textContent = "Signal: live";
}

function updateAskHelper() {
  const el = $("ask-helper");
  if (!el) return;
  const styleNote =
    advisorStyle === "conversational"
      ? "Conversational voice"
      : advisorStyle === "analyst"
        ? "Analyst voice"
        : "Civic voice";
  const submitBtn = $("ask-submit");
  const question = $("question");
  if (llmConfigured) {
    el.textContent = `${styleNote}. Grounded in your city snapshot and Cities Wiki.`;
    if (submitBtn) submitBtn.disabled = false;
    if (question) question.disabled = false;
  } else {
    el.innerHTML = `${styleNote}. <strong>Add an API key in Settings</strong> for AI answers — stats, Insights, and Issues work without one.`;
    if (submitBtn) submitBtn.disabled = true;
    if (question) question.disabled = true;
  }
}

function openSettingsSection(section) {
  const id = String(section || "paths");
  document.querySelectorAll(".settings-index-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.settingsSection === id);
  });
  document.querySelectorAll(".settings-section").forEach((panel) => {
    const active = panel.dataset.settingsSection === id;
    panel.hidden = !active;
  });
  const target = document.getElementById(`settings-section-${id}`);
  target?.scrollIntoView({ block: "nearest" });
}

function selectedAdvisorStyleFromForm() {
  const checked = document.querySelector('input[name="advisor-style"]:checked');
  return checked?.value || advisorStyle || "civic";
}

function applyAdvisorStyleToForm(style) {
  advisorStyle = style || "civic";
  const input = document.querySelector(`input[name="advisor-style"][value="${advisorStyle}"]`);
  if (input) input.checked = true;
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
    suffix: "%",
    description: "Average citizen health index (0–100%).",
  },
  {
    key: "congestion_percent",
    label: "Traffic congestion",
    group: "mobility",
    decimals: 0,
    suffix: "%",
    invertDelta: true,
    description: "Share of road vehicles moving slowly due to blockers (0–100%). Requires CS2 Data Export schema 2.10.0+.",
  },
  {
    key: "wellbeing",
    label: "Wellbeing",
    group: "social",
    decimals: 1,
    suffix: "%",
    description: "Average citizen wellbeing index (0–100%).",
  },
  {
    key: "unemployment_percent",
    label: "Unemployment",
    group: "social",
    suffix: "%",
    invertDelta: true,
    description: "Share of working-age citizens without jobs.",
  },
  {
    key: "electricity_fulfillment_percent",
    label: "Power fulfillment",
    group: "services",
    decimals: 0,
    suffix: "%",
    description: "Share of electricity consumption met by local production and batteries. Requires schema 2.11.0+.",
  },
  {
    key: "water_fulfillment_percent",
    label: "Water fulfillment",
    group: "services",
    decimals: 0,
    suffix: "%",
    description: "Share of fresh water consumption met by local production and imports.",
  },
  {
    key: "sewage_fulfillment_percent",
    label: "Sewage fulfillment",
    group: "services",
    decimals: 0,
    suffix: "%",
    description: "Share of sewage demand met by local treatment capacity.",
  },
  {
    key: "crime_rate",
    label: "Crime rate",
    group: "social",
    decimals: 0,
    suffix: "%",
    invertDelta: true,
    description: "Official city crime rate (0–100%). Lower is better.",
  },
];

function metricDefByKey(key) {
  return METRIC_DEFS.find((def) => def.key === key);
}

function sparklineSeries(def, metrics, series) {
  const historyValues = series[def.key] || [];
  const numeric = historyValues.filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (numeric.length >= 2) return historyValues;
  const live = metrics[def.key];
  if (typeof live !== "number" || Number.isNaN(live)) return historyValues;
  if (numeric.length === 1) return [numeric[0], live];
  return [live, live];
}

function buildMetricCardHtml(def, m, deltas, series, options = {}) {
  const sparklineEmptyLabel = options.sparklineEmptyLabel ?? "Collecting…";
  const val = m[def.key];
  const formatted = formatMetricValue(val, def);
  const delta = deltas?.[def.key];
  const formatOpts = { decimals: def.decimals ?? 0 };
  const deltaCls = metricDeltaClass(delta, Boolean(def.invertDelta));
  const sparkValues = sparklineSeries(def, m, series);
  const hasSparkline = sparkValues.filter((v) => typeof v === "number" && !Number.isNaN(v)).length >= 2;
  const deltaOpts = { decimals: def.decimals ?? 0, currency: Boolean(def.currency) };

  let signalHtml = "";
  if (def.hourlyKey) {
    const hourlyVal = m[def.hourlyKey];
    const hourlyText = formatHourlyRate(hourlyVal, {
      decimals: formatOpts.decimals,
      currency: Boolean(def.hourlyCurrency || def.currency),
    });
    if (hourlyText) {
      signalHtml = `<span class="metric-signal metric-hourly ${hourlyRateClass(hourlyVal)}">${hourlyText}</span>`;
    }
  }
  if (!signalHtml) {
    const deltaText = formatDelta(delta, deltaOpts);
    if (deltaText) {
      signalHtml = `<span class="metric-signal metric-delta ${deltaCls}">${deltaText}</span>`;
    }
  }

  return `<button type="button" class="metric-card metric-group-${escapeAttr(def.group || "city")}" data-metric-key="${escapeAttr(def.key)}" aria-label="${escapeAttr(`View ${def.label} trend, current ${formatted}`)}">
    <div class="metric-card-head">
      <span class="metric-label">${escapeHtml(def.label)}</span>
      <span class="metric-trend-hint" aria-hidden="true">›</span>
    </div>
    <div class="metric-value-row">
      <span class="metric-value">${escapeHtml(formatted)}</span>
      ${signalHtml}
    </div>
    <div class="metric-spark-wrap">
      <svg class="sparkline" viewBox="0 0 160 28" data-key="${escapeAttr(def.key)}" aria-hidden="true"></svg>
      ${hasSparkline ? "" : `<span class="sparkline-empty muted small">${escapeHtml(sparklineEmptyLabel)}</span>`}
    </div>
  </button>`;
}

function bindMetricCards() {
  $("metric-grid").querySelectorAll(".metric-row, .metric-card").forEach((card) => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".metric-row.active").forEach((el) => el.classList.remove("active"));
      card.classList.add("active");
      openMetricModal(card.dataset.metricKey, card);
    });
  });
}

function openMetricModalFromSeries(def, ctx, returnFocusEl) {
  const {
    metrics,
    series,
    timestamps,
    deltas,
    sourceLabel,
    deltaSinceLabel = "since last snapshot",
  } = ctx;
  const key = def.key;
  const values = series[key] || [];
  const formatOpts = { decimals: def.decimals ?? 0 };
  const suffix = def.suffix || "";

  metricModalReturnFocus = returnFocusEl || null;
  $("metric-modal-title").textContent = def.label;
  $("metric-modal-desc").textContent = def.description || "";

  let valueRow = `<span class="metric-modal-value">${formatMetricValue(metrics[def.key], def)}</span>`;
  let hourlyShown = false;
  if (def.hourlyKey) {
    const hourlyText = formatHourlyRate(metrics[def.hourlyKey], {
      decimals: formatOpts.decimals,
      currency: Boolean(def.hourlyCurrency || def.currency),
    });
    if (hourlyText) {
      hourlyShown = true;
      valueRow += `<span class="metric-hourly ${hourlyRateClass(metrics[def.hourlyKey])}">${hourlyText}</span>`;
    }
  }
  const deltaOpts = { decimals: formatOpts.decimals, currency: Boolean(def.currency) };
  const deltaText = formatDelta(deltas[key], deltaOpts);
  if (deltaText && !hourlyShown) {
    const deltaCls = metricDeltaClass(deltas[key], def.invertDelta);
    valueRow += `<span class="metric-modal-session-delta ${deltaCls}">${deltaText} ${deltaSinceLabel}</span>`;
  }
  $("metric-modal-values").innerHTML = valueRow;

  const chart = $("metric-modal-chart");
  const drew = drawDetailChart(chart, {
    timestamps,
    values,
    suffix,
    currency: Boolean(def.currency),
  });
  chart.hidden = !drew;

  const spanSec = historySpanSeconds(timestamps);
  const metaParts = [sourceLabel];
  if (spanSec != null) metaParts.push(formatHistoryDuration(spanSec));
  if (!drew) metaParts.push("waiting for more snapshots");
  $("metric-modal-meta").textContent = metaParts.join(" · ");
  const chartSummary = $("metric-chart-summary");
  if (chartSummary) {
    chartSummary.textContent = drew
      ? `${def.label} trend · ${metaParts.join(" · ")}`
      : `${def.label} · waiting for more snapshots`;
  }

  const inspector = $("metric-modal") || $("metric-inspector");
  inspector.removeAttribute("hidden");
  inspector.hidden = false;
  const shell = $("app-shell");
  if (shell) shell.inert = true;
  bindModalFocusTrap(inspector, closeMetricModal);
  $("metric-modal-close")?.focus();
}

function openMetricModal(key, returnFocusEl) {
  const def = metricDefByKey(key);
  if (!def || !lastDashboardData?.ok) return;
  const hist = lastDashboardData.historian || {};
  const count = hist.count ?? 0;
  openMetricModalFromSeries(
    def,
    {
      metrics: lastDashboardData.metrics,
      series: hist.series || {},
      timestamps: hist.timestamps || [],
      deltas: hist.deltas || {},
      sourceLabel: `Historian · ${count} snapshot${count === 1 ? "" : "s"}`,
      deltaSinceLabel: "since prior snapshot",
    },
    returnFocusEl
  );
}

function closeMetricModal() {
  const modal = $("metric-modal") || $("metric-inspector");
  if (!modal || modal.hasAttribute("hidden")) return;
  modal.setAttribute("hidden", "");
  modal.hidden = true;
  const shell = $("app-shell");
  if (shell) shell.inert = false;
  document.querySelectorAll(".metric-card.active, .metric-row.active").forEach((el) => el.classList.remove("active"));
  const returnFocus = metricModalReturnFocus;
  metricModalReturnFocus = null;
  if (returnFocus && typeof returnFocus.focus === "function") returnFocus.focus();
}

function openDiagnosticsModal(returnFocusEl) {
  diagnosticsModalReturnFocus = returnFocusEl || $("open-diagnostics");
  const brief = lastDashboardData?.brief || "";
  $("brief-technical").textContent = brief || "No snapshot loaded yet. Load a city in CS2 with the export mod enabled.";
  $("diagnostics-modal").removeAttribute("hidden");
  const shell = $("app-shell");
  if (shell) shell.inert = true;
  bindModalFocusTrap($("diagnostics-modal"), closeDiagnosticsModal);
  $("diagnostics-modal-close").focus();
}

function closeDiagnosticsModal() {
  const modal = $("diagnostics-modal");
  if (modal.hasAttribute("hidden")) return;
  modal.setAttribute("hidden", "");
  const shell = $("app-shell");
  if (shell) shell.inert = false;
  if (diagnosticsModalReturnFocus) {
    diagnosticsModalReturnFocus.focus();
    diagnosticsModalReturnFocus = null;
  }
}

function renderGradeHistoryChart(svg, gradeHistory) {
  if (!svg) return;
  const points = gradeHistory?.points || [];
  const scores = points
    .map((point) => point.overall_score)
    .filter((value) => typeof value === "number");
  if (scores.length < 2) {
    svg.innerHTML = "";
    return;
  }
  const width = 560;
  const height = 120;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const span = Math.max(max - min, 1);
  const coords = scores
    .map((score, index) => {
      const x = (index / (scores.length - 1)) * (width - 20) + 10;
      const y = height - 10 - ((score - min) / span) * (height - 20);
      return `${x},${y}`;
    })
    .join(" ");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${coords}" />`;
}


function renderDemandFactorsCard(demandFactors) {
  if (!demandFactors?.ok) {
    return `<div class="insight-ledger"><h3>RCI demand</h3><p class="muted">${escapeHtml(demandFactors?.summary || "Demand factor export unavailable.")}</p></div>`;
  }
  const rows = (demandFactors.zones || [])
    .map((zone) => {
      const pct = zone.demand_percent != null ? `${Math.round(zone.demand_percent)}%` : "—";
      return `<li class="finding-row severity-${escapeAttr(zone.severity || "info")}">
        <div class="finding-copy"><strong>${escapeHtml(zone.label)} · ${escapeHtml(pct)}</strong></div>
      </li>`;
    })
    .join("");
  return `<div class="insight-ledger">
    <h3>RCI demand</h3>
    <p class="muted">${escapeHtml(demandFactors.summary || "")}</p>
    <ul class="finding-list">${rows}</ul>
  </div>`;
}

function renderAccessGapsCard(accessGaps) {
  if (!accessGaps) {
    return "";
  }
  if (!accessGaps.ok) {
    return `<div class="insight-ledger"><h3>Next line advisor</h3><p class="muted">${escapeHtml(accessGaps.summary || "Transit access gap data unavailable.")}</p></div>`;
  }
  const hotspots = (accessGaps.hotspots || []).slice(0, 5);
  const rows = hotspots
    .map(
      (spot) => `<li class="finding-row severity-${escapeAttr(spot.severity || "warn")}">
        <div class="finding-copy"><strong>${escapeHtml(spot.title || "Hotspot")}</strong> — ${escapeHtml(spot.detail || spot.suggestion || "Uncovered demand")}</div>
      </li>`
    )
    .join("");
  const capture = accessGaps.capture_note
    ? `<p class="muted small">${escapeHtml(accessGaps.capture_note)}</p>`
    : "";
  return `<div class="insight-ledger">
    <h3>Next line advisor</h3>
    <p class="muted">${escapeHtml(accessGaps.summary || "")}</p>
    ${capture}
    <ul class="finding-list">${rows || "<li class='muted'>No hotspots recorded yet — play with citizens traveling to populate trip capture.</li>"}</ul>
  </div>`;
}

function renderUtilitiesCard(utilities) {
  if (!utilities?.ok) {
    return `<div class="insight-ledger"><p class="muted">${escapeHtml(utilities?.summary || "Utilities export unavailable.")}</p></div>`;
  }
  const serviceRows = (utilities.services || [])
    .map((row) => {
      const severity = row.severity || (String(row.detail || "").toLowerCase().includes("shortage") ? "error" : "info");
      const statusClass = severity === "error" ? "error" : severity === "warn" ? "warn" : "ok";
      const sevLabel = severity === "error" ? "Critical" : severity === "warn" ? "Warning" : "OK";
      return `<li class="service-status-row ${statusClass}">
        <strong>${escapeHtml(row.label)}</strong>
        <span class="muted">${escapeHtml(row.detail || "")}</span>
        <span class="service-sev">${sevLabel}</span>
      </li>`;
    })
    .join("");
  return `<div class="insight-ledger">
    <p class="muted">${escapeHtml(utilities.summary || "")}</p>
    <ul class="service-status-list">${serviceRows || "<li class='muted'>No utility rows.</li>"}</ul>
  </div>`;
}

function renderResolvedIssues(_resolved) {
  /* Resolved history intentionally omitted from civic-command UI. */
}

async function submitAnswerFeedback(rating, question, answer) {
  try {
    await fetchJson("/api/feedback/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating, question, answer }),
    });
    toast(rating === "up" ? "Thanks for the feedback" : "Feedback saved", "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
}

function answerFeedbackButton(rating, label) {
  const icon =
    rating === "up"
      ? `<svg class="answer-feedback-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M6.5 17V9.2L4.2 10.8 2.5 9l4.8-5.6L12 9l-1.7 1.6-2.3-1.8V17h-1.5z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
          <path d="M14.5 17h-2V8.5l1.8-1.4c.8-.6 2-.1 2 .9V17z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
        </svg>`
      : `<svg class="answer-feedback-icon" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M6.5 3v7.8l-2.3-1.6L2.5 11l4.8 5.6L12 11l-1.7-1.6-2.3 1.8V3h-1.5z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
          <path d="M14.5 3h-2v8.5l1.8 1.4c.8.6 2 .1 2-.9V3z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
        </svg>`;
  return `<button type="button" class="answer-feedback-btn answer-feedback-${rating}" data-rating="${rating}" title="${escapeAttr(label)}" aria-label="${escapeAttr(label)}">${icon}</button>`;
}

function attachAnswerFeedback(assistantEl, question, answer) {
  if (!assistantEl || assistantEl.querySelector(".answer-feedback")) return;
  const wrap = document.createElement("div");
  wrap.className = "answer-feedback";
  wrap.innerHTML = `${answerFeedbackButton("up", "Helpful")}${answerFeedbackButton("down", "Not helpful")}`;
  assistantEl.appendChild(wrap);
  wrap.querySelectorAll(".answer-feedback-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      void submitAnswerFeedback(btn.dataset.rating, question, answer);
      wrap.querySelectorAll(".answer-feedback-btn").forEach((other) => {
        other.disabled = true;
      });
      btn.classList.add("active");
    });
  });
}

async function clearAskUi() {
  if (activeAskAbort) {
    activeAskAbort.abort();
    activeAskAbort = null;
  }
  activeAskGeneration += 1;
  $("chat-log").innerHTML = "";
  localStorage.removeItem("citiesai-chat");
  try {
    await fetchJson("/api/chat/clear", { method: "POST", body: "{}" });
  } catch {
    /* ignore */
  }
  updateAskWelcome();
}

function onActiveCityChange(cityName) {
  const name = String(cityName || "").trim();
  if (!name || name === lastActiveCity) return;
  const prev = lastActiveCity;
  lastActiveCity = name;
  if (!prev) return;
  void clearAskUi();
  toast(`Now advising: ${name}`, "ok");
}


function renderDashboard(data) {
  const grid = $("metric-grid");
  if (!data.ok) {
    lastDashboardData = data;
    $("hero-title").textContent = "No city data yet";
    $("hero-sub").textContent = data.hint || data.error || "";
    $("freshness-pill").textContent = "No snapshot";
    $("freshness-pill").className = "pill missing";
    grid.innerHTML = `<div class="dashboard-error">
      <p><strong>${escapeHtml(data.error || "Dashboard unavailable")}</strong></p>
      <p class="muted">${escapeHtml(data.hint || "Load a city in CS2 with CS2 Data Export enabled.")}</p>
    </div>`;
    $("brief-technical").textContent = "";
    const metaEl = $("dashboard-meta");
    if (metaEl) metaEl.textContent = "";
    closeMetricModal();
    return;
  }

  lastDashboardData = data;
  const m = data.metrics;
  const meta = data.meta;
  const hist = data.historian || {};
  onActiveCityChange(m.city_name);
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

  const deltas = hist.deltas || {};
  const series = hist.series || {};
  grid.innerHTML = METRIC_DEFS.map((def) =>
    buildMetricCardHtml(def, m, deltas, series, { sparklineEmptyLabel: "No data in range" })
  ).join("");

  const metaEl = $("dashboard-meta");
  if (metaEl) {
    const count = hist.count ?? 0;
    const spanSec = historySpanSeconds(hist.timestamps);
    const metaParts = [`${count} snapshot${count === 1 ? "" : "s"} in range`];
    if (spanSec != null) metaParts.push(formatHistoryDuration(spanSec));
    metaEl.textContent = metaParts.join(" · ");
  }

  const forecastData = data.forecasts?.forecasts || {};
  grid.querySelectorAll(".sparkline").forEach((svg) => {
    const key = svg.dataset.key;
    const def = metricDefByKey(key);
    const values = def ? sparklineSeries(def, m, series) : series[key] || [];
    drawSparkline(svg, values, forecastData[key]?.projected);
  });
  bindMetricCards();
  renderAskContextRail();

  $("brief-technical").textContent = data.brief || "";

  const cardStrip = $("report-card-strip");
  const card = data.report_card;
  if (card && card.domains) {
    cardStrip.hidden = false;
    cardStrip.innerHTML =
      `<button type="button" class="report-overall" title="Open Insights"><span class="report-domain-label">Overall</span> ${renderGradeBadge(card.overall_grade)}</button>` +
      card.domains
        .map(
          (d) =>
            `<button type="button" class="report-domain" title="${escapeAttr(d.detail || "")}"><span class="report-domain-label">${escapeHtml(d.label)}</span> ${renderGradeBadge(d.grade)}</button>`
        )
        .join("");
    cardStrip.onclick = (e) => {
      if (e.target.closest("button")) switchView("insights");
    };
  } else {
    cardStrip.hidden = true;
    cardStrip.innerHTML = "";
  }

  if ($("metric-inspector") && !$("metric-inspector").hidden && metricModalReturnFocus) {
    openMetricModal(metricModalReturnFocus.dataset.metricKey, metricModalReturnFocus);
  }
}

function isIssueActionable(issue) {
  return Boolean(issue.ask_prompt || issue.action_view === "settings" || issue.id);
}

function issueInspectorBusy() {
  const input = $("issue-ask-input");
  return document.activeElement === input;
}

function selectIssue(issueId, options = {}) {
  selectedIssueId = issueId ? String(issueId) : null;
  document.querySelectorAll(".issue-item").forEach((el) => {
    el.classList.toggle("selected", el.dataset.issueId === selectedIssueId);
  });
  const issue = (lastIssues || []).find((row) => String(row.id) === selectedIssueId);
  renderIssueInspector(issue || null, options);
}

function softRefreshIssueInspector(issue) {
  if (!issue) return;
  const empty = $("issue-inspector-empty");
  const body = $("issue-inspector-body");
  if (!empty || !body || body.hidden) return;
  const severity = issue.severity || "warn";
  const sevEl = $("issue-inspector-severity");
  if (sevEl) {
    sevEl.textContent = severity === "error" ? "Critical" : severity === "info" ? "Info" : "Warning";
    sevEl.className = `severity-label severity-${escapeAttr(severity)}`;
  }
  const title = $("issue-inspector-title");
  if (title) title.textContent = issue.title || "Issue";
  const detail = $("issue-inspector-detail");
  if (detail) detail.textContent = issue.detail || "";
  const evidence = issue.evidence || [];
  const evidenceEl = $("issue-inspector-evidence");
  if (evidenceEl) {
    evidenceEl.innerHTML = evidence.length
      ? evidence.map((row) => `<li><strong>${escapeHtml(row.label || "Evidence")}:</strong> ${escapeHtml(row.value || "")}</li>`).join("")
      : `<li class="muted">No structured evidence.</li>`;
  }
  const causes = issue.likely_causes || [];
  const causesEl = $("issue-inspector-causes");
  if (causesEl) {
    causesEl.innerHTML = causes.length
      ? causes.map((row) => `<li>${escapeHtml(row)}</li>`).join("")
      : `<li class="muted">No likely causes listed.</li>`;
  }
  const actions = issue.actions || [];
  const actionsEl = $("issue-inspector-actions");
  if (actionsEl) {
    actionsEl.innerHTML = actions.length
      ? actions.map((row) => `<li>${escapeHtml(row)}</li>`).join("")
      : `<li class="muted">No recommended actions listed.</li>`;
  }
}

function renderIssueInspector(issue, options = {}) {
  const preserveComposer = Boolean(options.preserveComposer);
  const empty = $("issue-inspector-empty");
  const body = $("issue-inspector-body");
  if (!empty || !body) return;
  if (!issue) {
    empty.hidden = false;
    body.hidden = true;
    return;
  }
  empty.hidden = true;
  body.hidden = false;
  const severity = issue.severity || "warn";
  const sevEl = $("issue-inspector-severity");
  sevEl.textContent = severity === "error" ? "Critical" : severity === "info" ? "Info" : "Warning";
  sevEl.className = `severity-label severity-${escapeAttr(severity)}`;
  $("issue-inspector-title").textContent = issue.title || "Issue";
  $("issue-inspector-detail").textContent = issue.detail || "";
  const evidence = issue.evidence || [];
  $("issue-inspector-evidence").innerHTML = evidence.length
    ? evidence.map((row) => `<li><strong>${escapeHtml(row.label || "Evidence")}:</strong> ${escapeHtml(row.value || "")}</li>`).join("")
    : `<li class="muted">No structured evidence.</li>`;
  const causes = issue.likely_causes || [];
  $("issue-inspector-causes").innerHTML = causes.length
    ? causes.map((row) => `<li>${escapeHtml(row)}</li>`).join("")
    : `<li class="muted">No likely causes listed.</li>`;
  const actions = issue.actions || [];
  $("issue-inspector-actions").innerHTML = actions.length
    ? actions.map((row) => `<li>${escapeHtml(row)}</li>`).join("")
    : `<li class="muted">No recommended actions listed.</li>`;
  const settingsBtn = $("issue-open-settings");
  if (settingsBtn) {
    settingsBtn.hidden = issue.action_view !== "settings";
    settingsBtn.onclick = () => switchView("settings", { section: "paths" });
  }
  if (!preserveComposer) {
    const askInput = $("issue-ask-input");
    if (askInput && issue.ask_prompt) askInput.value = issue.ask_prompt;
  }
}

function handleIssueRowClick(btn) {
  const issueId = btn.dataset.issueId;
  if (issueId) {
    selectIssue(issueId);
    return;
  }
  if (btn.dataset.actionView === "settings") {
    switchView("settings", { section: "paths" });
  }
}

function renderIssueCard(issue) {
  const detailParts = [issue.detail, issue.hint].filter(Boolean);
  const detailText = detailParts.join(" — ");
  const severityClass = `severity-${escapeAttr(issue.severity)}`;
  const severityLabel = issue.severity === "error" ? "Critical" : issue.severity === "info" ? "Info" : "Warning";
  const bodyHtml = `<span class="issue-severity-text">${severityLabel}</span>
    <div class="issue-item-body">
      <strong class="issue-item-title">${escapeHtml(issue.title)}</strong>
      ${detailText ? `<p class="issue-item-detail">${escapeHtml(detailText)}</p>` : ""}
    </div>`;

  const ariaLabel = `Inspect ${issue.title}`;
  const actionAttr = issue.action_view ? ` data-action-view="${escapeAttr(issue.action_view)}"` : "";
  return `<li><button type="button" class="issue-item issue-item-btn ${severityClass}" data-issue-id="${escapeAttr(issue.id || "")}" aria-label="${escapeAttr(ariaLabel)}"${actionAttr}>
    ${bodyHtml}
    <span class="issue-item-chevron" aria-hidden="true">›</span>
  </button></li>`;
}

function renderIssueSection(title, issueList) {
  if (!issueList.length) return "";
  const critical = issueList.filter((issue) => issue.severity === "error").length;
  const warnings = issueList.filter((issue) => issue.severity === "warn").length;
  const summaryParts = [];
  if (critical) summaryParts.push(`${critical} critical`);
  if (warnings) summaryParts.push(`${warnings} warning${warnings === 1 ? "" : "s"}`);
  const summary = summaryParts.length
    ? `<span class="issues-panel-summary">${summaryParts.join(" · ")}</span>`
    : "";

  return `<section class="issues-panel">
    <header class="issues-panel-head">
      <div class="issues-panel-head-main">
        <h2 class="issues-panel-title">${title}</h2>
        ${summary}
      </div>
      <span class="issues-count-badge">${issueList.length}</span>
    </header>
    <ul class="issue-feed">${issueList.map((issue) => renderIssueCard(issue)).join("")}</ul>
  </section>`;
}

function renderIssues(issues, options = {}) {
  const list = $("issues-list");
  const preserveSelection = Boolean(options.preserveSelection);
  const scrollTop = list.scrollTop;
  const activeId = document.activeElement?.dataset?.issueId || null;
  if (!issues.length) {
    list.innerHTML = `<div class="issues-empty">
      <div>
        <p class="issues-empty-title">All clear</p>
        <p class="issues-empty-lead muted small">No setup or city issues right now.</p>
      </div>
    </div>`;
    issuesDisplayOrder = [];
    selectIssue(null);
    return;
  }

  // Keep list order stable while reading; re-rank only on fresh entry (empty order).
  const displayIssues =
    preserveSelection && issuesDisplayOrder.length
      ? stabilizeIssueOrder(issues, issuesDisplayOrder)
      : issues.slice();
  issuesDisplayOrder = displayIssues.map((issue) => String(issue.id));

  const cityIssues = displayIssues.filter((issue) => issue.kind === "city");
  const setupIssues = displayIssues.filter((issue) => issue.kind !== "city");
  const sections = [
    renderIssueSection("Your city", cityIssues),
    renderIssueSection("Setup &amp; app", setupIssues),
  ].filter(Boolean);

  list.innerHTML = sections.join("");
  list.querySelectorAll(".issue-item-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleIssueRowClick(btn));
  });
  list.scrollTop = scrollTop;

  let preferred = pendingIssueId || null;
  pendingIssueId = null;
  if (!preferred && selectedIssueId) {
    preferred = displayIssues.some((issue) => String(issue.id) === String(selectedIssueId))
      ? selectedIssueId
      : null;
  }
  // Hard sticky: never auto-advance to another issue while preserving selection.
  if (!preferred && !preserveSelection) {
    preferred = displayIssues[0]?.id ?? null;
  }

  const sameSelection =
    Boolean(preferred) && String(preferred) === String(selectedIssueId);
  if (sameSelection) {
    document.querySelectorAll(".issue-item").forEach((el) => {
      el.classList.toggle("selected", el.dataset.issueId === selectedIssueId);
    });
    const issue = displayIssues.find((row) => String(row.id) === String(selectedIssueId));
    softRefreshIssueInspector(issue || null);
  } else {
    const keepComposer =
      preserveSelection ||
      issueInspectorBusy() ||
      (Boolean(preferred) && String(preferred) === String(selectedIssueId));
    selectIssue(preferred, { preserveComposer: keepComposer && Boolean(preferred) });
  }
  if (activeId) {
    list.querySelector(`.issue-item-btn[data-issue-id="${CSS.escape(activeId)}"]`)?.focus({ preventScroll: true });
  }
}

function renderAskContextRail() {
  const root = $("ask-context-body");
  if (!root) return;
  const data = lastDashboardData;
  if (!data?.ok) {
    root.innerHTML = `<p class="muted small">Waiting for city data…</p>`;
    return;
  }
  const m = data.metrics || {};
  const card = data.report_card || {};
  const priorities = (data.priorities || []).slice(0, 3);
  root.innerHTML = `
    <div class="ask-context-item"><div class="ask-context-label">City</div><div class="ask-context-value">${escapeHtml(m.city_name || "Unknown")}</div></div>
    <div class="ask-context-item"><div class="ask-context-label">Overall</div><div class="ask-context-value">${escapeHtml(card.overall_grade || "n/a")} (${escapeHtml(String(card.overall_score ?? "n/a"))})</div></div>
    <div class="ask-context-item"><div class="ask-context-label">Population</div><div class="ask-context-value">${escapeHtml(formatMetricValue(m.population, metricDefByKey("population") || { key: "population" }))}</div></div>
    <div class="ask-context-item"><div class="ask-context-label">Treasury</div><div class="ask-context-value">${escapeHtml(formatMetricValue(m.treasury, metricDefByKey("treasury") || { key: "treasury", currency: true }))}</div></div>
    <div class="ask-context-item"><div class="ask-context-label">Top priorities</div><div>${priorities.length ? priorities.map((p) => `<div class="muted small">• ${escapeHtml(p.title || "")}</div>`).join("") : `<div class="muted small">None</div>`}</div></div>`;
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

async function refreshIssues({ toastOnError = false, preserveSelection = true } = {}) {
  try {
    const data = await fetchJson("/api/issues");
    applyIssuesData(data, { preserveSelection });
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
      applyIssuesData(data, { preserveSelection: true });
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
  const grid = $("metric-grid");
  if (grid && !lastDashboardData?.ok && !grid.querySelector(".metric-card")) {
    grid.innerHTML = `<div class="skeleton"></div>`.repeat(6);
  }
  try {
    const data = await fetchJson("/api/dashboard");
    pollErrorActive = false;
    renderDashboard(data);
    if (Array.isArray(data.issues)) {
      const prevFp = lastIssuesFingerprint;
      applyIssuesData(data, { preserveSelection: true });
      if (lastIssuesFingerprint !== prevFp) {
        await renderSuggestions();
      }
    } else {
      await refreshIssues();
      await renderSuggestions();
    }
    if ($("view-insights").classList.contains("active")) {
      void loadInsights({ silent: true });
    }
  } catch (err) {
    renderDashboard({
      ok: false,
      error: "Could not refresh dashboard",
      hint: String(err.message || err),
    });
    if (!pollErrorActive) toast(String(err.message || err), "err");
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
      applyIssuesData({ issues: status.issues }, { preserveSelection: true });
    }
    renderHealthStrip(status);

    if (promptOnboarding && !onboardingDismissed && !status.onboarding_complete) {
      showOnboarding();
    }
    return status;
  } catch (err) {
    renderHealthStrip(null);
    if (!pollErrorActive) toast(String(err.message || err), "err");
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
  scrollChatToBottom();
  updateAskWelcome();
  return div;
}

function loadChatHistory() {
  try {
    const raw = localStorage.getItem("citiesai-chat");
    if (!raw) return;
    JSON.parse(raw).forEach((entry) => {
      appendBubble("user", escapeHtml(entry.q || ""));
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

function askFetchSignal(timeoutMs = ASK_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), timeoutMs);
  controller.signal.addEventListener("abort", () => clearTimeout(timer), { once: true });
  return controller.signal;
}

function resetAskSubmit() {
  const submitBtn = $("ask-submit");
  const askForm = $("ask-form");
  submitBtn.disabled = false;
  submitBtn.textContent = ASK_SUBMIT_LABEL;
  askForm.setAttribute("aria-busy", "false");
}

function setAskBusy(active) {
  const submitBtn = $("ask-submit");
  if (!submitBtn) return;
  if (active) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Sending…";
    $("ask-form")?.setAttribute("aria-busy", "true");
  } else {
    resetAskSubmit();
  }
}

async function askStream(question) {
  if (activeAskAbort) {
    activeAskAbort.abort();
  }
  const generation = ++activeAskGeneration;
  const controller = new AbortController();
  activeAskAbort = controller;
  appendBubble("user", escapeHtml(question));
  const assistant = appendBubble(
    "assistant",
    `<div class="ask-answer">${typingIndicatorHtml()}</div><div class="ask-sources-wrap"></div>`
  );
  const answerEl = assistant.querySelector(".ask-answer");
  const sourcesEl = assistant.querySelector(".ask-sources-wrap");
  let answer = "";
  let streamFailed = false;
  let streamFinished = false;
  let bodyReader = null;
  setAskBusy(true);

  const finishStream = () => {
    if (streamFinished) return;
    streamFinished = true;
    if (activeAskAbort === controller) {
      activeAskAbort = null;
    }
    resetAskSubmit();
    scrollChatToBottom("smooth");
    if (bodyReader && typeof bodyReader.cancel === "function") {
      bodyReader.cancel().catch(() => {});
    }
  };

  const handlers = {
    onEvent(event, payload) {
      if (event === "status") {
        if (answerEl) answerEl.innerHTML = typingIndicatorHtml(payload.text || "");
        scrollChatToBottom();
      }
      if (event === "sources" && payload.sources && payload.sources.length && sourcesEl) {
        const items = payload.sources.slice(0, 8).map((s) => {
          const label = s.title || s.tool || s.source || "source";
          const href = safeHttpUrl(s.url);
          if (href) {
            return `<li><a href="${escapeAttr(href)}" target="_blank" rel="noopener">${escapeHtml(label)}</a></li>`;
          }
          return `<li>${escapeHtml(label)}</li>`;
        });
        sourcesEl.innerHTML = `<details class="ask-sources"><summary>Sources (${payload.sources.length})</summary><ul>${items.join("")}</ul></details>`;
        scrollChatToBottom();
      }
      if (event === "token") {
        answer += payload.text || "";
        if (answerEl) answerEl.innerHTML = renderMarkdown(answer);
        scrollChatToBottom();
      }
      if (event === "error") {
        streamFailed = true;
        answer = "";
        const hint = payload.hint ? `<p class="muted small">${escapeHtml(payload.hint)}</p>` : "";
        if (answerEl) {
          answerEl.innerHTML = `<span class="muted">${escapeHtml(payload.error || "Ask failed")}</span>${hint}`;
        }
        if (payload.mode === "bundle" && payload.bundle && answerEl) {
          answerEl.innerHTML += `<details><summary>Retrieval bundle</summary><pre class="mono-block">${escapeHtml(payload.bundle)}</pre></details>`;
        }
        scrollChatToBottom();
        finishStream();
      }
      if (event === "done") {
        if (payload.fallback_used && answerEl && answer.trim()) {
          answerEl.insertAdjacentHTML(
            "beforeend",
            `<p class="muted small ask-fallback-note">Answered after the research limit — retry or disable Deep research for a faster single-call answer.</p>`
          );
        }
        if (!answer.trim()) {
          streamFailed = true;
          if (answerEl) {
            answerEl.innerHTML =
              `<span class="muted">No answer returned. Check Settings for your API key or try again.</span>`;
          }
        } else if (generation === activeAskGeneration) {
          attachAnswerFeedback(assistant, question, answer);
          saveChatEntry(question, answer);
        }
        finishStream();
      }
    },
  };

  try {
    const response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CitiesAI-Token": sessionToken(),
      },
      body: JSON.stringify({
        question,
        use_llm: true,
        agentic: $("setup-agentic")?.checked !== false,
      }),
      signal: controller.signal,
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
    if (answerEl) {
      answerEl.innerHTML = `<span class="muted">${escapeHtml(message)}</span>`;
    }
    scrollChatToBottom();
  } finally {
    finishStream();
  }
}

function formatGameMinutes(minutes) {
  if (minutes == null || !Number.isFinite(Number(minutes))) return "n/a";
  const total = Math.round(Number(minutes));
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const rem = total % 60;
  return rem > 0 ? `${hours}h ${rem}m` : `${hours}h`;
}

function formatTransitModes(modes) {
  if (!modes || typeof modes !== "object") return "";
  return Object.entries(modes)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([mode, count]) => `${mode} ${count}`)
    .join(", ");
}

function renderTransitGroup(group) {
  const modesText = formatTransitModes(group.modes);
  const metaParts = [`${group.line_count} lines`];
  if (modesText) metaParts.push(modesText);
  if (group.total_waiting) metaParts.push(`${Number(group.total_waiting).toLocaleString()} waiting`);
  const lineRows = (group.lines || [])
    .map(
      (line) => `<tr>
        <td>${escapeHtml(line.line_name)}</td>
        <td>${escapeHtml(line.mode)}</td>
        <td>${Number(line.waiting || 0).toLocaleString()}</td>
        <td>${formatGameMinutes(line.round_trip_minutes)}</td>
      </tr>`
    )
    .join("");
  return `<li class="transit-group-card severity-${escapeAttr(group.severity || "info")}">
    <div class="finding-row transit-group-head">
      <div class="finding-copy">
        <strong>${escapeHtml(group.title)}</strong> — ${escapeHtml(group.diagnosis)}
        <p class="transit-group-meta muted small">${escapeHtml(metaParts.join(" · "))}</p>
        ${group.action ? `<p class="muted small">${escapeHtml(group.action)}</p>` : ""}
      </div>
    </div>
    <details class="transit-group-details">
      <summary>Show all ${group.line_count} lines</summary>
      <div class="insights-table-wrap">
        <table class="insights-table transit-group-lines">
          <thead><tr><th>Line</th><th>Mode</th><th>Waiting</th><th>Round trip</th></tr></thead>
          <tbody>${lineRows}</tbody>
        </table>
      </div>
    </details>
  </li>`;
}

async function loadInsights(options = {}) {
  const silent = Boolean(options.silent);
  const root = $("insights-content");
    if (!silent) {
    root.innerHTML = `<div class="skeleton"></div>`.repeat(3);
  }
  try {
    const data = await fetchJson("/api/insights");
    if (!data.ok) {
      root.innerHTML = `<p class="muted">${escapeHtml(data.error || "No insights yet")}</p>`;
      return;
    }
    const card = data.report_card;
    const transit = data.transit;
    const demandFactors = data.demand_factors;
    const utilities = data.utilities_services;
    const housing = data.housing;
    const accessGaps = data.access_gaps;
    const budget = data.budget;
    const gradeHistory = data.grade_history;

    const findingHtml = (items) =>
      (items || [])
        .map(
          (f) => `<li class="finding-row severity-${escapeAttr(f.severity || "info")}">
        <div class="finding-copy">
          <strong>${escapeHtml(f.title)}</strong> — ${escapeHtml(f.detail)}
          ${f.action ? `<p class="muted small">${escapeHtml(f.action)}</p>` : ""}
        </div>
      </li>`
        )
        .join("");

    const sectionAsk = (prompt, label = "Advisor") =>
      prompt
        ? `<button type="button" class="btn ghost btn-sm insight-ask" data-prompt="${escapeAttr(prompt)}">${escapeHtml(label)}</button>`
        : "";

    const domainHtml = (card.domains || [])
      .map((d) => {
        const delta = d.grade_delta ? `<span class="grade-delta muted small">${escapeHtml(d.grade_delta)}</span>` : "";
        return `<div class="insight-domain ${gradeClass(d.grade)}">
        <div class="insight-domain-head">
          <div class="insight-domain-title">
            <strong>${escapeHtml(d.label)}</strong>
            ${delta}
          </div>
          ${renderGradeBadge(d.grade)}
        </div>
        <p class="insight-domain-detail muted small">${escapeHtml(d.detail || "")}</p>
      </div>`;
      })
      .join("");

    const transitGroups = (transit.problem_groups || []).map((group) => renderTransitGroup(group)).join("");
    const sections = [
      {
        id: "report-card",
        label: "Report card",
        html: `<section id="insight-report-card" class="insight-section">
          <div class="insight-section-head report-card-head">
            <div class="report-card-hero">
              <h2>Report card</h2>
              <div class="report-grade-cluster">
                ${renderGradeBadge(card.overall_grade, { size: "lg" })}
                <span class="report-score">${escapeHtml(String(card.overall_score ?? "—"))}<span class="report-score-den">/100</span></span>
              </div>
            </div>
            ${sectionAsk(card.domains?.[0]?.ask_prompt, "Advisor")}
          </div>
          <div class="insights-domains">${domainHtml}</div>
          <div class="grade-history-wrap">
            <p class="muted small">Overall score trend</p>
            <svg id="grade-history-chart" class="grade-history-chart" role="img" aria-label="Overall score trend"></svg>
          </div>
        </section>`,
      },
      {
        id: "economy",
        label: "Economy",
        html: `<section id="insight-economy" class="insight-section">
          <div class="insight-section-head">
            <h2>Economy &amp; budget</h2>
            ${sectionAsk(budget?.ask_prompt || "What should I fix in my budget?", "Advisor")}
          </div>
          <p class="muted">${escapeHtml(budget?.summary || "Budget analysis unavailable.")}</p>
          <ul class="finding-list">${findingHtml(budget?.findings) || "<li class='muted'>No budget findings.</li>"}</ul>
        </section>`,
      },
      {
        id: "housing",
        label: "Housing",
        html: `<section id="insight-housing" class="insight-section">
          <div class="insight-section-head">
            <h2>Housing &amp; labor</h2>
            ${sectionAsk(housing?.ask_prompt || "How can I improve housing and jobs?", "Advisor")}
          </div>
          <ul class="finding-list">${findingHtml(housing?.findings) || "<li class='muted'>Balanced</li>"}</ul>
          ${renderDemandFactorsCard(demandFactors)}
        </section>`,
      },
      {
        id: "services",
        label: "Services",
        html: `<section id="insight-services" class="insight-section">
          <div class="insight-section-head">
            <h2>Utilities &amp; services</h2>
            ${sectionAsk(utilities?.ask_prompt || "How do I fix utility pressure?", "Advisor")}
          </div>
          ${renderUtilitiesCard(utilities)}
        </section>`,
      },
      {
        id: "transit",
        label: "Transit",
        html: `<section id="insight-transit" class="insight-section">
          <div class="insight-section-head">
            <h2>Transit</h2>
            ${sectionAsk(transit?.ask_prompt || "Should I add transit lines?", "Advisor")}
          </div>
          <p class="muted">${escapeHtml(transit?.summary || "")}</p>
          ${transitGroups ? `<ul class="finding-list transit-group-list">${transitGroups}</ul>` : `<p class="muted">All transit lines look healthy.</p>`}
          ${renderAccessGapsCard(accessGaps)}
        </section>`,
      },
    ];

    root.innerHTML = sections.map((section) => section.html).join("");
    root.querySelectorAll(".insight-ask").forEach((btn) => {
      btn.addEventListener("click", () => askFromPrompt(btn.dataset.prompt));
    });
    renderGradeHistoryChart($("grade-history-chart"), gradeHistory);
  } catch (err) {
    root.innerHTML = `<p class="muted">${escapeHtml(String(err.message || err))}</p>`;
  }
}

async function initWatchToggle() {
  const checkbox = $("watch-enabled");
  if (!checkbox || watchToggleTouched) return;
  try {
    const data = await fetchJson("/api/watch");
    checkbox.checked = Boolean(data.enabled);
  } catch { /* ignore */ }
}

function currentLlmForm() {
  const provider = $("setup-provider")?.value || "mistral";
  const model = ($("setup-model")?.value || "").trim();
  const preset = llmPresets[provider] || {};
  const envName = preset.api_key_env || lastApiKeyEnv;
  return { provider, model, envName };
}

async function persistLlmForm() {
  const { provider, model, envName } = currentLlmForm();
  await fetchJson("/api/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      llm_provider: provider,
      llm_model: model || undefined,
    }),
  });
  lastApiKeyEnv = envName;
}

function updateKeyHint(provider) {
  const hint = $("key-hint");
  if (!hint) return;
  if (provider === "local") {
    hint.textContent = "Local Ollama/LM Studio: use any placeholder or leave empty if the server needs no key.";
  } else if (provider === "openai") {
    hint.textContent = "Set OPENAI_API_KEY in Settings or your environment.";
  } else {
    hint.textContent = "Required for Mistral. Get a free key at console.mistral.ai";
  }
}

function renderApiKeyState({ configured, suffix, provider, verified = false, replacing = false }) {
  const savedBlock = $("api-key-saved");
  const editBlock = $("api-key-edit");
  const savedTitle = $("api-key-saved-title");
  const savedSuffix = $("api-key-saved-suffix");
  const replaceBtn = $("replace-key");
  const removeBtn = $("remove-key");
  const cancelBtn = $("cancel-replace-key");
  const saveBtn = $("save-key");
  const keyLine = $("key-status");
  if (!savedBlock || !editBlock) return;

  const isLocal = provider === "local";
  const showConfigured = configured && !replacing;

  savedBlock.hidden = !showConfigured;
  editBlock.hidden = showConfigured;
  if (replaceBtn) replaceBtn.hidden = !showConfigured || isLocal;
  if (removeBtn) removeBtn.hidden = !showConfigured;
  if (cancelBtn) cancelBtn.hidden = !replacing;
  if (saveBtn) saveBtn.hidden = showConfigured;

  if (showConfigured) {
    savedTitle.textContent = isLocal
      ? "Local provider — no cloud key required"
      : "Key saved on this PC";
    if (savedSuffix && suffix && !isLocal) {
      savedSuffix.hidden = false;
      savedSuffix.innerHTML = `Ends with <span class="api-key-suffix-mono">···${escapeHtml(suffix)}</span>`;
    } else if (savedSuffix) {
      savedSuffix.hidden = true;
      savedSuffix.textContent = "";
    }
  } else if (replacing) {
    $("api-key")?.focus();
  }

  if (keyLine) {
    if (verified) {
      keyLine.textContent = "API key verified";
      keyLine.className = "key-status-pill ok";
    } else if (configured) {
      keyLine.textContent = "API key configured";
      keyLine.className = "key-status-pill ok";
    } else {
      keyLine.textContent = "No API key saved";
      keyLine.className = "key-status-pill muted";
    }
  }
}

function renderUpdateBanner(info) {
  const value = $("update-status-text");
  const settingsBtn = $("nav-settings");
  if (!value) return;
  settingsBtn?.classList.remove("has-update");
  if (!info) {
    value.textContent = "Updates: checking…";
    return;
  }
  if (info.update_available) {
    value.textContent = `Update available: v${info.latest_version || ""}`;
    settingsBtn?.classList.add("has-update");
    return;
  }
  value.textContent = info.current_version ? `Updates: v${info.current_version}` : "Updates: up to date";
}

function formatUpdateCheckedAt(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function renderUpdateSettings(info) {
  const current = $("update-current-version");
  const status = $("update-status");
  const installBtn = $("update-download-install");
  const releaseLink = $("update-release-notes");
  const startupToggle = $("update-check-startup");
  if (!current || !status || !installBtn || !releaseLink || !startupToggle) return;

  current.textContent = info?.current_version ? `v${info.current_version}` : "…";
  startupToggle.checked = info?.check_on_startup !== false;
  if (info?.release_url) {
    releaseLink.href = info.release_url;
  }

  if (!info) {
    status.textContent = "Checking…";
    status.className = "muted small settings-mod-hint";
    installBtn.hidden = true;
    return;
  }

  let statusText = "";
  if (info.status_message) {
    statusText = info.status_message;
    status.className =
      info.warning || info.error
        ? "muted small settings-mod-hint update-status-warn"
        : "muted small settings-mod-hint";
  } else if (info.error) {
    status.textContent = info.error;
    status.className = "muted small settings-mod-hint update-status-warn";
    installBtn.hidden = true;
    return;
  } else if (info.update_available) {
    statusText = `Update available${info.latest_version ? ` · v${info.latest_version}` : ""}`;
    status.className = "muted small settings-mod-hint";
  } else {
    statusText = "Up to date";
    status.className = "muted small settings-mod-hint";
  }

  const checkedAt = formatUpdateCheckedAt(info.checked_at);
  status.textContent = checkedAt ? `${statusText} · Checked ${checkedAt}` : statusText;

  if (info.update_available) {
    installBtn.hidden = false;
    installBtn.textContent = info.can_install ? "Download & install" : "Open release page";
    installBtn.dataset.mode = info.can_install ? "install" : "open";
  } else {
    installBtn.hidden = true;
  }
}

async function refreshUpdateUi({ force = false } = {}) {
  if (updateCheckInFlight) {
    if (!force) return lastUpdateInfo;
    while (updateCheckInFlight) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  updateCheckInFlight = true;
  if (force && $("view-settings")?.classList.contains("active")) {
    renderUpdateSettings(null);
  }
  try {
    const query = force ? "?force=1" : "";
    const info = await fetchJson(`/api/update/check${query}`);
    lastUpdateInfo = info;
    renderUpdateBanner(info);
    if (force || $("view-settings")?.classList.contains("active")) {
      renderUpdateSettings(info);
    renderUpdateBanner(info);
    }
    return info;
  } catch (err) {
    const fallback = {
      current_version: lastUpdateInfo?.current_version,
      check_on_startup: lastUpdateInfo?.check_on_startup !== false,
      error: String(err.message || err),
    };
    if (force || $("view-settings")?.classList.contains("active")) {
      renderUpdateSettings(fallback);
    }
    if (force) toast(String(err.message || err), "err");
    return null;
  } finally {
    updateCheckInFlight = false;
  }
}

async function runUpdateCheckNow() {
  const btn = $("update-check-now");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Checking…";
  }
  try {
    await refreshUpdateUi({ force: true });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Check for updates";
    }
  }
}

async function dismissUpdate(version) {
  if (!version) return;
  try {
    await fetchJson("/api/update/dismiss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version }),
    });
    await refreshUpdateUi({ force: true });
  } catch (err) {
    toast(String(err.message || err), "err");
  }
}

async function runUpdateInstall() {
  const info = lastUpdateInfo;
  if (!info?.update_available) {
    toast("No update available", "err");
    return;
  }
  if (!info.can_install) {
    if (info.release_url) window.open(info.release_url, "_blank", "noopener");
    return;
  }
  const installBtn = $("update-download-install");
  const bannerBtn = $("update-banner-install");
  [installBtn, bannerBtn].forEach((btn) => {
    if (btn) btn.disabled = true;
  });
  try {
    toast("Downloading update…", "ok");
    const downloaded = await fetchJson("/api/update/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: false }),
    });
    const installed = await fetchJson("/api/update/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: downloaded.path }),
    });
    if (installed.quitting) {
      toast("Installing update… CitiesAI will restart.", "ok");
      setTimeout(() => window.close(), 1200);
    }
  } catch (err) {
    toast(String(err.message || err), "err");
  } finally {
    [installBtn, bannerBtn].forEach((btn) => {
      if (btn) btn.disabled = false;
    });
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
    const agenticToggle = $("setup-agentic");
    if (agenticToggle) {
      agenticToggle.checked = data.llm_agentic_enabled !== false;
    }
    try {
      const presets = await fetchJson("/api/settings/llm-presets");
      llmPresets = presets.presets || {};
      const providerSelect = $("setup-provider");
      if (providerSelect && llmPresets) {
        providerSelect.value = data.llm_provider || "mistral";
        updateKeyHint(providerSelect.value);
        providerSelect.onchange = () => {
          const preset = llmPresets[providerSelect.value];
          if (preset) {
            $("setup-model").value = preset.model;
            lastApiKeyEnv = preset.api_key_env;
          }
          lastKeyUiState.provider = providerSelect.value;
          updateKeyHint(providerSelect.value);
          renderApiKeyState({ ...lastKeyUiState, replacing: apiKeyReplacing });
        };
      }
    } catch { /* ignore */ }
    const modBadge = $("mod-status");
    const installBtn = $("install-mod");
    if (modBadge) {
      modBadge.textContent = data.mod_installed ? "Installed" : "Not installed";
      modBadge.className = `mod-status-pill ${data.mod_installed ? "ok" : "missing"}`;
    }
    if (installBtn) {
      installBtn.textContent = data.mod_installed ? "Reinstall" : "Install mod";
      installBtn.classList.toggle("primary", !data.mod_installed);
      installBtn.classList.toggle("secondary", Boolean(data.mod_installed));
    }
    lastApiKeyEnv = data.llm_api_key_env || "MISTRAL_API_KEY";
    lastKeyUiState = {
      configured: Boolean(data.llm_configured),
      suffix: data.api_key_suffix || null,
      provider: data.llm_provider || "mistral",
    };
    apiKeyReplacing = false;
    renderApiKeyState({ ...lastKeyUiState, replacing: false });
    if (lastUpdateInfo) {
      renderUpdateSettings(lastUpdateInfo);
    }
    renderComayorToggle(Boolean(data.comayor_enabled !== false));
    applyAdvisorStyleToForm(data.advisor_style || "civic");
    updateAskHelper();
    const watch = $("watch-enabled");
    if (watch && !watchToggleTouched) {
      watch.checked = Boolean(data.watch_enabled);
    }
  } catch (err) {
    toast(String(err.message || err), "err");
  }
}

function renderComayorToggle(enabled) {
  const btn = $("toggle-comayor");
  if (!btn) return;
  btn.dataset.enabled = enabled ? "1" : "0";
  btn.textContent = enabled ? "Disable Co-Mayor" : "Enable Co-Mayor";
  btn.classList.toggle("primary", !enabled);
  btn.classList.toggle("secondary", enabled);
}

$("toggle-comayor")?.addEventListener("click", async () => {
  const btn = $("toggle-comayor");
  if (!btn) return;
  const currentlyEnabled = btn.dataset.enabled !== "0";
  const next = !currentlyEnabled;
  btn.disabled = true;
  try {
    let result;
    if (window.pywebview?.api?.set_comayor_enabled) {
      result = await window.pywebview.api.set_comayor_enabled(next);
    } else {
      result = await fetchJson("/api/comayor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
    }
    if (!result?.ok) {
      toast(result?.error || "Could not update Co-Mayor", "err");
      return;
    }
    renderComayorToggle(next);
    if (next && result.error) {
      toast(result.error, "err");
    } else {
      toast(next ? "Co-Mayor enabled" : "Co-Mayor disabled", "ok");
    }
  } catch (err) {
    toast(String(err.message || err), "err");
  } finally {
    btn.disabled = false;
  }
});

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
        el.textContent = "Snapshot received!";
        clearInterval(exportPollTimer);
      } else if (dash.ok) {
        el.textContent = "Snapshot found but stale. Load your city in CS2.";
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
  bindModalFocusTrap($("onboarding"), hideOnboarding);
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
  const progress = document.querySelector(".onboarding-progress");
  if (progress) {
    progress.setAttribute("aria-valuenow", String(onboardingStep + 1));
    progress.setAttribute("aria-valuemax", String(total));
  }
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
    const style =
      document.querySelector('input[name="onboard-advisor-style"]:checked')?.value ||
      advisorStyle ||
      "civic";
    advisorStyle = style;
    await fetchJson("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ advisor_style: style }),
    });
    toast("Setup complete", "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
  loadDashboard();
  await loadStatus();
}

document.querySelectorAll(".nav-item[data-view], .nav-icon-btn[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});
$("open-diagnostics")?.addEventListener("click", () => openDiagnosticsModal($("open-diagnostics")));
$("settings-open-diagnostics")?.addEventListener("click", () =>
  openDiagnosticsModal($("settings-open-diagnostics"))
);
document.querySelectorAll(".settings-index-item").forEach((btn) => {
  btn.addEventListener("click", () => openSettingsSection(btn.dataset.settingsSection));
});
$("save-advisor-style")?.addEventListener("click", async () => {
  try {
    const style = selectedAdvisorStyleFromForm();
    await fetchJson("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ advisor_style: style }),
    });
    advisorStyle = style;
    updateAskHelper();
    toast("Advisor style saved", "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});
$("issue-ask-form")?.addEventListener("submit", (e) => {
  e.preventDefault();
  askFromPrompt($("issue-ask-input")?.value || "");
});

document.querySelectorAll("[data-view-jump]").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.viewJump));
});


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
  void clearAskUi();
});

$("export-report")?.addEventListener("click", async () => {
  try {
    const data = await fetchJson("/api/report/export", { method: "POST", body: "{}" });
    toast(`Report saved: ${data.path}`, "ok");
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("watch-enabled")?.addEventListener("change", async (e) => {
  watchToggleTouched = true;
  try {
    await fetchJson("/api/watch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: e.target.checked }),
    });
  } catch (err) {
    e.target.checked = !e.target.checked;
    toast(String(err.message || err), "err");
  }
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
        llm_provider: $("setup-provider")?.value || "mistral",
        llm_agentic_enabled: $("setup-agentic")?.checked !== false,
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

$("update-check-now")?.addEventListener("click", () => {
  void runUpdateCheckNow();
});

$("update-download-install")?.addEventListener("click", () => {
  const btn = $("update-download-install");
  if (btn?.dataset.mode === "open" && lastUpdateInfo?.release_url) {
    window.open(lastUpdateInfo.release_url, "_blank", "noopener");
    return;
  }
  void runUpdateInstall();
});

$("update-check-startup")?.addEventListener("change", async (e) => {
  try {
    await fetchJson("/api/update/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ check_on_startup: e.target.checked }),
    });
    if (lastUpdateInfo) {
      lastUpdateInfo.check_on_startup = e.target.checked;
    }
    toast(e.target.checked ? "Startup update checks enabled" : "Startup update checks disabled", "ok");
  } catch (err) {
    e.target.checked = !e.target.checked;
    toast(String(err.message || err), "err");
  }
});

$("install-mod").addEventListener("click", async () => {
  try {
    const data = await fetchJson("/api/install-mod", { method: "POST", body: "{}" });
    if (!data.ok) throw new Error(data.error);
    toast(`Mod installed to ${data.installed_to}`, "ok");
    const modBadge = $("mod-status");
    const installBtn = $("install-mod");
    if (modBadge) {
      modBadge.textContent = "Installed";
      modBadge.className = "mod-status-pill ok";
    }
    if (installBtn) {
      installBtn.textContent = "Reinstall";
      installBtn.classList.remove("primary");
      installBtn.classList.add("secondary");
    }
    loadStatus();
    refreshIssues();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("replace-key").addEventListener("click", () => {
  apiKeyReplacing = true;
  $("api-key").value = "";
  renderApiKeyState({ ...lastKeyUiState, replacing: true });
});

$("cancel-replace-key").addEventListener("click", () => {
  apiKeyReplacing = false;
  $("api-key").value = "";
  renderApiKeyState({ ...lastKeyUiState, replacing: false });
});

$("remove-key").addEventListener("click", async () => {
  if (!confirm("Remove the saved API key from this PC?")) return;
  try {
    await fetchJson("/api/settings/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: "", env_name: lastApiKeyEnv }),
    });
    apiKeyReplacing = false;
    toast("API key removed", "ok");
    await loadSettings();
    await loadStatus();
    llmConfigured = false;
    updateAskHelper();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("save-key").addEventListener("click", async () => {
  try {
    await persistLlmForm();
    const { envName } = currentLlmForm();
    await fetchJson("/api/settings/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: $("api-key").value.trim(),
        env_name: envName,
      }),
    });
    toast("API key saved locally", "ok");
    apiKeyReplacing = false;
    $("api-key").value = "";
    await loadSettings();
    await loadStatus();
    llmConfigured = true;
    updateAskHelper();
  } catch (err) {
    toast(String(err.message || err), "err");
  }
});

$("test-key").addEventListener("click", async () => {
  try {
    await persistLlmForm();
    const { envName } = currentLlmForm();
    const key = $("api-key").value.trim();
    if (key) {
      await fetchJson("/api/settings/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: key, env_name: envName }),
      });
    }
    const data = await fetchJson("/api/settings/key/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!data.ok) throw new Error(data.error);
    toast(`Key OK (${data.model})`, "ok");
    renderApiKeyState({ ...lastKeyUiState, verified: true, replacing: apiKeyReplacing });
    llmConfigured = true;
    updateAskHelper();
    await loadSettings();
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
  if (onboardingStep === 1) {
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
  const metricModal = $("metric-modal") || $("metric-inspector");
  if (metricModal && !metricModal.hasAttribute("hidden")) {
    closeMetricModal();
    return;
  }
  const diagnosticsModal = $("diagnostics-modal");
  if (diagnosticsModal && !diagnosticsModal.hasAttribute("hidden")) {
    closeDiagnosticsModal();
    return;
  }
  const onboarding = $("onboarding");
  if (onboarding && !onboarding.hasAttribute("hidden")) {
    hideOnboarding();
  }
});

$("metric-modal-close")?.addEventListener("click", closeMetricModal);
$("metric-modal")?.querySelectorAll("[data-close-metric-modal]").forEach((el) => {
  el.addEventListener("click", closeMetricModal);
});
$("metric-inspector")?.querySelectorAll("[data-close-metric-modal]").forEach((el) => {
  el.addEventListener("click", closeMetricModal);
});

$("diagnostics-modal-close").addEventListener("click", closeDiagnosticsModal);
$("diagnostics-modal").querySelectorAll("[data-close-diagnostics-modal]").forEach((el) => {
  el.addEventListener("click", closeDiagnosticsModal);
});

async function init() {
  loadChatHistory();
  updateAskHelper();
  setFeedbackCategory($("feedback-category").value);
  await loadStatus({ promptOnboarding: true });
  void refreshUpdateUi({ force: false });
  await loadDashboard();
  void initWatchToggle();
  dashboardTimer = setInterval(async () => {
    await loadDashboard();
    statusPollCounter += 1;
    if (statusPollCounter >= STATUS_POLL_INTERVALS) {
      statusPollCounter = 0;
      await loadStatus();
    }
  }, POLL_MS);
}

init();
