const $ = (selector) => document.querySelector(selector);
const apiRoot = "/api/v1/risk-evals";
let currentReport = null;
let currentApiKey = "";

const pipelineSteps = [
  "接收並驗證加倉請求",
  "載入 NAV、持倉與市場快照",
  "計算 YTD 收益、回撤與 VaR",
  "執行合同、監管及內控規則",
  "生成結構化風控評估報告",
  "AI Risk Officer 第一級覆核",
  "AI MIC 第二級覆核",
  "生成雙簽、工件與審計證據",
];

function formatMoney(value) {
  return new Intl.NumberFormat("zh-HK", { style: "currency", currency: "HKD", maximumFractionDigits: 0 }).format(value ?? 0);
}

function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function toast(message, type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 3500);
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) throw new Error("health check failed");
    const health = await response.json();
    $("#health").classList.add("online");
    $("#health").lastChild.textContent = "服務運行中";
    $("#workflowMode").textContent = health.workflow_mode;
    $("#aiProvider").textContent = health.ai_provider;
  } catch {
    $("#health").lastChild.textContent = "服務不可用";
  }
}

function initPipeline() {
  $("#pipeline").innerHTML = pipelineSteps.map((step, index) =>
    `<div class="pipe-step" data-step="${index}"><i>${String(index + 1).padStart(2, "0")}</i><span>${step}</span></div>`
  ).join("");
}

function startPipeline() {
  $("#emptyState").classList.add("hidden");
  $("#resultState").classList.add("hidden");
  $("#loadingState").classList.remove("hidden");
  const nodes = [...document.querySelectorAll(".pipe-step")];
  nodes.forEach((node) => node.className = "pipe-step");
  let index = 0;
  const tick = () => {
    nodes.forEach((node, nodeIndex) => {
      node.classList.toggle("done", nodeIndex < index);
      node.classList.toggle("active", nodeIndex === index);
      if (nodeIndex < index) node.querySelector("i").textContent = "✓";
      else node.querySelector("i").textContent = String(nodeIndex + 1).padStart(2, "0");
    });
    $("#loadingMessage").textContent = pipelineSteps[Math.min(index, pipelineSteps.length - 1)];
    $("#progressBar").style.width = `${Math.min(100, ((index + 1) / pipelineSteps.length) * 100)}%`;
    index += 1;
  };
  tick();
  return setInterval(() => {
    if (index < pipelineSteps.length) tick();
  }, 360);
}

function finishPipeline(timer) {
  clearInterval(timer);
  document.querySelectorAll(".pipe-step").forEach((node) => {
    node.className = "pipe-step done";
    node.querySelector("i").textContent = "✓";
  });
  $("#progressBar").style.width = "100%";
}

function renderMetrics(calculation) {
  const metrics = calculation.metrics;
  const portfolio = calculation.portfolio;
  const items = [
    ["基金資產淨值", formatMoney(metrics.nav_hkd), "演示估值快照"],
    ["請求加倉金額", formatMoney(currentReport.proposed_trade.amount_hkd), "PRE_TRADE"],
    ["今年以來收益", formatPercent(metrics.ytd_return), "YTD RETURN"],
    ["年內最大回撤", formatPercent(metrics.max_drawdown), "MAX DRAWDOWN"],
    ["1 日 95% VaR", formatPercent(metrics.var_95_1d), "PARAMETRIC VAR"],
    ["年化波動率", formatPercent(metrics.annualized_volatility), "252 TRADING DAYS"],
    ["加倉後集中度", formatPercent(metrics.single_stock_concentration), "POST-TRADE"],
    ["加倉後流動性", formatPercent(metrics.liquidity_ratio), `可用 ${formatMoney(portfolio.available_liquidity_after_hkd)}`],
  ];
  $("#metricsGrid").innerHTML = items.map(([label, value, note]) =>
    `<article class="metric"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`
  ).join("");
}

