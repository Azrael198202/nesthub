const stateColor = {
  ready: "is-ready",
  attention: "is-attention",
  active: "is-active",
  running: "is-active",
  planning: "is-planning",
  complete: "is-ready",
  blocked: "is-attention",
  idle: "is-muted",
  collecting: "is-attention",
  cancelled: "is-muted"
};

const tabs = ["home", "exchange", "work", "cortex", "blueprints", "agents", "settings"];
let activeTab = "home";
let activeSettingsSection = "language";
let latestDashboard = null;
let latestCortexUnpacked = null;
let currentLocale = "en-US";
let generatedArtifactsRuntime = { items: {}, isLoading: false, error: "" };
let runtimeMemoryInspection = { query: "", namespace: "*", result: null, isLoading: false, error: "" };
let trainingAssetsInspection = { profile: "lora_sft", backend: "mock", result: null, isLoading: false, isRunning: false, error: "", notice: "" };
let mediaRecorder = null;
let mediaChunks = [];
let isRecording = false;
let isBuddySpeaking = false;
let isBuddyThinking = false;
let buddySpeechTimer = null;
let buddyDragState = { dragging: false, offsetX: 0, offsetY: 0, x: null, y: null };
let buddyThreeModulesPromise = null;
let buddyModelViewer = null;
let avatarSettingsState = { customModelUrl: "", isSaving: false };
let deviceWeatherSyncState = { inFlight: false, attempted: false, lastSyncAt: 0 };
let activeReminderId = null;
let announcedReminderId = null;
let isCompletingReminder = false;
const managedScrollContainers = new Map();
let testConversation = [];
let customAgentStudio = { items: [], recentActions: [], selectedAgentId: "", isLoading: false, isGenerating: false, isThinking: false };
let studioFeatureRuntime = { featureId: "", items: [], fieldNames: [], detail: null, isLoading: false, isSaving: false, error: "", exportArtifact: null, draftText: "" };
let activeBlueprintStudioTab = "creating";
let activeRuntimeAgentId = "";
let testUploadAttachment = null;
let testUploadMode = "generic";
let bootstrapPollTimer = null;
let dashboardRefreshPromise = null;
let mailTesterState = { to: "", subject: "", body: "", status: "", isSending: false, isSyncing: false };
let mailboxSettingsState = {
  mailAddress: "",
  mailPassword: "",
  mailSmtpHost: "",
  mailSmtpPort: "",
  mailImapHost: "",
  mailImapPort: "",
  status: "",
  isSaving: false
};
let cortexTesterState = {
  command: "",
  taskType: "general_chat",
  locale: "en-US",
  inputModes: "text",
  requiresNetwork: true,
  requireArtifacts: false,
  speakReply: false,
  status: "",
  isLoading: false
};
let settingsI18nStrings = {};

function s(key, fallback = "") {
  return settingsI18nStrings[key] || fallback || key;
}

async function loadSettingsI18n(locale) {
  const target = String(locale || currentLocale || "en-US");
  try {
    const response = await fetch(`/api/i18n/settings?locale=${encodeURIComponent(target)}`);
    if (!response.ok) return;
    const payload = await response.json();
    settingsI18nStrings = payload?.strings || {};
    if (payload?.fallbackUiText && typeof payload.fallbackUiText === "object") {
      UI_TEXT["en-US"] = payload.fallbackUiText;
    }
    if (payload?.uiText && typeof payload.uiText === "object") {
      UI_TEXT[String(payload?.locale || target)] = payload.uiText;
    }
  } catch (_error) {
    // Keep local fallback text when i18n API is unavailable.
  }
}

let UI_TEXT = {"en-US": {}};

function t(path, vars = {}) {
  const fallback = UI_TEXT["en-US"];
  const bundle = UI_TEXT[currentLocale] || fallback;
  const value = path.split(".").reduce((acc, key) => acc?.[key], bundle)
    ?? path.split(".").reduce((acc, key) => acc?.[key], fallback)
    ?? path;
  if (typeof value !== "string") return path;
  return value.replace(/\{(\w+)\}/g, (_, key) => String(vars[key] ?? ""));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function isNearScrollBottom(container, threshold = 28) {
  if (!(container instanceof HTMLElement)) return true;
  return container.scrollTop + container.clientHeight >= container.scrollHeight - threshold;
}

function getScrollOverflow(container) {
  if (!(container instanceof HTMLElement)) return 0;
  return Math.max(0, container.scrollHeight - container.clientHeight);
}

function updateScrollJumpButtonPosition(container, button) {
  if (!(container instanceof HTMLElement) || !(button instanceof HTMLElement)) return;
  const rect = container.getBoundingClientRect();
  const top = Math.min(window.innerHeight - 56, Math.max(20, rect.bottom - 54));
  const left = Math.min(window.innerWidth - 52, Math.max(12, rect.right - 42));
  button.style.top = `${top}px`;
  button.style.left = `${left}px`;
}

function syncManagedScrollContainer(container) {
  if (!(container instanceof HTMLElement)) return;
  const managed = managedScrollContainers.get(container.id);
  if (!managed) return;
  const hasOverflow = getScrollOverflow(container) > 24;
  const atBottom = isNearScrollBottom(container);
  managed.button.hidden = !(hasOverflow && !atBottom);
  updateScrollJumpButtonPosition(container, managed.button);
}

function ensureManagedScrollContainer(containerId) {
  const container = document.getElementById(containerId);
  if (!(container instanceof HTMLElement)) return null;
  if (managedScrollContainers.has(containerId)) {
    const managed = managedScrollContainers.get(containerId);
    if (managed?.button?.isConnected) {
      syncManagedScrollContainer(container);
      return managed;
    }
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "scroll-jump-button remote-target";
  button.hidden = true;
  button.dataset.scrollJumpTarget = containerId;
  button.dataset.title = t("common.jumpToBottom");
  button.setAttribute("aria-label", button.dataset.title);
  button.textContent = "↓";
  document.body.appendChild(button);
  const onScroll = () => syncManagedScrollContainer(container);
  container.addEventListener("scroll", onScroll, { passive: true });
  managedScrollContainers.set(containerId, { button, onScroll });
  syncManagedScrollContainer(container);
  return managedScrollContainers.get(containerId) || null;
}

function syncAllManagedScrollContainers() {
  [
    "conversation",
    "test-conversation",
    "timeline",
    "modules",
    "agents",
    "relay",
    "work-request-list",
    "work-pipeline-scroll",
    "studio-blueprints",
    "settings-detail-scroll",
    "settings-directory-list"
  ].forEach((containerId) => ensureManagedScrollContainer(containerId));
  managedScrollContainers.forEach((_managed, containerId) => {
    const container = document.getElementById(containerId);
    if (container) syncManagedScrollContainer(container);
  });
}

function preserveManagedScroll(container, render) {
  if (!(container instanceof HTMLElement)) {
    render();
    return;
  }
  ensureManagedScrollContainer(container.id);
  const shouldStickToBottom = isNearScrollBottom(container);
  const offsetFromBottom = Math.max(0, container.scrollHeight - container.clientHeight - container.scrollTop);
  render();
  requestAnimationFrame(() => {
    if (!container.isConnected) return;
    if (shouldStickToBottom) {
      container.scrollTop = container.scrollHeight;
    } else {
      const nextTop = Math.max(0, container.scrollHeight - container.clientHeight - offsetFromBottom);
      container.scrollTop = nextTop;
    }
    syncManagedScrollContainer(container);
  });
}

function setTextIfPresent(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function normalizeTabName(tabName) {
  if (tabName === "voice" || tabName === "test") return "exchange";
  if (tabName === "pairing") return "settings";
  return tabs.includes(tabName) ? tabName : "home";
}

function settingsSectionCatalog() {
  return {
    language: {
      label: t("settings.sections.language.label"),
      summary: t("settings.sections.language.summary")
    },
    avatar: {
      label: t("settings.sections.avatar.label"),
      summary: t("settings.sections.avatar.summary")
    },
    pairing: {
      label: t("settings.sections.pairing.label"),
      summary: t("settings.sections.pairing.summary")
    },
    mailbox: {
      label: t("settings.sections.mailbox.label"),
      summary: t("settings.sections.mailbox.summary")
    },
    skills: {
      label: t("settings.sections.skills.label"),
      summary: t("settings.sections.skills.summary")
    },
    agents: {
      label: t("settings.sections.agents.label"),
      summary: t("settings.sections.agents.summary")
    },
    "ai-models": {
      label: t("settings.sections.ai-models.label"),
      summary: t("settings.sections.ai-models.summary")
    },
    artifacts: {
      label: "Generated Artifacts",
      summary: "Browse runtime generated blueprints, agents, and features"
    },
    memory: {
      label: "Runtime Memory",
      summary: "Inspect promotion artifacts, promoted facts, and reusable experiences"
    },
    training: {
      label: "Training Assets",
      summary: "Review SFT datasets, preference sets, and train-ready manifests"
    }
  };
}

async function loadGeneratedArtifacts() {
  generatedArtifactsRuntime.isLoading = true;
  generatedArtifactsRuntime.error = "";
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/generated-artifacts");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to load generated artifacts.");
    }
    generatedArtifactsRuntime.items = payload.items || {};
  } catch (error) {
    generatedArtifactsRuntime.error = String(error.message || error);
  } finally {
    generatedArtifactsRuntime.isLoading = false;
    renderSettings(latestDashboard);
  }
}

async function deleteGeneratedArtifact(category, artifactId) {
  try {
    const response = await fetch("/api/generated-artifacts/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, artifactId })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to delete generated artifact.");
    }
    await loadGeneratedArtifacts();
  } catch (error) {
    generatedArtifactsRuntime.error = String(error.message || error);
    renderSettings(latestDashboard);
  }
}

async function loadRuntimeMemoryInspection(query = runtimeMemoryInspection.query || "", namespace = runtimeMemoryInspection.namespace || "*") {
  runtimeMemoryInspection.isLoading = true;
  runtimeMemoryInspection.error = "";
  runtimeMemoryInspection.query = String(query || "");
  runtimeMemoryInspection.namespace = String(namespace || "*");
  renderSettings(latestDashboard);
  try {
    const params = new URLSearchParams();
    if (runtimeMemoryInspection.query) params.set("query", runtimeMemoryInspection.query);
    if (runtimeMemoryInspection.namespace && runtimeMemoryInspection.namespace !== "*") params.set("namespace", runtimeMemoryInspection.namespace);
    params.set("top_k", "8");
    const response = await fetch(`/api/runtime-memory?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || "Failed to load runtime memory.");
    }
    runtimeMemoryInspection.result = payload.result || null;
  } catch (error) {
    runtimeMemoryInspection.error = String(error.message || error);
  } finally {
    runtimeMemoryInspection.isLoading = false;
    renderSettings(latestDashboard);
  }
}

async function loadTrainingAssetsInspection(profile = trainingAssetsInspection.profile || "lora_sft") {
  trainingAssetsInspection.isLoading = true;
  trainingAssetsInspection.error = "";
  trainingAssetsInspection.notice = "";
  trainingAssetsInspection.profile = String(profile || "lora_sft");
  renderSettings(latestDashboard);
  try {
    const params = new URLSearchParams();
    params.set("profile", trainingAssetsInspection.profile);
    const response = await fetch(`/api/training-assets?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || "Failed to load training assets.");
    }
    trainingAssetsInspection.result = payload.result || null;
  } catch (error) {
    trainingAssetsInspection.error = String(error.message || error);
  } finally {
    trainingAssetsInspection.isLoading = false;
    renderSettings(latestDashboard);
  }
}

async function rebuildTrainingAssets(profile = trainingAssetsInspection.profile || "lora_sft") {
  trainingAssetsInspection.isLoading = true;
  trainingAssetsInspection.error = "";
  trainingAssetsInspection.notice = "";
  trainingAssetsInspection.profile = String(profile || "lora_sft");
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/training-assets/rebuild", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: trainingAssetsInspection.profile }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || "Failed to rebuild training manifest.");
    }
    trainingAssetsInspection.result = payload.result || null;
    trainingAssetsInspection.notice = "Training manifest rebuilt.";
  } catch (error) {
    trainingAssetsInspection.error = String(error.message || error);
  } finally {
    trainingAssetsInspection.isLoading = false;
    renderSettings(latestDashboard);
  }
}

async function runTrainingAssetsDryRun(profile = trainingAssetsInspection.profile || "lora_sft", backend = trainingAssetsInspection.backend || "mock") {
  trainingAssetsInspection.isRunning = true;
  trainingAssetsInspection.error = "";
  trainingAssetsInspection.notice = "";
  trainingAssetsInspection.profile = String(profile || "lora_sft");
  trainingAssetsInspection.backend = String(backend || "mock");
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/training-assets/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile: trainingAssetsInspection.profile,
        backend: trainingAssetsInspection.backend,
        dryRun: true,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.error || "Failed to generate training run skeleton.");
    }
    trainingAssetsInspection.result = payload.trainingAssets || trainingAssetsInspection.result;
    if (trainingAssetsInspection.result) {
      trainingAssetsInspection.result.last_run = payload.result || null;
    }
    trainingAssetsInspection.notice = payload?.result?.message || "Training run skeleton generated.";
  } catch (error) {
    trainingAssetsInspection.error = String(error.message || error);
  } finally {
    trainingAssetsInspection.isRunning = false;
    renderSettings(latestDashboard);
  }
}

function renderGeneratedArtifactGroups() {
  const groups = generatedArtifactsRuntime.items || {};
  const order = ["blueprint", "agent", "feature", "trace", "code"];
  return order.map((category) => {
    const items = Array.isArray(groups[category]) ? groups[category] : [];
    const rows = items.length
      ? items.map((item) => `
        <article class="settings-card">
          <strong>${escapeHtml(item.name || item.artifactId || "-")}</strong>
          <p>${escapeHtml(item.path || "")}</p>
          <p>size: ${escapeHtml(String(item.size || 0))}</p>
          <pre class="cortex-json-view">${escapeHtml(item.contentPreview || "")}</pre>
          <div class="studio-actions">
            <button class="test-action remote-target is-secondary" type="button" data-generated-delete="${escapeHtml(category)}:${escapeHtml(item.artifactId || "")}">Delete</button>
          </div>
        </article>
      `).join("")
      : `<div class="settings-card"><p>No ${escapeHtml(category)} artifacts.</p></div>`;
    return `
      <div class="settings-stack">
        <div class="panel-header compact"><h3>${escapeHtml(category)}</h3></div>
        ${rows}
      </div>
    `;
  }).join("");
}

function renderRuntimeMemoryHits(result) {
  const hits = Array.isArray(result?.vector_hits) ? result.vector_hits : [];
  if (!hits.length) return `<div class="settings-card"><p>No runtime memory hits yet.</p></div>`;
  return hits.map((hit) => `
    <article class="settings-card memory-hit-card">
      <div class="agent-row">
        <strong>${escapeHtml(hit.namespace || "memory")}</strong>
        <span class="pill">${escapeHtml(hit.id || "-")}</span>
      </div>
      <p>${escapeHtml(hit.content || "")}</p>
      <pre class="cortex-json-view">${escapeHtml(JSON.stringify(hit.metadata || {}, null, 2))}</pre>
    </article>
  `).join("");
}

function renderRuntimeMemoryArtifacts(result) {
  const items = Array.isArray(result?.promotion_artifacts) ? result.promotion_artifacts : [];
  if (!items.length) return `<div class="settings-card"><p>No promotion artifacts yet.</p></div>`;
  return items.map((item) => `
    <article class="settings-card memory-hit-card">
      <strong>${escapeHtml(item.name || item.artifactId || "memory artifact")}</strong>
      <p>${escapeHtml(item.path || "")}</p>
      <p>${escapeHtml(item.contentPreview || "")}</p>
    </article>
  `).join("");
}

function renderTrainingArtifactRows(items, emptyText) {
  if (!Array.isArray(items) || !items.length) return `<div class="settings-card"><p>${escapeHtml(emptyText)}</p></div>`;
  return items.map((item) => `
    <article class="settings-card memory-hit-card">
      <div class="agent-row">
        <strong>${escapeHtml(item.name || item.artifact_id || item.artifactId || "artifact")}</strong>
        <span class="pill">${escapeHtml(String(item.sample_count || item.count || item.size || 0))}</span>
      </div>
      <p>${escapeHtml(item.path || "")}</p>
      <p>${escapeHtml(item.profile || item.kind || "")}</p>
    </article>
  `).join("");
}

function renderRepairPreferenceCounts(counts) {
  const entries = Object.entries(counts || {});
  if (!entries.length) return `<div class="settings-card"><p>No repair preference signals recorded yet.</p></div>`;
  return entries.map(([key, value]) => `
    <article class="settings-card memory-hit-card">
      <div class="agent-row">
        <strong>${escapeHtml(key)}</strong>
        <span class="pill">${escapeHtml(String(value || 0))}</span>
      </div>
    </article>
  `).join("");
}

function renderTrainingMetricCards(summary, manifest, runner) {
  const cards = [
    { label: "SFT Samples", value: summary.sft_samples || 0, meta: `${manifest.counts?.sft || 0} datasets` },
    { label: "Preference Samples", value: summary.preference_samples || 0, meta: `${manifest.counts?.preference || 0} datasets` },
    { label: "Manifest Builds", value: summary.training_manifests || 0, meta: runner?.backend?.label || "Runner pending" },
    { label: "Run Specs", value: summary.training_runs || 0, meta: runner?.ready ? "Ready for dry-run" : "Waiting for datasets" },
  ];
  return cards.map((card) => `
    <article class="training-metric-card">
      <span class="training-metric-label">${escapeHtml(card.label)}</span>
      <strong class="training-metric-value">${escapeHtml(String(card.value))}</strong>
      <p class="training-metric-meta">${escapeHtml(card.meta)}</p>
    </article>
  `).join("");
}

function renderTrainingPlan(plan) {
  const steps = Array.isArray(plan?.stages) ? plan.stages : [];
  if (!steps.length) return `<div class="settings-card"><p>No training plan available yet.</p></div>`;
  return `
    <article class="settings-card training-plan-card">
      <div class="agent-row">
        <strong>Execution Plan</strong>
        <span class="pill ${plan.preference_objective && plan.preference_objective !== "none" ? "is-active" : "is-ready"}">${escapeHtml(plan.preference_objective || "sft")}</span>
      </div>
      <div class="training-stage-row">
        ${steps.map((step) => `<span class="training-stage-pill">${escapeHtml(step)}</span>`).join("")}
      </div>
      <p>Required assets: ${escapeHtml((plan.requires || []).join(", "))}</p>
    </article>
  `;
}

function renderCommandPreview(lines) {
  const items = Array.isArray(lines) ? lines : [];
  if (!items.length) return `<div class="settings-card"><p>No runner command preview available yet.</p></div>`;
  return `
    <article class="settings-card training-command-card">
      <strong>Command Preview</strong>
      <pre class="cortex-json-view">${escapeHtml(items.join(" "))}</pre>
    </article>
  `;
}

function renderTrainingBackendOptions(runner) {
  const runtimeConfig = runner?.runtime_config || {};
  const backends = Object.keys(runtimeConfig.backends || {});
  const items = backends.length ? backends : ["mock", "unsloth", "llamafactory"];
  return items.map((item) => `<option value="${escapeHtml(item)}" ${trainingAssetsInspection.backend === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("");
}

function renderTrainingRunTimeline(runs, lastRun) {
  const merged = [];
  if (lastRun) {
    merged.push({
      name: lastRun.run_id || "latest run",
      created_at: lastRun.created_at || "",
      status: lastRun.status || "unknown",
      path: lastRun.artifact_path || "",
      preview: lastRun.message || "",
    });
  }
  (Array.isArray(runs) ? runs : []).forEach((item) => {
    if (merged.some((existing) => existing.path && existing.path === item.path)) return;
    merged.push({
      name: item.name || item.artifactId || "run",
      created_at: item.created_at || "",
      status: item.status || "artifact",
      path: item.path || "",
      preview: item.contentPreview || "",
    });
  });
  if (!merged.length) return `<div class="settings-card"><p>No training runs yet.</p></div>`;
  return merged.map((item) => `
    <article class="settings-card training-timeline-card">
      <div class="agent-row">
        <strong>${escapeHtml(item.name)}</strong>
        <span class="pill ${item.status === "completed" ? "is-ready" : item.status === "failed" ? "is-attention" : "is-active"}">${escapeHtml(item.status)}</span>
      </div>
      <p>${escapeHtml(item.created_at || "Pending timestamp")}</p>
      <p>${escapeHtml(item.path || "")}</p>
      <p>${escapeHtml(item.preview || "")}</p>
    </article>
  `).join("");
}

function localizeCatalogText(entry) {
  return typeof entry === "string" ? entry : "";
}

function localizeSpeaker(speaker) {
  if (speaker === "You") return t("speakers.you");
  if (speaker === "HomeHub") return t("speakers.homehub");
  return speaker;
}

function localizeMode(mode) {
  return mode === "Listening" ? t("status.listening") : mode;
}

function localizeStatusWord(status) {
  const text = t(`statusWords.${status}`);
  return text === `statusWords.${status}` ? status : text;
}

function translateItem(item, table) {
  return { ...item, ...(table[item.id]?.[currentLocale] || {}) };
}

const moduleTranslations = {
  briefing: {
    "zh-CN": { name: "每日晨报", summary: "天气、日程、任务和账单已完成整合。", actionLabel: "打开晨报" },
    "ja-JP": { name: "朝のブリーフィング", summary: "天気、予定、タスク、請求をまとめました。", actionLabel: "ブリーフを見る" }
  },
  schedule: {
    "zh-CN": { name: "家庭日程同步", summary: "今晚检测到两个时间冲突。", actionLabel: "立即处理" },
    "ja-JP": { name: "家族予定同期", summary: "今夜の予定に 2 件の競合があります。", actionLabel: "今すぐ確認" }
  },
  travel: {
    "zh-CN": { name: "旅行准备清单", summary: "充电宝和证件复印件仍未准备。", actionLabel: "打开清单" },
    "ja-JP": { name: "旅行チェックリスト", summary: "モバイルバッテリーと書類コピーが未準備です。", actionLabel: "リストを開く" }
  },
  knowledge: {
    "zh-CN": { name: "本地知识问答", summary: "政策、手册和票据已建立本地索引。", actionLabel: "立即提问" },
    "ja-JP": { name: "ローカル知識 Q&A", summary: "規約、マニュアル、領収書をローカル索引化しました。", actionLabel: "質問する" }
  },
  messages: {
    "zh-CN": { name: "统一消息", summary: "来自 LINE、微信和伴侣应用的最近更新。", actionLabel: "查看收件箱" },
    "ja-JP": { name: "統合メッセージ", summary: "LINE、WeChat、コンパニオンアプリの最新更新です。", actionLabel: "受信箱を見る" }
  }
};

const timelineTranslations = {
  t1: {
    "zh-CN": { title: "请求已解析", detail: "规划智能体已把任务拆分为设备设置、家庭同步和语音配置三条路径。" },
    "ja-JP": { title: "リクエスト解析完了", detail: "プランナーが端末設定、家族同期、音声設定の 3 系統に分解しました。" }
  },
  t2: {
    "zh-CN": { title: "并行智能体已启动", detail: "四个智能体正在使用不同模型和技能并行运行。" },
    "ja-JP": { title: "並列エージェント開始", detail: "4 つのエージェントが異なるモデルとスキルで並列実行中です。" }
  },
  t3: {
    "zh-CN": { title: "语音链路已就绪", detail: "本地语音识别已激活，并保留云端语音合成兜底。" },
    "ja-JP": { title: "音声経路準備完了", detail: "ローカル音声認識が有効になり、クラウド音声合成を予備にしています。" }
  },
  t4: {
    "zh-CN": { title: "晨报已生成", detail: "家庭摘要已经准备好，可直接显示在客厅屏幕。" },
    "ja-JP": { title: "朝の要約を生成", detail: "家族向けサマリーが完成し、リビング画面に表示できます。" }
  }
};

const agentTranslations = {
  planner: {
    "zh-CN": { role: "任务拆解与路由", lastUpdate: "已将家庭请求映射为三条执行路径。" },
    "ja-JP": { role: "タスク分解とルーティング", lastUpdate: "家庭内リクエストを 3 つの実行経路に整理しました。" }
  },
  device: {
    "zh-CN": { role: "配对、盒子状态与自动化", lastUpdate: "正在刷新伴侣设备的配对状态。" },
    "ja-JP": { role: "ペアリング、ボックス状態、自動化", lastUpdate: "コンパニオン端末のペアリング状態を更新しています。" }
  },
  lifestyle: {
    "zh-CN": { role: "家庭助理编排", lastUpdate: "正在准备晨报与提醒。" },
    "ja-JP": { role: "家庭アシスタントのオーケストレーション", lastUpdate: "朝の要約とリマインダーを準備しています。" }
  },
  developer: {
    "zh-CN": { role: "AI 驱动开发流程", lastUpdate: "正在向电视壳层发布工作流更新。" },
    "ja-JP": { role: "AI 駆動開発流", lastUpdate: "TV シェルへワークフロー更新を反映しています。" }
  }
};

const skillTranslations = {
  "daily-briefing": {
    "zh-CN": { name: "每日晨报", description: "组合天气、日程、账单和提醒，生成家庭晨报。" },
    "ja-JP": { name: "朝のブリーフィング", description: "天気、予定、請求、リマインダーをまとめて朝の要約を作成します。" }
  },
  "family-schedule-sync": {
    "zh-CN": { name: "家庭日程同步", description: "合并家庭事件并在电视首页展示冲突。" },
    "ja-JP": { name: "家族予定同期", description: "家族イベントを統合し、TV ホームで競合を表示します。" }
  },
  "knowledge-qa": {
    "zh-CN": { name: "本地知识问答", description: "检索家庭私有文档并带引用回答。" },
    "ja-JP": { name: "ローカル知識 Q&A", description: "家庭内の非公開文書を検索し、出典付きで回答します。" }
  },
  "im-command-bridge": {
    "zh-CN": { name: "IM 指令桥接", description: "接收来自 LINE、微信与伴侣应用的命令。" },
    "ja-JP": { name: "IM コマンドブリッジ", description: "LINE、WeChat、コンパニオンアプリからの命令を受け取ります。" }
  }
};
function iconSvg(name) {
  const icons = {
    status: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="rgba(85,208,177,0.14)" stroke="rgba(136,239,214,0.6)"/><circle cx="12" cy="12" r="3.2" fill="#82eed3"/></svg>`,
    weather: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 18h9a4 4 0 0 0 .4-8A5.5 5.5 0 0 0 6 11.2 3.4 3.4 0 0 0 7 18Z" fill="rgba(101,182,255,0.18)" stroke="rgba(170,215,255,0.75)"/><path d="M9 6.5l.9 1.7M14.1 6.5l-.9 1.7M7 8.9l1.7.5M16.9 8.9l-1.7.5" stroke="#ffd27a" stroke-linecap="round"/></svg>`,
    box: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4.5" y="7" width="15" height="10" rx="3" fill="rgba(164,188,212,0.12)" stroke="rgba(189,210,232,0.58)"/><circle cx="9" cy="12" r="1.2" fill="#6edfc5"/><circle cx="15" cy="12" r="1.2" fill="#65b6ff"/></svg>`,
    tip: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.8a6 6 0 0 0-3.5 10.8c.9.7 1.4 1.4 1.6 2.1h3.8c.2-.7.7-1.4 1.6-2.1A6 6 0 0 0 12 4.8Z" fill="rgba(255,189,92,0.18)" stroke="rgba(255,220,150,0.7)"/><path d="M10.2 19h3.6" stroke="#ffe6ab" stroke-linecap="round"/></svg>`,
  };
  return icons[name] || icons.status;
}

