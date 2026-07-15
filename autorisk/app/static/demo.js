const $ = (selector) => document.querySelector(selector);
const apiRoot = "/api/v1/risk-evals";
let currentReport = null;
let currentApiKey = "";
let currentConclusion = null;
let currentFeedbackReceipt = null;

const pipelineSteps = [
  "接收並驗證風控請求",
  "標準化風險指標輸入",
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
  const metrics = calculation;
  const items = [
    ["槓桿率", (metrics.leverage_ratio ?? 0).toFixed(4), "LEVERAGE RATIO"],
    ["單一標的集中度", formatPercent(metrics.single_stock_concentration), "CONCENTRATION"],
    ["1 日 95% VaR", formatPercent(metrics.var_95_1d), "PARAMETRIC VAR"],
    ["流動性比例", formatPercent(metrics.liquidity_ratio), "LIQUIDITY"],
    ["今年以來收益", formatPercent(metrics.ytd_return), "YTD RETURN"],
    ["年內最大回撤", formatPercent(metrics.max_drawdown), "MAX DRAWDOWN"],
    ["年化波動率", formatPercent(metrics.annualized_volatility), "ANNUALIZED VOL"],
    ["每日可變現比例", formatPercent(metrics.daily_liquid_pct), "DAILY LIQUID"],
    ["每週可變現比例", formatPercent(metrics.weekly_liquid_pct), "WEEKLY LIQUID"],
  ];
  $("#metricsGrid").innerHTML = items.map(([label, value, note]) =>
    `<article class="metric"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`
  ).join("");
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
  if (!review) {
    return `<div class="review-head"><span class="review-index">0${index + 3} · ${index === 0 ? "FIRST REVIEW" : "FINAL REVIEW"}</span><span class="review-result">PENDING</span></div><h3>${index === 0 ? "AI Risk Officer" : "AI MIC"}</h3><p class="review-reason">等待當前工作流完成此級覆核。</p>`;
  }
  const reject = review.recommendation === "REJECT";
  return `<div class="review-head"><span class="review-index">0${index + 3} · ${index === 0 ? "FIRST REVIEW" : "FINAL REVIEW"}</span><span class="review-result ${reject ? "reject" : ""}">${review.recommendation}</span></div><h3>${index === 0 ? "AI Risk Officer" : "AI MIC"}</h3><div class="provider">${escapeHtml(review.reviewer_id)} · ${escapeHtml(review.provider)}</div><p class="review-reason">${escapeHtml(review.reasoning)}</p><div class="confidence"><span>審核信心度</span><strong>${(review.confidence * 100).toFixed(0)}%</strong></div><div class="confidence-track"><span style="width:${review.confidence * 100}%"></span></div>`;
}