function renderChart(history) {
  const svg = $("#navChart");
  const width = 900;
  const height = 260;
  const padding = { left: 52, right: 20, top: 24, bottom: 35 };
  const values = history.map((point) => point.nav);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const x = (index) => padding.left + index / Math.max(1, history.length - 1) * (width - padding.left - padding.right);
  const y = (value) => padding.top + (max - value) / range * (height - padding.top - padding.bottom);
  const points = history.map((point, index) => `${x(index).toFixed(1)},${y(point.nav).toFixed(1)}`).join(" ");
  const area = `${padding.left},${height - padding.bottom} ${points} ${width - padding.right},${height - padding.bottom}`;
  const grid = [0, 0.5, 1].map((ratio) => {
    const gy = padding.top + ratio * (height - padding.top - padding.bottom);
    const label = max - ratio * range;
    return `<line class="chart-grid" x1="${padding.left}" y1="${gy}" x2="${width - padding.right}" y2="${gy}"/><text class="chart-label" x="4" y="${gy + 4}">${label.toFixed(2)}</text>`;
  }).join("");
  svg.innerHTML = `<defs><linearGradient id="areaGradient" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#0d7b5f" stop-opacity=".24"/><stop offset="1" stop-color="#0d7b5f" stop-opacity="0"/></linearGradient></defs>${grid}<polygon class="chart-area" points="${area}"/><polyline class="chart-line" points="${points}"/><text class="chart-label" x="${padding.left}" y="250">${history[0].date}</text><text class="chart-label" x="${width - 90}" y="250">${history.at(-1).date}</text>`;
  $("#chartSubtitle").textContent = `${history.length} 個交易日 · ${history[0].date} 至 ${history.at(-1).date}`;
}

function renderRules(report) {
  $("#ruleVersion").textContent = `規則版本 ${report.rule_version} · ${report.rule_violations.length} 項命中`;
  if (!report.rule_violations.length) {
    $("#violations").innerHTML = `<div class="no-violations">✓ 未命中任何黃燈或紅燈規則，符合自動批准條件。</div>`;
    return;
  }
  $("#violations").innerHTML = report.rule_violations.map((item) =>
    `<div class="rule-item ${item.severity.toLowerCase()}"><span class="rule-level">${item.severity}</span><div><strong>${escapeHtml(item.rule_name)}</strong><p>${escapeHtml(item.description)}</p></div><code>${escapeHtml(item.action)}</code></div>`
  ).join("");
}

function renderReview(review, index) {
  const reject = review.recommendation === "REJECT";
  return `<div class="review-head"><span class="review-index">0${index + 4} · ${index === 0 ? "FIRST REVIEW" : "FINAL REVIEW"}</span><span class="review-result ${reject ? "reject" : ""}">${review.recommendation}</span></div><h3>${index === 0 ? "AI Risk Officer" : "AI MIC"}</h3><div class="provider">${escapeHtml(review.reviewer_id)} · ${escapeHtml(review.provider)}</div><p class="review-reason">${escapeHtml(review.reasoning)}</p><div class="confidence"><span>審核信心度</span><strong>${(review.confidence * 100).toFixed(0)}%</strong></div><div class="confidence-track"><span style="width:${review.confidence * 100}%"></span></div>`;
}