function mascotSvg(mode = "idle", pose = "home") {
  const bubble = pose === "voice"
    ? `<path d="M184 40c0-19.9 16.1-36 36-36h90c19.9 0 36 16.1 36 36v34c0 19.9-16.1 36-36 36h-54l-22 18v-18h-14c-19.9 0-36-16.1-36-36V40Z" fill="rgba(101,182,255,0.14)" stroke="rgba(174,220,255,0.45)"/>`
    : "";
  const eyeRx = mode === "listening" ? 12 : mode === "speaking" ? 8 : 9;
  const eyeRy = mode === "listening" ? 6 : mode === "speaking" ? 10 : 9;
  const mouth = mode === "speaking"
    ? `<ellipse class="mouth-speaker" cx="142" cy="165" rx="16" ry="10" fill="#95f5de"/>`
    : mode === "listening"
      ? `<path class="mouth-speaker" d="M126 166c10-8 22-8 32 0" fill="none" stroke="#95f5de" stroke-width="4" stroke-linecap="round"/>`
      : `<path class="mouth-speaker" d="M124 164c7 6 29 6 36 0" fill="none" stroke="#95f5de" stroke-width="4" stroke-linecap="round"/>`;
  const armLeft = pose === "agents"
    ? `<path d="M76 116c-24 -6 -38 10 -40 28" fill="none" stroke="rgba(125,222,210,0.58)" stroke-width="6" stroke-linecap="round"/>`
    : `<path d="M80 116c-18 2-28 12-30 28" fill="none" stroke="rgba(125,222,210,0.5)" stroke-width="6" stroke-linecap="round"/>`;
  const armRight = pose === "settings"
    ? `<path d="M206 116c28 -8 40 8 42 28" fill="none" stroke="rgba(125,222,210,0.58)" stroke-width="6" stroke-linecap="round"/>`
    : `<path d="M206 116c18 2 28 12 30 28" fill="none" stroke="rgba(125,222,210,0.5)" stroke-width="6" stroke-linecap="round"/>`;
  const accessory = {
    home: `<path d="M262 38c10-8 24-4 29 7 4 10 0 20-18 32-18-12-22-22-18-32 5-11 19-15 29-7 2-2 4-3 6-4Z" fill="rgba(255,189,92,0.22)" stroke="rgba(255,219,160,0.55)"/>`,
    agents: `<circle cx="286" cy="46" r="8" fill="rgba(101,182,255,0.18)" stroke="rgba(174,220,255,0.55)"/><circle cx="310" cy="64" r="8" fill="rgba(125,222,210,0.18)" stroke="rgba(159,243,222,0.55)"/><circle cx="284" cy="82" r="8" fill="rgba(181,126,255,0.18)" stroke="rgba(218,190,255,0.55)"/><path d="M292 52 302 60M292 76 302 68" stroke="rgba(174,220,255,0.6)" stroke-width="4" stroke-linecap="round"/>`,
    pairing: `<path d="M274 44h18a10 10 0 0 1 0 20h-10" fill="none" stroke="rgba(174,220,255,0.7)" stroke-width="5" stroke-linecap="round"/><path d="M306 58h-18a10 10 0 0 0 0 20h10" fill="none" stroke="rgba(125,222,210,0.7)" stroke-width="5" stroke-linecap="round"/>`,
    settings: `<circle cx="290" cy="58" r="15" fill="rgba(101,182,255,0.14)" stroke="rgba(174,220,255,0.55)"/><circle cx="290" cy="58" r="5" fill="#8ff1db"/><path d="M290 34v8M290 74v8M266 58h8M306 58h8M273 41l5 5M302 70l5 5M273 75l5-5M302 46l5-5" stroke="rgba(174,220,255,0.55)" stroke-width="4" stroke-linecap="round"/>`,
    voice: `<path d="M276 44v30" stroke="rgba(159,243,222,0.68)" stroke-width="6" stroke-linecap="round"/><path d="M292 50c7 6 7 18 0 24M308 44c12 10 12 30 0 40" fill="none" stroke="rgba(174,220,255,0.58)" stroke-width="5" stroke-linecap="round"/>`,
  }[pose] || "";
  return `
    <svg viewBox="0 0 360 240" class="house-mascot-svg is-${mode} pose-${pose}" aria-hidden="true">
      <defs>
        <linearGradient id="roofGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#7dded2"/>
          <stop offset="100%" stop-color="#57a9ff"/>
        </linearGradient>
        <linearGradient id="bodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#143047"/>
          <stop offset="100%" stop-color="#1c425f"/>
        </linearGradient>
        <radialGradient id="cheekGrad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="rgba(255,182,182,0.9)"/>
          <stop offset="100%" stop-color="rgba(255,182,182,0.05)"/>
        </radialGradient>
      </defs>
      <ellipse cx="140" cy="208" rx="94" ry="18" fill="rgba(0,0,0,0.22)"/>
      ${bubble}
      <path d="M64 94 142 34l78 60v84c0 14.4-11.6 26-26 26H90c-14.4 0-26-11.6-26-26V94Z" fill="url(#bodyGrad)" stroke="rgba(154,210,243,0.5)" stroke-width="3"/>
      <path d="M48 102 142 24l94 78" fill="none" stroke="url(#roofGrad)" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="104" y="124" width="76" height="54" rx="22" fill="rgba(9,20,30,0.66)" stroke="rgba(144,220,203,0.36)"/>
      <ellipse class="eye-listener eye-blink" cx="124" cy="146" rx="${eyeRx}" ry="${eyeRy}" fill="#8ff1db"/>
      <ellipse class="eye-listener eye-blink" cx="160" cy="146" rx="${eyeRx}" ry="${eyeRy}" fill="#8ff1db"/>
      <circle cx="120" cy="142" r="2.4" fill="#103c35"/>
      <circle cx="156" cy="142" r="2.4" fill="#103c35"/>
      ${mouth}
      <ellipse cx="108" cy="156" rx="10" ry="7" fill="url(#cheekGrad)"/>
      <ellipse cx="176" cy="156" rx="10" ry="7" fill="url(#cheekGrad)"/>
      <rect x="128" y="178" width="28" height="26" rx="10" fill="rgba(101,182,255,0.18)" stroke="rgba(174,220,255,0.35)"/>
      ${armLeft}
      ${armRight}
      <circle cx="42" cy="150" r="12" fill="rgba(101,182,255,0.16)" stroke="rgba(174,220,255,0.5)"/>
      <circle cx="244" cy="150" r="12" fill="rgba(101,182,255,0.16)" stroke="rgba(174,220,255,0.5)"/>
      ${accessory}
    </svg>
  `;
}

function getActiveTabLabel() {
  const tab = document.getElementById(`tab-${activeTab}`);
  return tab?.textContent?.trim() || "Home";
}

function buddyDisplayName() {
  return t("buddy.name");
}

function buddyPoseForTab() {
  const map = {
    home: "home",
    agents: "agents",
    exchange: "voice",
    work: "agents",
    cortex: "agents",
    blueprints: "agents",
    settings: "settings",
  };
  return map[activeTab] || "home";
}

function buddyPromptForTab() {
  if (activeTab === "exchange") {
    return isRecording ? t("buddy.prompt.exchangeRecording") : t("buddy.prompt.exchangeIdle");
  }
  return t(`buddy.prompt.${activeTab}`) || t("buddy.prompt.home");
}

function buddySubtitleForTab() {
  if (activeTab === "exchange") {
    return isRecording ? t("buddy.subtitle.exchangeRecording") : t("buddy.subtitle.exchangeIdle");
  }
  return t(`buddy.subtitle.${activeTab}`) || "";
}

function currentBuddyMode() {
  if (isRecording) return "listening";
  if (isBuddyThinking) return "thinking";
  if (isBuddySpeaking) return "speaking";
  return "idle";
}

function getAssistantAvatarConfig() {
  return latestDashboard?.assistantAvatar || {
    mode: "house",
    customModelUrl: "/generated/avatar/pixellabs-glb-3347.glb",
    backupMode: "house",
    defaultMode: "custom",
    techStack: [],
  };
}

function shouldRenderCustomBuddy() {
  const avatar = getAssistantAvatarConfig();
  return avatar.mode === "custom" && !!avatar.customModelUrl;
}

function destroyBuddyModelViewer() {
  if (!buddyModelViewer) return;
  if (buddyModelViewer.frameId) cancelAnimationFrame(buddyModelViewer.frameId);
  if (buddyModelViewer.mixer) {
    buddyModelViewer.mixer.stopAllAction();
  }
  if (buddyModelViewer.renderer) {
    buddyModelViewer.renderer.dispose();
    const canvas = buddyModelViewer.renderer.domElement;
    if (canvas?.parentNode) {
      canvas.parentNode.removeChild(canvas);
    }
  }
  buddyModelViewer = null;
}

async function loadBuddyThreeModules() {
  if (!buddyThreeModulesPromise) {
    buddyThreeModulesPromise = Promise.all([
      import("/generated/vendor/three/three.module.js"),
      import("/generated/vendor/three/GLTFLoader.js"),
    ]).then(([THREE, loaderModule]) => ({
      THREE,
      GLTFLoader: loaderModule.GLTFLoader,
    })).catch((error) => {
      buddyThreeModulesPromise = null;
      throw error;
    });
  }
  return buddyThreeModulesPromise;
}

function resizeBuddyModelViewer() {
  if (!buddyModelViewer) return;
  const rect = buddyModelViewer.container.getBoundingClientRect();
  const width = Math.max(220, Math.round(rect.width || 280));
  const height = Math.max(220, Math.round(rect.height || 280));
  buddyModelViewer.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  buddyModelViewer.renderer.setSize(width, height, false);
  buddyModelViewer.camera.aspect = width / height;
  buddyModelViewer.camera.updateProjectionMatrix();
}

function collectBuddyMorphTargets(root) {
  const slots = [];
  root.traverse((node) => {
    if (!node?.isMesh || !node.morphTargetDictionary || !Array.isArray(node.morphTargetInfluences)) return;
    const names = Object.keys(node.morphTargetDictionary);
    const indices = names
      .filter((name) => /mouth|smile|talk|speak|viseme|phoneme|jaw|open/i.test(name))
      .map((name) => node.morphTargetDictionary[name])
      .filter((value) => Number.isInteger(value));
    if (indices.length) {
      slots.push({ node, indices });
    }
  });
  return slots;
}

function collectBuddyAccentMaterials(root) {
  const materials = [];
  root.traverse((node) => {
    if (!node?.isMesh) return;
    const materialList = Array.isArray(node.material) ? node.material : [node.material];
    materialList.forEach((material) => {
      if (!material || typeof material !== "object" || typeof material.emissive === "undefined") return;
      materials.push({
        material,
        baseIntensity: Number(material.emissiveIntensity || 0),
      });
    });
  });
  return materials;
}

function animateBuddyState(elapsed, mode, root, stateNodes) {
  const baseY = stateNodes.baseY ?? -0.5;
  const baseScale = stateNodes.baseScale ?? 1;
  const earTilt = mode === "listening" ? Math.sin(elapsed * 4.8) * 0.06 : 0;
  const thinkTilt = mode === "thinking" ? Math.sin(elapsed * 2.4) * 0.08 : 0;
  const speakBounce = mode === "speaking" ? Math.abs(Math.sin(elapsed * 7.2)) * 0.09 : 0;
  const idleBounce = mode === "idle" ? Math.sin(elapsed * 1.1) * 0.035 : 0;
  const listeningBounce = mode === "listening" ? Math.sin(elapsed * 2.8) * 0.055 : 0;
  const thinkingBounce = mode === "thinking" ? Math.sin(elapsed * 2.1) * 0.075 : 0;
  root.rotation.y = Math.sin(elapsed * (mode === "thinking" ? 0.8 : 0.5)) * (mode === "speaking" ? 0.24 : 0.16);
  root.rotation.z = earTilt + thinkTilt;
  root.position.y = baseY + idleBounce + listeningBounce + thinkingBounce + speakBounce;
  const scalePulse = mode === "speaking"
    ? 1 + Math.abs(Math.sin(elapsed * 7.2)) * 0.02
    : mode === "thinking"
      ? 1 + Math.sin(elapsed * 2.1) * 0.012
      : 1;
  root.scale.setScalar(baseScale * scalePulse);

  const morphStrength = mode === "speaking"
    ? 0.18 + Math.abs(Math.sin(elapsed * 9.4)) * 0.82
    : mode === "listening"
      ? 0.12 + Math.abs(Math.sin(elapsed * 3.8)) * 0.18
      : 0;
  stateNodes.morphTargets.forEach(({ node, indices }) => {
    indices.forEach((index) => {
      node.morphTargetInfluences[index] = morphStrength;
    });
  });

  const emissiveBoost = mode === "speaking"
    ? 0.75 + Math.abs(Math.sin(elapsed * 6.4)) * 0.85
    : mode === "listening"
      ? 0.35 + Math.abs(Math.sin(elapsed * 3.2)) * 0.45
      : mode === "thinking"
        ? 0.28 + Math.abs(Math.sin(elapsed * 2.4)) * 0.4
        : 0.08 + Math.abs(Math.sin(elapsed * 1.2)) * 0.08;
  stateNodes.accentMaterials.forEach(({ material, baseIntensity }) => {
    material.emissiveIntensity = baseIntensity + emissiveBoost;
  });
}

async function mountBuddyModelViewer(container, modelUrl) {
  if (!container) return;
  if (buddyModelViewer?.modelUrl === modelUrl && buddyModelViewer.container === container) {
    resizeBuddyModelViewer();
    return;
  }
  destroyBuddyModelViewer();
  container.innerHTML = "";
  const status = document.createElement("div");
  status.className = "floating-buddy-model-status";
  status.textContent = t("avatar.loading3d");
  container.appendChild(status);
  try {
    const { THREE, GLTFLoader } = await loadBuddyThreeModules();
    if (!container.isConnected) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
    camera.position.set(0, 0.45, 3.2);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const hemi = new THREE.HemisphereLight(0xc7efff, 0x091420, 1.9);
    const key = new THREE.DirectionalLight(0xffffff, 2.6);
    key.position.set(2.8, 4.4, 3.6);
    const rim = new THREE.DirectionalLight(0x76d9ff, 1.6);
    rim.position.set(-2.4, 2.4, -1.2);
    scene.add(hemi, key, rim);

    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(modelUrl);
    if (!container.isConnected) return;
    const root = gltf.scene || gltf.scenes?.[0];
    if (!root) {
      throw new Error("GLB scene is empty.");
    }
    scene.add(root);

    const box = new THREE.Box3().setFromObject(root);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    root.position.sub(center);
    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const scale = 2.05 / maxDim;
    root.scale.setScalar(scale);
    root.position.y = -0.5;
    const stateNodes = {
      accentMaterials: collectBuddyAccentMaterials(root),
      baseScale: scale,
      baseY: -0.5,
      morphTargets: collectBuddyMorphTargets(root),
    };

    let mixer = null;
    if (Array.isArray(gltf.animations) && gltf.animations.length) {
      mixer = new THREE.AnimationMixer(root);
      gltf.animations.slice(0, 3).forEach((clip, index) => {
        const action = mixer.clipAction(clip);
        action.enabled = true;
        action.setEffectiveWeight(index === 0 ? 1 : 0.35);
        action.play();
      });
    }

    const clock = new THREE.Clock();
    buddyModelViewer = {
      THREE,
      camera,
      container,
      frameId: 0,
      mixer,
      modelUrl,
      renderer,
      root,
      scene,
      stateNodes,
    };
    const animate = () => {
      if (!buddyModelViewer || buddyModelViewer.modelUrl !== modelUrl) return;
      const delta = clock.getDelta();
      const elapsed = clock.elapsedTime;
      if (mixer) mixer.update(delta);
      const mode = currentBuddyMode();
      animateBuddyState(elapsed, mode, root, stateNodes);
      renderer.render(scene, camera);
      buddyModelViewer.frameId = requestAnimationFrame(animate);
    };
    resizeBuddyModelViewer();
    animate();
  } catch (error) {
    destroyBuddyModelViewer();
    container.innerHTML = `
      <div class="floating-buddy-model-status is-error">
        ${escapeHtml(t("avatar.load3dFailed", { error: String(error.message || error) }))}
      </div>
    `;
  }
}

function ensureFloatingBuddyStructure(shell, useCustomAvatar) {
  const avatarType = useCustomAvatar ? "custom" : "house";
  if (shell.dataset.avatarType === avatarType) return;
  destroyBuddyModelViewer();
  shell.dataset.avatarType = avatarType;
  shell.innerHTML = `
    <div class="floating-buddy">
      <div class="floating-buddy-bubble">
        <strong data-buddy-name></strong>
        <em data-buddy-subtitle></em>
        <span data-buddy-preview></span>
      </div>
      <div class="floating-buddy-avatar">
        ${useCustomAvatar
          ? `<div class="floating-buddy-model-shell"><div class="floating-buddy-model-stage"></div></div>`
          : `<div class="floating-buddy-svg-stage"></div>`}
      </div>
    </div>
  `;
}

function renderFloatingBuddy() {
  const shell = document.getElementById("floating-buddy");
  if (!shell) return;
  const spoken = document.getElementById("spoken-line")?.textContent?.trim() || "";
  const preview = spoken && spoken !== t("voice.noConversation")
    ? spoken.slice(0, 54)
    : buddyPromptForTab();
  const buddyName = buddyDisplayName();
  const pose = buddyPoseForTab();
  const mode = currentBuddyMode();
  const avatar = getAssistantAvatarConfig();
  const useCustomAvatar = shouldRenderCustomBuddy();
  ensureFloatingBuddyStructure(shell, useCustomAvatar);
  const buddy = shell.querySelector(".floating-buddy");
  if (!buddy) return;
  buddy.className = `floating-buddy is-${mode} pose-${pose}`;
  const nameNode = shell.querySelector("[data-buddy-name]");
  const subtitleNode = shell.querySelector("[data-buddy-subtitle]");
  const previewNode = shell.querySelector("[data-buddy-preview]");
  if (nameNode) nameNode.textContent = buddyName;
  if (subtitleNode) subtitleNode.textContent = buddySubtitleForTab();
  if (previewNode) previewNode.textContent = preview;
  if (useCustomAvatar) {
    const stage = shell.querySelector(".floating-buddy-model-stage");
    if (stage) {
      void mountBuddyModelViewer(stage, avatar.customModelUrl);
    }
  } else {
    const svgStage = shell.querySelector(".floating-buddy-svg-stage");
    if (svgStage) {
      svgStage.innerHTML = mascotSvg(mode, pose);
    }
  }
  if (buddyDragState.x !== null && buddyDragState.y !== null) {
    shell.style.right = "auto";
    shell.style.bottom = "auto";
    shell.style.left = `${buddyDragState.x}px`;
    shell.style.top = `${buddyDragState.y}px`;
  }
}

function loadBuddyPosition() {
  try {
    const raw = localStorage.getItem("homehubBuddyPosition");
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (typeof parsed.x === "number" && typeof parsed.y === "number") {
      buddyDragState.x = parsed.x;
      buddyDragState.y = parsed.y;
    }
  } catch {}
}

function persistBuddyPosition() {
  try {
    if (buddyDragState.x !== null && buddyDragState.y !== null) {
      localStorage.setItem("homehubBuddyPosition", JSON.stringify({ x: buddyDragState.x, y: buddyDragState.y }));
    }
  } catch {}
}

function clampBuddyPosition(x, y, shell) {
  const width = shell.offsetWidth || 480;
  const height = shell.offsetHeight || 260;
  const maxX = Math.max(12, window.innerWidth - width - 12);
  const maxY = Math.max(12, window.innerHeight - height - 12);
  return {
    x: Math.min(Math.max(12, x), maxX),
    y: Math.min(Math.max(12, y), maxY),
  };
}

function statCard(label, value, meta = "", icon = "status", className = "") {
  return `
    <div class="stat-card ${className}">
      <div class="stat-card-head">
        <span class="stat-icon">${iconSvg(icon)}</span>
        <span>${label}</span>
      </div>
      <strong>${value}</strong>
      ${meta ? `<small class="stat-meta">${meta}</small>` : ""}
    </div>
  `;
}

function getSelectedProviders() {
  return latestDashboard?.audioProviders?.selected || { stt: "google", tts: "google" };
}

function localizeInline(zh, ja, en) {
  if (currentLocale === "zh-CN") return zh;
  if (currentLocale === "ja-JP") return ja;
  return en;
}

function buildHomeWorkspaceSummary(data) {
  const assistantMemory = data?.assistantMemory || {};
  const dueReminders = Array.isArray(assistantMemory.dueReminders) ? assistantMemory.dueReminders : [];
  const pendingReminders = Array.isArray(assistantMemory.pendingReminders) ? assistantMemory.pendingReminders : [];
  const upcomingEvents = Array.isArray(assistantMemory.upcomingEvents) ? assistantMemory.upcomingEvents : [];
  const customAgents = Array.isArray(data?.customAgents) ? data.customAgents : [];
  const collectingAgents = customAgents.filter((item) => ["collecting", "review"].includes(String(item?.status || "")));
  const completedAgents = customAgents.filter((item) => String(item?.status || "") === "complete");
  const features = Array.isArray(data?.features) ? data.features : [];
  const conversation = Array.isArray(data?.conversation) ? data.conversation : [];
  const externalChannels = data?.externalChannels || {};
  const apps = externalChannels.apps || {};
  const mail = externalChannels.mail || {};
  const weather = data?.weather || {};
  const lineInbox = Array.isArray(apps?.line?.inbox) ? apps.line.inbox.length : 0;
  const wechatInbox = Array.isArray(apps?.wechatOfficial?.inbox) ? apps.wechatOfficial.inbox.length : 0;
  const mailInbox = Array.isArray(mail?.inbox) ? mail.inbox.length : 0;
  const inboundCount = lineInbox + wechatInbox + mailInbox;
  const hasWeather = weather && weather.temperatureC !== null && weather.temperatureC !== undefined && weather.location;
  const hour = new Date().getHours();
  const greeting = currentLocale === "zh-CN"
    ? (hour < 12 ? "早上好，HomeHub 已经准备好了。" : hour < 18 ? "下午好，HomeHub 正在待命。" : "晚上好，HomeHub 已经在线。")
    : currentLocale === "ja-JP"
      ? (hour < 12 ? "おはようございます。HomeHub の準備ができています。" : hour < 18 ? "こんにちは。HomeHub は待機中です。" : "こんばんは。HomeHub はオンラインです。")
      : (hour < 12 ? "Good morning. HomeHub is ready." : hour < 18 ? "Good afternoon. HomeHub is standing by." : "Good evening. HomeHub is online.");

  let focusTitle = localizeInline("系统待命中", "待機中です", "System is ready");
  let focusSummary = localizeInline("可以直接提问、创建提醒，或者开始新的蓝图。", "質問、リマインダー作成、新しいブループリント作成をそのまま始められます。", "You can ask a question, create a reminder, or start a new blueprint right away.");

  if (dueReminders.length) {
    focusTitle = localizeInline("有提醒到时间了", "今すぐ処理すべきリマインダーがあります", "A reminder is due now");
    focusSummary = localizeInline(
      `当前最紧急的是“${dueReminders[0].title || "提醒"}”。进入交流区后可以直接完成它。`,
      `最優先は「${dueReminders[0].title || "リマインダー"}」です。会話タブですぐに処理できます。`,
      `The most urgent item is "${dueReminders[0].title || "Reminder"}". Open Exchange to complete it.`
    );
  } else if (collectingAgents.length) {
    focusTitle = localizeInline("有蓝图还在收集中", "収集中のブループリントがあります", "A blueprint is still in progress");
    focusSummary = localizeInline(
      `“${collectingAgents[0].name || "未命名蓝图"}” 还没有完成确认，继续补充后就可以生成 feature。`,
      `「${collectingAgents[0].name || "無題のブループリント"}」はまだ確認前です。続きを補えば feature を生成できます。`,
      `"${collectingAgents[0].name || "Untitled blueprint"}" still needs confirmation before feature generation.`
    );
  } else if (pendingReminders.length) {
    focusTitle = localizeInline("今天已有待处理提醒", "今日のリマインダーがあります", "There are reminders queued");
    focusSummary = localizeInline(
      `接下来是“${pendingReminders[0].title || "提醒"}”，时间 ${formatReminderTimestamp(pendingReminders[0].triggerAt)}。`,
      `次は「${pendingReminders[0].title || "リマインダー"}」、時刻は ${formatReminderTimestamp(pendingReminders[0].triggerAt)} です。`,
      `Next up is "${pendingReminders[0].title || "Reminder"}" at ${formatReminderTimestamp(pendingReminders[0].triggerAt)}.`
    );
  } else if (upcomingEvents.length) {
    focusTitle = localizeInline("本地日程已经排好", "ローカル予定が入っています", "Local schedule is active");
    focusSummary = localizeInline(
      `下一项安排是“${upcomingEvents[0].title || "事件"}”，时间 ${formatReminderTimestamp(upcomingEvents[0].startAt || upcomingEvents[0].triggerAt)}。`,
      `次の予定は「${upcomingEvents[0].title || "イベント"}」、時刻は ${formatReminderTimestamp(upcomingEvents[0].startAt || upcomingEvents[0].triggerAt)} です。`,
      `The next event is "${upcomingEvents[0].title || "Event"}" at ${formatReminderTimestamp(upcomingEvents[0].startAt || upcomingEvents[0].triggerAt)}.`
    );
  } else if (hasWeather) {
    focusTitle = localizeInline("当前天气已经同步", "現在の天気が同期されています", "Weather is synced");
    focusSummary = localizeInline(
      `${weather.location} 当前 ${weather.condition}，${weather.temperatureC}°C。你可以继续追问温度、体感或出行建议。`,
      `${weather.location} は現在 ${weather.condition}、${weather.temperatureC}°C です。体感や外出の相談も続けてできます。`,
      `${weather.location} is currently ${weather.condition} at ${weather.temperatureC}°C. You can follow up with travel or outfit questions.`
    );
  } else if (inboundCount) {
    focusTitle = localizeInline("外部通道有新动态", "外部チャネルに動きがあります", "External channels have activity");
    focusSummary = localizeInline(
      `目前共有 ${inboundCount} 条外部收件，设置页可以继续配置邮件、LINE 或微信桥接。`,
      `現在 ${inboundCount} 件の外部受信があります。設定タブでメール、LINE、WeChat 連携を続けて設定できます。`,
      `There are ${inboundCount} inbound external items. Configure mail, LINE, or WeChat from Settings.`
    );
  }

  const featureNames = features.map((item) => item?.name).filter(Boolean).slice(0, 3);
  const cards = [
    {
      id: "overview-home",
      label: localizeInline("提醒", "リマインダー", "Reminders"),
      value: dueReminders.length
        ? localizeInline(`${dueReminders.length} 个到点提醒`, `${dueReminders.length} 件の期限リマインダー`, `${dueReminders.length} due reminders`)
        : pendingReminders.length
          ? localizeInline(`${pendingReminders.length} 条待处理`, `${pendingReminders.length} 件の待機中`, `${pendingReminders.length} queued`)
          : "0",
      meta: dueReminders.length
        ? (dueReminders[0].title || localizeInline("提醒", "リマインダー", "Reminder"))
        : pendingReminders.length
          ? localizeInline("当前没有到点提醒", "期限の通知はまだありません", "No reminder is due yet")
          : localizeInline("当前没有待处理提醒", "現在保留中の通知はありません", "No active reminders"),
      state: dueReminders.length ? "attention" : (pendingReminders.length ? "active" : "ready"),
      buttonLabel: localizeInline("进入交流", "会話へ", "Open Exchange"),
      tab: "exchange",
    },
    {
      id: "overview-blueprints",
      label: localizeInline("蓝图", "ブループリント", "Blueprints"),
      value: localizeInline(`${completedAgents.length} 已创建 / ${collectingAgents.length} 创建中`, `${completedAgents.length} 作成済み / ${collectingAgents.length} 作成中`, `${completedAgents.length} created / ${collectingAgents.length} in progress`),
      meta: collectingAgents.length
        ? localizeInline("继续补字段，确认后即可生成 feature。", "項目を補い、確認後に feature を生成できます。", "Finish the missing fields, then generate a feature.")
        : localizeInline("可以直接从语音开始新的业务蓝图。", "音声から新しい業務ブループリントを始められます。", "You can start a new business blueprint by voice."),
      state: collectingAgents.length ? "attention" : (completedAgents.length ? "active" : "ready"),
      buttonLabel: localizeInline("打开蓝图", "ブループリントを開く", "Open Blueprints"),
      tab: "blueprints",
    },
    {
      id: "overview-channels",
      label: localizeInline("通道", "チャネル", "Channels"),
      value: localizeInline(`${inboundCount} 条收件`, `${inboundCount} 件の受信`, `${inboundCount} inbound`),
      meta: localizeInline(
        `LINE ${lineInbox} / 微信 ${wechatInbox} / 邮件 ${mailInbox}`,
        `LINE ${lineInbox} / WeChat ${wechatInbox} / Mail ${mailInbox}`,
        `LINE ${lineInbox} / WeChat ${wechatInbox} / Mail ${mailInbox}`
      ),
      state: inboundCount ? "active" : "ready",
      buttonLabel: localizeInline("打开设置", "設定を開く", "Open Settings"),
      tab: "settings",
    },
  ];

  return { greeting, focusTitle, focusSummary, cards };
}

