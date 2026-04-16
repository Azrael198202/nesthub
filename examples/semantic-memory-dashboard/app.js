const baseUrlInput = document.getElementById("baseUrl");
const policyKeyInput = document.getElementById("policyKey");
const statusSelect = document.getElementById("status");
const refreshBtn = document.getElementById("refreshBtn");
const resetBtn = document.getElementById("resetBtn");
const requestUrl = document.getElementById("requestUrl");
const candidateCount = document.getElementById("candidateCount");
const activeCount = document.getElementById("activeCount");
const rolledBackCount = document.getElementById("rolledBackCount");
const rollbackCard = document.getElementById("rollbackCard");
const versionList = document.getElementById("versionList");
const learningRules = document.getElementById("learningRules");
const candidateList = document.getElementById("candidateList");
const resultMeta = document.getElementById("resultMeta");
const rawJson = document.getElementById("rawJson");
const candidateTemplate = document.getElementById("candidateTemplate");

function buildUrl() {
  const url = new URL("/core/admin/semantic-memory", normalizeBaseUrl(baseUrlInput.value));
  if (policyKeyInput.value.trim()) {
    url.searchParams.set("policy_key", policyKeyInput.value.trim());
  }
  if (statusSelect.value) {
    url.searchParams.set("status", statusSelect.value);
  }
  return url;
}

function normalizeBaseUrl(raw) {
  const trimmed = raw.trim();
  return trimmed.endsWith("/") ? trimmed : `${trimmed}/`;
}

function setLoading() {
  candidateCount.textContent = "...";
  activeCount.textContent = "...";
  rolledBackCount.textContent = "...";
  candidateList.textContent = "加载中...";
  versionList.textContent = "加载中...";
  rollbackCard.textContent = "加载中...";
  learningRules.textContent = "加载中...";
}

function renderSummary(summary = {}) {
  candidateCount.textContent = summary.candidate ?? 0;
  activeCount.textContent = summary.active ?? 0;
  rolledBackCount.textContent = summary.rolled_back ?? 0;
}

function renderRollback(rollback) {
  if (!rollback) {
    rollbackCard.className = "empty-state";
    rollbackCard.textContent = "暂无回滚记录。";
    return;
  }

  rollbackCard.className = "rollback-item";
  rollbackCard.innerHTML = `
    <div class="candidate-topline">
      <span class="chip">${escapeHtml(rollback.policy_key)}</span>
      <span class="chip status" data-status="rolled_back">rolled_back</span>
    </div>
    <div class="rollback-meta">reason: ${escapeHtml(rollback.reason || "unknown")} | updated_at: ${escapeHtml(rollback.updated_at || "-")}</div>
    <p class="candidate-evidence">${escapeHtml(rollback.evidence || "")}</p>
  `;
}

function renderVersions(items = []) {
  if (!items.length) {
    versionList.className = "stack-list empty-state";
    versionList.textContent = "暂无版本快照。";
    return;
  }

  versionList.className = "stack-list";
  versionList.innerHTML = "";
  items.forEach((item) => {
    const article = document.createElement("article");
    article.className = "version-item";
    article.innerHTML = `
      <div class="version-meta">${escapeHtml(item.reason)} | ${escapeHtml(item.source)} | ${escapeHtml(item.created_at)}</div>
      <pre class="candidate-value">${escapeHtml(item.content_hash)}</pre>
    `;
    versionList.appendChild(article);
  });
}

function renderLearningRules(rules = {}) {
  const allowedPolicyKeys = rules.allowed_policy_keys || [];
  const blockedTerms = rules.blocked_terms || [];
  learningRules.className = "rules-grid";
  learningRules.innerHTML = `
    <article class="rule-card">
      <h3>Allowed Policy Keys</h3>
      ${renderList(allowedPolicyKeys, "当前没有限制")}
    </article>
    <article class="rule-card">
      <h3>Blocked Terms</h3>
      ${renderList(blockedTerms, "当前没有黑名单")}
    </article>
    <article class="rule-card">
      <h3>Min Candidate Length</h3>
      <p>${escapeHtml(rules.min_candidate_text_length ?? 0)}</p>
    </article>
    <article class="rule-card">
      <h3>Reject Existing Conflicts</h3>
      <p>${rules.reject_existing_conflicts ? "enabled" : "disabled"}</p>
    </article>
  `;
}

function renderList(items, emptyText) {
  if (!items.length) {
    return `<p>${escapeHtml(emptyText)}</p>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderCandidates(items = []) {
  if (!items.length) {
    candidateList.className = "stack-list empty-state";
    candidateList.textContent = "当前筛选条件下没有候选记录。";
    return;
  }

  candidateList.className = "stack-list";
  candidateList.innerHTML = "";
  items.forEach((item) => {
    const fragment = candidateTemplate.content.cloneNode(true);
    const policyKey = fragment.querySelector(".policy-key");
    const status = fragment.querySelector(".status");
    const meta = fragment.querySelector(".candidate-meta");
    const value = fragment.querySelector(".candidate-value");
    const evidence = fragment.querySelector(".candidate-evidence");

    policyKey.textContent = item.policy_key;
    status.textContent = item.status;
    status.dataset.status = item.status;
    meta.textContent = `confidence=${item.confidence} | hits=${item.hit_count} | failures=${item.failure_count} | source=${item.source}`;
    value.textContent = JSON.stringify(item.value, null, 2);
    evidence.textContent = item.evidence || "";
    candidateList.appendChild(fragment);
  });
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function refresh() {
  const url = buildUrl();
  requestUrl.textContent = url.toString();
  setLoading();
  try {
    const response = await fetch(url.toString());
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const result = payload.result || {};
    renderSummary(result.summary);
    renderRollback(result.latest_rollback);
    renderVersions(result.recent_versions || []);
    renderLearningRules(result.learning_rules || {});
    renderCandidates(result.candidates || []);
    resultMeta.textContent = `filters=${JSON.stringify(result.filters || {})} | count=${(result.candidates || []).length}`;
    rawJson.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    candidateList.className = "stack-list empty-state";
    candidateList.textContent = `加载失败: ${error.message}`;
    versionList.className = "stack-list empty-state";
    versionList.textContent = "请确认 API 已启动，且允许当前来源访问。";
    rollbackCard.className = "empty-state";
    rollbackCard.textContent = "没有拿到回滚信息。";
    learningRules.className = "empty-state";
    learningRules.textContent = "没有拿到学习规则。";
    rawJson.textContent = JSON.stringify({ error: error.message }, null, 2);
  }
}

refreshBtn.addEventListener("click", refresh);
resetBtn.addEventListener("click", () => {
  policyKeyInput.value = "";
  statusSelect.value = "";
  refresh();
});

refresh();