function renderReport(report) {
  $("#reportSummary").innerHTML = `<strong>${escapeHtml(report.fund_name)}</strong> 於 ${escapeHtml(report.market_snapshot.evaluation_date)} 提交 ${formatMoney(report.proposed_trade.amount_hkd)} 加倉請求。${escapeHtml(report.auto_commentary)}<br><strong>最終結論：</strong>${escapeHtml(report.final_commentary)}`;
  $("#evidenceGrid").innerHTML = [
    ["內容哈希", `${report.content_hash.slice(0, 12)}…`],
    ["第一級簽章", report.first_sign ? "已簽署" : "待簽署"],
    ["第二級簽章", report.second_sign ? "已簽署" : "待簽署"],
    ["報告工件", `${report.artifacts.length} 個`],
  ].map(([label, value]) => `<div class="evidence"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderResult(payload) {
  const { calculation, report } = payload;
  currentReport = report;
  const severity = report.severity.toLowerCase();
  $("#decisionCard").className = `decision-card card ${severity}`;
  $("#severityBadge").textContent = report.severity;
  $("#decisionText").textContent = report.execution_decision;
  $("#finalCommentary").textContent = report.final_commentary;
  $("#reportId").textContent = report.report_id;
  $("#reportStatus").textContent = report.status;
  renderMetrics(calculation);
  renderChart(calculation.nav_history);
  renderRules(report);
  $("#firstReview").innerHTML = renderReview(report.ai_reviews[0], 0);
  $("#secondReview").innerHTML = renderReview(report.ai_reviews[1], 1);
  renderReport(report);
  $("#verifyResult").classList.add("hidden");
  $("#loadingState").classList.add("hidden");
  $("#resultState").classList.remove("hidden");
  window.scrollTo({ top: document.querySelector(".workspace").offsetTop - 92, behavior: "smooth" });
}

async function parseError(response) {
  try {
    const payload = await response.json();
    return typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
  } catch {
    return `HTTP ${response.status}`;
  }
}

$("#assessmentForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  currentApiKey = $("#apiKey").value.trim();
  const timer = startPipeline();
  const button = $("#submitButton");
  button.disabled = true;
  try {
    const response = await fetch(`${apiRoot}/demo/assess`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": currentApiKey },
      body: JSON.stringify({
        fund_name: $("#fundName").value.trim(),
        evaluation_date: $("#evaluationDate").value,
        add_amount_hkd: Number($("#addAmount").value),
      }),
    });
    if (!response.ok) throw new Error(await parseError(response));
    const payload = await response.json();
    finishPipeline(timer);
    await new Promise((resolve) => setTimeout(resolve, 350));
    renderResult(payload);
    toast("智能風控評估已完成");
  } catch (error) {
    clearInterval(timer);
    $("#loadingState").classList.add("hidden");
    $("#emptyState").classList.remove("hidden");
    toast(`評估失敗：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

$("#assessmentForm").addEventListener("invalid", (event) => {
  toast(`請檢查輸入：${event.target.validationMessage}`, "error");
}, true);

$("#verifyButton").addEventListener("click", async () => {
  if (!currentReport) return;
  try {
    const response = await fetch(`${apiRoot}/reports/${currentReport.report_id}/verify`, { headers: { "X-API-Key": currentApiKey } });
    if (!response.ok) throw new Error(await parseError(response));
    const payload = await response.json();
    $("#verifyResult").textContent = JSON.stringify(payload, null, 2);
    $("#verifyResult").classList.remove("hidden");
    toast(payload.content_hash_valid && payload.audit_chain.valid ? "完整性驗證通過" : "完整性驗證未通過", payload.content_hash_valid ? "" : "error");
  } catch (error) {
    toast(`驗證失敗：${error.message}`, "error");
  }
});

document.querySelectorAll("[data-format]").forEach((button) => button.addEventListener("click", async () => {
  if (!currentReport) return;
  const format = button.dataset.format;
  const artifact = currentReport.artifacts.find((item) => item.format === format);
  if (!artifact) return toast("未找到報告工件", "error");
  const filename = artifact.path.split("/").at(-1);
  try {
    const response = await fetch(`${apiRoot}/reports/${currentReport.report_id}/artifacts/${filename}`, { headers: { "X-API-Key": currentApiKey } });
    if (!response.ok) throw new Error(await parseError(response));
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    toast(`下載失敗：${error.message}`, "error");
  }
}));

document.querySelectorAll("[data-amount]").forEach((button) => button.addEventListener("click", () => {
  $("#addAmount").value = button.dataset.amount;
}));

$("#evaluationDate").value = new Date().toISOString().slice(0, 10);
initPipeline();
checkHealth();