function applyStaticTranslations() {
  document.documentElement.lang = currentLocale;
  document.title = t("metaTitle");
  setTextIfPresent("brand-eyebrow", t("brandEyebrow"));
  setTextIfPresent("tab-home", t("tabs.home"));
  setTextIfPresent("tab-exchange", t("tabs.exchange"));
  setTextIfPresent("tab-work", t("tabs.work"));
  setTextIfPresent("tab-cortex", t("tabs.cortex"));
  setTextIfPresent("tab-blueprints", t("tabs.blueprints"));
  setTextIfPresent("tab-agents", t("tabs.agents"));
  setTextIfPresent("tab-settings", t("tabs.settings"));
  setTextIfPresent("home-assistant-title", localizeInline("当前能力", "現在の能力", "Current Capabilities"));
  setTextIfPresent("home-assistant-pill", localizeInline("可直接使用", "すぐ使える", "Ready Now"));
  setTextIfPresent("home-dev-title", localizeInline("最近动态", "最近の動き", "Recent Activity"));
  setTextIfPresent("home-dev-pill", localizeInline("真实运行", "実行中", "Live Feed"));
  setTextIfPresent("agents-title", t("top.parallelAgents"));
  setTextIfPresent("agents-pill", t("top.coreEngine"));
  setTextIfPresent("models-skills-title", t("top.modelsSkills"));
  setTextIfPresent("models-skills-pill", t("top.extensible"));
  setTextIfPresent("models-title", t("top.models"));
  setTextIfPresent("skills-title", t("top.skills"));
  setTextIfPresent("voice-title", t("top.voiceSession"));
  setTextIfPresent("voice-pill", "STT / TTS");
  setTextIfPresent("voice-guidance", t("voice.guidance"));
  setTextIfPresent("conversation-title", t("voice.onScreenConversation"));
  setTextIfPresent("conversation-pill", t("top.transcript"));
  setTextIfPresent("test-title", t("top.testLab"));
  setTextIfPresent("test-pill", currentLocale === "zh-CN" ? "语音 / 文字 / 文件" : currentLocale === "ja-JP" ? "音声 / テキスト / ファイル" : "Voice / Text / Files");
  setTextIfPresent("test-doc-summary-pick", currentLocale === "zh-CN" ? "文档总结" : currentLocale === "ja-JP" ? "文書要約" : "Document Summary");
  setTextIfPresent("test-doc-translate-pick", currentLocale === "zh-CN" ? "文档翻译" : currentLocale === "ja-JP" ? "文書翻訳" : "Document Translation");
  setTextIfPresent("work-title", t("top.workLab"));
  setTextIfPresent("work-pill", t("top.workBoard"));
  setTextIfPresent("work-factory-title", t("top.workFactory"));
  setTextIfPresent("work-factory-pill", currentLocale === "zh-CN" ? "技能 / 智能体流水线" : currentLocale === "ja-JP" ? "スキル / エージェント ライン" : "Skill / Agent Pipeline");
  setTextIfPresent("work-guidance", currentLocale === "zh-CN"
    ? "左边追踪用户请求，右边观察技能和智能体如何被唤醒、执行与完成。"
    : currentLocale === "ja-JP"
      ? "左側で依頼一覧を追い、右側でスキルとエージェントが起動・実行・完了する流れを見ます。"
      : "Track incoming requests on the left and watch skills and agents wake up, run, and finish on the right.");
  setTextIfPresent("test-blueprints-title", t("top.blueprintStudio"));
  setTextIfPresent("test-blueprints-pill", t("test.storageTag"));
  setTextIfPresent("test-blueprints-guidance", t("test.blueprintsGuidance"));
  const testInput = document.getElementById("test-input");
  if (testInput) testInput.placeholder = t("test.inputPlaceholder");
  setTextIfPresent("test-send", t("test.send"));
  setTextIfPresent("test-generate-feature", customAgentStudio.isGenerating ? t("test.generating") : t("test.generate"));
  setTextIfPresent("settings-directory-title", t("tabs.settings"));
  setTextIfPresent("settings-directory-pill", currentLocale === "zh-CN" ? "目录" : currentLocale === "ja-JP" ? "一覧" : "Directory");
  setTextIfPresent("dock-eyebrow", t("top.conversationDock"));
  setTextIfPresent("dock-title", t("top.currentRequest"));
  setTextIfPresent("reminder-eyebrow", t("reminder.eyebrow"));
  syncReminderButtonState();
  const micCore = document.querySelector("#mic-orb .mic-core");
  if (micCore && !isRecording) micCore.textContent = t("voice.micIdle");
}

function renderClock() {
  const now = new Date();
  setTextIfPresent("clock-time", now.toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" }));
  setTextIfPresent("clock-date", now.toLocaleDateString(currentLocale, { weekday: "short", month: "short", day: "numeric" }));
}

function renderStatusStrip(data) {
  const strip = document.getElementById("status-strip");
  const micStatus = document.getElementById("mic-status");
  if (!strip || !micStatus) return;
  const hasWeather = data.weather && data.weather.temperatureC !== null && data.weather.temperatureC !== undefined && data.weather.location;
  const weatherValue = hasWeather ? `${data.weather.condition} ${data.weather.temperatureC}°C` : (currentLocale === "zh-CN" ? "等待定位" : currentLocale === "ja-JP" ? "位置情報待機中" : "Waiting for location");
  const weatherMeta = hasWeather
    ? `${data.weather.location} · ${data.weather.highC}° / ${data.weather.lowC}°${data.weather.gpsEnabled ? " · GPS" : ""}`
    : (currentLocale === "zh-CN" ? "允许定位后自动刷新" : currentLocale === "ja-JP" ? "位置情報を許可すると自動更新します" : "Allow location access to refresh automatically");
  const nextReminder = data.assistantMemory?.dueReminders?.[0] || data.assistantMemory?.pendingReminders?.[0];
  const tipValue = nextReminder ? nextReminder.title : t("status.remoteReady");
  const tipMeta = nextReminder ? nextReminder.triggerAt.replace("T", " ") : "Directional navigation enabled";
  strip.innerHTML = `
    ${statCard(t("status.status"), localizeMode(data.systemStatus.mode), "Voice link active", "status", "status-card status-card-status")}
    ${statCard(t("status.weather"), weatherValue, weatherMeta, "weather", "status-card status-card-weather")}
    ${statCard(t("status.box"), data.systemStatus.boxHealth, "Living room runtime", "box", "status-card status-card-box")}
    ${statCard(t("status.tip"), tipValue, tipMeta, "tip", "status-card status-card-tip")}
  `;
  micStatus.textContent = localizeMode(data.systemStatus.mode);
}

function formatReminderTimestamp(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).replace("T", " ");
  }
  return parsed.toLocaleString(currentLocale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function buildReminderSpeech(reminder) {
  const title = reminder?.title || "";
  const localePrefix = t("reminder.voicePrefix");
  if (currentLocale === "zh-CN") {
    return `${localePrefix}，现在该${title}了。`;
  }
  if (currentLocale === "ja-JP") {
    return `${localePrefix}。${title}の時間です。`;
  }
  return `${localePrefix}: it is time to ${title}.`;
}

function syncReminderButtonState() {
  const completeButton = document.getElementById("reminder-complete");
  const overlay = document.getElementById("reminder-overlay");
  if (!completeButton) return;
  completeButton.disabled = isCompletingReminder;
  completeButton.setAttribute("aria-busy", isCompletingReminder ? "true" : "false");
  completeButton.textContent = isCompletingReminder ? t("reminder.completing") : t("reminder.markComplete");
  if (overlay) {
    overlay.classList.toggle("is-processing", isCompletingReminder);
  }
}

function speakWithHomeHub(text, lang = currentLocale) {
  if (!("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = 1;
  utterance.pitch = 1;
  isBuddySpeaking = true;
  if (buddySpeechTimer) clearTimeout(buddySpeechTimer);
  renderFloatingBuddy();
  utterance.onend = () => {
    isBuddySpeaking = false;
    renderFloatingBuddy();
  };
  window.speechSynthesis.speak(utterance);
  buddySpeechTimer = setTimeout(() => {
    isBuddySpeaking = false;
    renderFloatingBuddy();
  }, 4200);
}

function renderReminderOverlay(data) {
  const overlay = document.getElementById("reminder-overlay");
  const reminderTitle = document.getElementById("reminder-title");
  const reminderTime = document.getElementById("reminder-time");
  const reminderNotes = document.getElementById("reminder-notes");
  const dueReminder = data.assistantMemory?.dueReminders?.[0] || null;
  if (!overlay || !reminderTitle || !reminderTime || !reminderNotes) return;
  if (!dueReminder) {
    overlay.hidden = true;
    activeReminderId = null;
    return;
  }

  activeReminderId = dueReminder.id;
  overlay.hidden = false;
  reminderTitle.textContent = dueReminder.title || t("reminder.dueNow");
  reminderTime.textContent = `${t("reminder.dueNow")} · ${formatReminderTimestamp(dueReminder.triggerAt)}`;
  reminderNotes.textContent = dueReminder.notes || t("reminder.noNotes");
  const completeButton = document.getElementById("reminder-complete");
  syncReminderButtonState();
  requestAnimationFrame(() => {
    if (!overlay.hidden && !isCompletingReminder) completeButton.focus();
  });

  if (announcedReminderId !== dueReminder.id) {
    announcedReminderId = dueReminder.id;
    const spoken = buildReminderSpeech(dueReminder);
    updateSpokenLine(`${localizeSpeaker("HomeHub")}: ${spoken}`);
    speakWithHomeHub(spoken);
  }
}

function getCurrentLanguage(data) {
  const supported = data.languageSettings?.supported || [];
  return supported.find((item) => item.code === currentLocale) || supported[0] || null;
}

function renderHero(data) {
  const hero = document.getElementById("hero");
  if (!hero) return;
  const homeSummary = buildHomeWorkspaceSummary(data);
  const reminderCount = (data.assistantMemory?.pendingReminders || []).length + (data.assistantMemory?.dueReminders || []).length;
  const collectingCount = (data.customAgents || []).filter((item) => ["collecting", "review"].includes(String(item?.status || ""))).length;
  const inboundCount = (data.externalChannels?.apps?.line?.inbox || []).length
    + (data.externalChannels?.apps?.wechatOfficial?.inbox || []).length
    + (data.externalChannels?.mail?.inbox || []).length;
  hero.innerHTML = `
    <div class="hero-copy">
      <p class="eyebrow">${t("brandEyebrow")}</p>
      <h2 class="hero-title">${data.hero.title}</h2>
      <p class="tagline">${homeSummary.greeting}</p>
      <p class="hero-focus">${homeSummary.focusTitle}</p>
      <div class="hero-mini-tabs" aria-label="${localizeInline("首页状态概览", "ホーム状態の概要", "Home status summary")}">
        ${homeSummary.cards.map((card) => `
          <button type="button" class="hero-mini-tab remote-target ${stateColor[card.state] || "is-ready"}" data-tab="${escapeHtml(card.tab || "home")}">
            <span class="hero-mini-tab-label">${escapeHtml(card.label)}</span>
            <strong class="hero-mini-tab-value">${escapeHtml(String(card.value || "-"))}</strong>
            <small class="hero-mini-tab-meta">${escapeHtml(String(card.meta || ""))}</small>
          </button>
        `).join("")}
      </div>
      <div class="hero-actions">
        <button type="button" class="hero-action-button is-primary remote-target" data-tab="exchange">${localizeInline("开始交流", "会話を始める", "Start Exchange")}</button>
        <button type="button" class="hero-action-button remote-target" data-tab="blueprints">${localizeInline("创建蓝图", "ブループリント作成", "Create Blueprint")}</button>
      </div>
      <div class="hero-ambient" aria-hidden="true">
        <svg viewBox="0 0 420 120" class="hero-wave">
          <defs>
            <linearGradient id="heroLine" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stop-color="rgba(85,208,177,0.0)" />
              <stop offset="35%" stop-color="rgba(85,208,177,0.9)" />
              <stop offset="100%" stop-color="rgba(101,182,255,0.0)" />
            </linearGradient>
          </defs>
          <path d="M0 76 C48 70, 78 40, 122 46 S203 103, 255 82 S343 40, 420 54" fill="none" stroke="url(#heroLine)" stroke-width="4" stroke-linecap="round"/>
        </svg>
      </div>
    </div>
    <div class="hero-meta">
      ${statCard(localizeInline("提醒", "リマインダー", "Reminders"), String(reminderCount), reminderCount ? localizeInline("已进入本地提醒链路", "ローカル通知チェーンで管理中", "Managed by the local reminder chain") : localizeInline("当前没有待处理提醒", "現在保留中のリマインダーはありません", "No queued reminders right now"), "tip")}
      ${statCard(localizeInline("蓝图", "ブループリント", "Blueprints"), String(collectingCount), collectingCount ? localizeInline("仍有创建中的业务蓝图", "作成途中のブループリントがあります", "There are still blueprints in progress") : localizeInline("当前没有未完成蓝图", "未完了のブループリントはありません", "No unfinished blueprints"), "status")}
      ${statCard(localizeInline("通道", "チャネル", "Channels"), String(inboundCount), localizeInline(`${data.boxProfile.networkState} · ${data.boxProfile.pairedClients} 设备`, `${data.boxProfile.networkState} · ${data.boxProfile.pairedClients} 台`, `${data.boxProfile.networkState} · ${data.boxProfile.pairedClients} devices`), "box")}
    </div>
  `;
}

function renderHomeOverview(data) {
  const container = document.getElementById("home-overview");
  if (!container) return;
  container.innerHTML = "";
}

function renderTimeline(events) {
  const timeline = document.getElementById("timeline");
  if (!timeline) return;
  if (!Array.isArray(events) || !events.length) {
    timeline.innerHTML = `<div class="timeline-log-empty">${localizeInline("HomeHub 已准备好，新的交流、邮件、外部设备和处理记录会持续显示在这里。", "HomeHub の準備ができました。新しい会話、メール、外部デバイス、処理ログがここに流れます。", "HomeHub is ready. New conversations, mail, external device events, and processing logs will appear here.")}</div>`;
    return;
  }
  timeline.innerHTML = events.slice().reverse().map((item) => translateItem(item, timelineTranslations)).map((event) => `
    <div class="timeline-log-line" tabindex="0">
      <span class="timeline-log-time">${escapeHtml(event.time || "")}</span>
      <span class="timeline-log-title">${escapeHtml(event.title || "")}</span>
      <span class="timeline-log-detail">${escapeHtml(event.detail || "")}</span>
    </div>
  `).join("");
  requestAnimationFrame(() => syncAllManagedScrollContainers());
}

function renderModules(modules) {
  const container = document.getElementById("modules");
  if (!container) return;
  const data = latestDashboard || {};
  const weather = data.weather || {};
  const hasWeather = weather && weather.temperatureC !== null && weather.temperatureC !== undefined && weather.location;
  const assistantMemory = data.assistantMemory || {};
  const pendingReminders = Array.isArray(assistantMemory.pendingReminders) ? assistantMemory.pendingReminders : [];
  const dueReminders = Array.isArray(assistantMemory.dueReminders) ? assistantMemory.dueReminders : [];
  const upcomingEvents = Array.isArray(assistantMemory.upcomingEvents) ? assistantMemory.upcomingEvents : [];
  const customAgents = Array.isArray(data.customAgents) ? data.customAgents : [];
  const collectingAgents = customAgents.filter((item) => ["collecting", "review"].includes(String(item?.status || "")));
  const completedAgents = customAgents.filter((item) => String(item?.status || "") === "complete");
  const featureNames = Array.isArray(data.features) ? data.features.map((item) => item?.name).filter(Boolean) : [];
  const externalChannels = data.externalChannels || {};
  const externalApps = externalChannels.apps || {};
  const lineInbox = Array.isArray(externalApps?.line?.inbox) ? externalApps.line.inbox.length : 0;
  const wechatInbox = Array.isArray(externalApps?.wechatOfficial?.inbox) ? externalApps.wechatOfficial.inbox.length : 0;
  const mailInbox = Array.isArray(externalChannels?.mail?.inbox) ? externalChannels.mail.inbox.length : 0;
  const latestConversation = Array.isArray(data.conversation) ? data.conversation.slice(-1)[0] : null;
  const allModules = [
    {
      id: "weather-live",
      name: currentLocale === "zh-CN" ? "实时天气" : currentLocale === "ja-JP" ? "ライブ天気" : "Live Weather",
      summary: hasWeather
        ? `${weather.location || "-"} · ${weather.condition || "-"} · ${weather.temperatureC ?? "-"}°C`
        : localizeInline("等待浏览器定位天气", "ブラウザの位置情報を待っています", "Waiting for browser location weather"),
      actionLabel: localizeInline("去交流里继续追问天气", "会話で天気の続きを聞く", "Ask follow-up weather questions in Exchange"),
      buttonLabel: localizeInline("进入交流", "会話へ", "Open Exchange"),
      buttonTab: "exchange",
      state: hasWeather ? "active" : "ready",
    },
    {
      id: "schedule-live",
      name: localizeInline("本地提醒与日程", "ローカル予定と通知", "Local Schedule and Reminders"),
      summary: dueReminders.length
        ? localizeInline(`当前有 ${dueReminders.length} 条提醒到时间，最紧急的是 ${dueReminders[0].title || "提醒"}。`, `現在 ${dueReminders.length} 件のリマインダーが期限です。最優先は ${dueReminders[0].title || "リマインダー"} です。`, `${dueReminders.length} reminders are due now. Next up: ${dueReminders[0].title || "Reminder"}.`)
        : pendingReminders.length
          ? localizeInline(`已有 ${pendingReminders.length} 条待处理提醒，下一条在 ${formatReminderTimestamp(pendingReminders[0].triggerAt)}。`, `${pendingReminders.length} 件のリマインダーがあります。次は ${formatReminderTimestamp(pendingReminders[0].triggerAt)} です。`, `${pendingReminders.length} reminders are queued. Next at ${formatReminderTimestamp(pendingReminders[0].triggerAt)}.`)
          : upcomingEvents.length
            ? localizeInline(`最近的本地安排是 ${upcomingEvents[0].title || "事件"}。`, `次のローカル予定は ${upcomingEvents[0].title || "イベント"} です。`, `The next local event is ${upcomingEvents[0].title || "Event"}.`)
            : localizeInline("还没有本地提醒或日程，可以直接用语音创建。", "ローカル予定や通知はまだありません。音声ですぐ作成できます。", "No local reminders or events yet. Create one by voice."),
      actionLabel: localizeInline("提醒我今晚八点联系家人", "今夜8時に家族へ連絡するよう通知して", "Remind me at 8 PM to contact my family"),
      buttonLabel: localizeInline("进入交流", "会話へ", "Open Exchange"),
      buttonTab: "exchange",
      state: dueReminders.length ? "attention" : (pendingReminders.length || upcomingEvents.length ? "active" : "ready"),
    },
    {
      id: "conversation-live",
      name: localizeInline("交流工作区", "会話ワークスペース", "Conversation Workspace"),
      summary: latestConversation
        ? localizeInline(`最近一条是 ${latestConversation.speaker === "You" ? "你" : "HomeHub"}：${String(latestConversation.text || "").slice(0, 48)}`, `直近は ${latestConversation.speaker === "You" ? "あなた" : "HomeHub"}：${String(latestConversation.text || "").slice(0, 48)}`, `Latest line: ${String(latestConversation.text || "").slice(0, 56)}`)
        : localizeInline("还没有开始交流，可以先问天气、航班或创建智能体。", "まだ会話がありません。天気、フライト、ブループリント作成から始められます。", "No conversation yet. Start with weather, flights, or blueprint creation."),
      actionLabel: localizeInline("你好", "こんにちは", "Hello"),
      buttonLabel: localizeInline("打开交流", "会話を開く", "Open Exchange"),
      buttonTab: "exchange",
      state: latestConversation ? "active" : "ready",
    },
    {
      id: "blueprint-live",
      name: localizeInline("蓝图工作室", "ブループリント工房", "Blueprint Studio"),
      summary: collectingAgents.length
        ? localizeInline(`当前有 ${collectingAgents.length} 个蓝图尚未完成，最近的是 ${collectingAgents[0].name || "未命名蓝图"}。`, `現在 ${collectingAgents.length} 件のブループリントが未完了です。最新は ${collectingAgents[0].name || "無題のブループリント"} です。`, `${collectingAgents.length} blueprints are still in progress. Latest: ${collectingAgents[0].name || "Untitled blueprint"}.`)
        : completedAgents.length
          ? localizeInline(`当前已有 ${completedAgents.length} 个已创建蓝图，可以继续生成或查看 feature。`, `現在 ${completedAgents.length} 件の作成済みブループリントがあります。feature 生成や確認を続けられます。`, `${completedAgents.length} blueprints have already been created. You can inspect or generate features.`)
          : localizeInline("还没有业务蓝图，可以直接从需求描述开始创建。", "業務ブループリントはまだありません。要件を話せばそのまま作成できます。", "No business blueprints yet. Start by describing the workflow you want."),
      actionLabel: localizeInline("创建智能体，名称为提醒", "エージェントを作成、名前はリマインダー", "Create an agent named Reminder"),
      buttonLabel: localizeInline("打开蓝图", "ブループリントを開く", "Open Blueprints"),
      buttonTab: "blueprints",
      state: collectingAgents.length ? "attention" : (completedAgents.length ? "active" : "ready"),
    },
    {
      id: "features-live",
      name: localizeInline("功能运行", "機能ランタイム", "Feature Runtime"),
      summary: featureNames.length
        ? localizeInline(`当前已加载 ${featureNames.length} 个功能：${featureNames.slice(0, 3).join(" / ")}`, `現在 ${featureNames.length} 個の機能を読込済み：${featureNames.slice(0, 3).join(" / ")}`, `${featureNames.length} features are loaded: ${featureNames.slice(0, 3).join(" / ")}`)
        : localizeInline("当前只有 HomeHub 核心能力，还没有新生成的业务 feature。", "現在は HomeHub の中核機能のみで、新しく生成した business feature はありません。", "Only the HomeHub core capabilities are loaded right now."),
      actionLabel: localizeInline("查看当前智能体和功能运行状态", "現在のエージェントと機能状態を見る", "Inspect the current agent and feature runtime"),
      buttonLabel: localizeInline("查看智能体", "エージェントを見る", "View Agents"),
      buttonTab: "agents",
      state: featureNames.length ? "active" : "ready",
    },
  ];
  container.innerHTML = allModules.map((item) => {
    const localized = moduleTranslations[item.id]?.[currentLocale] || {};
    return {
      ...item,
      name: localized.name || item.name,
      summary: localized.summary || item.summary,
      actionLabel: localized.actionLabel || item.actionLabel
    };
  }).map((module) => `
      <div class="module-card ${stateColor[module.state] || "is-ready"} remote-target focusable-card" tabindex="0" data-action-text="${escapeHtml(module.actionLabel)}" data-title="${escapeHtml(module.name)}">
        <div class="dot ${stateColor[module.state] || "is-muted"}"></div>
        <div>
          <strong>${module.name}</strong>
        <p>${module.summary}</p>
      </div>
      <button type="button" class="remote-target" ${module.buttonTab ? `data-tab="${escapeHtml(module.buttonTab)}"` : ""}>${escapeHtml(module.buttonLabel || module.actionLabel)}</button>
    </div>
  `).join("");
  requestAnimationFrame(() => syncAllManagedScrollContainers());
}

async function syncDeviceWeatherFromBrowser(force = false) {
  if (!navigator.geolocation || deviceWeatherSyncState.inFlight) return;
  const weather = latestDashboard?.weather || {};
  const shouldSync = force
    || !weather.gpsEnabled
    || !deviceWeatherSyncState.attempted
    || (Date.now() - deviceWeatherSyncState.lastSyncAt > 30 * 60 * 1000);
  if (!shouldSync) return;
  deviceWeatherSyncState.inFlight = true;
  deviceWeatherSyncState.attempted = true;
  try {
    const position = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: false,
        timeout: 8000,
        maximumAge: 15 * 60 * 1000,
      });
    });
    const response = await fetch("/api/device/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to update weather");
    }
    deviceWeatherSyncState.lastSyncAt = Date.now();
    await loadDashboard();
  } catch (error) {
    console.warn("GPS weather sync failed.", error);
  } finally {
    deviceWeatherSyncState.inFlight = false;
  }
}

function renderAgents(agents) {
  const container = document.getElementById("agents");
  if (!container) return;
  if (!Array.isArray(agents) || !agents.length) {
    container.innerHTML = `<div class="settings-card"><p>${currentLocale === "zh-CN" ? "当前还没有可展示的业务智能体运行数据。" : currentLocale === "ja-JP" ? "現在表示できる業務エージェント実行データはありません。" : "No live business agent activity is available yet."}</p></div>`;
    const detail = document.getElementById("agent-runtime-detail");
    const timeline = document.getElementById("agent-runtime-timeline");
    if (detail) detail.innerHTML = "";
    if (timeline) timeline.innerHTML = "";
    return;
  }
  const localizedAgents = agents.map((item) => translateItem(item, agentTranslations));
  const selectedAgent = localizedAgents.find((item) => item.id === activeRuntimeAgentId) || localizedAgents[0];
  if (selectedAgent && activeRuntimeAgentId !== selectedAgent.id) activeRuntimeAgentId = selectedAgent.id;
  container.innerHTML = localizedAgents.map((agent) => `
    <div class="agent-card remote-target focusable-card" tabindex="0" data-title="${escapeHtml(agent.name)}">
      <button type="button" class="agent-card-hitbox remote-target" data-runtime-agent-id="${escapeHtml(agent.id)}" data-title="${escapeHtml(agent.name)}"></button>
      <div class="agent-row">
        <strong>${agent.name}</strong>
        <span class="pill ${stateColor[agent.status] || "is-muted"}">${localizeStatusWord(agent.status)}</span>
      </div>
      <p>${agent.role}</p>
      <div class="progress"><div style="width:${agent.progress}%"></div></div>
      <small>${agent.lastUpdate}</small>
    </div>
  `).join("");
  const detail = document.getElementById("agent-runtime-detail");
  if (detail && selectedAgent) {
    const parallelMeaning = currentLocale === "zh-CN"
      ? "并行工作的意思是：HomeHub 会同时维持多个运行单元，例如语音路由、本地日程、外部消息桥、蓝图工作室和功能运行时。它们不是都在执行同一件事，而是各自负责当前系统里的不同工作面。"
      : currentLocale === "ja-JP"
        ? "並列動作とは、HomeHub が音声ルーター、ローカル予定、外部チャネル、ブループリント作業、機能ランタイムなど複数の実行単位を同時に維持することです。同じ処理を重複して走らせるのではなく、別々の仕事面を並行して受け持っています。"
        : "Parallel work means HomeHub keeps multiple runtime units alive at the same time, such as the voice router, local schedule, external channels, blueprint studio, and feature runtime. They do not all do the same job; each owns a different active surface of the system.";
    detail.innerHTML = `
      <div class="settings-card agent-runtime-card">
        <p class="eyebrow">${escapeHtml(currentLocale === "zh-CN" ? "当前单元" : currentLocale === "ja-JP" ? "現在のユニット" : "Live Unit")}</p>
        <div class="agent-row">
          <strong>${escapeHtml(selectedAgent.name)}</strong>
          <span class="pill ${stateColor[selectedAgent.status] || "is-muted"}">${escapeHtml(localizeStatusWord(selectedAgent.status))}</span>
        </div>
        <p>${escapeHtml(selectedAgent.role || "-")}</p>
        <div class="progress"><div style="width:${selectedAgent.progress || 0}%"></div></div>
        <small>${escapeHtml(selectedAgent.lastUpdate || "-")}</small>
        <small>${escapeHtml(parallelMeaning)}</small>
      </div>
    `;
  }
  const timeline = document.getElementById("agent-runtime-timeline");
  if (timeline) {
    const events = Array.isArray(latestDashboard?.timelineEvents) ? latestDashboard.timelineEvents.slice(-5).reverse() : [];
    timeline.innerHTML = `
      <div class="settings-card agent-runtime-card">
        <p class="eyebrow">${escapeHtml(currentLocale === "zh-CN" ? "最近并行活动" : currentLocale === "ja-JP" ? "最近の並列アクティビティ" : "Recent Parallel Activity")}</p>
        <div class="agent-runtime-events">
          ${events.length ? events.map((item) => `
            <div class="relay-item">
              <strong>${escapeHtml(item.time || "")} · ${escapeHtml(item.title || "")}</strong>
              <p>${escapeHtml(item.detail || "")}</p>
            </div>
          `).join("") : `<p>${escapeHtml(currentLocale === "zh-CN" ? "当前没有最近活动。" : currentLocale === "ja-JP" ? "最近のアクティビティはありません。" : "No recent activity yet.")}</p>`}
        </div>
      </div>
    `;
  }
  requestAnimationFrame(() => syncAllManagedScrollContainers());
}