function renderReport(report) {
  const evaluationDate = report.market_snapshot?.evaluation_date || "未提供評估日期";
  $("#reportSummary").innerHTML = `<strong>${escapeHtml(report.fund_name || report.fund_code)}</strong> 於 ${escapeHtml(evaluationDate)} 提交 ${escapeHtml(report.trigger_source)} 風控請求。${escapeHtml(report.auto_commentary)}<br><strong>最終結論：</strong>${escapeHtml(report.final_commentary)}`;
  $("#evidenceGrid").innerHTML = [
    ["內容哈希", `${report.content_hash.slice(0, 12)}…`],
    ["第一級簽章", report.first_sign ? "已簽署" : "待簽署"],
    ["第二級簽章", report.second_sign ? "已簽署" : "待簽署"],
    ["報告工件", `${report.artifacts.length} 個`],
  ].map(([label, value]) => `<div class="evidence"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderConclusion(conclusion) {
  currentConclusion = conclusion;
  const directive = conclusion.directive;
  $("#conclusionSheet").dataset.action = directive.action;
  $("#certificateId").textContent = conclusion.certificate_id;
  $("#conclusionCode").textContent = directive.conclusion_code;
  $("#conclusionHeadline").textContent = directive.headline;
  $("#conclusionSummary").textContent = directive.summary;
  $("#certificateHash").textContent = conclusion.verification.certificate_hash;
  const meta = [
    ["基金", `${conclusion.fund_code} / ${conclusion.fund_name}`],
    ["請求編號", conclusion.request_id],
    ["風險等級", conclusion.severity],
    ["執行決策", conclusion.execution_decision],
    ["簽發時間", new Date(conclusion.issued_at).toLocaleString("zh-HK")],
    ["有效至", new Date(conclusion.valid_until).toLocaleString("zh-HK")],
  ];
  $("#conclusionMeta").innerHTML = meta.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("#conclusionInstructions").innerHTML = directive.instructions.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("#conclusionRestrictions").innerHTML = (directive.restrictions.length ? directive.restrictions : ["無額外限制"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  $("#feedbackKey").value = `UI-${Date.now()}`;
  $("#feedbackMessage").value = conclusion.execution_decision === "BLOCK" ? "已確認並執行阻斷" : "已接收並按風控結論處理";
  $("#feedbackReceipt").classList.add("hidden");
  $("#downloadFeedback").classList.add("hidden");
  currentFeedbackReceipt = null;
}

async function loadConclusion(reportId) {
  const response = await fetch(`${apiRoot}/reports/${reportId}/conclusion`, {
    headers: { "X-API-Key": currentApiKey },
  });
  if (!response.ok) throw new Error(await parseError(response));
  renderConclusion(await response.json());
}

async function renderResult(payload) {
  const report = payload.report || payload;
  currentReport = report;
  const severity = report.severity.toLowerCase();
  $("#decisionCard").className = `decision-card card ${severity}`;
  $("#severityBadge").textContent = report.severity;
  $("#decisionText").textContent = report.execution_decision;
  $("#finalCommentary").textContent = report.final_commentary;
  $("#reportId").textContent = report.report_id;
  $("#reportStatus").textContent = report.status;
  renderMetrics(report.risk_indicators || {});
  renderRules(report);
  $("#firstReview").innerHTML = renderReview(report.ai_reviews[0], 0);
  $("#secondReview").innerHTML = renderReview(report.ai_reviews[1], 1);
  renderReport(report);
  await loadConclusion(report.report_id);
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

function parseOptionalJson(text, fieldName) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("必須是 JSON 對象");
    }
    return parsed;
  } catch (error) {
    throw new Error(`${fieldName} 格式錯誤：${error.message}`);
  }
}

$("#assessmentForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  currentApiKey = $("#apiKey").value.trim();
  const timer = startPipeline();
  const button = $("#submitButton");
  button.disabled = true;
  try {
    const requestId = $("#requestId").value.trim() || `DEMO-${Date.now()}`;
    const marketSnapshot = {
      evaluation_date: $("#evaluationDate").value,
      source: "demo-ui",
    };
    const proposedTrade = parseOptionalJson($("#proposedTrade").value, "擬議交易");
    const metadata = parseOptionalJson($("#metadata").value, "附加元數據");
    const additionalIndicators = parseOptionalJson($("#additionalIndicators").value, "擴展風險指標");
    Object.entries(additionalIndicators).forEach(([key, value]) => {
      if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
        throw new Error(`擴展風險指標 ${key} 必須是數值或 null`);
      }
    });

    const response = await fetch(`${apiRoot}/assess`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": currentApiKey },
      body: JSON.stringify({
        request_id: requestId,
        trigger_source: $("#triggerSource").value,
        fund_code: $("#fundCode").value.trim(),
        fund_name: $("#fundName").value.trim(),
        indicators: {
          ...additionalIndicators,
          leverage_ratio: Number($("#leverageRatio").value),
          single_stock_concentration: Number($("#singleConcentration").value),
          var_95_1d: Number($("#var95").value),
          liquidity_ratio: Number($("#liquidityRatio").value),
        },
        market_snapshot: marketSnapshot,
        proposed_trade: proposedTrade,
        metadata,
      }),
    });
    if (!response.ok) throw new Error(await parseError(response));
    const payload = await response.json();
    finishPipeline(timer);
    await new Promise((resolve) => setTimeout(resolve, 350));
    await renderResult(payload);
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

$("#reloadRulesButton").addEventListener("click", async () => {
  currentApiKey = $("#apiKey").value.trim();
  const button = $("#reloadRulesButton");
  button.disabled = true;
  try {
    const response = await fetch(`${apiRoot}/rules/reload`, {
      method: "POST",
      headers: { "X-API-Key": currentApiKey },
    });
    if (!response.ok) throw new Error(await parseError(response));
    const payload = await response.json();
    toast(`規則已重載：版本 ${payload.version}，共 ${payload.count} 條`);
  } catch (error) {
    toast(`規則重載失敗：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

async function downloadProtected(url, filename) {
  const response = await fetch(url, { headers: { "X-API-Key": currentApiKey } });
  if (!response.ok) throw new Error(await parseError(response));
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

$("#downloadConclusionJson").addEventListener("click", async () => {
  if (!currentConclusion) return;
  try {
    await downloadProtected(
      `${apiRoot}/reports/${currentConclusion.report_id}/conclusion/download?format=json`,
      `${currentConclusion.certificate_id}.json`,
    );
  } catch (error) {
    toast(`下載失敗：${error.message}`, "error");
  }
});

$("#downloadConclusionHtml").addEventListener("click", async () => {
  if (!currentConclusion) return;
  try {
    await downloadProtected(
      `${apiRoot}/reports/${currentConclusion.report_id}/conclusion/download?format=html`,
      `${currentConclusion.certificate_id}.html`,
    );
  } catch (error) {
    toast(`下載失敗：${error.message}`, "error");
  }
});

$("#submitFeedback").addEventListener("click", async () => {
  if (!currentReport || !currentConclusion) return;
  const idempotencyKey = $("#feedbackKey").value.trim();
  const actorId = $("#feedbackActor").value.trim();
  if (!idempotencyKey || !actorId) {
    return toast("回執冪等鍵和處理方不能留空", "error");
  }
  const button = $("#submitFeedback");
  button.disabled = true;
  try {
    const response = await fetch(`${apiRoot}/reports/${currentReport.report_id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": currentApiKey },
      body: JSON.stringify({
        idempotency_key: idempotencyKey,
        status: "OK",
        actor_id: actorId,
        observed_report_hash: currentReport.content_hash,
        observed_decision: currentReport.execution_decision,
        processed_at: new Date().toISOString(),
        message: $("#feedbackMessage").value.trim(),
        metadata: { source: "autorisk-demo-ui" },
      }),
    });
    if (!response.ok) throw new Error(await parseError(response));
    currentFeedbackReceipt = await response.json();
    $("#feedbackReceipt").textContent = JSON.stringify(currentFeedbackReceipt, null, 2);
    $("#feedbackReceipt").classList.remove("hidden");
    $("#downloadFeedback").classList.remove("hidden");
    toast("OK 回執已接收並寫入審計鏈");
  } catch (error) {
    toast(`回執提交失敗：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
});

$("#downloadFeedback").addEventListener("click", async () => {
  if (!currentFeedbackReceipt) return;
  try {
    const key = encodeURIComponent(currentFeedbackReceipt.idempotency_key);
    await downloadProtected(
      `${apiRoot}/reports/${currentFeedbackReceipt.report_id}/feedback/${key}/download`,
      `${currentFeedbackReceipt.receipt_id}.json`,
    );
  } catch (error) {
    toast(`回執下載失敗：${error.message}`, "error");
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

$("#evaluationDate").value = new Date().toISOString().slice(0, 10);
initPipeline();
checkHealth();