function renderModels(models) {
  const container = document.getElementById("models");
  if (!container) return;
  container.innerHTML = models.map((provider) => `
    <li class="remote-target focusable-card" tabindex="0" data-title="${escapeHtml(provider.name)}">
      <strong>${provider.name}</strong>
      <span>${provider.capabilities.join(" / ")}</span>
    </li>
  `).join("");
}

function renderSkills(skills) {
  const container = document.getElementById("skills");
  if (!container) return;
  container.innerHTML = skills.map((item) => translateItem(item, skillTranslations)).map((skill) => `
    <li class="remote-target focusable-card" tabindex="0" data-title="${escapeHtml(skill.name)}">
      <strong>${skill.name}</strong>
      <span>${skill.description}</span>
    </li>
  `).join("");
}
function renderPairing(pairing, relayMessages) {
  const pairingCode = document.getElementById("pairing-code");
  const pairingExpiry = document.getElementById("pairing-expiry");
  const pairingPayload = document.getElementById("pairing-payload");
  const relay = document.getElementById("relay");
  if (!pairingCode || !pairingExpiry || !pairingPayload || !relay) return;
  pairingCode.textContent = pairing.code;
  pairingExpiry.textContent = `${t("pairing.expiresIn")}: ${pairing.expiresInSeconds}s`;
  pairingPayload.textContent = pairing.qrPayload;
  relay.innerHTML = relayMessages.map((message) => `
    <div class="relay-item remote-target focusable-card" tabindex="0" data-title="${escapeHtml(message.source)}">
      <strong>${message.source}</strong>
      <span>${message.preview}</span>
    </div>
  `).join("");
  requestAnimationFrame(() => syncAllManagedScrollContainers());
}

function renderConversationItems(containerId, items, emptyText = t("voice.noConversation")) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const list = Array.isArray(items) ? [...items] : [];
  if (containerId === "test-conversation" && customAgentStudio.isThinking) {
    list.push({
      speaker: "HomeHub",
      text: t("test.thinking"),
      time: "",
      isThinking: true,
      artifacts: [],
    });
  }
  if (!list.length) {
    preserveManagedScroll(container, () => {
      container.innerHTML = `<div class="settings-card"><p>${emptyText}</p></div>`;
    });
    return;
  }
  preserveManagedScroll(container, () => {
    container.innerHTML = list.map((item, index, renderedItems) => `
      <div class="conversation-item ${item.speaker === "You" ? "is-user" : "is-bot"} ${index === renderedItems.length - 1 ? "is-latest" : ""} ${item.isThinking ? "is-thinking" : ""}">
        <div class="conversation-avatar">${item.speaker === "You" ? "你" : "HH"}</div>
        <div class="conversation-bubble">
          <div class="conversation-head">
            <strong>${localizeSpeaker(item.speaker)}</strong>
            <span>${item.time || ""}</span>
          </div>
          <p>${escapeHtml(item.text || "")}</p>
          ${Array.isArray(item.artifacts) && item.artifacts.length ? `
            <div class="conversation-artifacts">
              ${item.artifacts.map((artifact) => `
                <a class="artifact-chip" href="${escapeHtml(artifact.url || "#")}" target="_blank" rel="noreferrer">
                  <strong>${escapeHtml(artifact.label || artifact.fileName || "Artifact")}</strong>
                  <span>${escapeHtml(artifact.fileName || "")}</span>
                  <em>${t("test.openArtifact")}</em>
                </a>
              `).join("")}
            </div>
          ` : ""}
        </div>
      </div>
    `).join("");
  });
}

function renderVoice(data) {
  const voice = document.getElementById("voice");
  const spokenLine = document.getElementById("spoken-line");
  if (!voice || !spokenLine) return;
  const language = getCurrentLanguage(data);
  const upcomingEvents = data.assistantMemory?.upcomingEvents || [];
  const reminders = data.assistantMemory?.pendingReminders || [];
  const recentActions = data.assistantMemory?.recentActions || [];
  const studyAgents = data.studyPlanAgents || [];
  const studyRecent = data.studyPlanRecentActions || [];
  const agentTypes = data.agentTypes || [];
  const voiceRoute = data.lastVoiceRoute || data.voiceRoute || null;
  const pendingClarification = data.pendingVoiceClarification || null;
  const routeKindLabel = voiceRoute?.kind === "feature"
    ? (voiceRoute.selected?.intent || "-")
    : voiceRoute?.kind === "agent_factory"
      ? t("voice.routeAgentFactory")
      : voiceRoute?.kind === "ui_action"
        ? t("voice.routeUiAction")
      : voiceRoute?.kind === "clarify"
        ? t("voice.routeClarify")
        : t("voice.routeGeneral");
  const routeTargetLabel = voiceRoute?.selected
    ? `${voiceRoute.selected.featureName || "-"} / ${voiceRoute.selected.intent || "-"}`
    : "-";
  const routeActionLabel = voiceRoute?.selected?.action || "-";
  const routeReasoning = voiceRoute?.clarificationQuestion || voiceRoute?.reasoning || "-";
  const taskSpec = voiceRoute?.taskSpec || null;
  const modelRoute = voiceRoute?.modelRoute || null;
  const toolPlan = Array.isArray(voiceRoute?.toolPlan) ? voiceRoute.toolPlan : [];
  const clarificationLine = pendingClarification
    ? `<p><strong>${t("voice.pendingClarification")}:</strong> ${pendingClarification.clarificationQuestion || "-"} · ${t("voice.originalRequest")} ${pendingClarification.originalRequest || "-"}</p>`
    : "";
  const weatherLine = `${data.weather.condition}, ${data.weather.highC}C / ${data.weather.lowC}C`;
  voice.innerHTML = `
    <div class="exchange-voice-pill"><strong>${t("voice.stt")}:</strong><span>${escapeHtml(data.voiceProfile.sttProvider)}</span></div>
    <div class="exchange-voice-pill"><strong>${t("voice.tts")}:</strong><span>${escapeHtml(data.voiceProfile.ttsProvider)}</span></div>
    <div class="exchange-voice-pill"><strong>${t("voice.locale")}:</strong><span>${escapeHtml(language?.code || data.voiceProfile.locale)}</span></div>
    <div class="exchange-voice-pill"><strong>${t("voice.route")}:</strong><span>${escapeHtml(routeKindLabel)}</span></div>
    <div class="exchange-voice-pill"><strong>${t("voice.weather")}:</strong><span>${escapeHtml(weatherLine)}</span></div>
    ${taskSpec ? `<div class="exchange-voice-pill is-wide"><strong>Task:</strong><span>${escapeHtml(taskSpec.taskType || "-")} · ${escapeHtml(taskSpec.summary || "-")}</span></div>` : ""}
    ${modelRoute ? `<div class="exchange-voice-pill is-wide"><strong>Model:</strong><span>${escapeHtml(modelRoute.primaryModel || "-")} · ${escapeHtml(modelRoute.reason || "-")}</span></div>` : ""}
    ${clarificationLine ? `<div class="exchange-voice-pill is-wide">${clarificationLine}</div>` : ""}
  `;
  renderConversationItems("conversation", data.conversation, t("voice.noConversation"));

  const lastSpoken = data.conversation[data.conversation.length - 1];
  spokenLine.textContent = lastSpoken ? `${localizeSpeaker(lastSpoken.speaker)}: ${lastSpoken.text}` : t("voice.noConversation");
  renderFloatingBuddy();
}

function selectStudioAgent(agentId) {
  customAgentStudio.selectedAgentId = agentId || "";
  renderTestLab();
}

function getSelectedStudioAgent() {
  const items = customAgentStudio.items || [];
  return items.find((item) => item.id === customAgentStudio.selectedAgentId)
    || items.find((item) => item.status === "complete")
    || items[0]
    || null;
}

function getBlueprintStudioGroups() {
  const items = Array.isArray(customAgentStudio.items) ? customAgentStudio.items : [];
  return {
    creating: items.filter((item) => item.status !== "complete"),
    created: items.filter((item) => item.status === "complete"),
    actions: Array.isArray(customAgentStudio.recentActions) ? customAgentStudio.recentActions : []
  };
}

function getSelectedStudioAgentForTab(tabName) {
  const groups = getBlueprintStudioGroups();
  const items = tabName === "created" ? groups.created : tabName === "creating" ? groups.creating : [];
  return items.find((item) => item.id === customAgentStudio.selectedAgentId) || items[0] || null;
}

function resetStudioFeatureRuntime(featureId = "") {
  studioFeatureRuntime = {
    featureId,
    items: [],
    fieldNames: [],
    detail: null,
    isLoading: false,
    isSaving: false,
    error: "",
    exportArtifact: null,
    draftText: ""
  };
}

function getStudioFeatureApiRoot(agent) {
  const featureId = String(agent?.generatedFeatureId || "").trim();
  return featureId ? `/api/${featureId}` : "";
}

async function loadStudioFeatureRuntime(agent, force = false) {
  const apiRoot = getStudioFeatureApiRoot(agent);
  if (!apiRoot) {
    resetStudioFeatureRuntime("");
    renderTestLab();
    return;
  }
  const featureId = String(agent.generatedFeatureId || "").trim();
  const previousExportArtifact = studioFeatureRuntime.featureId === featureId ? studioFeatureRuntime.exportArtifact : null;
  const previousDraftText = studioFeatureRuntime.featureId === featureId ? studioFeatureRuntime.draftText : "";
  if (!force && studioFeatureRuntime.featureId === featureId && (studioFeatureRuntime.isLoading || studioFeatureRuntime.detail)) {
    return;
  }
  resetStudioFeatureRuntime(featureId);
  studioFeatureRuntime.isLoading = true;
  studioFeatureRuntime.exportArtifact = previousExportArtifact;
  studioFeatureRuntime.draftText = previousDraftText;
  renderTestLab();
  try {
    const [detailResponse, itemsResponse] = await Promise.all([
      fetch(apiRoot),
      fetch(`${apiRoot}/items`)
    ]);
    const detailPayload = await detailResponse.json();
    const itemsPayload = await itemsResponse.json();
    if (!detailResponse.ok) {
      throw new Error(detailPayload.error || "Feature detail request failed.");
    }
    if (!itemsResponse.ok) {
      throw new Error(itemsPayload.error || "Feature items request failed.");
    }
    studioFeatureRuntime.featureId = featureId;
    studioFeatureRuntime.detail = detailPayload;
    studioFeatureRuntime.items = Array.isArray(itemsPayload.items) ? itemsPayload.items : [];
    studioFeatureRuntime.fieldNames = Array.isArray(detailPayload.fieldNames)
      ? detailPayload.fieldNames
      : (Array.isArray(itemsPayload.fieldNames) ? itemsPayload.fieldNames : []);
    studioFeatureRuntime.error = "";
  } catch (error) {
    studioFeatureRuntime.error = String(error.message || error);
  } finally {
    studioFeatureRuntime.isLoading = false;
    renderTestLab();
  }
}

function ensureStudioFeatureRuntime(agent) {
  const featureId = String(agent?.generatedFeatureId || "").trim();
  if (!featureId) {
    if (studioFeatureRuntime.featureId) resetStudioFeatureRuntime("");
    return;
  }
  if (studioFeatureRuntime.featureId !== featureId || (!studioFeatureRuntime.detail && !studioFeatureRuntime.isLoading)) {
    loadStudioFeatureRuntime(agent).catch((error) => {
      studioFeatureRuntime.error = String(error.message || error);
      studioFeatureRuntime.isLoading = false;
      renderTestLab();
    });
  }
}

function renderStudioFeatureRuntime(agent) {
  if (!agent?.generatedFeatureId) {
    return `
      <div class="studio-feature-panel is-empty">
        <strong>${escapeHtml(t("test.featurePanelTitle"))}</strong>
        <p>${escapeHtml(t("test.featurePanelEmpty"))}</p>
      </div>
    `;
  }
  const runtimeMatches = studioFeatureRuntime.featureId === String(agent.generatedFeatureId || "").trim();
  const loading = runtimeMatches && studioFeatureRuntime.isLoading;
  const errorText = runtimeMatches ? studioFeatureRuntime.error : "";
  const items = runtimeMatches && Array.isArray(studioFeatureRuntime.items)
    ? studioFeatureRuntime.items.map((item) => ({ ...item, ...summarizeLegacyFeatureItem(item) }))
    : [];
  const detail = runtimeMatches ? studioFeatureRuntime.detail : null;
  const fieldNames = runtimeMatches && Array.isArray(studioFeatureRuntime.fieldNames) ? studioFeatureRuntime.fieldNames : [];
  const draftText = runtimeMatches ? studioFeatureRuntime.draftText : "";
  const exportArtifact = runtimeMatches ? studioFeatureRuntime.exportArtifact : null;
  const body = loading
    ? `<p>${escapeHtml(t("test.featurePanelLoading"))}</p>`
    : errorText
      ? `<p>${escapeHtml(t("test.featurePanelError", { error: errorText }))}</p>`
      : `
        <div class="studio-feature-meta">
          <div class="studio-detail-section">
            <strong>${escapeHtml(t("test.featureFields"))}</strong>
            <p>${fieldNames.length ? escapeHtml(fieldNames.join(" / ")) : "-"}</p>
          </div>
          <div class="studio-detail-section">
            <strong>${escapeHtml(t("test.featureStoragePath"))}</strong>
            <p>${escapeHtml(detail?.storagePath || "-")}</p>
          </div>
          <div class="studio-detail-section">
            <strong>${escapeHtml(t("test.featureGeneratedRoot"))}</strong>
            <p>${escapeHtml(detail?.generatedRoot || "-")}</p>
          </div>
        </div>
        <div class="studio-feature-compose">
          <label for="studio-feature-draft">${escapeHtml(t("test.featureDraftLabel"))}</label>
          <textarea id="studio-feature-draft" class="settings-input studio-feature-textarea" rows="4" placeholder="${escapeHtml(t("test.featureDraftPlaceholder"))}">${escapeHtml(draftText)}</textarea>
          <div class="studio-feature-actions">
            <button id="studio-feature-create" class="test-action remote-target" type="button">${escapeHtml(t("test.featureCreate"))}</button>
            <button id="studio-feature-refresh" class="test-action remote-target is-secondary" type="button">${escapeHtml(loading ? t("test.featureRefreshing") : t("test.featureRefresh"))}</button>
            <button id="studio-feature-export" class="test-action remote-target is-secondary" type="button">${escapeHtml(t("test.featureExport"))}</button>
            ${exportArtifact?.url ? `<a class="test-action is-secondary studio-export-link" href="${escapeHtml(exportArtifact.url)}" target="_blank" rel="noreferrer">${escapeHtml(t("test.featureOpenExport"))}</a>` : ""}
          </div>
        </div>
        <div class="studio-feature-records">
          <div class="studio-feature-records-head">
            <strong>${escapeHtml(t("test.featureRecords"))}</strong>
            <span class="mini-pill">${items.length}</span>
          </div>
          ${items.length ? items.map((item) => `
            <article class="studio-feature-record">
              <div class="studio-feature-record-head">
                <strong>${escapeHtml(item.title || "Untitled")}</strong>
                <button class="test-action remote-target is-secondary studio-feature-delete" type="button" data-feature-record-id="${escapeHtml(item.id || "")}">${escapeHtml(t("test.featureDeleteRecord"))}</button>
              </div>
              <p>${escapeHtml(item.summary || "-")}</p>
              <small>${escapeHtml(item.createdAt || "")}</small>
            </article>
          `).join("") : `<p>${escapeHtml(t("test.featureNoRecords"))}</p>`}
        </div>
      `;
  return `
    <div class="studio-feature-panel">
      <div class="studio-detail-head">
        <div>
          <p class="eyebrow">${escapeHtml(t("test.featurePanelTitle"))}</p>
          <h3>${escapeHtml(agent.name || "Feature")}</h3>
        </div>
        <span class="pill is-ready">${escapeHtml(agent.generatedFeatureId || "")}</span>
      </div>
      ${body}
    </div>
  `;
}

function summarizeLegacyFeatureItem(item) {
  if (!item || typeof item !== "object") {
    return { title: "Untitled", summary: "-" };
  }
  const fields = item.fields && typeof item.fields === "object" ? item.fields : {};
  const titleCandidates = [
    item.title,
    fields["姓名"],
    fields.name,
    item.merchant,
    item.category,
    item.sourceText
  ];
  const summaryCandidates = [];
  if (item.summary) summaryCandidates.push(item.summary);
  if (Number.isFinite(Number(item.amount))) {
    const amountLabel = String(item.category || "").trim() || (currentLocale === "zh-CN" ? "消费" : currentLocale === "ja-JP" ? "支出" : "Amount");
    summaryCandidates.push(`${amountLabel} ${item.amount} ${item.currency || "JPY"}`);
  }
  if (item.sourceText) summaryCandidates.push(item.sourceText);
  if (item.createdAt) summaryCandidates.push(item.createdAt);
  const title = titleCandidates.find((value) => String(value || "").trim()) || "Untitled";
  const summary = summaryCandidates.find((value) => String(value || "").trim()) || "-";
  return { title: String(title).trim(), summary: String(summary).trim() };
}

function renderStudioDetail(agent, mode) {
  if (!agent) {
    return `<div class="settings-card"><p>${escapeHtml(t("test.detailEmpty"))}</p></div>`;
  }
  const profile = agent.profile || {};
  const records = Array.isArray(agent.records) ? agent.records : [];
  const latestRecord = records[0]?.message || "";
  const sections = [
    [t("test.detailGoal"), profile.goal || "-"],
    [t("test.detailTrigger"), profile.trigger || "-"],
    [t("test.detailInputs"), profile.inputs || "-"],
    [t("test.detailOutput"), profile.output || "-"],
    [t("test.detailConstraints"), profile.constraints || "-"],
    [t("test.detailCheckPrompt"), profile.checkPrompt || "-"],
    [t("test.detailNoInput"), profile.noInputAction || "-"],
    [t("test.detailHasInput"), profile.hasInputAction || "-"],
  ];
  if (agent.generatedFeaturePath) {
    sections.push([t("test.detailFeaturePath"), agent.generatedFeaturePath]);
  }
  if (latestRecord) {
    sections.push([t("test.detailRecentRecord"), latestRecord]);
  }
  const generateDisabled = mode !== "created" || !!agent.generatedFeaturePath || customAgentStudio.isGenerating;
  const generateLabel = agent.generatedFeaturePath
    ? t("test.featureAlreadyGenerated")
    : (customAgentStudio.isGenerating ? t("test.generating") : t("test.generate"));
  return `
    <div class="studio-detail-card">
      <div class="studio-detail-head">
        <div>
          <p class="eyebrow">${escapeHtml(t("test.detailTitle"))}</p>
          <h3>${escapeHtml(agent.name || "Blueprint")}</h3>
        </div>
        <span class="pill ${stateColor[agent.status] || "is-muted"}">${escapeHtml(localizeStatusWord(agent.status || "draft"))}</span>
      </div>
      <div class="studio-detail-grid">
        ${sections.map(([label, value]) => `
          <div class="studio-detail-section">
            <strong>${escapeHtml(label)}</strong>
            <p>${escapeHtml(value)}</p>
          </div>
        `).join("")}
      </div>
      <div class="studio-detail-actions">
        ${mode === "creating" ? `<button id="test-delete-draft" class="test-action remote-target is-secondary" type="button">${escapeHtml(t("test.deleteDraft"))}</button>` : ""}
        ${mode === "created" && !agent.generatedFeaturePath ? `<button id="test-generate-feature" class="test-action remote-target" type="button" ${generateDisabled ? "disabled" : ""}>${escapeHtml(generateLabel)}</button>` : ""}
        ${mode === "created" && agent.generatedFeaturePath ? `<button id="test-delete-feature" class="test-action remote-target is-secondary" type="button">${escapeHtml(t("test.deleteFeature"))}</button>` : ""}
        ${mode === "created" ? `<button id="test-delete-blueprint" class="test-action remote-target is-secondary" type="button">${escapeHtml(t("test.deleteBlueprint"))}</button>` : ""}
      </div>
      ${mode === "created" ? renderStudioFeatureRuntime(agent) : ""}
    </div>
  `;
}

function renderStudioAgentCards(items) {
  return items.map((item) => {
    const isSelected = item.id === customAgentStudio.selectedAgentId;
    const tag = item.generatedFeaturePath ? t("test.generatedTag") : t("test.storageTag");
    const statusClass = stateColor[item.status] || "is-muted";
    const output = item.profile?.output || "-";
    const trigger = item.profile?.trigger || "-";
    const recordCount = Array.isArray(item.records) ? item.records.length : 0;
    const featureItemCount = Number.isFinite(Number(item.featureItemCount)) ? Number(item.featureItemCount) : null;
    const countLabel = featureItemCount !== null
      ? `${featureItemCount} items`
      : `${recordCount} records`;
    const latestRecord = featureItemCount !== null
      ? (item.featureLatestAction || "")
      : (recordCount ? item.records[0]?.message || "" : "");
    return `
      <div
        class="studio-card remote-target focusable-card ${isSelected ? "is-selected" : ""}"
        tabindex="0"
        data-agent-id="${item.id}"
        data-title="${escapeHtml(item.name || "Blueprint")}"
      >
        <div class="studio-head">
          <strong>${escapeHtml(item.name || "Blueprint")}</strong>
          <span class="pill ${statusClass}">${escapeHtml(localizeStatusWord(item.status || "draft"))}</span>
        </div>
        <p>${escapeHtml(item.profile?.goal || "-")}</p>
        <div class="studio-meta">
          <span class="mini-pill">${escapeHtml(trigger)}</span>
          <span class="mini-pill capability">${escapeHtml(tag)}</span>
          <span class="mini-pill">${countLabel}</span>
        </div>
        <small>${escapeHtml(output)}</small>
        ${latestRecord ? `<small>${escapeHtml(latestRecord)}</small>` : ""}
        ${item.generatedFeaturePath ? `<small>${escapeHtml(item.generatedFeaturePath)}</small>` : ""}
      </div>
    `;
  }).join("");
}

function renderTestLab() {
  const studioContainer = document.getElementById("studio-blueprints");
  const previousListScrollTop = studioContainer?.querySelector(".studio-master-list")?.scrollTop ?? 0;
  const previousDetailScrollTop = studioContainer?.querySelector(".studio-detail-pane")?.scrollTop ?? 0;
  const previousContainerScrollTop = studioContainer?.scrollTop ?? 0;
  const studioGroups = getBlueprintStudioGroups();
  if (activeBlueprintStudioTab === "created" && !studioGroups.created.length) {
    activeBlueprintStudioTab = studioGroups.creating.length ? "creating" : "actions";
  }
  if (activeBlueprintStudioTab === "creating" && !studioGroups.creating.length) {
    activeBlueprintStudioTab = studioGroups.created.length ? "created" : "actions";
  }
  const selected = getSelectedStudioAgentForTab(activeBlueprintStudioTab) || getSelectedStudioAgent();
  if (selected && customAgentStudio.selectedAgentId !== selected.id) {
    customAgentStudio.selectedAgentId = selected.id;
  }
  if (activeBlueprintStudioTab === "created" && selected?.generatedFeatureId) {
    ensureStudioFeatureRuntime(selected);
  } else if (studioFeatureRuntime.featureId) {
    resetStudioFeatureRuntime("");
  }

  renderConversationItems("test-conversation", testConversation, t("test.emptyConversation"));

  if (studioContainer) {
    if (!customAgentStudio.items.length) {
      studioContainer.innerHTML = `<div class="settings-card"><p>${t("test.emptyBlueprints")}</p></div>`;
    } else {
      let listHtml = "";
      if (activeBlueprintStudioTab === "actions") {
        listHtml = studioGroups.actions.length
          ? studioGroups.actions.map((item) => `<div class="relay-item studio-log-card"><strong>${escapeHtml(item.createdAt || "")}</strong><p>${escapeHtml(item.summary || "")}</p></div>`).join("")
          : `<div class="settings-card"><p>${t("test.emptyActions")}</p></div>`;
      } else if (activeBlueprintStudioTab === "created") {
        listHtml = studioGroups.created.length
          ? renderStudioAgentCards(studioGroups.created)
          : `<div class="settings-card"><p>${t("test.emptyCreated")}</p></div>`;
      } else {
        listHtml = studioGroups.creating.length
          ? renderStudioAgentCards(studioGroups.creating)
          : `<div class="settings-card"><p>${t("test.emptyCreating")}</p></div>`;
      }
      studioContainer.innerHTML = `
        <div class="studio-tab-strip">
          <button class="studio-mini-tab remote-target ${activeBlueprintStudioTab === "creating" ? "is-active" : ""}" type="button" data-studio-tab="creating">${escapeHtml(t("test.studioCreating"))}<span>${studioGroups.creating.length}</span></button>
          <button class="studio-mini-tab remote-target ${activeBlueprintStudioTab === "created" ? "is-active" : ""}" type="button" data-studio-tab="created">${escapeHtml(t("test.studioCreated"))}<span>${studioGroups.created.length}</span></button>
          <button class="studio-mini-tab remote-target ${activeBlueprintStudioTab === "actions" ? "is-active" : ""}" type="button" data-studio-tab="actions">${escapeHtml(t("test.studioActions"))}<span>${studioGroups.actions.length}</span></button>
        </div>
        <div class="studio-tab-panel ${activeBlueprintStudioTab === "actions" ? "is-log-view" : ""}">
          ${activeBlueprintStudioTab === "actions" ? listHtml : `<div class="studio-master-detail"><div class="studio-master-list">${listHtml}</div><div class="studio-detail-pane">${renderStudioDetail(selected, activeBlueprintStudioTab)}</div></div>`}
        </div>
      `;
    }
  }

  const actionsLog = document.getElementById("studio-actions-log");
  if (actionsLog) {
    actionsLog.hidden = true;
    actionsLog.innerHTML = "";
  }
  const uploadMeta = document.getElementById("test-upload-meta");
  const summaryButton = document.getElementById("test-doc-summary-pick");
  const translateButton = document.getElementById("test-doc-translate-pick");
  summaryButton?.classList.toggle("is-active", testUploadMode === "summary");
  translateButton?.classList.toggle("is-active", testUploadMode === "translation");
  if (uploadMeta) {
    if (testUploadAttachment) {
      const fileKindLabel = testUploadAttachment.kind === "file"
        ? (currentLocale === "zh-CN" ? "文档已选择" : currentLocale === "ja-JP" ? "ファイル添付済み" : "Document attached")
        : (currentLocale === "zh-CN" ? "图片已选择" : currentLocale === "ja-JP" ? "画像添付済み" : "Image attached");
      const modeLabel = testUploadMode === "summary"
        ? (currentLocale === "zh-CN" ? "文档总结" : currentLocale === "ja-JP" ? "要約" : "Summary")
        : testUploadMode === "translation"
          ? (currentLocale === "zh-CN" ? "文档翻译" : currentLocale === "ja-JP" ? "翻訳" : "Translation")
          : (currentLocale === "zh-CN" ? "通用处理" : currentLocale === "ja-JP" ? "汎用处理" : "General");
      uploadMeta.classList.add("is-pending-task");
      uploadMeta.innerHTML = `
        <span class="test-upload-mode-pill">${escapeHtml(modeLabel)}</span>
        <span>${escapeHtml(fileKindLabel)}: ${escapeHtml(testUploadAttachment.name)} (${Math.round((testUploadAttachment.sizeBytes || 0) / 1024)} KB)</span>
      `;
    } else {
      if (testUploadMode === "summary" || testUploadMode === "translation") {
        const pendingLabel = testUploadMode === "summary"
          ? (currentLocale === "zh-CN" ? "文档总结" : currentLocale === "ja-JP" ? "要約" : "Summary")
          : (currentLocale === "zh-CN" ? "文档翻译" : currentLocale === "ja-JP" ? "翻訳" : "Translation");
        const pendingHint = currentLocale === "zh-CN"
          ? "已选择动作，请继续上传文档。"
          : currentLocale === "ja-JP"
            ? "アクションを選択しました。続けて文書をアップロードしてください。"
            : "Action selected. Upload a document to continue.";
        uploadMeta.classList.add("is-pending-task");
        uploadMeta.innerHTML = `
          <span class="test-upload-mode-pill">${escapeHtml(pendingLabel)}</span>
          <span>${escapeHtml(pendingHint)}</span>
        `;
      } else {
        uploadMeta.classList.remove("is-pending-task");
        uploadMeta.textContent = "";
      }
    }
  }
  requestAnimationFrame(() => {
    if (studioContainer?.isConnected) {
      const nextList = studioContainer.querySelector(".studio-master-list");
      const nextDetail = studioContainer.querySelector(".studio-detail-pane");
      if (nextList instanceof HTMLElement) nextList.scrollTop = previousListScrollTop;
      if (nextDetail instanceof HTMLElement) nextDetail.scrollTop = previousDetailScrollTop;
      studioContainer.scrollTop = previousContainerScrollTop;
    }
    syncAllManagedScrollContainers();
  });
}

function workCopy(key) {
  const bundle = {
    empty: {
      "zh-CN": "还没有可演示的执行请求。",
      "ja-JP": "まだ表示できる実行リクエストがありません。",
      "en-US": "No runnable requests to visualize yet."
    },
    source: {
      app: { "zh-CN": "自身 App", "ja-JP": "自身アプリ", "en-US": "App" },
      voice: { "zh-CN": "语音", "ja-JP": "音声", "en-US": "Voice" },
      image: { "zh-CN": "图片", "ja-JP": "画像", "en-US": "Image" },
      file: { "zh-CN": "文件", "ja-JP": "ファイル", "en-US": "File" },
      mail: { "zh-CN": "邮件", "ja-JP": "メール", "en-US": "Mail" },
      line: { "zh-CN": "LINE", "ja-JP": "LINE", "en-US": "LINE" },
      web: { "zh-CN": "网页", "ja-JP": "Web", "en-US": "Web" }
    },
    status: {
      sleeping: { "zh-CN": "待唤醒", "ja-JP": "待機中", "en-US": "Sleeping" },
      working: { "zh-CN": "执行中", "ja-JP": "実行中", "en-US": "Working" },
      packed: { "zh-CN": "已完成", "ja-JP": "完了", "en-US": "Packed" },
      queued: { "zh-CN": "排队中", "ja-JP": "待機列", "en-US": "Queued" }
    },
    intake: {
      "zh-CN": "输入接收",
      "ja-JP": "入力受付",
      "en-US": "Intake"
    },
    routing: {
      "zh-CN": "需求判断",
      "ja-JP": "要求判定",
      "en-US": "Routing"
    },
    execution: {
      "zh-CN": "执行编排",
      "ja-JP": "実行編成",
      "en-US": "Execution"
    },
    packaging: {
      "zh-CN": "结果打包",
      "ja-JP": "結果梱包",
      "en-US": "Packaging"
    }
  };
  const value = bundle[key];
  if (!value) return key;
  if (typeof value === "object" && !Object.prototype.hasOwnProperty.call(value, currentLocale) && !Object.prototype.hasOwnProperty.call(value, "en-US")) {
    return value;
  }
  if (typeof value[currentLocale] === "string") return value[currentLocale];
  return value["en-US"] || key;
}

function localizeWorkSource(source) {
  const bundle = workCopy("source");
  if (bundle && typeof bundle === "object") {
    const item = bundle[source] || bundle.app;
    return item?.[currentLocale] || item?.["en-US"] || source;
  }
  return source;
}

function localizeWorkStatus(status) {
  const bundle = workCopy("status");
  if (bundle && typeof bundle === "object") {
    const item = bundle[status] || bundle.queued;
    return item?.[currentLocale] || item?.["en-US"] || status;
  }
  return status;
}

function workAgentCountLabel(count) {
  const total = Number(count) || 0;
  if (currentLocale === "zh-CN") {
    return total === 1 ? "1 个执行单元" : `${total} 个执行单元`;
  }
  if (currentLocale === "ja-JP") {
    return total === 1 ? "1 実行ユニット" : `${total} 実行ユニット`;
  }
  return total === 1 ? "1 execution unit" : `${total} execution units`;
}

function inferWorkSource(text, attachment) {
  const value = String(text || "").toLowerCase();
  if (attachment?.kind === "image") return "image";
  if (attachment?.kind === "file") return "file";
  if (value.includes("mail") || value.includes("邮箱") || value.includes("邮件") || value.includes("email")) return "mail";
  if (value.includes("line")) return "line";
  if (value.includes("http://") || value.includes("https://") || value.includes("网页") || value.includes("网站")) return "web";
  return isRecording ? "voice" : "app";
}

function hashString(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash) + text.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function workColorStyle(key) {
  const palette = [
    ["#5ad4b2", "rgba(90, 212, 178, 0.22)", "rgba(90, 212, 178, 0.52)"],
    ["#67b5ff", "rgba(103, 181, 255, 0.22)", "rgba(103, 181, 255, 0.52)"],
    ["#ffb763", "rgba(255, 183, 99, 0.22)", "rgba(255, 183, 99, 0.52)"],
    ["#c48eff", "rgba(196, 142, 255, 0.22)", "rgba(196, 142, 255, 0.52)"],
    ["#ff8ea1", "rgba(255, 142, 161, 0.22)", "rgba(255, 142, 161, 0.52)"],
    ["#8fe388", "rgba(143, 227, 136, 0.22)", "rgba(143, 227, 136, 0.52)"]
  ];
  const [accent, surface, border] = palette[hashString(key) % palette.length];
  return `--work-accent:${accent};--work-surface:${surface};--work-border:${border};`;
}

function deriveWorkItems() {
  const conversation = Array.isArray(testConversation) && testConversation.length
    ? testConversation
    : (Array.isArray(latestDashboard?.conversation) ? latestDashboard.conversation : []);
  const userMessages = conversation
    .map((item, index) => ({ ...item, index }))
    .filter((item) => item.speaker === "You" && String(item.text || "").trim());
  return userMessages.slice(-10).reverse().map((item, position) => {
    const reply = conversation.slice(item.index + 1).find((entry) => entry.speaker !== "You");
    const isLatest = position === 0;
    const source = inferWorkSource(item.text, isLatest ? testUploadAttachment : null);
    const latestRoute = latestDashboard?.lastVoiceRoute || latestDashboard?.voiceRoute || null;
    const latestRouteRequest = String(latestRoute?.requestText || "").trim();
    const itemText = String(item.text || "").trim();
    const status = isLatest
      ? (customAgentStudio.isThinking ? "working" : reply ? "packed" : "queued")
      : (reply ? "packed" : "sleeping");
    return {
      id: `work-${item.index}`,
      time: item.time || "",
      text: item.text || "",
      status,
      source,
      reply,
      route: isLatest && latestRoute && latestRouteRequest && latestRouteRequest === itemText ? latestRoute : null
    };
  });
}

function buildWorkPipeline(item) {
  const route = item?.route || {};
  const taskSpec = route.taskSpec || {};
  const cortex = route.cortex || {};
  const toolPlan = Array.isArray(route.toolPlan) ? route.toolPlan : [];
  const requiresNetwork = Boolean(
    taskSpec.requiresNetworkLookup
    || taskSpec.requiresNetwork
    || cortex.shouldNetwork
    || toolPlan.some((tool) => String(tool || "").toLowerCase().includes("network"))
  );
  const taskType = String(taskSpec.taskType || "").trim() || "general_chat";
  const requestText = String(item?.text || "").toLowerCase();
  const isWeatherRequest = taskType === "weather";
  const inputAgents = [];
  inputAgents.push({
    name: item?.source === "voice" ? "Speech Intake" : item?.source === "image" ? "OCR Intake" : item?.source === "file" ? "Document Intake" : "Text Intake",
    state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
  });
  inputAgents.push({
    name: "Semantic Parser",
    state: item?.status === "queued" ? "sleeping" : item?.status === "working" ? "working" : "packed"
  });
  const routingAgents = [{
    name: route.kind === "agent_factory" ? "Agent Factory" : route.kind === "feature" ? (route.selected?.featureName || "Skill Router") : "Task Router",
    state: item?.status === "queued" ? "sleeping" : "packed"
  }];
  if (requiresNetwork) {
    routingAgents.push({
      name: "Official Search",
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
  }
  const executionAgents = [];
  if (isWeatherRequest) {
    executionAgents.push({
      name: "GPS Location",
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
    executionAgents.push({
      name: "Weather Fetch",
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
  } else if (taskType === "agent_creation" || route.kind === "agent_factory") {
    executionAgents.push({
      name: route.selected?.featureName || "Agent Factory",
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
  } else if (route.kind === "feature" && route.selected?.featureName) {
    executionAgents.push({
      name: route.selected.featureName,
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
  }
  if (toolPlan.length && !isWeatherRequest) {
    toolPlan.slice(0, 3).forEach((tool, index) => {
      const label = String(tool?.label || tool?.name || tool || `Tool ${index + 1}`);
      if (executionAgents.some((agent) => agent.name === label)) return;
      executionAgents.push({
        name: label,
        state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
      });
    });
  }
  if (!executionAgents.length) {
    executionAgents.push({
      name: route.selected?.intent || taskSpec.taskType || "General Worker",
      state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
    });
  }
  const packagingAgents = [{
    name: item?.reply ? "Result Packager" : "Reply Builder",
    state: item?.status === "packed" ? "packed" : item?.status === "working" ? "working" : "sleeping"
  }];
  return [
    { id: "intake", name: workCopy("intake"), agents: inputAgents },
    { id: "routing", name: workCopy("routing"), agents: routingAgents },
    { id: "execution", name: workCopy("execution"), agents: executionAgents },
    { id: "packaging", name: workCopy("packaging"), agents: packagingAgents }
  ];
}

function renderWorkTab() {
  const listNode = document.getElementById("work-request-list");
  const pipelineNode = document.getElementById("work-pipeline");
  if (!listNode || !pipelineNode) return;
  const items = deriveWorkItems();
  if (!items.length) {
    listNode.innerHTML = `<div class="settings-card"><p>${escapeHtml(workCopy("empty"))}</p></div>`;
    pipelineNode.innerHTML = `<div class="settings-card"><p>${escapeHtml(workCopy("empty"))}</p></div>`;
    return;
  }
  listNode.innerHTML = items.map((item, index) => `
    <button
      class="work-request-card remote-target ${index === 0 ? "is-active" : ""}"
      type="button"
      data-title="${escapeHtml(item.text.slice(0, 24) || "Request")}"
      style="${workColorStyle(item.source)}"
    >
      <div class="work-request-meta">
        <span class="mini-pill">${escapeHtml(item.time || "--:--")}</span>
        <span class="mini-pill">${escapeHtml(localizeWorkSource(item.source))}</span>
        <span class="pill ${item.status === "packed" ? "is-ready" : item.status === "working" ? "is-active" : "is-muted"}">${escapeHtml(localizeWorkStatus(item.status))}</span>
      </div>
      <p>${escapeHtml(item.text)}</p>
      ${item.reply?.text ? `<small>${escapeHtml(item.reply.text.slice(0, 88))}</small>` : ""}
    </button>
  `).join("");

  const focusItem = items[0];
  const pipeline = buildWorkPipeline(focusItem);
  pipelineNode.innerHTML = `
    <div class="work-conveyor-line"></div>
    ${pipeline.map((skill, skillIndex) => `
      <section class="work-skill-stage" style="${workColorStyle(skill.id)}">
        <div class="work-skill-factory">
          <div class="work-factory-decor" aria-hidden="true">
            <span class="work-factory-arm work-factory-arm-main"></span>
            <span class="work-factory-arm work-factory-arm-joint"></span>
            <span class="work-factory-arm work-factory-arm-claw"></span>
            <span class="work-factory-belt"></span>
          </div>
          <div class="work-skill-head">
            <span class="work-skill-dot"></span>
            <strong>${escapeHtml(skill.name)}</strong>
          </div>
          <small>${escapeHtml(workAgentCountLabel(skill.agents.length))}</small>
        </div>
        <div class="work-skill-robots">
          ${skill.agents.map((agent) => `
            <article class="work-robot-card is-${agent.state}" style="${workColorStyle(skill.id)}">
              <div class="work-robot-visual">
                <div class="work-robot-bubble">${escapeHtml(localizeWorkStatus(agent.state))}</div>
                <div class="work-robot-shell">
                  <span class="work-robot-eye"></span>
                  <span class="work-robot-eye"></span>
                  <span class="work-robot-mouth"></span>
                </div>
                <div class="work-robot-platform"></div>
                <div class="work-robot-box"></div>
              </div>
              <strong>${escapeHtml(agent.name)}</strong>
              <span>${escapeHtml(localizeWorkStatus(agent.state))}</span>
            </article>
          `).join("")}
        </div>
        ${skillIndex < pipeline.length - 1 ? `<div class="work-link-arrow"></div>` : ""}
      </section>
    `).join("")}
  `;
}

async function completeActiveReminder() {
  if (!activeReminderId || isCompletingReminder) return;
  const reminderId = activeReminderId;
  const overlay = document.getElementById("reminder-overlay");
  isCompletingReminder = true;
  syncReminderButtonState();
  try {
    if (overlay) {
      overlay.hidden = true;
    }
    activeReminderId = null;
    const response = await fetch("/api/memory/reminders/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: reminderId })
    });
    const payload = await response.json();
    if (!response.ok) {
      activeReminderId = reminderId;
      if (overlay) {
        overlay.hidden = false;
      }
      updateSpokenLine(`HomeHub: ${payload.error || "Failed to complete reminder."}`);
      return;
    }
    if (latestDashboard) {
      latestDashboard.assistantMemory = payload.assistantMemory || latestDashboard.assistantMemory;
      renderStatusStrip(latestDashboard);
      renderVoice(latestDashboard);
      renderReminderOverlay(latestDashboard);
    }
    updateSpokenLine(t("reminder.completed"));
    await loadDashboard();
  } finally {
    isCompletingReminder = false;
    syncReminderButtonState();
  }
}

function cortexCopy(key) {
  const bundle = {
    title: {
      "zh-CN": "Cortex 解构台",
      "ja-JP": "Cortex 展開ビュー",
      "en-US": "Cortex Unpacked"
    },
    guidance: {
      "zh-CN": "输入一个需求，观察 HomeHub 如何理解、检索、判断、规划与学习。",
      "ja-JP": "要求を入力して、HomeHub が理解・検索・判断・計画・学習する流れを確認します。",
      "en-US": "Enter a request and inspect how HomeHub understands, retrieves, decides, plans, and learns."
    },
    testTitle: {
      "zh-CN": "Cortex 测试台",
      "ja-JP": "Cortex テストコンソール",
      "en-US": "Cortex Test Console"
    },
    run: {
      "zh-CN": "运行 Cortex 分析",
      "ja-JP": "Cortex 分析を実行",
      "en-US": "Run Cortex Analysis"
    },
    running: {
      "zh-CN": "正在分析这个需求...",
      "ja-JP": "この要求を分析しています...",
      "en-US": "Analyzing this request..."
    },
    idle: {
      "zh-CN": "这里会显示共享大脑对当前需求的拆解与执行蓝图。",
      "ja-JP": "ここに共有ブレインが現在の要求をどう分解したかが表示されます。",
      "en-US": "This area shows how the shared brain decomposes the current request."
    },
    failed: {
      "zh-CN": "Cortex 加载失败。",
      "ja-JP": "Cortex の読み込みに失敗しました。",
      "en-US": "Failed to load cortex blueprint."
    },
    overview: {
      "zh-CN": "概要",
      "ja-JP": "概要",
      "en-US": "Overview"
    },
    loop: {
      "zh-CN": "请求环路",
      "ja-JP": "リクエストループ",
      "en-US": "Request Loop"
    },
    architecture: {
      "zh-CN": "架构浏览器",
      "ja-JP": "アーキテクチャエクスプローラー",
      "en-US": "Architecture Explorer"
    },
    capability: {
      "zh-CN": "能力浏览器",
      "ja-JP": "ケイパビリティエクスプローラー",
      "en-US": "Capability Explorer"
    },
    status: {
      "zh-CN": "功能状态",
      "ja-JP": "機能ステータス",
      "en-US": "Feature Status"
    },
    raw: {
      "zh-CN": "原始蓝图",
      "ja-JP": "生のブループリント",
      "en-US": "Raw Blueprint"
    }
  };
  return bundle[key]?.[currentLocale] || bundle[key]?.["en-US"] || key;
}

function defaultCortexCommand() {
  if (currentLocale === "zh-CN") {
    return "帮我读取一张账单图片，整理本月家庭支出，必要时联网查官方价格参考，并决定是否应该创建新的智能体。";
  }
  if (currentLocale === "ja-JP") {
    return "請求書の画像を読み取り、今月の支出を整理し、必要なら公式情報を調べ、新しいスマートユニットを作るべきか判断してください。";
  }
  return "Read a bill image, organize this month's household spending, research official references when needed, and decide whether HomeHub should create a new smart unit.";
}

function ensureCortexTesterState() {
  if (!cortexTesterState.command) cortexTesterState.command = defaultCortexCommand();
  cortexTesterState.locale = latestDashboard?.languageSettings?.current || currentLocale || cortexTesterState.locale;
}

function readCortexTesterInputs() {
  const commandInput = document.getElementById("cortex-request-input");
  const taskTypeInput = document.getElementById("cortex-task-type");
  const localeInput = document.getElementById("cortex-locale-input");
  const inputModesInput = document.getElementById("cortex-input-modes");
  const requiresNetworkInput = document.getElementById("cortex-requires-network");
  const requireArtifactsInput = document.getElementById("cortex-require-artifacts");
  const speakReplyInput = document.getElementById("cortex-speak-reply");
  if (commandInput) cortexTesterState.command = commandInput.value.trim();
  if (taskTypeInput) cortexTesterState.taskType = taskTypeInput.value || "general_chat";
  if (localeInput) cortexTesterState.locale = localeInput.value.trim() || currentLocale;
  if (inputModesInput) cortexTesterState.inputModes = inputModesInput.value.trim() || "text";
  if (requiresNetworkInput) cortexTesterState.requiresNetwork = Boolean(requiresNetworkInput.checked);
  if (requireArtifactsInput) cortexTesterState.requireArtifacts = Boolean(requireArtifactsInput.checked);
  if (speakReplyInput) cortexTesterState.speakReply = Boolean(speakReplyInput.checked);
}

function cortexStatusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value === "stable") return "is-ready";
  if (value === "experimental") return "is-planning";
  if (value === "planned") return "is-muted";
  return "is-muted";
}

function renderCortexUnpacked(payload = latestCortexUnpacked) {
  ensureCortexTesterState();
  const titleNode = document.getElementById("cortex-title");
  const guidanceNode = document.getElementById("cortex-guidance");
  const testTitleNode = document.getElementById("cortex-test-title");
  const runButton = document.getElementById("cortex-run-test");
  const statusNode = document.getElementById("cortex-test-status");
  const overviewNode = document.getElementById("cortex-overview");
  const loopNode = document.getElementById("cortex-loop");
  const architectureNode = document.getElementById("cortex-architecture");
  const capabilitiesNode = document.getElementById("cortex-capabilities");
  const featureStatusNode = document.getElementById("cortex-status");
  const jsonNode = document.getElementById("cortex-json");
  const requestInput = document.getElementById("cortex-request-input");
  const taskTypeInput = document.getElementById("cortex-task-type");
  const localeInput = document.getElementById("cortex-locale-input");
  const inputModesInput = document.getElementById("cortex-input-modes");
  const requiresNetworkInput = document.getElementById("cortex-requires-network");
  const requireArtifactsInput = document.getElementById("cortex-require-artifacts");
  const speakReplyInput = document.getElementById("cortex-speak-reply");

  setTextIfPresent("cortex-title", cortexCopy("title"));
  setTextIfPresent("cortex-guidance", cortexCopy("guidance"));
  setTextIfPresent("cortex-test-title", cortexCopy("testTitle"));
  setTextIfPresent("cortex-loop-title", cortexCopy("loop"));
  setTextIfPresent("cortex-architecture-title", cortexCopy("architecture"));
  setTextIfPresent("cortex-capability-title", cortexCopy("capability"));
  setTextIfPresent("cortex-status-title", cortexCopy("status"));
  setTextIfPresent("cortex-json-title", cortexCopy("raw"));
  if (runButton) {
    runButton.textContent = cortexTesterState.isLoading ? cortexCopy("running") : cortexCopy("run");
    runButton.disabled = cortexTesterState.isLoading;
  }
  if (requestInput && !requestInput.value) requestInput.value = cortexTesterState.command;
  if (taskTypeInput) taskTypeInput.value = cortexTesterState.taskType;
  if (localeInput) localeInput.value = cortexTesterState.locale;
  if (inputModesInput && !inputModesInput.value) inputModesInput.value = cortexTesterState.inputModes;
  if (requiresNetworkInput) requiresNetworkInput.checked = cortexTesterState.requiresNetwork;
  if (requireArtifactsInput) requireArtifactsInput.checked = cortexTesterState.requireArtifacts;
  if (speakReplyInput) speakReplyInput.checked = cortexTesterState.speakReply;
  if (statusNode) statusNode.textContent = cortexTesterState.status || cortexCopy("idle");

  const item = payload?.item || null;
  if (!item) {
    if (overviewNode) overviewNode.innerHTML = `<div class="settings-card"><p>${escapeHtml(cortexCopy("idle"))}</p></div>`;
    if (loopNode) loopNode.innerHTML = "";
    if (architectureNode) architectureNode.innerHTML = "";
    if (capabilitiesNode) capabilitiesNode.innerHTML = "";
    if (featureStatusNode) featureStatusNode.innerHTML = "";
    if (jsonNode) jsonNode.textContent = "";
    return;
  }

  const summary = item.summary || {};
  const autonomous = item.autonomousCreation || {};
  const request = payload.request || {};
  if (overviewNode) {
    overviewNode.innerHTML = `
      <div class="settings-overview-strip">
        <div class="settings-overview-card">
          <small>${escapeHtml(cortexCopy("overview"))}</small>
          <strong>${escapeHtml(summary.agentName || payload.seed?.agentName || "HomeHub Shared Brain")}</strong>
          <span>${escapeHtml(summary.brainMode || "execution-first")}</span>
        </div>
        <div class="settings-overview-card">
          <small>Task</small>
          <strong>${escapeHtml(request.taskType || "-")}</strong>
          <span>${escapeHtml((request.inputModes || []).join(" / ") || "-")}</span>
        </div>
        <div class="settings-overview-card">
          <small>Decision</small>
          <strong>${escapeHtml(autonomous.decision || autonomous.action || "reuse_or_create")}</strong>
          <span>${escapeHtml((autonomous.requirement?.requiredCapabilities || autonomous.proposedBrain?.requiredCapabilities || []).join(" / ") || "-")}</span>
        </div>
        <div class="settings-overview-card">
          <small>Models</small>
          <strong>${escapeHtml(summary.primaryPlanner || "-")}</strong>
          <span>${escapeHtml(summary.primaryExecutor || "-")}</span>
        </div>
      </div>
    `;
  }
  if (loopNode) {
    loopNode.innerHTML = (item.requestLoop?.steps || []).map((step, index) => `
      <div class="cortex-step-card">
        <div class="cortex-step-index">${index + 1}</div>
        <div>
          <strong>${escapeHtml(step.label || step.id || `Step ${index + 1}`)}</strong>
          <p>${escapeHtml(step.purpose || "")}</p>
          ${(step.modelRole || step.decisionMode) ? `<small>${escapeHtml(step.modelRole || step.decisionMode)}</small>` : ""}
        </div>
      </div>
    `).join("");
  }
  if (architectureNode) {
    architectureNode.innerHTML = (item.architectureExplorer?.zones || []).map((zone) => `
      <div class="cortex-zone-card">
        <div class="cortex-zone-head">
          <strong>${escapeHtml(zone.label || zone.id || "Zone")}</strong>
          <span class="mini-pill">${escapeHtml(zone.id || "")}</span>
        </div>
        <p>${escapeHtml(zone.purpose || "")}</p>
        ${(zone.modules || []).length ? `<small>${escapeHtml(zone.modules.join(" · "))}</small>` : ""}
        ${zone.state ? `<small>${escapeHtml(JSON.stringify(zone.state))}</small>` : ""}
      </div>
    `).join("");
  }
  if (capabilitiesNode) {
    capabilitiesNode.innerHTML = (item.capabilityExplorer?.groups || []).map((group) => `
      <div class="cortex-capability-card">
        <strong>${escapeHtml(group.label || group.id || "Group")}</strong>
        <div class="studio-meta">
          ${(group.items || []).map((capability) => `<span class="mini-pill capability">${escapeHtml(capability)}</span>`).join("")}
        </div>
      </div>
    `).join("");
  }
  if (featureStatusNode) {
    featureStatusNode.innerHTML = (item.featureStatus?.items || []).map((entry) => `
      <div class="relay-item">
        <strong>${escapeHtml(entry.label || entry.id || "Feature")}</strong>
        <span class="pill ${cortexStatusClass(entry.status)}">${escapeHtml(entry.status || "unknown")}</span>
      </div>
    `).join("");
  }
  if (jsonNode) {
    jsonNode.textContent = JSON.stringify(item, null, 2);
  }
}

async function loadCortexUnpacked(request = null) {
  ensureCortexTesterState();
  if (request) {
    cortexTesterState = {
      ...cortexTesterState,
      ...request
    };
  }
  cortexTesterState.isLoading = true;
  cortexTesterState.status = cortexCopy("running");
  renderCortexUnpacked();
  try {
    const response = await fetch("/api/cortex/unpacked", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command: cortexTesterState.command,
        locale: cortexTesterState.locale,
        taskType: cortexTesterState.taskType,
        inputModes: cortexTesterState.inputModes.split(",").map((item) => item.trim()).filter(Boolean),
        requireArtifacts: cortexTesterState.requireArtifacts,
        requiresNetwork: cortexTesterState.requiresNetwork,
        speakReply: cortexTesterState.speakReply
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || cortexCopy("failed"));
    }
    latestCortexUnpacked = payload;
    cortexTesterState.status = currentLocale === "zh-CN"
      ? "Cortex：已更新共享大脑蓝图。"
      : currentLocale === "ja-JP"
        ? "Cortex: 共有ブレインの設計を更新しました。"
        : "Cortex: Shared brain blueprint updated.";
  } catch (error) {
    cortexTesterState.status = `${cortexCopy("failed")} ${error.message || ""}`.trim();
  } finally {
    cortexTesterState.isLoading = false;
    renderCortexUnpacked(latestCortexUnpacked);
  }
}

function setupCortexControls() {
  const runButton = document.getElementById("cortex-run-test");
  if (!runButton) return;
  runButton.onclick = async () => {
    readCortexTesterInputs();
    await loadCortexUnpacked();
  };
}

function syncMailboxSettingsFromDom() {
  mailboxSettingsState.mailAddress = document.getElementById("mailbox-address")?.value?.trim() || mailboxSettingsState.mailAddress;
  mailboxSettingsState.mailPassword = document.getElementById("mailbox-password")?.value || mailboxSettingsState.mailPassword;
  mailboxSettingsState.mailSmtpHost = document.getElementById("mailbox-smtp-host")?.value?.trim() || mailboxSettingsState.mailSmtpHost;
  mailboxSettingsState.mailSmtpPort = document.getElementById("mailbox-smtp-port")?.value?.trim() || mailboxSettingsState.mailSmtpPort;
  mailboxSettingsState.mailImapHost = document.getElementById("mailbox-imap-host")?.value?.trim() || mailboxSettingsState.mailImapHost;
  mailboxSettingsState.mailImapPort = document.getElementById("mailbox-imap-port")?.value?.trim() || mailboxSettingsState.mailImapPort;
}

function initializeMailboxSettingsState(data) {
  const mailConfig = data.externalChannels?.mailConfig || {};
  if (!mailboxSettingsState.mailAddress) mailboxSettingsState.mailAddress = mailConfig.address || "";
  if (!mailboxSettingsState.mailSmtpHost) mailboxSettingsState.mailSmtpHost = mailConfig.smtpHost || "";
  if (!mailboxSettingsState.mailSmtpPort) mailboxSettingsState.mailSmtpPort = mailConfig.smtpPort || "";
  if (!mailboxSettingsState.mailImapHost) mailboxSettingsState.mailImapHost = mailConfig.imapHost || "";
  if (!mailboxSettingsState.mailImapPort) mailboxSettingsState.mailImapPort = mailConfig.imapPort || "";
}

function settingsSectionHeading(sectionId) {
  const item = settingsSectionCatalog()[sectionId];
  return item ? localizeCatalogText(item.label) : sectionId;
}

function settingsSectionSummary(sectionId) {
  const item = settingsSectionCatalog()[sectionId];
  return item ? localizeCatalogText(item.summary) : "";
}

function buildConceptText(kind) {
  const bundle = {
    session: {
      "zh-CN": "会话是使用者输入文字、语音、图片后的总入口。HomeHub 会先判断这是不是具体指令，再按需要路由到技能和智能体。",
      "ja-JP": "会話は文字、音声、画像の入力を受ける総合入口です。HomeHub はまず依頼かどうかを判断し、必要なスキルやエージェントに振り分けます。",
      "en-US": "A session is the shared intake surface for text, voice, and image input. HomeHub first decides whether the message is a concrete request, then routes it to the right skills and agents."
    },
    skills: {
      "zh-CN": "技能是一系列智能体操作的高频组合。HomeHub 会根据流程使用率，把可复用的流程沉淀成技能，方便多次调用。",
      "ja-JP": "スキルは複数のエージェント操作をまとめた高頻度フローです。HomeHub は利用頻度を見て再利用しやすい流れをスキル化します。",
      "en-US": "Skills are reusable flows composed of multiple agent actions. HomeHub promotes repeated patterns into skills when it sees stable usage."
    },
    agents: {
      "zh-CN": "智能体是最小可理解的执行单元，例如提醒、OCR 提取、联网检索、分析与归档。",
      "ja-JP": "エージェントは最小の実行単位で、リマインダー、OCR、検索、分析、保存などを担当します。",
      "en-US": "Agents are the smallest understandable execution units, such as reminders, OCR extraction, search, analysis, or archival."
    },
    models: {
      "zh-CN": "AI 模型是智能体可调用的推理能力层，包括本地模型、云模型，以及按能力归类的模型目录。",
      "ja-JP": "AI モデルはエージェントが呼び出す推論レイヤーで、ローカルモデル、クラウドモデル、能力別カタログを含みます。",
      "en-US": "AI models are the reasoning layer agents can call, including local models, cloud models, and capability-specific catalogs."
    }
  };
  return bundle[kind]?.[currentLocale] || bundle[kind]?.["en-US"] || "";
}

function activateSettingsSection(sectionId, focusButton = false) {
  activeSettingsSection = settingsSectionCatalog()[sectionId] ? sectionId : "language";
  if (activeSettingsSection === "artifacts" && !generatedArtifactsRuntime.isLoading) {
    loadGeneratedArtifacts().catch(() => {});
  }
  if (activeSettingsSection === "memory" && !runtimeMemoryInspection.isLoading) {
    loadRuntimeMemoryInspection().catch(() => {});
  }
  if (activeSettingsSection === "training" && !trainingAssetsInspection.isLoading) {
    loadTrainingAssetsInspection().catch(() => {});
  }
  if (latestDashboard) {
    renderSettings(latestDashboard);
  }
  if (focusButton) {
    requestAnimationFrame(() => {
      document.querySelector(`[data-settings-section="${activeSettingsSection}"]`)?.focus();
    });
  }
}

function renderSettingsDirectory() {
  const nav = document.getElementById("settings-directory-list");
  if (!nav) return;
  nav.innerHTML = Object.entries(settingsSectionCatalog()).map(([id, item]) => `
    <button
      type="button"
      class="settings-directory-item remote-target ${activeSettingsSection === id ? "is-selected" : ""}"
      data-settings-section="${id}"
      data-title="${escapeHtml(localizeCatalogText(item.label))}"
    >
      <strong>${escapeHtml(localizeCatalogText(item.label))}</strong>
      <span>${escapeHtml(localizeCatalogText(item.summary))}</span>
    </button>
  `).join("");
  nav.querySelectorAll("[data-settings-section]").forEach((button) => {
    button.onclick = () => activateSettingsSection(button.dataset.settingsSection, true);
  });
}

async function saveMailboxSettings() {
  syncMailboxSettingsFromDom();
  mailboxSettingsState.isSaving = true;
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/settings/secrets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mailAddress: mailboxSettingsState.mailAddress,
        mailPassword: mailboxSettingsState.mailPassword,
        mailSmtpHost: mailboxSettingsState.mailSmtpHost,
        mailSmtpPort: mailboxSettingsState.mailSmtpPort,
        mailImapHost: mailboxSettingsState.mailImapHost,
        mailImapPort: mailboxSettingsState.mailImapPort
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to save mailbox settings.");
    }
    mailboxSettingsState.status = s("mailboxSaved", "HomeHub: Mailbox settings saved.");
    updateSpokenLine(mailboxSettingsState.status);
    await loadDashboard();
  } catch (error) {
    mailboxSettingsState.status = `${s("mailboxSaveFailed", "HomeHub: Failed to save mailbox settings.")} ${String(error.message || error)}`.trim();
    updateSpokenLine(mailboxSettingsState.status);
    renderSettings(latestDashboard);
  } finally {
    mailboxSettingsState.isSaving = false;
    renderSettings(latestDashboard);
  }
}

function populateAiModelsSection(data, language) {
  const catalog = data.audioProviders?.catalog || {};
  const secrets = data.audioProviders?.secrets || {};
  const modelCatalog = data.modelCatalog || [];
  const counts = data.audioProviders?.counts || { total: modelCatalog.length, editable: 0 };
  const runtimeProfile = data.runtimeProfile || null;
  const modelStackCards = document.getElementById("model-stack-cards");
  const audioStack = document.getElementById("audio-stack");
  if (!modelStackCards || !audioStack) return;

  modelStackCards.innerHTML = modelCatalog.map((item) => `
    <div class="provider-card focusable-card ${item.editable ? "is-selected-provider" : ""}" tabindex="0" data-title="${escapeHtml(item.label)}">
      <strong>${item.label}</strong>
      <div class="meta-row">
        <span class="mini-pill source">${item.source}</span>
        ${item.deployment ? `<span class="mini-pill deployment">${escapeHtml(item.deployment)}</span>` : ""}
        ${item.access ? `<span class="mini-pill access">${escapeHtml(item.access)}</span>` : ""}
        ${item.status ? `<span class="mini-pill status">${escapeHtml(item.status)}</span>` : ""}
        ${item.capabilities.map((capability) => `<span class="mini-pill capability">${capability}</span>`).join("")}
      </div>
      <p>${item.summary}</p>
      <div class="provider-models">
        ${item.models.map((model) => `<span>${escapeHtml(model)}</span>`).join("")}
      </div>
      <small>${(item.languages || []).join(" / ")}</small>
      <small>${t("settings.syncOpenclaw")}: ${item.sync?.openclaw || "manual"} | ${t("settings.syncWorkbuddy")}: ${item.sync?.workbuddy || "manual"}</small>
      ${(item.requirements || []).length ? `<div class="provider-notes"><strong>${escapeHtml(s("providerNeeds", "Needs"))}</strong><ul>${item.requirements.map((requirement) => `<li>${escapeHtml(requirement)}</li>`).join("")}</ul></div>` : ""}
      ${(item.notes || []).length ? `<div class="provider-notes"><strong>${escapeHtml(s("providerRouteTips", "Route Tips"))}</strong><ul>${item.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul></div>` : ""}
      ${item.installCommand ? `<div class="provider-install"><strong>${escapeHtml(s("providerInstall", "Install"))}</strong><code>${escapeHtml(item.installCommand)}</code></div>` : ""}
      <div class="provider-actions">
        ${(item.actions || []).map((action) => `
          <button
            type="button"
            class="provider-action remote-target ${action.selected ? "is-selected" : ""}"
            data-provider-type="${action.type}"
            data-provider-id="${item.id.replace(/^provider-/, "")}"
            data-title="${escapeHtml(item.label)}"
          >${action.type === "stt" ? t("settings.useStt") : t("settings.useTts")}${action.selected ? ` · ${t("settings.selected")}` : ""}</button>
        `).join("")}
      </div>
    </div>
  `).join("");

  audioStack.innerHTML = `
    <div class="settings-detail-grid">
      <div class="settings-card">
        <strong>${t("settings.speechToText")}</strong>
        <p>${t("settings.provider")}: ${data.audioStack.stt.provider}</p>
        <p>${t("settings.primary")}: ${data.audioStack.stt.primaryModel}</p>
        <p>${t("settings.fallback")}: ${data.audioStack.stt.fallbackModel}</p>
        <p>${t("settings.mode")}: ${data.audioStack.stt.mode}</p>
      </div>
      <div class="settings-card">
        <strong>${t("settings.textToSpeech")}</strong>
        <p>${t("settings.provider")}: ${data.audioStack.tts.provider}</p>
        <p>${t("settings.primary")}: ${data.audioStack.tts.primaryModel}</p>
        <p>${t("settings.fallback")}: ${data.audioStack.tts.fallbackModel}</p>
        <p>${t("settings.mode")}: ${data.audioStack.tts.mode}</p>
      </div>
      <div class="settings-card">
        <strong>${t("settings.realtimeRecommendation")}</strong>
        <p>${data.audioStack.recommendedRealtime}</p>
        <p>${t("settings.currentUiLanguage")}: ${language?.label || data.voiceProfile.locale}</p>
        <p>${t("settings.totalStacks")}: ${counts.total}</p>
        <p>${t("settings.googleKey")}: ${secrets.googleConfigured ? t("settings.configured") : t("settings.missing")}</p>
        <p>${t("settings.openaiKey")}: ${secrets.openaiConfigured ? t("settings.configured") : t("settings.missing")}</p>
      </div>
      <div class="settings-card">
        <strong>${escapeHtml(s("runtimeStrategy", "Runtime Strategy"))}</strong>
        ${runtimeProfile ? `
          <p>${escapeHtml(runtimeProfile.label || "-")}</p>
          <p>${escapeHtml(runtimeProfile.summary || "-")}</p>
          <p>${escapeHtml(s("runtimeLocal", "Local"))}: ${escapeHtml((runtimeProfile.localRoles || []).join(" / ") || "-")}</p>
          <p>${escapeHtml(s("runtimeCloud", "Cloud"))}: ${escapeHtml((runtimeProfile.cloudRoles || []).join(" / ") || "-")}</p>
          <p>${escapeHtml(s("runtimeInstalled", "Installed local models"))}: ${escapeHtml((runtimeProfile.localDetected || []).slice(0, 5).join(", ") || "-")}</p>
        ` : `<p>-</p>`}
      </div>
    </div>
  `;
  setupCustomProviderControls();
}

function buildSettingsOverview(data, language) {
  const pairing = data.pairingSession || {};
  const mailConfig = data.externalChannels?.mailConfig || {};
  const modelCount = data.audioProviders?.counts?.total || 0;
  return `
    <div class="settings-overview-strip">
      <div class="settings-overview-card">
        <strong>${escapeHtml(s("overviewLanguage", "Language"))}</strong>
        <span>${escapeHtml(language?.label || currentLocale)}</span>
      </div>
      <div class="settings-overview-card">
        <strong>${escapeHtml(s("overviewPairing", "Pairing"))}</strong>
        <span>${escapeHtml(pairing.code || "-")}</span>
      </div>
      <div class="settings-overview-card">
        <strong>${escapeHtml(s("overviewMailbox", "Mailbox"))}</strong>
        <span>${escapeHtml(mailConfig.address || (mailConfig.configured ? s("configured", "configured") : "-"))}</span>
      </div>
      <div class="settings-overview-card">
        <strong>${escapeHtml(s("overviewModels", "AI Models"))}</strong>
        <span>${escapeHtml(String(modelCount))}</span>
      </div>
    </div>
  `;
}

function initializeAvatarSettingsState(data) {
  const avatar = data.assistantAvatar || {};
  if (!avatarSettingsState.customModelUrl) {
    avatarSettingsState.customModelUrl = avatar.customModelUrl || "/generated/avatar/pixellabs-glb-3347.glb";
  }
}

function syncAvatarSettingsFromDom() {
  const input = document.getElementById("avatar-custom-model-url");
  if (input) {
    avatarSettingsState.customModelUrl = String(input.value || "").trim();
  }
}

function renderSettingsDetail(data) {
  const detail = document.getElementById("settings-detail");
  if (!detail) return;
  initializeAvatarSettingsState(data);
  const language = getCurrentLanguage(data);
  const mailConfig = data.externalChannels?.mailConfig || {};
  const mailData = data.externalChannels?.mail || {};
  const agentTypes = data.agentTypes || [];
  const defaultRecipient = mailTesterState.to || mailboxSettingsState.mailAddress || "";
  const defaultSubject = mailTesterState.subject || s("mailDefaultSubject", "HomeHub mail test");
  const defaultBody = mailTesterState.body || s("mailDefaultBody", "Hello from HomeHub.");
  const overview = buildSettingsOverview(data, language);

  if (activeSettingsSection === "language") {
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("language"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("language"))}</h3>
        </div>
        <span class="pill">${escapeHtml(t("settings.languageBadge"))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("language"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>${escapeHtml(language?.label || currentLocale)}</strong>
          <select id="language-select" class="settings-input remote-target" data-title="${escapeHtml(language?.label || currentLocale)}">
            ${(data.languageSettings?.supported || []).map((item) => `
              <option value="${escapeHtml(item.code)}" ${item.code === language?.code ? "selected" : ""}>${escapeHtml(item.label)} · ${escapeHtml(item.code)}</option>
            `).join("")}
          </select>
          <p>${escapeHtml(language?.sample || "")}</p>
        </div>
        <div class="settings-card">
          <strong>${escapeHtml(s("sectionSession", "Session"))}</strong>
          <p>${escapeHtml(buildConceptText("session"))}</p>
        </div>
      </div>
    `;
    const languageSelect = document.getElementById("language-select");
    if (languageSelect) {
      languageSelect.onchange = async (event) => {
        const nextCode = String(event.target?.value || "").trim();
        if (nextCode) await persistLanguage(nextCode);
      };
    }
    return;
  }

  if (activeSettingsSection === "avatar") {
    const avatar = data.assistantAvatar || getAssistantAvatarConfig();
    const isCustom = avatar.mode === "custom";
    const stackList = Array.isArray(avatar.techStack) ? avatar.techStack : [];
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("avatar"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("avatar"))}</h3>
        </div>
        <span class="pill">${escapeHtml(isCustom ? "GLB / Three.js" : s("avatarBadgeDefault", "Default Backup"))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("avatar"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>${escapeHtml(s("avatarCurrent", "Current Avatar"))}</strong>
          <p>${escapeHtml(isCustom ? s("avatarActiveCustom", "Your custom GLB robot is active") : s("avatarActiveBackup", "The backup house mascot is active"))}</p>
          <p>${escapeHtml(s("avatarCustomModelUrl", "Custom model URL"))}: ${escapeHtml(avatar.customModelUrl || "-")}</p>
          <input
            id="avatar-custom-model-url"
            class="settings-input full-span"
            type="text"
            placeholder="/generated/avatar/your-model.glb"
            value="${escapeHtml(avatarSettingsState.customModelUrl || avatar.customModelUrl || "")}"
          />
          <div class="avatar-mode-actions">
            <button id="avatar-use-custom" class="remote-target ${isCustom ? "is-selected-provider" : ""}" type="button">${escapeHtml(s("avatarUseCustom", "Use GLB Robot"))}</button>
            <button id="avatar-use-house" class="remote-target ${!isCustom ? "is-selected-provider" : ""}" type="button">${escapeHtml(s("avatarUseBackup", "Return to House Mascot"))}</button>
            <button id="avatar-save-model-url" class="remote-target" type="button">${escapeHtml(avatarSettingsState.isSaving ? s("avatarSaving", "Saving...") : s("avatarSaveModelUrl", "Save Model URL"))}</button>
          </div>
        </div>
        <div class="settings-card">
          <strong>${escapeHtml(s("avatarStack", "Integrated Stack"))}</strong>
          <div class="avatar-tech-list">
            ${stackList.map((item) => `
              <div class="avatar-tech-item">
                <span>${escapeHtml(item.label || "")}</span>
                <strong>${escapeHtml(item.value || "")}</strong>
              </div>
            `).join("")}
          </div>
        </div>
      </div>
      <div class="settings-stack">
        <div class="settings-card">
          <strong>${escapeHtml(s("avatarNotes", "Integration Notes"))}</strong>
          <p>${escapeHtml(s("avatarNote1", "This setup prioritizes your GLB model and renders it with Three.js. If the 3D asset fails to load, you can switch back to the default house mascot here."))}</p>
          <p>${escapeHtml(s("avatarNote2", "This GLB does not contain built-in skeletal or BlendShape animation tracks, so speaking/listening/thinking are currently driven by frontend state animation. If you later swap in an animated GLB, this same entry point still works."))}</p>
        </div>
      </div>
    `;
    const customButton = document.getElementById("avatar-use-custom");
    const houseButton = document.getElementById("avatar-use-house");
    const saveModelUrlButton = document.getElementById("avatar-save-model-url");
    const modelUrlInput = document.getElementById("avatar-custom-model-url");
    if (modelUrlInput) {
      modelUrlInput.oninput = () => {
        syncAvatarSettingsFromDom();
      };
    }
    if (customButton) customButton.onclick = async () => {
      syncAvatarSettingsFromDom();
      await persistAssistantAvatar("custom", avatarSettingsState.customModelUrl || avatar.customModelUrl);
    };
    if (houseButton) houseButton.onclick = async () => {
      syncAvatarSettingsFromDom();
      await persistAssistantAvatar("house", avatarSettingsState.customModelUrl || avatar.customModelUrl);
    };
    if (saveModelUrlButton) saveModelUrlButton.onclick = async () => {
      syncAvatarSettingsFromDom();
      await persistAssistantAvatar(avatar.mode || "custom", avatarSettingsState.customModelUrl || avatar.customModelUrl);
    };
    return;
  }

  if (activeSettingsSection === "artifacts") {
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">Generated Artifacts</p>
          <h3>Generated Artifacts</h3>
        </div>
        <span class="pill">runtime/generated</span>
      </div>
      <p class="settings-section-copy">Browse and delete blueprints, agents, and features generated at runtime without touching core source files.</p>
      <div class="studio-actions">
        <button id="generated-artifacts-refresh" class="test-action remote-target" type="button">Refresh</button>
      </div>
      ${generatedArtifactsRuntime.isLoading ? `<div class="settings-card"><p>Loading generated artifacts...</p></div>` : ""}
      ${generatedArtifactsRuntime.error ? `<div class="settings-card"><p>${escapeHtml(generatedArtifactsRuntime.error)}</p></div>` : ""}
      ${renderGeneratedArtifactGroups()}
    `;
    const refreshButton = document.getElementById("generated-artifacts-refresh");
    if (refreshButton) refreshButton.onclick = () => loadGeneratedArtifacts();
    detail.querySelectorAll("[data-generated-delete]").forEach((button) => {
      button.onclick = async () => {
        const [category, artifactId] = String(button.dataset.generatedDelete || "").split(":");
        if (category && artifactId) await deleteGeneratedArtifact(category, artifactId);
      };
    });
    return;
  }

  if (activeSettingsSection === "memory") {
    const result = runtimeMemoryInspection.result || {};
    const semanticSummary = result.semantic_memory_summary || {};
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">Runtime Memory</p>
          <h3>Runtime Memory</h3>
        </div>
        <span class="pill">promotion + facts</span>
      </div>
      <p class="settings-section-copy">Inspect what HomeHub promoted into long-term memory, including artifacts, structured facts, and reusable experiences.</p>
      <div class="mail-tester-grid">
        <input id="runtime-memory-query" class="settings-input full-span" type="text" placeholder="Search memory, e.g. 供应商甲 / 联调 / project" value="${escapeHtml(runtimeMemoryInspection.query || "")}" />
        <select id="runtime-memory-namespace" class="settings-input">
          ${["*", "document_analysis", "information_agent", "information_agent_fact"].map((item) => `<option value="${escapeHtml(item)}" ${runtimeMemoryInspection.namespace === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
        </select>
      </div>
      <div class="studio-actions">
        <button id="runtime-memory-refresh" class="test-action remote-target" type="button">Inspect</button>
      </div>
      ${runtimeMemoryInspection.isLoading ? `<div class="settings-card"><p>Loading runtime memory...</p></div>` : ""}
      ${runtimeMemoryInspection.error ? `<div class="settings-card"><p>${escapeHtml(runtimeMemoryInspection.error)}</p></div>` : ""}
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>Semantic Memory Summary</strong>
          <pre class="cortex-json-view">${escapeHtml(JSON.stringify(semanticSummary, null, 2))}</pre>
        </div>
        <div class="settings-card">
          <strong>Latest Rollback</strong>
          <pre class="cortex-json-view">${escapeHtml(JSON.stringify(result.semantic_memory_latest_rollback || {}, null, 2))}</pre>
        </div>
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Promotion Artifacts</h3></div>
        ${renderRuntimeMemoryArtifacts(result)}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Vector Hits</h3></div>
        ${renderRuntimeMemoryHits(result)}
      </div>
    `;
    const refreshButton = document.getElementById("runtime-memory-refresh");
    const queryInput = document.getElementById("runtime-memory-query");
    const namespaceInput = document.getElementById("runtime-memory-namespace");
    if (refreshButton) {
      refreshButton.onclick = () => loadRuntimeMemoryInspection(queryInput?.value || "", namespaceInput?.value || "*");
    }
    return;
  }

  if (activeSettingsSection === "training") {
    const result = trainingAssetsInspection.result || {};
    const summary = result.summary || {};
    const manifest = result.manifest || {};
    const runner = result.runner || {};
    const artifacts = result.artifacts || {};
    const lastRun = result.last_run || result.lastRun || null;
    const latestRuns = result.latest_runs || [];
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">Training Assets</p>
          <h3>Training Assets</h3>
        </div>
        <span class="pill">manifest + datasets</span>
      </div>
      <p class="settings-section-copy">Inspect the private-brain training pipeline outputs, including SFT/preference datasets, repair preference signals, and the train-ready manifest profile.</p>
      <div class="mail-tester-grid training-controls-grid">
        <select id="training-assets-profile" class="settings-input">
          ${["lora_sft"].map((item) => `<option value="${escapeHtml(item)}" ${trainingAssetsInspection.profile === item ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")}
        </select>
        <select id="training-assets-backend" class="settings-input">
          ${renderTrainingBackendOptions(runner)}
        </select>
      </div>
      <div class="studio-actions training-action-row">
        <button id="training-assets-refresh" class="test-action remote-target" type="button">Inspect</button>
        <button id="training-assets-rebuild" class="test-action remote-target is-secondary" type="button">Rebuild Manifest</button>
        <button id="training-assets-dry-run" class="test-action remote-target" type="button">Generate Dry Run</button>
      </div>
      ${trainingAssetsInspection.isLoading ? `<div class="settings-card"><p>Loading training assets...</p></div>` : ""}
      ${trainingAssetsInspection.isRunning ? `<div class="settings-card"><p>Generating training run skeleton...</p></div>` : ""}
      ${trainingAssetsInspection.error ? `<div class="settings-card"><p>${escapeHtml(trainingAssetsInspection.error)}</p></div>` : ""}
      ${trainingAssetsInspection.notice ? `<div class="settings-card"><p>${escapeHtml(trainingAssetsInspection.notice)}</p></div>` : ""}
      <div class="training-metrics-grid">
        ${renderTrainingMetricCards(summary, manifest, runner)}
      </div>
      <div class="settings-detail-grid">
        ${renderTrainingPlan(manifest.training_plan || {})}
        ${renderCommandPreview(runner.command_preview || lastRun?.command_preview || [])}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Repair Preferences</h3></div>
        ${renderRepairPreferenceCounts(result.repair_preference_counts || summary.repair_preference_counts || {})}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>SFT Datasets</h3></div>
        ${renderTrainingArtifactRows(manifest.datasets?.sft || artifacts.dataset_sft || [], "No SFT datasets yet.")}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Preference Datasets</h3></div>
        ${renderTrainingArtifactRows(manifest.datasets?.preference || artifacts.dataset_preference || [], "No preference datasets yet.")}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Manifest Artifacts</h3></div>
        ${renderTrainingArtifactRows(artifacts.dataset_manifest || [], "No manifest artifacts yet.")}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Run Specs</h3></div>
        ${lastRun ? renderTrainingArtifactRows([{ name: lastRun.run_id || "run", path: lastRun.artifact_path || "", profile: lastRun.status || "", sample_count: lastRun.ready ? 1 : 0 }], "No run specs yet.") : renderTrainingArtifactRows(artifacts.dataset_run || [], "No run specs yet.")}
      </div>
      <div class="settings-stack">
        <div class="panel-header compact"><h3>Latest Run Timeline</h3></div>
        ${renderTrainingRunTimeline(latestRuns, lastRun)}
      </div>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>Layer Summary</strong>
          <pre class="cortex-json-view">${escapeHtml(JSON.stringify(summary, null, 2))}</pre>
        </div>
        <div class="settings-card">
          <strong>Training Manifest</strong>
          <pre class="cortex-json-view">${escapeHtml(JSON.stringify(manifest, null, 2))}</pre>
        </div>
      </div>
    `;
    const refreshButton = document.getElementById("training-assets-refresh");
    const rebuildButton = document.getElementById("training-assets-rebuild");
    const dryRunButton = document.getElementById("training-assets-dry-run");
    const profileInput = document.getElementById("training-assets-profile");
    const backendInput = document.getElementById("training-assets-backend");
    if (refreshButton) {
      refreshButton.onclick = () => loadTrainingAssetsInspection(profileInput?.value || "lora_sft");
    }
    if (rebuildButton) {
      rebuildButton.onclick = () => rebuildTrainingAssets(profileInput?.value || "lora_sft");
    }
    if (dryRunButton) {
      dryRunButton.onclick = () => runTrainingAssetsDryRun(profileInput?.value || "lora_sft", backendInput?.value || "mock");
    }
    return;
  }

  if (activeSettingsSection === "pairing") {
    const pairing = data.pairingSession || {};
    const relayMessages = data.relayMessages || [];
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("pairing"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("pairing"))}</h3>
        </div>
        <span class="pill">${escapeHtml(s("pairingBadge", "QR + Relay"))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("pairing"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <div class="qr-box">
            <div class="fake-qr remote-target focusable-card" aria-label="pairing qr" tabindex="0">
              <span id="pairing-code">${escapeHtml(pairing.code || "-")}</span>
            </div>
            <div>
              <p id="pairing-description">${escapeHtml(t("pairing.description"))}</p>
              <p id="pairing-expiry">${escapeHtml(t("pairing.expiresIn"))}: ${escapeHtml(String(pairing.expiresInSeconds || 0))}s</p>
              <small id="pairing-payload">${escapeHtml(pairing.qrPayload || "-")}</small>
            </div>
          </div>
        </div>
        <div class="settings-card">
          <div class="panel-header compact">
            <h3>${escapeHtml(s("relayMessages", "Relay Messages"))}</h3>
            <span class="pill">${relayMessages.length}</span>
          </div>
          <div class="mini-list" id="relay">
            ${relayMessages.map((message) => `
              <div class="relay-item remote-target focusable-card" tabindex="0" data-title="${escapeHtml(message.source)}">
                <strong>${escapeHtml(message.source)}</strong>
                <span>${escapeHtml(message.preview)}</span>
              </div>
            `).join("") || `<div class="settings-card"><p>${escapeHtml(s("relayEmpty", "No relay messages right now."))}</p></div>`}
          </div>
        </div>
      </div>
    `;
    return;
  }

  if (activeSettingsSection === "mailbox") {
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("mailbox"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("mailbox"))}</h3>
        </div>
        <span class="pill">${escapeHtml(t("mail.badge"))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("mailbox"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>${escapeHtml(s("mailboxConfig", "Mailbox Configuration"))}</strong>
          <div class="mail-tester-grid">
            <input id="mailbox-address" class="settings-input full-span" type="email" placeholder="${escapeHtml(t("mail.address"))}" value="${escapeHtml(mailboxSettingsState.mailAddress)}" />
            <input id="mailbox-password" class="settings-input full-span" type="password" placeholder="${escapeHtml(s("mailboxPasswordPlaceholder", "Mailbox password / app password"))}" value="${escapeHtml(mailboxSettingsState.mailPassword)}" />
            <input id="mailbox-smtp-host" class="settings-input" type="text" placeholder="SMTP Host" value="${escapeHtml(mailboxSettingsState.mailSmtpHost)}" />
            <input id="mailbox-smtp-port" class="settings-input" type="text" placeholder="SMTP Port" value="${escapeHtml(mailboxSettingsState.mailSmtpPort)}" />
            <input id="mailbox-imap-host" class="settings-input" type="text" placeholder="IMAP Host" value="${escapeHtml(mailboxSettingsState.mailImapHost)}" />
            <input id="mailbox-imap-port" class="settings-input" type="text" placeholder="IMAP Port" value="${escapeHtml(mailboxSettingsState.mailImapPort)}" />
          </div>
          <div class="mail-tester-actions">
            <button id="mailbox-save-button" class="remote-target" type="button">${mailboxSettingsState.isSaving ? escapeHtml(s("mailboxSaving", "Saving...")) : escapeHtml(s("mailboxSave", "Save Mailbox Settings"))}</button>
          </div>
          <div class="mail-tester-status">${escapeHtml(mailboxSettingsState.status || (mailConfig.configured ? s("mailboxReady", "The current mailbox is configured and ready.") : s("mailboxNeedConfig", "Fill in the mailbox address, password, and server settings first.")))}</div>
        </div>
        <div class="settings-card mail-tester-card">
          <div class="panel-header compact">
            <h3>${t("mail.title")}</h3>
            <span class="pill">${t("mail.badge")}</span>
          </div>
          <p><strong>${t("mail.address")}:</strong> ${escapeHtml(mailConfig.address || mailboxSettingsState.mailAddress || "-")}</p>
          <p>${escapeHtml(s("mailInbox", "Inbox"))}: ${Array.isArray(mailData.inbox) ? mailData.inbox.length : 0} · ${escapeHtml(s("mailOutbox", "Outbox"))}: ${Array.isArray(mailData.outbox) ? mailData.outbox.length : 0} · ${escapeHtml(s("mailLastSync", "Last sync"))}: ${escapeHtml(mailData.lastSyncAt || "-")}</p>
          <div class="mail-tester-grid">
            <input id="mail-test-to" class="settings-input full-span" type="email" placeholder="${escapeHtml(t("mail.recipient"))}" value="${escapeHtml(defaultRecipient)}" />
            <input id="mail-test-subject" class="settings-input full-span" type="text" placeholder="${escapeHtml(t("mail.subject"))}" value="${escapeHtml(defaultSubject)}" />
            <textarea id="mail-test-body" class="settings-input full-span custom-summary" placeholder="${escapeHtml(t("mail.body"))}">${escapeHtml(defaultBody)}</textarea>
          </div>
          <div class="mail-tester-actions">
            <button id="mail-sync-button" class="remote-target" type="button">${mailTesterState.isSyncing ? `${t("mail.sync")}...` : t("mail.sync")}</button>
            <button id="mail-send-button" class="remote-target" type="button">${mailTesterState.isSending ? `${t("mail.send")}...` : t("mail.send")}</button>
          </div>
          <div class="mail-tester-status" id="mail-tester-status">${escapeHtml(mailTesterState.status || t("mail.statusIdle"))}</div>
        </div>
      </div>
    `;
    const mailboxSaveButton = document.getElementById("mailbox-save-button");
    const mailSyncButton = document.getElementById("mail-sync-button");
    const mailSendButton = document.getElementById("mail-send-button");
    if (mailboxSaveButton) mailboxSaveButton.onclick = async () => { await saveMailboxSettings(); };
    if (mailSyncButton) mailSyncButton.onclick = async () => { await syncMailTester(); };
    if (mailSendButton) mailSendButton.onclick = async () => { await sendMailTester(); };
    return;
  }

  if (activeSettingsSection === "skills") {
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("skills"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("skills"))}</h3>
        </div>
        <span class="pill">${escapeHtml(String((data.skillCatalog || []).length))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("skills"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>${escapeHtml(s("sectionSession", "Session"))}</strong>
          <p>${escapeHtml(buildConceptText("session"))}</p>
        </div>
        <div class="settings-card">
          <strong>${escapeHtml(s("sectionSkills", "Skills"))}</strong>
          <p>${escapeHtml(buildConceptText("skills"))}</p>
        </div>
      </div>
      <div class="settings-stack">
        ${(data.skillCatalog || []).map((skill) => `
          <div class="settings-card">
            <strong>${escapeHtml(skill.name)}</strong>
            <p>${escapeHtml(skill.description)}</p>
            <small>${escapeHtml((skill.inputModes || []).join(" / "))}</small>
          </div>
        `).join("")}
      </div>
    `;
    return;
  }

  if (activeSettingsSection === "agents") {
    detail.innerHTML = `
      ${overview}
      <div class="settings-section-header">
        <div>
          <p class="eyebrow">${escapeHtml(settingsSectionHeading("agents"))}</p>
          <h3>${escapeHtml(settingsSectionHeading("agents"))}</h3>
        </div>
        <span class="pill">${escapeHtml(String((data.activeAgents || []).length))}</span>
      </div>
      <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("agents"))}</p>
      <div class="settings-detail-grid">
        <div class="settings-card">
          <strong>${escapeHtml(s("sectionAgents", "Agents"))}</strong>
          <p>${escapeHtml(buildConceptText("agents"))}</p>
        </div>
        <div class="settings-card">
          <strong>${escapeHtml(s("sectionAvailableTypes", "Available Types"))}</strong>
          <p>${escapeHtml(agentTypes.map((item) => item.name).slice(0, 4).join(" / ") || "-")}</p>
        </div>
      </div>
      <div class="settings-stack">
        ${(data.activeAgents || []).map((agent) => `
          <div class="agent-card remote-target focusable-card" tabindex="0" data-title="${escapeHtml(agent.name)}">
            <div class="agent-row">
              <strong>${escapeHtml(agent.name)}</strong>
              <span class="pill ${stateColor[agent.status] || "is-muted"}">${escapeHtml(localizeStatusWord(agent.status))}</span>
            </div>
            <p>${escapeHtml(agent.role)}</p>
            <div class="progress"><div style="width:${agent.progress}%"></div></div>
            <small>${escapeHtml(agent.lastUpdate)}</small>
          </div>
        `).join("")}
      </div>
    `;
    return;
  }

  detail.innerHTML = `
    ${overview}
    <div class="settings-section-header">
      <div>
        <p class="eyebrow">${escapeHtml(settingsSectionHeading("ai-models"))}</p>
        <h3>${escapeHtml(settingsSectionHeading("ai-models"))}</h3>
      </div>
      <span class="pill">${escapeHtml(t("settings.catalogBadge"))}</span>
    </div>
    <p class="settings-section-copy">${escapeHtml(settingsSectionSummary("ai-models"))}</p>
    <div class="settings-detail-grid">
      <div class="settings-card">
        <strong>${escapeHtml(s("sectionSkills", "Skills"))}</strong>
        <p>${escapeHtml(buildConceptText("skills"))}</p>
      </div>
      <div class="settings-card">
        <strong>${escapeHtml(s("sectionAiModels", "AI Models"))}</strong>
        <p>${escapeHtml(buildConceptText("models"))}</p>
      </div>
    </div>
    <div class="settings-stack" id="audio-stack"></div>
    <div class="catalog-grid" id="model-stack-cards"></div>
    <div class="custom-provider-form">
      <div class="panel-header compact">
        <h3 id="custom-stack-title">${t("settings.customStackTitle")}</h3>
        <span class="pill" id="custom-stack-pill">${t("settings.customStackBadge")}</span>
      </div>
      <div class="custom-provider-grid">
        <input id="custom-provider-id" class="settings-input" type="text" placeholder="${escapeHtml(s("customEntryId", "entry-id"))}" />
        <input id="custom-provider-label" class="settings-input" type="text" placeholder="${escapeHtml(s("customDisplayName", "Display name"))}" />
        <input id="custom-source" class="settings-input" type="text" placeholder="${escapeHtml(s("customSource", "Source: OpenClaw / WorkBuddy / Custom"))}" />
        <input id="custom-capabilities" class="settings-input" type="text" placeholder="${escapeHtml(s("customCapabilities", "Capabilities: Wake Word, ASR, LLM, RAG"))}" />
        <input id="custom-models" class="settings-input full-span" type="text" placeholder="${escapeHtml(s("customModels", "Models: Porcupine, Whisper, Qwen2.5"))}" />
        <textarea id="custom-summary" class="settings-input full-span custom-summary" placeholder="${escapeHtml(s("customSummary", "Summary of what this stack or capability does"))}"></textarea>
        <select id="custom-sync-openclaw" class="settings-input"><option value="manual">${escapeHtml(s("syncOpenclawManual", "OpenClaw sync: Manual"))}</option><option value="aligned">${escapeHtml(s("syncOpenclawAligned", "OpenClaw sync: Aligned"))}</option><option value="config-compatible">${escapeHtml(s("syncOpenclawCompatible", "OpenClaw sync: Config compatible"))}</option></select>
        <select id="custom-sync-workbuddy" class="settings-input"><option value="manual">${escapeHtml(s("syncWorkbuddyManual", "WorkBuddy sync: Manual"))}</option><option value="not-supported">${escapeHtml(s("syncWorkbuddyUnsupported", "WorkBuddy sync: Not supported"))}</option><option value="conceptual">${escapeHtml(s("syncWorkbuddyConceptual", "WorkBuddy sync: Conceptual only"))}</option></select>
        <input id="custom-languages" class="settings-input full-span" type="text" placeholder="zh-CN,en-US,ja-JP" />
      </div>
      <button id="custom-provider-save" class="custom-provider-save remote-target" type="button">${t("settings.customSave")}</button>
    </div>
  `;
  populateAiModelsSection(data, language);
}

function renderSettings(data) {
  syncMailboxSettingsFromDom();
  initializeMailboxSettingsState(data);
  renderSettingsDirectory(data);
  renderSettingsDetail(data);
  requestAnimationFrame(() => syncAllManagedScrollContainers());
}

function readMailTesterForm() {
  mailTesterState.to = document.getElementById("mail-test-to")?.value?.trim() || "";
  mailTesterState.subject = document.getElementById("mail-test-subject")?.value?.trim() || "";
  mailTesterState.body = document.getElementById("mail-test-body")?.value?.trim() || "";
}

async function syncMailTester() {
  mailTesterState.isSyncing = true;
  mailTesterState.status = t("mail.statusIdle");
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/external-channels/email/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 10 })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Mail sync failed.");
    }
    mailTesterState.status = t("mail.syncSuccess", { count: payload.imported || 0 });
    updateSpokenLine(mailTesterState.status);
    await loadDashboard();
  } catch (error) {
    mailTesterState.status = t("mail.failed", { error: String(error.message || error) });
    updateSpokenLine(mailTesterState.status);
    renderSettings(latestDashboard);
  } finally {
    mailTesterState.isSyncing = false;
    renderSettings(latestDashboard);
  }
}

async function sendMailTester() {
  readMailTesterForm();
  if (!mailTesterState.to || !mailTesterState.body) {
    mailTesterState.status = t("mail.failed", { error: "Recipient and message body are required." });
    updateSpokenLine(mailTesterState.status);
    renderSettings(latestDashboard);
    return;
  }
  mailTesterState.isSending = true;
  renderSettings(latestDashboard);
  try {
    const response = await fetch("/api/external-channels/email/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to: mailTesterState.to,
        subject: mailTesterState.subject,
        content: mailTesterState.body
      })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Mail send failed.");
    }
    mailTesterState.status = t("mail.sendSuccess");
    updateSpokenLine(mailTesterState.status);
    await loadDashboard();
  } catch (error) {
    mailTesterState.status = t("mail.failed", { error: String(error.message || error) });
    updateSpokenLine(mailTesterState.status);
    renderSettings(latestDashboard);
  } finally {
    mailTesterState.isSending = false;
    renderSettings(latestDashboard);
  }
}

function updateSpokenLine(text) {
  setTextIfPresent("spoken-line", text);
  renderFloatingBuddy();
}

function updateConversation(conversation) {
  if (!latestDashboard) return;
  latestDashboard.conversation = conversation;
  testConversation = Array.isArray(conversation) ? [...conversation] : [];
  renderVoice(latestDashboard);
  renderTestLab();
  renderWorkTab();
}

function focusUiNode(node, selector = "") {
  let target = node;
  if (!(target instanceof HTMLElement)) return false;
  if (selector) {
    const nested = target.matches(selector) ? target : target.querySelector(selector);
    if (nested instanceof HTMLElement) target = nested;
  }
  if (!target.classList.contains("remote-target") && !["INPUT", "TEXTAREA", "BUTTON"].includes(target.tagName)) {
    const fallback = target.querySelector(".remote-target, button, textarea, input, [tabindex]");
    if (fallback instanceof HTMLElement) target = fallback;
  }
  target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  if (typeof target.focus === "function") {
    target.focus();
  }
  return true;
}

function executeUiAction(action) {
  if (!action || typeof action !== "object") return false;
  if (action.type === "switch_tab" && action.tab) {
    if (action.tab === "pairing") {
      activeSettingsSection = "pairing";
    }
    activateTab(action.tab);
    return true;
  }
  if (action.type === "focus_element") {
    if (action.tab === "pairing") {
      activeSettingsSection = "pairing";
    }
    if (action.tab) {
      activateTab(action.tab, false);
    }
    requestAnimationFrame(() => {
      const target = (action.selector && document.querySelector(action.selector))
        || (action.targetId && document.getElementById(action.targetId));
      if (target instanceof HTMLElement) {
        focusUiNode(target);
      }
    });
    return true;
  }
  if (action.type === "select_agent") {
    if (action.tab) {
      activateTab(action.tab, false);
    }
    if (action.agentId) {
      selectStudioAgent(action.agentId);
    }
    requestAnimationFrame(() => {
      const target = (action.selector && document.querySelector(action.selector))
        || (action.agentId && document.querySelector(`[data-agent-id="${action.agentId}"]`))
        || document.getElementById("test-generate-feature");
      if (target instanceof HTMLElement) {
        focusUiNode(target);
      }
    });
    return true;
  }
  return false;
}

async function refreshCustomAgentStudio() {
  customAgentStudio.isLoading = true;
  try {
    const response = await fetch("/api/custom-agents");
    const payload = await response.json();
    if (!response.ok) {
      customAgentStudio.items = [];
      customAgentStudio.recentActions = [{ createdAt: "", summary: payload.error || "Failed to load custom agents." }];
      customAgentStudio.selectedAgentId = "";
      return;
    }
    customAgentStudio.items = Array.isArray(payload.items) ? payload.items : [];
    customAgentStudio.recentActions = Array.isArray(payload.recentActions) ? payload.recentActions : [];
    const selectedStillExists = customAgentStudio.items.some((item) => item.id === customAgentStudio.selectedAgentId);
    if (!selectedStillExists) {
      const preferred = customAgentStudio.items.find((item) => item.status === "complete") || customAgentStudio.items[0];
      customAgentStudio.selectedAgentId = preferred?.id || "";
    }
  } catch (error) {
    customAgentStudio.items = [];
    customAgentStudio.recentActions = [{ createdAt: "", summary: String(error.message || error) }];
    customAgentStudio.selectedAgentId = "";
  } finally {
    customAgentStudio.isLoading = false;
    renderWorkTab();
  }
}

async function sendTestMessage() {
  const input = document.getElementById("test-input");
  const message = input?.value?.trim() || "";
  if (!message && !testUploadAttachment) return;
  if (input) input.value = "";
  if (message && !testUploadAttachment) {
    testConversation.push({
      speaker: "You",
      text: message,
      time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" })
    });
  }
  customAgentStudio.isThinking = true;
  renderTestLab();
  renderWorkTab();
  try {
    if (testUploadAttachment) {
      await sendTestAttachmentMessage(message);
      testUploadAttachment = null;
    } else {
      await sendVoiceMessage(message, { speakReply: false });
    }
  } finally {
    customAgentStudio.isThinking = false;
    renderTestLab();
    renderWorkTab();
  }
}

async function sendTestAgentMessage(message, selected = null) {
  const agent = selected || getSelectedStudioAgent();
  if (!agent || agent.status !== "complete") {
    updateSpokenLine("HomeHub: Select a completed blueprint before sending a test message.");
    return;
  }
  const response = await fetch("/api/custom-agents/intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: agent.id,
      locale: currentLocale,
      message
    })
  });
  const payload = await response.json();
  if (!response.ok) {
    const errorText = payload.error || "Failed to process the test message.";
    testConversation.push({
      speaker: "HomeHub",
      text: errorText,
      time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" })
    });
    renderTestLab();
    updateSpokenLine(`HomeHub: ${errorText}`);
    return;
  }
  const replyText = payload.reply || "Message received.";
  testConversation.push({
    speaker: "HomeHub",
    text: replyText,
    time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" }),
    artifacts: Array.isArray(payload.artifacts) ? payload.artifacts : []
  });
  renderTestLab();
  updateSpokenLine(`HomeHub: ${replyText}`);
  await refreshCustomAgentStudio();
  refreshDashboardInBackground();
}

async function sendTestAttachmentMessage(message) {
  const selected = getSelectedStudioAgent();
  if (!selected || selected.status !== "complete") {
    const replyText = currentLocale === "zh-CN"
      ? "HomeHub：当前还没有可接收附件的已完成智能体，请先到“智能体”标签中完成一个蓝图。"
      : currentLocale === "ja-JP"
        ? "HomeHub: 添付を受け取れる完成済みエージェントがまだありません。先に「エージェント」タブでブループリントを完成させてください。"
        : "HomeHub: There is no completed smart unit ready for attachments yet. Finish one in the Agents tab first.";
    testConversation.push({
      speaker: "HomeHub",
      text: replyText,
      time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" })
    });
    renderTestLab();
    updateSpokenLine(replyText);
    return;
  }
  const fallbackMessage = testUploadMode === "summary"
    ? (currentLocale === "zh-CN"
      ? `请对这份文档进行总结，然后发给我：${testUploadAttachment?.name || ""}`
      : currentLocale === "ja-JP"
        ? `${testUploadAttachment?.name || ""} を要約して送ってください`
        : `Summarize this document and send it to me: ${testUploadAttachment?.name || ""}`)
    : testUploadMode === "translation"
      ? (currentLocale === "zh-CN"
        ? `请对这份文档进行翻译，然后发给我：${testUploadAttachment?.name || ""}`
        : currentLocale === "ja-JP"
          ? `${testUploadAttachment?.name || ""} を翻訳して送ってください`
          : `Translate this document and send it to me: ${testUploadAttachment?.name || ""}`)
      : (message || `[Image uploaded] ${testUploadAttachment?.name || ""}`.trim());
  const effectiveMessage = message || fallbackMessage;
  const userText = effectiveMessage;
  testConversation.push({
    speaker: "You",
    text: userText,
    time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" })
  });
  renderTestLab();
  let response;
  if (testUploadAttachment?.file instanceof File) {
    const formData = new FormData();
    formData.append("id", selected.id);
    formData.append("locale", currentLocale);
    formData.append("message", effectiveMessage || "");
    formData.append("attachment_kind", testUploadAttachment.kind || "file");
    formData.append(
      "attachment",
      testUploadAttachment.file,
      testUploadAttachment.name || testUploadAttachment.file.name || "attachment.bin"
    );
    response = await fetch("/api/custom-agents/intake", {
      method: "POST",
      body: formData
    });
  } else {
    response = await fetch("/api/custom-agents/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: selected.id,
        locale: currentLocale,
        message: effectiveMessage,
        attachments: [testUploadAttachment]
      })
    });
  }
  const payload = await response.json();
  if (!response.ok) {
    updateSpokenLine(`HomeHub: ${payload.error || "Failed to process the uploaded image."}`);
    return;
  }
  testConversation.push({
    speaker: "HomeHub",
    text: payload.reply || "Image received.",
    time: new Date().toLocaleTimeString(currentLocale, { hour: "2-digit", minute: "2-digit" }),
    artifacts: Array.isArray(payload.artifacts) ? payload.artifacts : []
  });
  testUploadMode = "generic";
  renderTestLab();
  updateSpokenLine(`HomeHub: ${payload.reply || "Image received."}`);
  await refreshCustomAgentStudio();
  refreshDashboardInBackground();
}

async function generateSelectedFeature() {
  const selected = getSelectedStudioAgent();
  if (!selected || selected.status !== "complete") {
    updateSpokenLine(t("test.noBlueprintSelected"));
    return;
  }
  if (selected.generatedFeaturePath) {
    updateSpokenLine(t("test.featureAlreadyGenerated"));
    return;
  }
  customAgentStudio.isGenerating = true;
  renderTestLab();
  try {
    const response = await fetch("/api/custom-agents/generate-feature", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected.id })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unknown error");
    }
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.generated", { name: selected.name || "Blueprint" }));
  } catch (error) {
    updateSpokenLine(t("test.generateFailed", { error: String(error.message || error) }));
  } finally {
    customAgentStudio.isGenerating = false;
    renderTestLab();
    renderWorkTab();
  }
}

async function deleteSelectedDraft() {
  const selected = getSelectedStudioAgentForTab("creating");
  if (!selected) {
    updateSpokenLine(t("test.detailEmpty"));
    return;
  }
  customAgentStudio.isGenerating = true;
  renderTestLab();
  try {
    const response = await fetch("/api/custom-agents/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected.id })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unknown error");
    }
    customAgentStudio.selectedAgentId = "";
    resetStudioFeatureRuntime("");
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.deleteDraftDone"));
  } catch (error) {
    updateSpokenLine(t("test.deleteDraftFailed", { error: String(error.message || error) }));
  } finally {
    customAgentStudio.isGenerating = false;
    renderTestLab();
    renderWorkTab();
  }
}

async function deleteSelectedBlueprint() {
  const selected = getSelectedStudioAgentForTab("created");
  if (!selected) {
    updateSpokenLine(t("test.detailEmpty"));
    return;
  }
  customAgentStudio.isGenerating = true;
  renderTestLab();
  try {
    const response = await fetch("/api/custom-agents/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected.id })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unknown error");
    }
    customAgentStudio.selectedAgentId = "";
    resetStudioFeatureRuntime("");
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.deleteBlueprintDone"));
  } catch (error) {
    updateSpokenLine(t("test.deleteBlueprintFailed", { error: String(error.message || error) }));
  } finally {
    customAgentStudio.isGenerating = false;
    renderTestLab();
    renderWorkTab();
  }
}

async function deleteSelectedFeature() {
  const selected = getSelectedStudioAgentForTab("created");
  if (!selected) {
    updateSpokenLine(t("test.detailEmpty"));
    return;
  }
  customAgentStudio.isGenerating = true;
  renderTestLab();
  try {
    const response = await fetch("/api/custom-agents/delete-feature", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selected.id })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unknown error");
    }
    resetStudioFeatureRuntime("");
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.deleteFeatureDone"));
  } catch (error) {
    updateSpokenLine(t("test.deleteFeatureFailed", { error: String(error.message || error) }));
  } finally {
    customAgentStudio.isGenerating = false;
    renderTestLab();
    renderWorkTab();
  }
}

async function createStudioFeatureRecord() {
  const selected = getSelectedStudioAgentForTab("created");
  const apiRoot = getStudioFeatureApiRoot(selected);
  if (!selected || !apiRoot) {
    updateSpokenLine(t("test.featurePanelEmpty"));
    return;
  }
  const draftNode = document.getElementById("studio-feature-draft");
  const message = draftNode?.value?.trim() || studioFeatureRuntime.draftText.trim();
  if (!message) {
    updateSpokenLine(t("test.featureDraftPlaceholder"));
    return;
  }
  studioFeatureRuntime.isSaving = true;
  studioFeatureRuntime.draftText = message;
  renderTestLab();
  try {
    const response = await fetch(`${apiRoot}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Create record failed.");
    }
    studioFeatureRuntime.draftText = "";
    await loadStudioFeatureRuntime(selected, true);
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.featureCreateDone"));
  } catch (error) {
    updateSpokenLine(t("test.featureCreateFailed", { error: String(error.message || error) }));
  } finally {
    studioFeatureRuntime.isSaving = false;
    renderTestLab();
  }
}

async function refreshStudioFeatureRuntime() {
  const selected = getSelectedStudioAgentForTab("created");
  const apiRoot = getStudioFeatureApiRoot(selected);
  if (!selected || !apiRoot) {
    updateSpokenLine(t("test.featurePanelEmpty"));
    return;
  }
  await loadStudioFeatureRuntime(selected, true);
  await refreshCustomAgentStudio();
  renderTestLab();
}

async function deleteStudioFeatureRecord(recordId) {
  const selected = getSelectedStudioAgentForTab("created");
  const apiRoot = getStudioFeatureApiRoot(selected);
  if (!selected || !apiRoot || !recordId) return;
  studioFeatureRuntime.isSaving = true;
  renderTestLab();
  try {
    const response = await fetch(`${apiRoot}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: recordId })
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Delete record failed.");
    }
    await loadStudioFeatureRuntime(selected, true);
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.featureDeleteDone"));
  } catch (error) {
    updateSpokenLine(t("test.featureDeleteFailed", { error: String(error.message || error) }));
  } finally {
    studioFeatureRuntime.isSaving = false;
    renderTestLab();
  }
}

async function exportStudioFeatureRecords() {
  const selected = getSelectedStudioAgentForTab("created");
  const apiRoot = getStudioFeatureApiRoot(selected);
  if (!selected || !apiRoot) {
    updateSpokenLine(t("test.featurePanelEmpty"));
    return;
  }
  studioFeatureRuntime.isSaving = true;
  renderTestLab();
  try {
    const response = await fetch(`${apiRoot}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Export failed.");
    }
    studioFeatureRuntime.exportArtifact = payload.artifact || null;
    await loadStudioFeatureRuntime(selected, true);
    await refreshCustomAgentStudio();
    renderTestLab();
    updateSpokenLine(t("test.featureExportDone"));
  } catch (error) {
    updateSpokenLine(t("test.featureExportFailed", { error: String(error.message || error) }));
  } finally {
    studioFeatureRuntime.isSaving = false;
    renderTestLab();
  }
}

function revealInScrollableParent(target) {
  const scrollParent = target.closest("#modules, #timeline, #agents, #models, #skills, #relay, #conversation, #voice, #test-conversation, #work-request-list, #work-pipeline-scroll, #studio-blueprints, #studio-actions-log, #settings-directory-list, #settings-detail-scroll");
  if (!scrollParent) return;
  target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
}

function getVisibleRemoteTargets() {
  return Array.from(document.querySelectorAll(".remote-target")).filter((element) => {
    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    if (element.closest("[hidden]")) return false;
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  });
}

function getCenter(rect) {
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function pickDirectionalTarget(current, direction) {
  const candidates = getVisibleRemoteTargets();
  if (!current || !candidates.length) return candidates[0] || null;
  const currentRect = current.getBoundingClientRect();
  const currentCenter = getCenter(currentRect);
  let best = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const candidate of candidates) {
    if (candidate === current) continue;
    const rect = candidate.getBoundingClientRect();
    const center = getCenter(rect);
    const dx = center.x - currentCenter.x;
    const dy = center.y - currentCenter.y;
    if (direction === "right" && dx <= 12) continue;
    if (direction === "left" && dx >= -12) continue;
    if (direction === "down" && dy <= 12) continue;
    if (direction === "up" && dy >= -12) continue;
    const primary = direction === "left" || direction === "right" ? Math.abs(dx) : Math.abs(dy);
    const secondary = direction === "left" || direction === "right" ? Math.abs(dy) : Math.abs(dx);
    const score = primary * 1000 + secondary;
    if (score < bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best;
}
async function triggerRemoteAction(target) {
  if (!target) return;
  if (target.dataset.tab) {
    activateTab(target.dataset.tab);
    updateSpokenLine(t("prompts.switchedTab", { tab: target.textContent }));
    return;
  }
  if (target.id === "reminder-complete") {
    await completeActiveReminder();
    return;
  }
  if (target.id === "mic-orb") {
    await toggleMicrophoneRecording();
    return;
  }
  if (target.id === "test-send") {
    await sendTestMessage();
    return;
  }
  if (target.id === "test-image-pick") {
    testUploadMode = "generic";
    const imageInput = document.getElementById("test-image-input");
    if (imageInput) {
      imageInput.value = "";
      imageInput.click();
    }
    return;
  }
  if (target.id === "test-file-pick") {
    testUploadMode = "generic";
    const fileInput = document.getElementById("test-file-input");
    if (fileInput) {
      fileInput.value = "";
      fileInput.click();
    }
    return;
  }
  if (target.id === "test-doc-summary-pick") {
    testUploadMode = "summary";
    const fileInput = document.getElementById("test-file-input");
    if (fileInput) {
      fileInput.value = "";
      fileInput.click();
    }
    return;
  }
  if (target.id === "test-doc-translate-pick") {
    testUploadMode = "translation";
    const fileInput = document.getElementById("test-file-input");
    if (fileInput) {
      fileInput.value = "";
      fileInput.click();
    }
    return;
  }
  if (target.id === "test-generate-feature") {
    await generateSelectedFeature();
    return;
  }
  if (target.id === "test-delete-draft") {
    await deleteSelectedDraft();
    return;
  }
  if (target.id === "test-delete-blueprint") {
    await deleteSelectedBlueprint();
    return;
  }
  if (target.id === "test-delete-feature") {
    await deleteSelectedFeature();
    return;
  }
  if (target.dataset.scrollJumpTarget) {
    const scrollTarget = document.getElementById(target.dataset.scrollJumpTarget);
    if (scrollTarget instanceof HTMLElement) {
      scrollTarget.scrollTo({ top: scrollTarget.scrollHeight, behavior: "smooth" });
      requestAnimationFrame(() => syncManagedScrollContainer(scrollTarget));
    }
    return;
  }
  if (target.id === "studio-feature-create") {
    await createStudioFeatureRecord();
    return;
  }
  if (target.id === "studio-feature-refresh") {
    await refreshStudioFeatureRuntime();
    return;
  }
  if (target.id === "studio-feature-export") {
    await exportStudioFeatureRecords();
    return;
  }
  if (target.dataset.featureRecordId) {
    await deleteStudioFeatureRecord(target.dataset.featureRecordId);
    return;
  }
  if (target.dataset.runtimeAgentId) {
    activeRuntimeAgentId = target.dataset.runtimeAgentId;
    renderAgents(latestDashboard?.activeAgents || []);
    return;
  }
  if (target.dataset.studioTab) {
    activeBlueprintStudioTab = target.dataset.studioTab;
    renderTestLab();
    return;
  }
  if (target.dataset.languageCode) {
    await persistLanguage(target.dataset.languageCode);
    return;
  }
  if (target.dataset.agentId) {
    selectStudioAgent(target.dataset.agentId);
    updateSpokenLine(t("prompts.selected", { title: target.dataset.title || target.textContent || "blueprint" }));
    return;
  }
  if (target.dataset.providerType && target.dataset.providerId) {
    await persistAudioProvider(target.dataset.providerType, target.dataset.providerId);
    return;
  }
  if (target.classList.contains("fake-qr")) {
    updateSpokenLine(t("prompts.qrHighlighted"));
    return;
  }
  const title = target.dataset.title || target.querySelector("strong")?.textContent || "item";
  const actionText = target.dataset.actionText;
  if (actionText) {
    updateSpokenLine(t("prompts.actionReady", { title, action: actionText }));
    return;
  }
  updateSpokenLine(t("prompts.selected", { title }));
}

function activateTab(tabName, focusTab = true) {
  const normalized = normalizeTabName(tabName);
  if (tabName === "pairing") activeSettingsSection = "pairing";
  activeTab = normalized;
  tabs.forEach((name) => {
    const tab = document.getElementById(`tab-${name}`);
    const panel = document.getElementById(`panel-${name}`);
    if (!tab || !panel) return;
    const selected = name === normalized;
    tab.classList.toggle("is-selected", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focusTab) tab.focus();
    panel.hidden = !selected;
    panel.classList.toggle("is-visible", selected);
  });
  renderFloatingBuddy();
  if (normalized === "cortex" && !latestCortexUnpacked) {
    loadCortexUnpacked().catch((error) => console.warn("Failed to load cortex unpacked view.", error));
  }
}

function goToPreviousTab() {
  const currentIndex = tabs.indexOf(activeTab);
  if (currentIndex > 0) {
    activateTab(tabs[currentIndex - 1]);
    const previousTabLabel = document.getElementById(`tab-${tabs[currentIndex - 1]}`)?.textContent || tabs[currentIndex - 1];
    updateSpokenLine(t("prompts.returnedTab", { tab: previousTabLabel }));
  } else {
    activateTab("home");
    updateSpokenLine(t("prompts.returnedTab", { tab: document.getElementById("tab-home")?.textContent || "home" }));
  }
}

function setupTabs() {
  const tabbar = document.getElementById("tabbar");
  if (!tabbar) return;
  tabbar.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) return;
    activateTab(button.dataset.tab);
  });
}

function setupRemoteNavigation() {
  syncAllManagedScrollContainers();
  window.addEventListener("resize", () => syncAllManagedScrollContainers());
  window.addEventListener("scroll", () => syncAllManagedScrollContainers(), { passive: true });
  document.addEventListener("focusin", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.classList.contains("remote-target")) revealInScrollableParent(target);
  });

  document.addEventListener("click", async (event) => {
    const target = event.target.closest(".remote-target");
    if (!target) return;
    await triggerRemoteAction(target);
  });
  document.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLTextAreaElement)) return;
    if (target.id === "studio-feature-draft") {
      studioFeatureRuntime.draftText = target.value || "";
    }
  });

  document.addEventListener("keydown", async (event) => {
    const activeElement = document.activeElement;
    const editingText =
      activeElement instanceof HTMLElement
      && (
        activeElement.tagName === "TEXTAREA"
        || (activeElement.tagName === "INPUT" && !["button", "checkbox", "radio", "range", "submit"].includes(String(activeElement.getAttribute("type") || "").toLowerCase()))
        || activeElement.isContentEditable
      );
    if (editingText) {
      if (event.key === "Enter" && activeElement.id === "test-input" && !event.shiftKey) {
        event.preventDefault();
        await sendTestMessage();
      }
      if (event.key === "Enter" && activeElement.id === "cortex-request-input" && !event.shiftKey) {
        event.preventDefault();
        readCortexTesterInputs();
        await loadCortexUnpacked();
      }
      return;
    }
    const keyToDirection = { ArrowRight: "right", ArrowLeft: "left", ArrowUp: "up", ArrowDown: "down" };
    if (keyToDirection[event.key]) {
      const next = pickDirectionalTarget(activeElement, keyToDirection[event.key]);
      if (next) {
        next.focus();
        revealInScrollableParent(next);
        event.preventDefault();
      }
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      if (activeElement && activeElement.classList.contains("remote-target")) {
        await triggerRemoteAction(activeElement);
        event.preventDefault();
      }
      return;
    }
    if (event.key === "Escape" || event.key === "Backspace") {
      goToPreviousTab();
      event.preventDefault();
    }
  });
}

function setupTestControls() {
  const applyAttachment = (file, kind) => {
    testUploadAttachment = {
      name: file.name,
      mimeType: file.type || (kind === "image" ? "image/png" : "application/octet-stream"),
      sizeBytes: file.size || 0,
      kind,
      file
    };
    if (kind === "image") testUploadMode = "generic";
    updateSpokenLine(`HomeHub: Attached ${kind === "file" ? "file" : "image"} ${file.name}.`);
    renderTestLab();
  };
  const imageInput = document.getElementById("test-image-input");
  if (imageInput) {
    imageInput.addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (!file) {
        testUploadAttachment = null;
        renderTestLab();
        return;
      }
      applyAttachment(file, "image");
      imageInput.value = "";
    });
  }
  const fileInput = document.getElementById("test-file-input");
  if (fileInput) {
    fileInput.addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (!file) {
        testUploadAttachment = null;
        renderTestLab();
        return;
      }
      applyAttachment(file, file.type.startsWith("image/") ? "image" : "file");
      fileInput.value = "";
    });
  }
}

function bootstrapCopy(snapshot) {
  const approved = Boolean(snapshot?.approved);
  const inProgress = Boolean(snapshot?.inProgress);
  const blocking = Boolean(snapshot?.blocking);
  const completed = Boolean(snapshot?.completed);
  const stale = Boolean(snapshot?.stale);
  const installingPackage = snapshot?.installingPythonPackage || "";
  const failedPackages = Array.isArray(snapshot?.failedPythonModules) ? snapshot.failedPythonModules : [];
  const missingPackages = Array.isArray(snapshot?.missingPythonModules) ? snapshot.missingPythonModules : [];
  const restartRequired = Boolean(snapshot?.restartRequired);
  if (currentLocale === "zh-CN") {
    if (!approved) {
      return {
        title: "首次安装准备",
        text: "HomeHub 第一次运行时需要一次性确认安装权限。确认后，后续启动将自动检查，不会重复要求你再次承认。",
        button: "确认并开始安装"
      };
    }
    if (stale) {
      return {
        title: "安装已中断",
        text: "HomeHub 的首次安装看起来已经卡住。现在可以先进入系统，剩余依赖稍后再手动补齐。",
        button: ""
      };
    }
    if (inProgress) {
      return {
        title: blocking ? "正在安装中" : "正在后台准备模型",
        text: blocking
          ? "HomeHub 正在补齐本机需要的开发环境、文档能力和本地模型，请先稍等。"
          : "HomeHub 已经可以使用，剩余本地模型正在后台继续下载。",
        button: ""
      };
    }
    if (completed) {
      return {
        title: "安装完成",
        text: "HomeHub 首次运行准备已经完成。",
        button: ""
      };
    }
    return {
      title: "准备继续安装",
      text: "HomeHub 已记录过你的授权，本次会自动继续补齐剩余项目。",
      button: ""
    };
  }
  return {
    title: !approved ? "First-Run Setup" : stale ? "Setup Interrupted" : inProgress ? "Installing HomeHub" : completed ? "Setup Complete" : "Preparing HomeHub",
    text: !approved
      ? "Approve one-time setup once, and HomeHub will reuse that decision on future launches."
      : stale
        ? "HomeHub setup appears stalled. You can continue using the app and install the remaining dependencies manually later."
      : inProgress
        ? "HomeHub is installing local tools, document support, and models."
        : completed
          ? "HomeHub first-run setup is complete."
          : "HomeHub is preparing the remaining local dependencies.",
    button: !approved ? "Approve One-Time Setup" : ""
  };
}

function renderBootstrapOverlay(snapshot) {
  const overlay = document.getElementById("installer-overlay");
  const title = document.getElementById("installer-title");
  const text = document.getElementById("installer-text");
  const status = document.getElementById("installer-status");
  const button = document.getElementById("installer-approve");
  if (!overlay || !title || !text || !status || !button) return;
  const approved = Boolean(snapshot?.approved);
  const inProgress = Boolean(snapshot?.inProgress);
  const blocking = Boolean(snapshot?.blocking);
  const completed = Boolean(snapshot?.completed);
  const shouldShow = !completed && (!approved || blocking);
  overlay.hidden = !shouldShow;
  if (!shouldShow) {
    if (bootstrapPollTimer) {
      clearInterval(bootstrapPollTimer);
      bootstrapPollTimer = null;
    }
    return;
  }
  const copy = bootstrapCopy(snapshot || {});
  title.textContent = copy.title;
  text.textContent = copy.text;
  const packageBits = [];
  if (snapshot?.installingPythonPackage) packageBits.push(`?????${snapshot.installingPythonPackage}`);
  if (Array.isArray(snapshot?.failedPythonModules) && snapshot.failedPythonModules.length) packageBits.push(`????${snapshot.failedPythonModules.join("?")}`);
  if (Array.isArray(snapshot?.missingPythonModules) && snapshot.missingPythonModules.length) packageBits.push(`????${snapshot.missingPythonModules.join("?")}`);
  if (snapshot?.restartRequired) packageBits.push("????????? HomeHub");
  status.textContent = [snapshot?.message || "", ...packageBits].filter(Boolean).join(" | ");
  button.textContent = copy.button;
  button.hidden = approved;
  if ((inProgress || approved) && !bootstrapPollTimer) {
    bootstrapPollTimer = setInterval(async () => {
      const response = await fetch("/api/bootstrap/status");
      const payload = await response.json();
      if (latestDashboard) {
        latestDashboard.bootstrap = payload;
      }
      renderBootstrapOverlay(payload);
      if (payload?.inProgress && !payload?.blocking) {
        updateSpokenLine(currentLocale === "zh-CN" ? "HomeHub：本地模型仍在后台下载中。" : "HomeHub: Local models are still downloading in the background.");
      }
      if (payload?.completed) {
        await loadDashboard();
      }
    }, 3000);
  }
}

async function approveBootstrapSetup() {
  const response = await fetch("/api/bootstrap/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve: true })
  });
  const payload = await response.json();
  if (!response.ok) {
    return;
  }
  if (latestDashboard) {
    latestDashboard.bootstrap = payload.bootstrap;
  }
  renderBootstrapOverlay(payload.bootstrap);
}

async function loadDashboard() {
  const response = await fetch("/api/dashboard");
  const data = await response.json();
  latestDashboard = data;
  currentLocale = data.languageSettings?.current || currentLocale;
  await loadSettingsI18n(currentLocale);
  if (!testConversation.length && Array.isArray(data.conversation)) {
    testConversation = data.conversation;
  }
  await refreshCustomAgentStudio();
  ensureCortexTesterState();
  applyStaticTranslations();
  renderClock();
  renderStatusStrip(data);
  renderHero(data);
  renderHomeOverview(data);
  renderTimeline(data.timelineEvents);
  renderModules(data.householdModules);
  renderAgents(data.activeAgents);
  renderModels(data.modelProviders);
  renderSkills(data.skillCatalog);
  renderPairing(data.pairingSession, data.relayMessages);
  renderVoice(data);
  renderTestLab();
  renderWorkTab();
  renderReminderOverlay(data);
  renderSettings(data);
  renderCortexUnpacked(latestCortexUnpacked);
  renderFloatingBuddy();
  renderBootstrapOverlay(data.bootstrap || {});
  void syncDeviceWeatherFromBrowser();
  if (!latestCortexUnpacked) {
    await loadCortexUnpacked();
  }
}

function refreshDashboardInBackground() {
  if (dashboardRefreshPromise) {
    return dashboardRefreshPromise;
  }
  dashboardRefreshPromise = loadDashboard().catch((error) => {
    console.warn("Background dashboard refresh failed.", error);
  }).finally(() => {
    dashboardRefreshPromise = null;
  });
  return dashboardRefreshPromise;
}

async function persistLanguage(languageCode) {
  try {
    const response = await fetch("/api/settings/language", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: languageCode })
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      console.warn("save language failed", response.status, payload);
      updateSpokenLine(`${t("prompts.saveLanguageFailed")} (${response.status})`);
      return;
    }
    currentLocale = String(payload?.language || languageCode || currentLocale);
    await loadDashboard();
    const language = getCurrentLanguage(latestDashboard);
    updateSpokenLine(t("prompts.languageSwitched", { language: language?.label || currentLocale }));
  } catch (error) {
    console.warn("save language request error", error);
    // Local fallback: keep the UI usable even if backend persistence fails.
    currentLocale = languageCode || currentLocale;
    applyStaticTranslations();
    if (latestDashboard) {
      renderSettings(latestDashboard);
      renderStatusStrip(latestDashboard);
      renderVoice(latestDashboard);
      renderWorkTab();
    }
    updateSpokenLine(`${t("prompts.saveLanguageFailed")} (${String(error?.message || error)})`);
  }
}

async function persistAudioProvider(providerType, providerId) {
  const catalog = latestDashboard?.audioProviders?.catalog || {};
  const provider = catalog[providerId];
  const runtime = providerType === "stt" ? provider?.stt?.runtime : provider?.tts?.runtime;
  if (runtime === "catalog") {
    updateSpokenLine(`HomeHub: ${provider?.label || providerId} is catalog-only right now.`);
    return;
  }
  const selected = getSelectedProviders();
  const body = {
    sttProvider: providerType === "stt" ? providerId : selected.stt,
    ttsProvider: providerType === "tts" ? providerId : selected.tts
  };
  const response = await fetch("/api/settings/audio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    updateSpokenLine(t("prompts.saveAudioFailed"));
    return;
  }
  await loadDashboard();
  updateSpokenLine(t("prompts.audioUpdated", { stt: body.sttProvider, tts: body.ttsProvider }));
}

async function persistAssistantAvatar(mode, customModelUrl = "") {
  avatarSettingsState.isSaving = true;
  if (latestDashboard) renderSettings(latestDashboard);
  const response = await fetch("/api/settings/avatar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, customModelUrl })
  });
  const payload = await response.json();
  if (!response.ok) {
    avatarSettingsState.isSaving = false;
    if (latestDashboard) renderSettings(latestDashboard);
    updateSpokenLine(payload.error || (currentLocale === "zh-CN"
      ? "HomeHub：形象设置保存失败。"
      : currentLocale === "ja-JP"
        ? "HomeHub: アバター設定の保存に失敗しました。"
        : "HomeHub: Failed to save the avatar setting."));
    return;
  }
  avatarSettingsState.customModelUrl = payload.customModelUrl || customModelUrl;
  avatarSettingsState.isSaving = false;
  await loadDashboard();
  updateSpokenLine(mode === "custom"
    ? (currentLocale === "zh-CN"
      ? "HomeHub：已切换到你的 GLB 机器人。"
      : currentLocale === "ja-JP"
        ? "HomeHub: カスタム GLB ロボットに切り替えました。"
        : "HomeHub: Switched to your custom GLB robot.")
    : (currentLocale === "zh-CN"
      ? "HomeHub：已切回房子小机器人备份形象。"
      : currentLocale === "ja-JP"
        ? "HomeHub: 家型マスコットのバックアップ表示に戻しました。"
        : "HomeHub: Returned to the backup house mascot."));
}

async function saveCustomProvider() {
  const idInput = document.getElementById("custom-provider-id");
  const labelInput = document.getElementById("custom-provider-label");
  const sourceInput = document.getElementById("custom-source");
  const capabilitiesInput = document.getElementById("custom-capabilities");
  const modelsInput = document.getElementById("custom-models");
  const summaryInput = document.getElementById("custom-summary");
  const syncOpenclawInput = document.getElementById("custom-sync-openclaw");
  const syncWorkbuddyInput = document.getElementById("custom-sync-workbuddy");
  const languagesInput = document.getElementById("custom-languages");
  if (!idInput || !labelInput || !sourceInput || !capabilitiesInput || !modelsInput || !summaryInput || !syncOpenclawInput || !syncWorkbuddyInput || !languagesInput) {
    updateSpokenLine(currentLocale === "zh-CN" ? "HomeHub：AI 模型目录尚未打开。" : currentLocale === "ja-JP" ? "HomeHub: AI モデル画面がまだ開かれていません。" : "HomeHub: The AI models section is not open yet.");
    return;
  }
  const body = {
    entryType: "capability",
    id: idInput.value.trim(),
    label: labelInput.value.trim(),
    source: sourceInput.value.trim(),
    capabilities: capabilitiesInput.value.trim(),
    models: modelsInput.value.trim(),
    summary: summaryInput.value.trim(),
    syncOpenclaw: syncOpenclawInput.value,
    syncWorkbuddy: syncWorkbuddyInput.value,
    supportedLanguages: languagesInput.value.trim()
  };
  const response = await fetch("/api/settings/audio-provider", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) {
    updateSpokenLine(payload.error || t("prompts.saveCustomProviderFailed"));
    return;
  }
  idInput.value = "";
  labelInput.value = "";
  sourceInput.value = "";
  capabilitiesInput.value = "";
  modelsInput.value = "";
  summaryInput.value = "";
  languagesInput.value = "zh-CN,en-US,ja-JP";
  await loadDashboard();
  updateSpokenLine(t("prompts.customProviderSaved", { label: body.label || body.id }));
}
async function sendVoiceMessage(message, options = {}) {
  const { speakReply = true, localeOverride = "" } = options;
  const clean = String(message || "").trim();
  if (!clean) return;
  updateSpokenLine(`${t("speakers.you")}: ${clean}`);
  isBuddyThinking = true;
  renderFloatingBuddy();
  updateSpokenLine(t("voice.thinking"));
  const response = await fetch("/api/voice/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: clean, locale: localeOverride || currentLocale, speakReply: false })
  });
  const payload = await response.json();
  isBuddyThinking = false;
  if (!response.ok) {
    updateSpokenLine(`HomeHub: ${payload.error || t("voice.sendFailure")}`);
    return payload;
  }
  if (payload.uiAction) {
    executeUiAction(payload.uiAction);
  }
  updateConversation(payload.conversation || []);
  if (payload.voiceRoute && latestDashboard) {
    latestDashboard.lastVoiceRoute = payload.voiceRoute;
    latestDashboard.pendingVoiceClarification = payload.pendingVoiceClarification || null;
    renderVoice(latestDashboard);
  }
  if (payload.assistantMemory && latestDashboard) {
    latestDashboard.assistantMemory = payload.assistantMemory;
    renderStatusStrip(latestDashboard);
    renderVoice(latestDashboard);
    renderReminderOverlay(latestDashboard);
  }
  updateSpokenLine(`${localizeSpeaker("HomeHub")}: ${payload.reply}`);
  if (speakReply) speakWithHomeHub(payload.reply);
  refreshDashboardInBackground();
  return payload;
}

async function transcribeBlob(blob) {
  const base64Audio = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = String(reader.result || "");
      const marker = "base64,";
      const index = result.indexOf(marker);
      if (index === -1) {
        reject(new Error("Unable to encode audio."));
        return;
      }
      resolve(result.slice(index + marker.length));
    };
    reader.onerror = () => reject(reader.error || new Error("FileReader failed."));
    reader.readAsDataURL(blob);
  });

  const provider = getSelectedProviders().stt;
  const response = await fetch("/api/audio/transcribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, locale: currentLocale, mimeType: blob.type || "audio/webm", audioBase64: base64Audio })
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || t("voice.sttFailure"));
  }
  return {
    transcript: String(payload.transcript || "").trim(),
    detectedLocale: String(payload.detectedLocale || currentLocale).trim()
  };
}

async function transcribeAudioFile(file) {
  updateSpokenLine(t("voice.transcribing"));
  try {
    const result = await transcribeBlob(file);
    await sendVoiceMessage(result.transcript, { localeOverride: result.detectedLocale });
  } catch (error) {
    updateSpokenLine(`HomeHub: ${error.message || t("voice.sttFailure")}`);
  }
}

async function toggleMicrophoneRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    updateSpokenLine(`HomeHub: ${t("voice.browserNoMic")}`);
    return;
  }
  const micCore = document.querySelector("#mic-orb .mic-core");
  const micOrb = document.getElementById("mic-orb");
  if (isRecording && mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    isRecording = false;
    micCore.textContent = t("voice.micIdle");
    micOrb.classList.remove("is-recording");
    updateSpokenLine(t("prompts.recordingStopped"));
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaChunks = [];
    const preferredMimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : "";
    mediaRecorder = preferredMimeType ? new MediaRecorder(stream, { mimeType: preferredMimeType }) : new MediaRecorder(stream);
    const activeMimeType = mediaRecorder.mimeType || preferredMimeType || "audio/webm";
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) mediaChunks.push(event.data);
    };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      mediaRecorder = null;
      const blob = new Blob(mediaChunks, { type: activeMimeType });
      updateSpokenLine(t("voice.transcribing"));
      try {
        const result = await transcribeBlob(blob);
        await sendVoiceMessage(result.transcript, { localeOverride: result.detectedLocale });
      } catch (error) {
        updateSpokenLine(`HomeHub: ${error.message || t("voice.sttFailure")}`);
      }
    };
    mediaRecorder.start();
    isRecording = true;
    micCore.textContent = t("voice.micRecording");
    micOrb.classList.add("is-recording");
    updateSpokenLine(t("prompts.recordingStarted"));
  } catch (error) {
    mediaRecorder = null;
    micCore.textContent = t("voice.micIdle");
    micOrb.classList.remove("is-recording");
    updateSpokenLine(t("prompts.micAccessFailed", { error: String(error) }));
  }
}

function setupVoiceControls() {
  const micCore = document.querySelector("#mic-orb .mic-core");
  if (micCore) {
    micCore.textContent = t("voice.micIdle");
  }
}

function setupFloatingBuddyControls() {
  const shell = document.getElementById("floating-buddy");
  if (!shell) return;

  const startDrag = (clientX, clientY) => {
    const rect = shell.getBoundingClientRect();
    buddyDragState.dragging = true;
    buddyDragState.offsetX = clientX - rect.left;
    buddyDragState.offsetY = clientY - rect.top;
    shell.classList.add("is-dragging");
  };

  const moveDrag = (clientX, clientY) => {
    if (!buddyDragState.dragging) return;
    const next = clampBuddyPosition(clientX - buddyDragState.offsetX, clientY - buddyDragState.offsetY, shell);
    buddyDragState.x = next.x;
    buddyDragState.y = next.y;
    shell.style.right = "auto";
    shell.style.bottom = "auto";
    shell.style.left = `${next.x}px`;
    shell.style.top = `${next.y}px`;
  };

  const stopDrag = () => {
    if (!buddyDragState.dragging) return;
    buddyDragState.dragging = false;
    shell.classList.remove("is-dragging");
    persistBuddyPosition();
  };

  shell.addEventListener("pointerdown", (event) => {
    startDrag(event.clientX, event.clientY);
  });
  window.addEventListener("pointermove", (event) => {
    moveDrag(event.clientX, event.clientY);
  });
  window.addEventListener("pointerup", stopDrag);
  window.addEventListener("resize", () => {
    if (buddyDragState.x === null || buddyDragState.y === null) return;
    const next = clampBuddyPosition(buddyDragState.x, buddyDragState.y, shell);
    buddyDragState.x = next.x;
    buddyDragState.y = next.y;
    shell.style.left = `${next.x}px`;
    shell.style.top = `${next.y}px`;
    resizeBuddyModelViewer();
  });
}

function setupCustomProviderControls() {
  const saveButton = document.getElementById("custom-provider-save");
  if (!saveButton) return;
  const languagesInput = document.getElementById("custom-languages");
  if (languagesInput && !languagesInput.value) {
    languagesInput.value = "zh-CN,en-US,ja-JP";
  }
  saveButton.onclick = async () => {
    await saveCustomProvider();
  };
}

function setupBootstrapControls() {
  const button = document.getElementById("installer-approve");
  if (!button) return;
  button.addEventListener("click", async () => {
    await approveBootstrapSetup();
  });
}

function setupReminderOverlayControls() {
  const completeButton = document.getElementById("reminder-complete");
  if (!completeButton) return;
  const runComplete = async (event) => {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    await completeActiveReminder();
  };
  completeButton.onclick = runComplete;
  completeButton.addEventListener("pointerup", runComplete);
  completeButton.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" || event.key === " ") {
      await runComplete(event);
    }
  });
}

setupTabs();
setupRemoteNavigation();
setupVoiceControls();
setupTestControls();
setupCortexControls();
setupCustomProviderControls();
setupBootstrapControls();
setupReminderOverlayControls();
loadBuddyPosition();
setupFloatingBuddyControls();
applyStaticTranslations();
activateTab("home", false);
renderClock();
loadDashboard();
setInterval(renderClock, 1000);
setInterval(loadDashboard, 5000);
