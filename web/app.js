const STATUS_LABELS = {
  queued: "排队中",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const BATCH_STATUS_LABELS = {
  queued: "排队中",
  running: "进行中",
  done: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

const MD_STAGE_LABELS = {
  queued: "排队",
  prep: "结构准备",
  topo: "拓扑构建",
  equil: "平衡",
  prod: "生产模拟",
  analysis: "分析",
  done: "完成",
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function statusBadge(status, text) {
  const label = text || statusLabel(status);
  return `<span class="status-badge status-${status}">${escapeHtml(label)}</span>`;
}

const FOLD_ENGINES = new Set(["boltz2", "esmfold2"]);

function engineLabel(engine) {
  if (engine === "esmfold2") return "ESMFold2";
  if (engine === "boltz2") return "Boltz2";
  return engine || "—";
}

function isFoldEngine(engine) {
  return FOLD_ENGINES.has(engine);
}

function onFoldEngineChange() {
  const engine = document.getElementById("foldEngine")?.value || "boltz2";
  const hint = document.getElementById("msaHintSingle");
  const esm = document.getElementById("esmfoldOptsSingle");
  if (hint) hint.classList.toggle("hidden", engine !== "boltz2");
  if (esm) esm.classList.toggle("hidden", engine !== "esmfold2");
}

function onPanelEngineChange() {
  const engine = document.getElementById("panelEngine")?.value || "boltz2";
  const esm = document.getElementById("esmfoldOptsPanel");
  if (esm) esm.classList.toggle("hidden", engine !== "esmfold2");
  updatePanelPreview();
}

function readIntInput(id, fallback) {
  const el = document.getElementById(id);
  const v = parseInt(el?.value, 10);
  return Number.isFinite(v) ? v : fallback;
}

function getEsmfoldParams(panel = false) {
  const pre = panel ? "panel" : "";
  return {
    num_loops: readIntInput(`${pre}EsmNumLoops`, 10),
    num_sampling_steps: readIntInput(`${pre}EsmSamplingSteps`, 68),
    num_diffusion_samples: readIntInput(`${pre}EsmDiffusionSamples`, 5),
    seed: readIntInput(`${pre}EsmSeed`, 0),
  };
}

function formatEsmfoldParams(params) {
  if (!params) return "";
  return `loops=${params.num_loops} · steps=${params.num_sampling_steps} · samples=${params.num_diffusion_samples}`;
}

function getSelectedFoldEngine(panel = false) {
  const id = panel ? "panelEngine" : "foldEngine";
  return document.getElementById(id)?.value || "boltz2";
}

const API = "";
const TOKEN_KEY = "boltzfold_token";
const USER_KEY = "boltzfold_user";

let selectedJobId = null;
let selectedMdJobId = null;
let selectedBatchId = null;
let mdUploadFile = null;
let currentModule = "fold";
let foldMode = "single";
let taskFilter = "all";
let foldJobsCache = [];
let foldBatchesCache = [];
let pollTimer = null;
let viewer = null;
let interfaceViewer = null;
let loadedStructureJobId = null;
let loadedInterfaceJobId = null;
let structureCifText = null;
let interfaceDataCache = null;
/** @type {Map<string, { chainId: string, resi: number }>} */
let selectedSeqResidues = new Map();
/** @type {{ chainId: string, resi: number } | null} */
let lastSeqPickAnchor = null;
let sequencesDataCache = null;

/** PyMOL 默认 selection 色 */
const PYMOL_SEL_COLOR = 0xff00ff;
const PYMOL_SEL_DIM = 0.22;
const PYMOL_CHAIN_DIM = 0.38;

const BATCH_JOBS_PAGE_SIZE = 100;
let batchDetailCache = null;
let batchJobsPage = 0;
let batchJobsTotal = 0;
/** @type {{ type: 'batch', batchId: string, page: number } | null} */
let jobDetailReturnContext = null;

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function getUser() {
  const raw = localStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp;
  try {
    resp = await fetch(API + path, { ...options, headers });
  } catch (err) {
    const msg = err?.message || "";
    if (msg === "Failed to fetch" || err?.name === "TypeError") {
      throw new Error("无法连接服务器，请确认平台已启动且当前页面地址可访问");
    }
    throw err;
  }
  const isAuthAttempt = path.includes("/api/auth/login") || path.includes("/api/auth/register");
  const ct = resp.headers.get("content-type") || "";
  const data = ct.includes("json") ? await resp.json() : null;

  if (resp.status === 401) {
    if (isAuthAttempt) {
      const detail = typeof data?.detail === "string" ? data.detail : "";
      if (detail.includes("Invalid username or password")) {
        throw new Error("用户名或密码错误");
      }
      throw new Error(detail || "用户名或密码错误");
    }
    clearAuth();
    showAuth();
    throw new Error("登录已过期，请重新登录");
  }
  if (resp.status === 204) return null;
  if (!resp.ok) {
    let msg = data?.detail || resp.statusText;
    if (typeof msg === "object") msg = JSON.stringify(msg);
    if (resp.status === 404 && path.includes("/interface")) {
      msg = "结合界面 API 不可用，请重启平台服务（scripts/start_platform.sh）后刷新页面";
    } else if (resp.status === 404) {
      msg = msg === "Not Found" ? "资源不存在或 API 未就绪" : msg;
    }
    throw new Error(msg || "Request failed");
  }
  return data ?? resp;
}

function showAuth() {
  document.getElementById("authPanel").classList.remove("hidden");
  document.getElementById("appPanel").classList.add("hidden");
  document.getElementById("userBar").classList.add("hidden");
}

function showApp() {
  document.getElementById("authPanel").classList.add("hidden");
  document.getElementById("appPanel").classList.remove("hidden");
  document.getElementById("userBar").classList.remove("hidden");
  const user = getUser();
  document.getElementById("usernameDisplay").textContent = user?.username || "";
  loadMdJobs();
  loadMdParentOptions();
  refreshFoldTasks();
  updatePanelPreview();
  updateEmptyHero();
}

function setAuthTab(tab) {
  document.getElementById("loginForm").classList.toggle("hidden", tab !== "login");
  document.getElementById("registerForm").classList.toggle("hidden", tab !== "register");
  document.querySelectorAll(".auth-tabs button").forEach((b, i) => {
    b.classList.toggle("active", (tab === "login" && i === 0) || (tab === "register" && i === 1));
  });
}

let mol3dLoadPromise = null;

function load3DmolLib() {
  if (window.$3Dmol) return Promise.resolve();
  if (!mol3dLoadPromise) {
    mol3dLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://3Dmol.org/build/3Dmol-min.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("3D 库加载失败"));
      document.head.appendChild(script);
    });
  }
  return mol3dLoadPromise;
}

function setButtonLoading(btn, loading, label) {
  if (!btn) return;
  btn.disabled = loading;
  btn.classList.toggle("btn-loading", loading);
  if (label) btn.textContent = label;
}

async function doLogin() {
  const username = document.getElementById("loginUser").value.trim();
  const password = document.getElementById("loginPass").value;
  const btn = document.getElementById("loginBtn");
  const defaultLabel = "登录";
  setButtonLoading(btn, true, "登录中…");
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setAuth(data.access_token, data.user);
    showApp();
  } catch (e) {
    alert(e.message);
  } finally {
    setButtonLoading(btn, false, defaultLabel);
  }
}

async function doRegister() {
  const username = document.getElementById("regUser").value.trim();
  const password = document.getElementById("regPass").value;
  const btn = document.getElementById("registerBtn");
  const defaultLabel = "创建账号";
  setButtonLoading(btn, true, "创建中…");
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (data.pending_approval) {
      alert(data.message || "注册成功，请等待管理员审批后再登录");
      setAuthTab("login");
      document.getElementById("loginUser").value = username;
      return;
    }
    const loginData = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setAuth(loginData.access_token, loginData.user);
    showApp();
  } catch (e) {
    alert(e.message);
  } finally {
    setButtonLoading(btn, false, defaultLabel);
  }
}

function logout() {
  clearAuth();
  if (pollTimer) clearInterval(pollTimer);
  showAuth();
}

async function submitJob() {
  const fasta = getFastaForSubmit();
  const name = document.getElementById("jobName").value.trim() || null;
  if (!fasta) {
    alert(document.getElementById("fastaFilePanel").classList.contains("hidden")
      ? "请粘贴 FASTA 序列"
      : "请上传 FASTA 文件");
    return;
  }

  const btn = document.getElementById("submitBtn");
  btn.disabled = true;
  try {
    const engine = getSelectedFoldEngine(false);
    const body = {
      fasta,
      name,
      engine,
      use_msa_server: engine === "boltz2",
    };
    if (engine === "esmfold2") body.esmfold_params = getEsmfoldParams(false);
    await api("/api/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    clearFastaInputs();
    document.getElementById("jobName").value = "";
    await refreshFoldTasks();
    startPolling();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
}

function loadExample() {
  setFastaTab("paste");
  document.getElementById("fastaInput").value = EXAMPLE_FASTA;
  document.getElementById("jobName").value = "vhh_lysozyme_demo";
}

function bytesToBase64(bytes) {
  const chunk = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function isLikelyXlsx(bytes) {
  return bytes.length >= 2 && bytes[0] === 0x50 && bytes[1] === 0x4b;
}

async function importHeavyChainFile(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const isExcel = ext === "xlsx" || ext === "xlsm" || isLikelyXlsx(bytes);

  let data;
  try {
    data = await api("/api/batches/parse-heavy-csv-b64", {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content_b64: bytesToBase64(bytes),
      }),
    });
  } catch (err) {
    if (isExcel) {
      throw new Error(
        err.message || "无法解析 Excel 文件。请在 Excel 中「另存为 → CSV UTF-8」或 .txt 后重试。"
      );
    }
    const { text, encoding } = decodeBytesAuto(bytes);
    const parsed = parseHeavyChainText(text);
    if (!parsed.rows.length) {
      throw new Error(err.message || "文件解析失败。请确认格式（见下方说明）。");
    }
    data = {
      text: formatHeavyChainDisplay(parsed.rows, parsed.format),
      encoding: `${encoding}（本地解析）`,
      format: parsed.format,
      rows: parsed.rows,
      row_count: parsed.rows.length,
    };
  }
  return data;
}

function applyHeavyChainImport(data, filename) {
  const fmt = data.format || "csv";
  if (fmt === "fasta") {
    document.getElementById("heavyFastaInput").value = data.text;
    document.getElementById("heavyCsvInput").value = "";
    setHeavyTab("fasta");
  } else {
    document.getElementById("heavyCsvInput").value = data.text;
    document.getElementById("heavyFastaInput").value = "";
    setHeavyTab("csv");
  }
  updatePanelPreview();
  const hint = document.getElementById("heavyCsvFileHint");
  if (hint) {
    hint.textContent = data.row_count
      ? `已导入 ${filename}（${data.encoding}）· 识别 ${data.row_count} 条重链`
      : `已读取 ${filename}（${data.encoding}），但未解析到有效重链，请检查格式`;
  }
  if (!data.row_count) {
    alert(
      "未能识别重链序列。支持格式：\n"
      + "· CSV/TXT：vhh_id,sequence\n"
      + "· TXT 每行：ID<Tab/空格>序列\n"
      + "· TXT 仅序列（自动编号 VHH_001…）\n"
      + "· FASTA：>ID 换行 序列"
    );
  }
}

function stripBom(text) {
  return text.replace(/^\uFEFF/, "");
}

function textQualityScore(text) {
  if (!text || !text.trim()) return 0;
  const len = Math.max(text.length, 1);
  const bad = (text.match(/\uFFFD/g) || []).length;
  const printable = (text.match(/[\t\n\r\x20-\x7E\u4e00-\u9fff]/g) || []).length;
  let score = printable / len - bad * 0.1;
  if (text.includes(",") || text.includes("\t") || text.includes(";")) score += 0.08;
  if (/^>/m.test(text)) score += 0.12;
  const firstLine = text.split(/\r?\n/)[0] || "";
  if (/vhh|sequence|^id[,;\t]/i.test(firstLine)) score += 0.12;
  const mojibake = (text.match(/[\u00C0-\u024F]{3,}/g) || []).length;
  score -= mojibake * 0.03;
  return score;
}

function decodeBytesAuto(bytes) {
  if (bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) {
    return { text: stripBom(new TextDecoder("utf-8").decode(bytes.slice(3))), encoding: "UTF-8" };
  }
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) {
    return { text: stripBom(new TextDecoder("utf-16le").decode(bytes.slice(2))), encoding: "UTF-16 LE" };
  }
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) {
    return { text: stripBom(new TextDecoder("utf-16be").decode(bytes.slice(2))), encoding: "UTF-16 BE" };
  }

  const candidates = [
    { encoding: "UTF-8", text: stripBom(new TextDecoder("utf-8", { fatal: false }).decode(bytes)) },
  ];
  try {
    candidates.push({
      encoding: "GB18030",
      text: stripBom(new TextDecoder("gb18030").decode(bytes)),
    });
  } catch (_) {
    /* older browsers may lack gb18030 */
  }

  const best = candidates.reduce((a, b) => (textQualityScore(b.text) > textQualityScore(a.text) ? b : a));
  return best;
}

async function readTextFileAutoEncoding(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return decodeBytesAuto(bytes);
}

function splitCsvLine(line) {
  if (line.includes("\t")) return line.split("\t");
  if (line.includes("|")) return line.split("|").map((p) => p.trim());
  const semi = line.split(";");
  const comma = line.split(",");
  if (semi.length > comma.length) return semi;
  return comma;
}

function setFastaTab(tab) {
  const isPaste = tab === "paste";
  document.getElementById("fastaPastePanel").classList.toggle("hidden", !isPaste);
  document.getElementById("fastaFilePanel").classList.toggle("hidden", isPaste);
  document.querySelectorAll(".input-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.inputTab === tab);
  });
}

function baseNameFromPath(name) {
  const base = name.replace(/\\/g, "/").split("/").pop() || name;
  return base.replace(/\.(fasta|fa|fas|txt|seq)$/i, "");
}

async function readFastaFile(file) {
  if (!file) return;
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const allowed = ["fasta", "fa", "fas", "txt", "seq"];
  if (ext && !allowed.includes(ext)) {
    alert("仅支持 .fasta / .fa / .fas / .txt 文件");
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    alert("文件过大（最大 2MB）");
    return;
  }
  const { text, encoding } = await readTextFileAutoEncoding(file);
  if (!text.trim().startsWith(">")) {
    alert("FASTA 格式无效：需以 >链ID 开头");
    return;
  }
  fastaUploadText = text.trim() + "\n";
  document.getElementById("fastaFileName").textContent =
    `已选择：${file.name}（${(file.size / 1024).toFixed(1)} KB · ${encoding}）`;
  const preview = document.getElementById("fastaFilePreview");
  preview.classList.remove("hidden");
  preview.value = fastaUploadText.length > 4000
    ? fastaUploadText.slice(0, 4000) + "\n…（预览已截断）"
    : fastaUploadText;
  const jobNameEl = document.getElementById("jobName");
  if (!jobNameEl.value.trim()) {
    jobNameEl.value = baseNameFromPath(file.name);
  }
}

function initFastaUpload() {
  const input = document.getElementById("fastaFile");
  const zone = document.getElementById("fastaDropZone");
  if (!input || !zone) return;

  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (file) readFastaFile(file);
    input.value = "";
  });

  zone.addEventListener("click", (e) => {
    if (e.target.closest("button")) return;
    input.click();
  });

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const file = e.dataTransfer?.files?.[0];
    if (file) readFastaFile(file);
  });
}

function getFastaForSubmit() {
  const filePanelVisible = !document.getElementById("fastaFilePanel").classList.contains("hidden");
  if (filePanelVisible) {
    return fastaUploadText.trim();
  }
  return document.getElementById("fastaInput").value.trim();
}

function clearFastaInputs() {
  document.getElementById("fastaInput").value = "";
  fastaUploadText = "";
  document.getElementById("fastaFileName").textContent = "";
  const preview = document.getElementById("fastaFilePreview");
  preview.value = "";
  preview.classList.add("hidden");
}

async function refreshFoldTasks() {
  try {
    const [jobs, batches] = await Promise.all([
      api("/api/jobs?limit=50&singles_only=true"),
      api("/api/batches?limit=50"),
    ]);
    foldJobsCache = jobs.items || [];
    foldBatchesCache = batches.items || [];
    renderFoldTaskList();
    const activeJob = foldJobsCache.find((j) => ["queued", "running"].includes(j.status));
    const activeBatch = foldBatchesCache.find((b) => ["queued", "running"].includes(b.status));
    if ((activeJob || activeBatch) && !pollTimer) startPolling();
  } catch (e) {
    console.error(e);
  }
}

async function loadJobs() {
  await refreshFoldTasks();
}

async function loadBatches() {
  await refreshFoldTasks();
}

function renderFoldTaskList() {
  const list = document.getElementById("foldTaskList");
  if (!list) return;

  const items = [];
  if (taskFilter === "all" || taskFilter === "single") {
    for (const j of foldJobsCache) {
      items.push({ kind: "single", data: j, ts: j.created_at });
    }
  }
  if (taskFilter === "all" || taskFilter === "batch") {
    for (const b of foldBatchesCache) {
      items.push({ kind: "batch", data: b, ts: b.created_at });
    }
  }
  items.sort((a, b) => new Date(b.ts) - new Date(a.ts));

  if (!items.length) {
    const emptyMsg =
      taskFilter === "single"
        ? "暂无单条任务"
        : taskFilter === "batch"
          ? "暂无批次"
          : "暂无任务，请在上方提交预测";
    list.innerHTML = `<div class="empty-state">${emptyMsg}</div>`;
    return;
  }

  list.innerHTML = items
    .map((item) => (item.kind === "batch" ? renderBatchListItem(item.data) : renderJobListItem(item.data)))
    .join("");

  list.querySelectorAll(".task-item[data-kind='single']").forEach((el) => {
    el.addEventListener("click", () => selectJob(el.dataset.id));
  });
  list.querySelectorAll(".task-item[data-kind='batch']").forEach((el) => {
    el.addEventListener("click", () => selectBatch(el.dataset.id));
  });
  list.querySelectorAll(".task-delete-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (btn.dataset.kind === "batch") {
        deleteBatch(btn.dataset.id, btn.dataset.name);
      } else {
        deleteJob(btn.dataset.id, btn.dataset.name);
      }
    });
  });
}

function renderJobListItem(j) {
  const title = j.name || j.id.slice(0, 8);
  const chains = Object.keys(j.chains_json || {}).join(", ");
  const iptm = j.iptm != null ? ` · ipTM ${j.iptm.toFixed(2)}` : "";
  const pq = j.pdockq != null ? ` · pDockQ ${j.pdockq.toFixed(2)}` : "";
  const active = j.id === selectedJobId ? " active" : "";
  const time = j.created_at
    ? new Date(j.created_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "";
  const eng = j.engine ? ` · ${engineLabel(j.engine)}` : "";
  return `<div class="job-item task-item${active}" data-kind="single" data-id="${j.id}">
    <div class="job-item-top">
      <div class="title"><span class="task-kind-badge kind-single">单条</span>${escapeHtml(title)}</div>
      <div class="job-item-actions">
        ${statusBadge(j.status)}
        <button class="job-delete-btn task-delete-btn" data-kind="single" data-id="${j.id}" data-name="${escapeHtml(title)}" type="button" title="删除">×</button>
      </div>
    </div>
    <div class="meta">${chains} · ${j.total_length} aa${eng}${iptm}${pq}${time ? ` · ${time}` : ""}</div>
  </div>`;
}

function renderBatchListItem(b) {
  const active = b.id === selectedBatchId ? " active" : "";
  const prog = `${b.done_count}/${b.heavy_chain_count}`;
  const time = new Date(b.created_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return `<div class="job-item task-item batch-item${active}" data-kind="batch" data-id="${b.id}">
    <div class="job-item-top">
      <div class="title"><span class="task-kind-badge kind-batch">批次</span>${escapeHtml(b.name)}</div>
      <div class="job-item-actions">
        ${statusBadge(b.status, BATCH_STATUS_LABELS[b.status] || b.status)}
        <button class="job-delete-btn task-delete-btn" data-kind="batch" data-id="${b.id}" data-name="${escapeHtml(b.name)}" type="button" title="删除">×</button>
      </div>
    </div>
    <div class="meta">${escapeHtml(b.target_name)} · ${prog} 完成 · ${time}</div>
  </div>`;
}

function setTaskFilter(filter) {
  taskFilter = filter;
  document.querySelectorAll("[data-task-filter]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.taskFilter === filter);
  });
  renderFoldTaskList();
}

function updateEmptyHero() {
  const title = document.getElementById("emptyHeroTitle");
  const desc = document.getElementById("emptyHeroDesc");
  const empty = document.getElementById("detailEmpty");
  const foldBody = document.getElementById("emptyHeroFold");
  const mdBody = document.getElementById("emptyHeroMd");
  if (!title || !desc) return;

  if (currentModule === "md") {
    title.textContent = "选择 MD 任务查看进度";
    desc.textContent = "提交或选择左侧 MD 任务，此处将显示模拟阶段与分析摘要";
    empty?.setAttribute("data-module", "md");
    foldBody?.classList.add("hidden");
    mdBody?.classList.remove("hidden");
  } else {
    title.textContent = "选择任务查看详情";
    desc.textContent = "提交或选择左侧任务，此处将显示 ipTM / pDockQ / pLDDT、Kabat CDR 与 3D 结构";
    empty?.setAttribute("data-module", "fold");
    foldBody?.classList.remove("hidden");
    mdBody?.classList.add("hidden");
  }
}

function setModule(module) {
  currentModule = module;
  document.querySelectorAll(".module-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.module === module);
  });
  document.getElementById("foldModule").classList.toggle("hidden", module !== "fold");
  document.getElementById("mdModule").classList.toggle("hidden", module !== "md");
  if (module === "md") loadMdParentOptions();
  updateEmptyHero();
  if (!selectedJobId && !selectedBatchId && !selectedMdJobId) {
    document.getElementById("detailEmpty").classList.remove("hidden");
  }
}

function setFoldMode(mode) {
  foldMode = mode;
  document.querySelectorAll("[data-fold-mode]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.foldMode === mode);
  });
  document.getElementById("singleJobPanel").classList.toggle("hidden", mode !== "single");
  document.getElementById("vhhPanelPanel").classList.toggle("hidden", mode !== "panel");
}

function setSidebarMode(mode) {
  if (mode === "md") {
    setModule("md");
    return;
  }
  setModule("fold");
  setFoldMode(mode === "panel" ? "panel" : "single");
}

async function selectJob(id, opts = {}) {
  const fromBatch = opts.fromBatch === true;
  if (id !== selectedJobId) {
    loadedStructureJobId = null;
  }
  selectedJobId = id;
  if (!fromBatch) {
    selectedBatchId = null;
    jobDetailReturnContext = null;
  }
  selectedMdJobId = null;
  setModule("fold");
  document.getElementById("mdDetailPanel").classList.add("hidden");
  document.getElementById("batchPanel").classList.add("hidden");
  document.querySelectorAll(".task-item").forEach((el) => {
    if (fromBatch && selectedBatchId) {
      el.classList.toggle("active", el.dataset.kind === "batch" && el.dataset.id === selectedBatchId);
    } else {
      el.classList.toggle("active", el.dataset.kind === "single" && el.dataset.id === id);
    }
  });
  try {
    const j = await api(`/api/jobs/${id}`);
    renderJobDetail(j);
    await loadJobSequences(id);
  } catch (e) {
    alert(e.message);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function cdrClass(name) {
  if (!name) return "seg-fw";
  return "seg-" + name.toLowerCase().replace(/[^a-z0-9]/g, "-");
}

function cdrClassForResidue(ch, index) {
  const i = index - 1;
  for (const sp of ch.cdr_spans || []) {
    if (i >= sp.start && i <= sp.end) return cdrClass(sp.name);
  }
  return "seg-fw";
}

function renderNumberedResidues(ch) {
  const residues = ch.residues && ch.residues.length
    ? ch.residues
    : (ch.sequence || "").split("").map((aa, i) => ({ index: i + 1, aa, kabat: String(i + 1) }));

  const cells = residues.map((r) => {
    const cls = cdrClassForResidue(ch, r.index);
    const kabatDiff = ch.is_antibody && r.kabat && String(r.kabat) !== String(r.index);
    const numLabel = kabatDiff ? r.kabat : r.index;
    const title = kabatDiff
      ? `序列位 ${r.index} · Kabat ${r.kabat} · 点击多选`
      : `序列位 ${r.index} · 点击多选`;
    return `<span class="res-cell res-selectable ${cls}"` +
      ` data-chain-id="${escapeHtml(ch.chain_id)}" data-resi="${r.index}"` +
      ` title="${escapeHtml(title)}">` +
      `<span class="res-num">${escapeHtml(String(numLabel))}</span>` +
      `<span class="res-aa">${escapeHtml(r.aa)}</span>` +
      `</span>`;
  }).join("");

  return `<div class="chain-seq-numbered" style="--seq-len:${residues.length}">` +
    `<div class="seq-res-grid">${cells}</div>` +
    `</div>`;
}

function findSequenceCell(chainId, resi) {
  return document.querySelector(
    `.res-cell[data-chain-id="${CSS.escape(String(chainId))}"][data-resi="${parseInt(resi, 10)}"]`
  );
}

function residueSelectionKey(chainId, resi) {
  return `${chainId}:${parseInt(resi, 10)}`;
}

function getSelectedResiduesList() {
  return [...selectedSeqResidues.values()];
}

function isResidueSelected(chainId, resi) {
  return selectedSeqResidues.has(residueSelectionKey(chainId, resi));
}

function syncSequenceSelectionUI() {
  document.querySelectorAll(".res-cell.res-selected").forEach((el) => el.classList.remove("res-selected"));
  for (const { chainId, resi } of selectedSeqResidues.values()) {
    findSequenceCell(chainId, resi)?.classList.add("res-selected");
  }
  const n = selectedSeqResidues.size;
  const btn = document.getElementById("clearSeqSelectionBtn");
  const countEl = document.getElementById("seqSelectionCount");
  if (btn) btn.classList.toggle("hidden", n === 0);
  if (countEl) countEl.textContent = n > 0 ? `已选 ${n} 个残基` : "";
}

function applyPyMOLSelectionView(v, mode, chains) {
  const selected = getSelectedResiduesList();
  if (!selected.length) return;

  const chainsWithSel = new Set(selected.map((r) => r.chainId));
  const orSel = selected.map((r) => ({ chain: r.chainId, resi: r.resi }));

  if (mode === "plddt") {
    v.setStyle({}, {
      cartoon: { colorfunc: (atom) => plddtToColor(atom.b), opacity: PYMOL_SEL_DIM },
    });
  } else if (chains?.length) {
    for (const ch of chains) {
      v.setStyle({ chain: ch.chain_id }, {
        cartoon: {
          color: hexColorToInt(ch.color),
          opacity: chainsWithSel.has(ch.chain_id) ? PYMOL_CHAIN_DIM : PYMOL_SEL_DIM,
        },
      });
    }
  } else {
    v.setStyle({}, { cartoon: { opacity: PYMOL_SEL_DIM } });
  }

  for (const cid of chainsWithSel) {
    v.addStyle({ chain: cid }, { cartoon: { opacity: 0.5 } });
  }

  v.addStyle({ or: orSel }, {
    cartoon: { color: PYMOL_SEL_COLOR, opacity: 1, thickness: 0.46 },
  });
}

function bindViewerResiduePick(v) {
  v.setClickable({}, true, (atom, _viewer, event) => {
    if (!atom || atom.resi == null || !atom.chain) return;
    const cell = findSequenceCell(atom.chain, atom.resi);
    selectSequenceResidue(atom.chain, atom.resi, cell, event);
  });
}

function selectSequenceResidue(chainId, resi, cellEl, event) {
  const resiNum = parseInt(resi, 10);
  const key = residueSelectionKey(chainId, resiNum);
  const shift = event?.shiftKey;
  const ctrl = event?.ctrlKey || event?.metaKey;

  if (shift && lastSeqPickAnchor?.chainId === chainId) {
    const a = Math.min(lastSeqPickAnchor.resi, resiNum);
    const b = Math.max(lastSeqPickAnchor.resi, resiNum);
    for (let i = a; i <= b; i += 1) {
      selectedSeqResidues.set(residueSelectionKey(chainId, i), { chainId, resi: i });
    }
    lastSeqPickAnchor = { chainId, resi: resiNum };
  } else if (ctrl) {
    if (selectedSeqResidues.has(key)) {
      selectedSeqResidues.delete(key);
    } else {
      selectedSeqResidues.set(key, { chainId, resi: resiNum });
      lastSeqPickAnchor = { chainId, resi: resiNum };
    }
  } else {
    if (selectedSeqResidues.has(key)) {
      selectedSeqResidues.delete(key);
    } else {
      selectedSeqResidues.set(key, { chainId, resi: resiNum });
      lastSeqPickAnchor = { chainId, resi: resiNum };
    }
  }

  syncSequenceSelectionUI();
  if (viewer) refreshMainViewerStyles();
}

function clearSequenceResidueSelection() {
  selectedSeqResidues.clear();
  lastSeqPickAnchor = null;
  syncSequenceSelectionUI();
  if (viewer) refreshMainViewerStyles();
}

function renderSequences(data) {
  const panel = document.getElementById("sequencePanel");
  const chainsEl = document.getElementById("sequenceChains");
  const legend = document.getElementById("sequenceLegend");
  if (!data || !data.chains || !data.chains.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  sequencesDataCache = data;
  clearSequenceResidueSelection();
  legend.innerHTML =
    '<span class="legend-fw">框架区</span>' +
    '<span class="legend-cdr1">CDR1 (H1/L1)</span>' +
    '<span class="legend-cdr2">CDR2 (H2/L2)</span>' +
    '<span class="legend-cdr3">CDR3 (H3/L3)</span>' +
    '<span class="legend-pymol-sel">PyMOL 选中</span>' +
    '<span id="seqSelectionCount" class="seq-selection-count"></span>' +
    '<span>点击添加/取消 · Shift 连选同链区间 · Ctrl 同点击</span>';

  chainsEl.innerHTML = data.chains.map((ch) => {
    const abLabel = ch.is_antibody
      ? `${ch.domain} 链 · Kabat · ${ch.length} aa`
      : `非抗体链 · 序列位 1–${ch.length}`;

    const cdrTags = (ch.cdr_spans || []).map((sp) =>
      `<span class="cdr-tag">${sp.name} (${sp.kabat_range}): <code>${escapeHtml(sp.sequence)}</code></span>`
    ).join("");

    return `<div class="chain-seq-block">
      <div class="chain-seq-head"><strong>&gt;${escapeHtml(ch.chain_id)}</strong><span>${abLabel}</span></div>
      <div class="chain-seq-body">${renderNumberedResidues(ch)}</div>
      ${cdrTags ? `<div class="cdr-tags">${cdrTags}</div>` : ""}
    </div>`;
  }).join("");
}

async function loadJobSequences(jobId) {
  try {
    const data = await api(`/api/jobs/${jobId}/sequences`);
    renderSequences(data);
  } catch (e) {
    document.getElementById("sequencePanel").classList.add("hidden");
  }
}

function renderJobDetail(j) {
  document.getElementById("detailEmpty").classList.add("hidden");
  document.getElementById("batchPanel").classList.add("hidden");
  document.getElementById("mdDetailPanel").classList.add("hidden");
  document.getElementById("detailPanel").classList.remove("hidden");

  document.getElementById("detailTitle").textContent = j.name || j.id;

  const chains = Object.entries(j.chains_json || {}).map(([k, v]) => `${k}:${v}`).join(" · ");
  const created = j.created_at
    ? new Date(j.created_at).toLocaleString("zh-CN")
    : "";
  const esmParams = j.engine === "esmfold2" ? formatEsmfoldParams(j.params_json) : "";
  document.getElementById("detailMeta").textContent =
    [engineLabel(j.engine), esmParams, chains && `${chains} aa`, created && `提交于 ${created}`]
      .filter(Boolean)
      .join(" · ");

  const statusEl = document.getElementById("detailStatus");
  statusEl.className = `status-badge status-${j.status}`;
  statusEl.textContent = statusLabel(j.status);

  const metrics = [
    ["ipTM", j.iptm, true],
    ["pDockQ", j.pdockq, j.pdockq != null],
    ["pDockQ2", j.pdockq2, j.pdockq2 != null],
    ["pTM", j.ptm, false],
    ["pLDDT", j.complex_plddt, true],
    ["置信度", j.confidence_score, false],
    ["耗时", j.runtime_seconds != null ? `${Math.round(j.runtime_seconds)}s` : null, false],
  ];
  document.getElementById("metricsGrid").innerHTML = metrics
    .map(([lbl, val, highlight]) => {
      const display = val != null
        ? (typeof val === "number" ? val.toFixed(3) : val)
        : "—";
      const cls = highlight ? " metric-highlight" : "";
      return `<div class="metric${cls}"><div class="val">${display}</div><div class="lbl">${lbl}</div></div>`;
    })
    .join("");

  const errBox = document.getElementById("errorBox");
  if (j.error_message) {
    errBox.textContent = j.error_message;
    errBox.classList.remove("hidden");
  } else {
    errBox.classList.add("hidden");
  }

  const dl = document.getElementById("downloadBtn");
  const mdBtn = document.getElementById("startMdBtn");
  if (j.status === "done" && isFoldEngine(j.engine)) {
    dl.classList.remove("hidden");
    dl.onclick = () => downloadStructure(j.id, j.name || j.id);
    if (mdBtn) {
      mdBtn.classList.remove("hidden");
      mdBtn.onclick = () => startMdFromFoldJob(j.id, j.name);
    }
  } else {
    dl.classList.add("hidden");
    if (mdBtn) mdBtn.classList.add("hidden");
  }
  maybeLoadStructure3D(j);

  document.getElementById("deleteBtn").onclick = () => deleteJob(j.id, j.name || j.id);
  updateJobDetailBackButton();
}

function prepareInterfaceSection(j) {
  const section = document.getElementById("interfaceSection");
  if (!section) return;
  const chainCount = Object.keys(j.chains_json || {}).length;
  if (j.status !== "done" || chainCount < 2) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
}

async function deleteJob(jobId, jobName) {
  const label = jobName || jobId.slice(0, 8);
  const msg = `确定删除任务「${label}」吗？\n\n将同时删除数据库记录和 outputs 目录中的结果文件，此操作不可恢复。`;
  if (!confirm(msg)) return;

  try {
    await api(`/api/jobs/${jobId}`, { method: "DELETE" });
    if (selectedJobId === jobId) {
      selectedJobId = null;
      loadedStructureJobId = null;
      clearViewer();
      document.getElementById("detailPanel").classList.add("hidden");
      document.getElementById("detailEmpty").classList.remove("hidden");
    }
    await refreshFoldTasks();
  } catch (e) {
    alert(e.message || "删除失败");
  }
}

function showViewerPlaceholder(message, loading = false) {
  if (loading) {
    viewer = null;
    const elem = document.getElementById("viewer3d");
    if (elem) {
      elem.innerHTML = `<div class="viewer-placeholder viewer-loading">${escapeHtml(message)}</div>`;
    }
    return;
  }
  clearViewer(false);
  const elem = document.getElementById("viewer3d");
  elem.innerHTML = `<div class="viewer-placeholder">${escapeHtml(message)}</div>`;
}

async function loadInterfaceForJob(jobId, cifText, jobMeta) {
  if (jobMeta) {
    prepareInterfaceSection(jobMeta);
  } else {
    document.getElementById("interfaceSection")?.classList.remove("hidden");
  }
  showInterfaceLoading(true);
  showInterfaceError("");
  hideInterfaceContent();
  try {
    const ifaceData = await api(`/api/jobs/${jobId}/interface`);
    interfaceDataCache = ifaceData;
    renderInterfacePanel(ifaceData);
    if (ifaceData?.primary_interface?.contact_pairs && cifText) {
      await loadInterfaceViewer(jobId, cifText, ifaceData);
    }
    refreshMainViewerStyles();
  } catch (e) {
    interfaceDataCache = null;
    showInterfaceLoading(false);
    showInterfaceError(e.message || "结合界面加载失败");
    hideInterfaceContent();
  }
}

async function maybeLoadStructure3D(j) {
  if (j.status === "queued") {
    loadedStructureJobId = null;
    loadedInterfaceJobId = null;
    document.getElementById("interfaceSection")?.classList.add("hidden");
    showViewerPlaceholder("任务排队中，完成后将自动显示 3D 结构…", true);
    return;
  }
  if (j.status === "running") {
    loadedStructureJobId = null;
    loadedInterfaceJobId = null;
    document.getElementById("interfaceSection")?.classList.add("hidden");
    showViewerPlaceholder("结构预测进行中，请稍候…", true);
    return;
  }
  if (j.status !== "done") {
    loadedStructureJobId = null;
    loadedInterfaceJobId = null;
    document.getElementById("interfaceSection")?.classList.add("hidden");
    showViewerPlaceholder(j.status === "failed" ? "预测失败，无结构可显示" : "暂无 3D 结构");
    return;
  }
  prepareInterfaceSection(j);
  if (loadedStructureJobId === j.id && viewer) {
    if (loadedInterfaceJobId !== j.id) {
      await loadInterfaceForJob(j.id, structureCifText, j);
    }
    return;
  }
  await loadStructure3D(j.id);
}

async function downloadStructure(jobId, filename) {
  try {
    const token = getToken();
    const resp = await fetch(`/api/jobs/${jobId}/structure`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `下载失败 (${resp.status})`);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filename}.cif`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(e.message || "下载失败");
  }
}

/** AlphaFold/Boltz-style pLDDT color (B-factor in mmCIF, 0–100). */
function plddtToColor(b) {
  if (b == null || Number.isNaN(b)) return 0x8b949e;
  let v = b;
  if (v <= 1.0) v *= 100;
  if (v > 90) return 0x0053d6;
  if (v > 70) return 0x00c1f2;
  if (v > 50) return 0xfffd00;
  return 0xff7d00;
}

function hexColorToInt(hex) {
  if (!hex) return 0x8b949e;
  const s = hex.replace("#", "");
  return parseInt(s, 16);
}

function applyPlddtStyle(v) {
  v.setStyle({}, {
    cartoon: {
      colorfunc: (atom) => plddtToColor(atom.b),
    },
  });
}

function applyChainStyle(v, chains) {
  v.setStyle({}, {});
  for (const ch of chains) {
    v.setStyle({ chain: ch.chain_id }, {
      cartoon: { color: hexColorToInt(ch.color), opacity: 0.92 },
    });
  }
}

function highlightInterfaceResidues(v, iface) {
  if (!iface) return;
  const residues = [...(iface.residues_a || []), ...(iface.residues_b || [])];
  for (const r of residues) {
    v.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
      stick: { colorscheme: "yellowCarbon", radius: 0.12 },
      sphere: { radius: 0.35, color: 0xff3366 },
    });
  }
}

function applyViewerStyles(v, mode, chains) {
  if (!v) return;
  if (mode === "plddt") {
    applyPlddtStyle(v);
  } else if (chains && chains.length) {
    applyChainStyle(v, chains);
  } else {
    applyPlddtStyle(v);
  }
}

function renderChainLegend(chains) {
  const el = document.getElementById("chainLegend");
  if (!el) return;
  if (!chains || !chains.length) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  el.innerHTML =
    '<div class="plddt-overlay-title">链标注</div>' +
    chains.map((ch) =>
      `<div class="chain-legend-item"><span class="chain-legend-swatch" style="background:${escapeHtml(ch.color)}"></span><span>${escapeHtml(ch.label)} · ${ch.length} aa</span></div>`
    ).join("");
}

const IX_TYPE_LABELS = {
  hbond: "氢键",
  salt_bridge: "盐桥",
  hydrophobic: "疏水",
  pi_stacking: "π-堆积",
  pi_cation: "π-阳离子",
  water_bridge: "水桥",
};

/** 3D 中绘制：疏水/π 等坐标多为环心或质心，预测结构下易误导；仅画氢键/盐桥 */
const IX_DRAW_IN_3D = new Set(["hbond", "salt_bridge"]);

const IX_COLORS = {
  hbond: 0xf59e0b,
  salt_bridge: 0xef4444,
  hydrophobic: 0x94a3b8,
  pi_stacking: 0x8b5cf6,
  pi_cation: 0x06b6d4,
  water_bridge: 0x38bdf8,
};

const IX_LINE_CSS = {
  hbond: "#f59e0b",
  salt_bridge: "#ef4444",
  hydrophobic: "#94a3b8",
  pi_stacking: "#8b5cf6",
  pi_cation: "#06b6d4",
  water_bridge: "#38bdf8",
};

const IX_LINE_RADIUS = {
  hbond: 0.02,
  salt_bridge: 0.028,
  hydrophobic: 0.02,
  pi_stacking: 0.025,
  pi_cation: 0.025,
  water_bridge: 0.022,
};

const IFACE_CHAIN_PALETTE = {
  target: 0x5b8def,
  binder: 0xe07a5f,
};

function getInterfaceChainPalette(primary, chains) {
  const meta = Object.fromEntries((chains || []).map((c) => [c.chain_id, c]));
  const palette = {};
  for (const cid of [primary.chain_a, primary.chain_b]) {
    const m = meta[cid] || {};
    const isTarget = m.role === "target" || (m.label && /靶|抗原|target/i.test(m.label)) || cid === "A";
    palette[cid] = isTarget ? IFACE_CHAIN_PALETTE.target : IFACE_CHAIN_PALETTE.binder;
  }
  return palette;
}

function hexCssFromInt(colorInt) {
  return `#${colorInt.toString(16).padStart(6, "0")}`;
}

function collectInterfaceResidueKeys(primary) {
  const interactions = (primary.interactions || []).filter((ix) => ix.type !== "contact");
  const ixResKeys = new Set();
  for (const ix of interactions) {
    ixResKeys.add(`${ix.chain_a}:${ix.resnum_a}`);
    ixResKeys.add(`${ix.chain_b}:${ix.resnum_b}`);
  }
  return { interactions, ixResKeys };
}

function renderInterfaceViewerOverlay(data, primary) {
  const el = document.getElementById("interfaceViewerOverlay");
  if (!el || !primary) return;

  const palette = getInterfaceChainPalette(primary, data?.chains || []);
  const chainRows = [
    { id: primary.chain_a, label: primary.label_a || primary.chain_a, color: palette[primary.chain_a] },
    { id: primary.chain_b, label: primary.label_b || primary.chain_b, color: palette[primary.chain_b] },
  ];
  const presentIx = new Set((primary.interactions || []).map((ix) => ix.type));
  const ixRows = Object.entries(IX_TYPE_LABELS)
    .filter(([k]) => presentIx.has(k) && IX_DRAW_IN_3D.has(k))
    .map(([k, lbl]) =>
      `<div class="interface-viewer-overlay-row">` +
      `<span class="interface-viewer-line" style="background:${IX_LINE_CSS[k]}"></span>` +
      `<span>${lbl}</span></div>`
    );

  el.innerHTML =
    `<div class="interface-viewer-overlay-title">结合界面</div>` +
    chainRows.map((ch) =>
      `<div class="interface-viewer-overlay-row">` +
      `<span class="interface-viewer-swatch" style="background:${hexCssFromInt(ch.color)}"></span>` +
      `<span>${escapeHtml(ch.label)} · 链 ${escapeHtml(ch.id)}</span></div>`
    ).join("") +
    (ixRows.length
      ? `<div class="interface-viewer-overlay-title" style="margin-top:0.45rem">PLIP 相互作用</div>${ixRows.join("")}`
      : "") +
    (presentIx.has("hydrophobic")
      ? `<div class="interface-viewer-overlay-note">疏水接触见下方表格（3D 中省略以避免线网过密）</div>`
      : "");
  el.classList.remove("hidden");
}

function drawInterfaceInteractionGraphics(viewer, interactions) {
  for (const ix of interactions) {
    if (!IX_DRAW_IN_3D.has(ix.type)) continue;
    if (!ix.coord_a?.length || !ix.coord_b?.length) continue;
    const color = IX_COLORS[ix.type] || 0x64748b;
    const radius = IX_LINE_RADIUS[ix.type] || 0.02;
    const start = { x: ix.coord_a[0], y: ix.coord_a[1], z: ix.coord_a[2] };
    const end = { x: ix.coord_b[0], y: ix.coord_b[1], z: ix.coord_b[2] };
    viewer.addCylinder({ start, end, radius, color, fromCap: 0, toCap: 0 });
  }
}

function paintInterfaceViewer(viewer, primary, chains) {
  const palette = getInterfaceChainPalette(primary, chains);
  const { interactions, ixResKeys } = collectInterfaceResidueKeys(primary);
  const ifaceRes = [...(primary.residues_a || []), ...(primary.residues_b || [])];
  const ifaceKeys = new Set(ifaceRes.map((r) => `${r.chain_id}:${r.seq_num}`));

  for (const ch of chains || []) {
    const onIface = ch.chain_id === primary.chain_a || ch.chain_id === primary.chain_b;
    if (!onIface) {
      viewer.setStyle({ chain: ch.chain_id }, { cartoon: { opacity: 0 } });
      continue;
    }
    const baseColor = palette[ch.chain_id] || hexColorToInt(ch.color);
    viewer.setStyle({ chain: ch.chain_id }, {
      cartoon: { color: baseColor, opacity: 0.2, thickness: 0.22 },
    });
  }

  for (const r of ifaceRes) {
    const key = `${r.chain_id}:${r.seq_num}`;
    const baseColor = palette[r.chain_id] || IFACE_CHAIN_PALETTE.target;
    const inIx = ixResKeys.has(key);
    viewer.addStyle({ chain: r.chain_id, resi: r.seq_num }, {
      cartoon: {
        color: baseColor,
        opacity: inIx ? 0.95 : 0.72,
        thickness: inIx ? 0.42 : 0.32,
      },
    });
  }

  drawInterfaceInteractionGraphics(viewer, interactions);

  const focusSelections = [];
  for (const key of ixResKeys.size ? ixResKeys : ifaceKeys) {
    const [chain, resi] = key.split(":");
    focusSelections.push({ chain, resi: parseInt(resi, 10) });
  }
  return focusSelections;
}

let interfaceIxFilter = "all";
let interfaceCifTextCache = null;

function renderInteractionLegend() {
  /* 图例已移至 3D 视窗内 overlay */
}

function renderInteractionTable(primary) {
  const tableEl = document.getElementById("interfaceInteractionTable");
  const filtersEl = document.getElementById("interfaceInteractionFilters");
  const interactions = primary.interactions || [];
  if (!tableEl) return;

  const counts = { all: interactions.length };
  for (const ix of interactions) {
    counts[ix.type] = (counts[ix.type] || 0) + 1;
  }

  if (filtersEl) {
    const types = ["all", ...Object.keys(IX_TYPE_LABELS).filter((t) => counts[t])];
    filtersEl.innerHTML = types.map((t) => {
      const lbl = t === "all" ? `全部 (${counts.all})` : `${IX_TYPE_LABELS[t]} (${counts[t]})`;
      const active = interfaceIxFilter === t ? " active" : "";
      return `<button type="button" class="interaction-filter-btn${active}" data-ix-filter="${t}">${lbl}</button>`;
    }).join("");
    filtersEl.querySelectorAll("[data-ix-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        interfaceIxFilter = btn.dataset.ixFilter;
        renderInteractionTable(primary);
      });
    });
  }

  const filtered = interfaceIxFilter === "all"
    ? interactions
    : interactions.filter((ix) => ix.type === interfaceIxFilter);

  if (!filtered.length) {
    tableEl.innerHTML = '<p class="hint" style="padding:0.75rem">暂无该类相互作用</p>';
    return;
  }

  tableEl.innerHTML =
    `<table class="interaction-table"><thead><tr>` +
    `<th>类型</th><th>受体/链 A</th><th>抗体/链 B</th><th>距离 (Å)</th><th>详情</th>` +
    `</tr></thead><tbody>` +
    filtered.map((ix, i) =>
      `<tr class="ix-row" data-ix-idx="${i}">` +
      `<td><span class="ix-type-pill ix-type-${ix.type}">${IX_TYPE_LABELS[ix.type] || ix.type}</span></td>` +
      `<td>${escapeHtml(ix.resname_a)} ${ix.chain_a}${ix.resnum_a}</td>` +
      `<td>${escapeHtml(ix.resname_b)} ${ix.chain_b}${ix.resnum_b}</td>` +
      `<td>${ix.distance_angstrom.toFixed(2)}</td>` +
      `<td class="ix-detail">${escapeHtml(ix.detail || `${ix.atom_a} ↔ ${ix.atom_b}`)}</td>` +
      `</tr>`
    ).join("") +
    `</tbody></table>`;

  tableEl.querySelectorAll(".ix-row").forEach((row) => {
    row.addEventListener("click", () => {
      const idx = parseInt(row.dataset.ixIdx, 10);
      focusInteractionInViewer(filtered[idx]);
      tableEl.querySelectorAll(".ix-row").forEach((r) => r.classList.remove("ix-row-active"));
      row.classList.add("ix-row-active");
    });
  });
}

function focusInteractionInViewer(ix) {
  if (!interfaceViewer || !ix) return;
  const mid = {
    x: (ix.coord_a[0] + ix.coord_b[0]) / 2,
    y: (ix.coord_a[1] + ix.coord_b[1]) / 2,
    z: (ix.coord_a[2] + ix.coord_b[2]) / 2,
  };
  interfaceViewer.zoomTo({ center: mid, radius: 7 });
  interfaceViewer.render();
}

function showInterfaceLoading(show) {
  document.getElementById("interfaceLoading")?.classList.toggle("hidden", !show);
}

function showInterfaceError(msg) {
  const el = document.getElementById("interfaceError");
  if (!el) return;
  if (msg) {
    el.textContent = msg;
    el.classList.remove("hidden");
  } else {
    el.textContent = "";
    el.classList.add("hidden");
  }
}

function hideInterfaceContent() {
  document.getElementById("interfaceContent")?.classList.add("hidden");
  document.getElementById("interfaceViewer3d").innerHTML = "";
  document.getElementById("interfaceViewerOverlay")?.classList.add("hidden");
  interfaceViewer = null;
  loadedInterfaceJobId = null;
}

function renderInterfacePanel(data) {
  showInterfaceLoading(false);
  const content = document.getElementById("interfaceContent");
  if (!content) return;

  const primary = data?.primary_interface;
  if (!data || data.error) {
    showInterfaceError(data?.error || "无法分析结合界面");
    hideInterfaceContent();
    return;
  }
  if (!primary || !primary.contact_pairs) {
    showInterfaceError("未检测到链间接触（可能为单链或链间距过大）");
    hideInterfaceContent();
    return;
  }

  showInterfaceError("");
  content.classList.remove("hidden");

  const methodEl = document.getElementById("interfaceMethod");
  if (methodEl) {
    methodEl.textContent = data.method ||
      `${primary.label_a} ↔ ${primary.label_b} · 非共价相互作用分析`;
  }

  const ixSum = primary.interaction_summary || {};
  const summary = document.getElementById("interfaceSummary");
  if (summary) {
    const extraIx = (ixSum.n_pi_stacking ?? 0) + (ixSum.n_water_bridges ?? 0) + (ixSum.n_polar_contacts ?? 0);
    summary.innerHTML = [
      ["pDockQ", primary.pdockq?.toFixed(3)],
      ["PLIP 相互作用", String(ixSum.n_total ?? primary.interactions?.length ?? 0)],
      ["氢键", String(ixSum.n_hbonds ?? 0)],
      ["盐桥", String(ixSum.n_salt_bridges ?? 0)],
      ["疏水", String(ixSum.n_hydrophobic ?? 0)],
      ["π/水桥等", String(extraIx)],
      [`${primary.label_a || primary.chain_a} 界面残基`, String(primary.residues_a?.length || 0)],
      [`${primary.label_b || primary.chain_b} 界面残基`, String(primary.residues_b?.length || 0)],
    ].map(([lbl, val]) =>
      `<div class="interface-stat"><div class="val">${val}</div><div class="lbl">${escapeHtml(lbl)}</div></div>`
    ).join("");
  }

  interfaceIxFilter = "all";
  renderInteractionLegend();
  renderInteractionTable(primary);

  const refEl = document.getElementById("interfaceRefTools");
  if (refEl && data.reference_tools?.length) {
    refEl.innerHTML =
      "参考工具：" +
      data.reference_tools.map((t) => `<a href="${escapeHtml(t.url)}" target="_blank" rel="noopener">${escapeHtml(t.name)}</a>`).join(" · ");
  }
}

async function loadInterfaceViewer(jobId, cifText, data) {
  const primary = data?.primary_interface;
  if (!primary || !primary.contact_pairs || !cifText) return;

  try {
    await load3DmolLib();
    const elem = document.getElementById("interfaceViewer3d");
    if (!elem) return;
    elem.innerHTML = "";
    interfaceCifTextCache = cifText;
    interfaceViewer = $3Dmol.createViewer(elem, { backgroundColor: "0xf8fafc" });
    interfaceViewer.addModel(cifText, "cif");

    const focusSelections = paintInterfaceViewer(interfaceViewer, primary, data.chains || []);
    renderInterfaceViewerOverlay(data, primary);

    if (focusSelections.length) {
      interfaceViewer.zoomTo({ or: focusSelections });
      interfaceViewer.zoom(1.12);
    } else {
      interfaceViewer.zoomTo();
    }
    interfaceViewer.render();
    loadedInterfaceJobId = jobId;
  } catch (e) {
    console.error("interface viewer", e);
  }
}

function refreshMainViewerStyles() {
  if (!viewer) return;
  const mode = document.getElementById("viewerColorMode")?.value || "chain";
  viewer.removeAllLabels();
  if (selectedSeqResidues.size) {
    applyPyMOLSelectionView(viewer, mode, interfaceDataCache?.chains || []);
  } else {
    applyViewerStyles(viewer, mode, interfaceDataCache?.chains || []);
  }
  document.getElementById("plddtLegend")?.classList.toggle("hidden", mode !== "plddt");
  renderChainLegend(interfaceDataCache?.chains || []);
  document.getElementById("chainLegend")?.classList.toggle("hidden", mode === "plddt" || !(interfaceDataCache?.chains?.length));
  viewer.render();
}

async function loadStructure3D(jobId) {
  try {
    showViewerPlaceholder("正在加载 3D 结构…", true);
    hideInterfaceContent();
    showInterfaceError("");
    await load3DmolLib();
    const token = getToken();
    const structResp = await fetch(`/api/jobs/${jobId}/structure`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!structResp.ok) {
      const err = await structResp.json().catch(() => ({}));
      throw new Error(err.detail || `无法加载结构 (${structResp.status})`);
    }
    const text = await structResp.text();
    structureCifText = text;

    const elem = document.getElementById("viewer3d");
    elem.innerHTML = "";
    viewer = $3Dmol.createViewer(elem, { backgroundColor: "0xeef2f7" });
    viewer.addModel(text, "cif");
    bindViewerResiduePick(viewer);

    const mode = document.getElementById("viewerColorMode")?.value || "chain";
    document.getElementById("plddtLegend")?.classList.toggle("hidden", mode !== "plddt");
    if (mode === "plddt") {
      applyPlddtStyle(viewer);
    }
    viewer.zoomTo();
    viewer.render();
    loadedStructureJobId = jobId;

    await loadInterfaceForJob(jobId, text, { status: "done", chains_json: { a: 1, b: 1 } });
    if (selectedSeqResidues.size && viewer) {
      refreshMainViewerStyles();
    }
  } catch (e) {
    loadedStructureJobId = null;
    structureCifText = null;
    interfaceDataCache = null;
    hideInterfaceContent();
    showInterfaceError(e.message || "3D 加载失败");
    showViewerPlaceholder(e.message || "3D 加载失败");
  }
}

function hideInterfaceViewer() {
  hideInterfaceContent();
  showInterfaceLoading(false);
}

function clearViewer(resetLoaded = true) {
  document.getElementById("viewer3d").innerHTML = "";
  document.getElementById("plddtLegend").classList.add("hidden");
  document.getElementById("chainLegend")?.classList.add("hidden");
  document.getElementById("interfaceSection")?.classList.add("hidden");
  viewer = null;
  structureCifText = null;
  interfaceDataCache = null;
  clearSequenceResidueSelection();
  hideInterfaceViewer();
  showInterfaceError("");
  if (resetLoaded) {
    loadedStructureJobId = null;
    loadedInterfaceJobId = null;
  }
}

function pollIntervalMs() {
  if (selectedBatchId && batchJobsTotal > 200) return 10000;
  if (selectedBatchId && batchJobsTotal > 50) return 8000;
  return 5000;
}

function restartPollingTimer() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
  startPolling();
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    await refreshFoldTasks();
    if (currentModule === "md") await loadMdJobs();
    if (selectedBatchId && currentModule === "fold") {
      try {
        await refreshBatchPanel();
      } catch (e) { /* ignore */ }
    }
    if (selectedMdJobId) {
      try {
        const j = await api(`/api/md-jobs/${selectedMdJobId}`);
        renderMdDetail(j);
      } catch (e) {
        selectedMdJobId = null;
        document.getElementById("mdDetailPanel").classList.add("hidden");
        document.getElementById("detailEmpty").classList.remove("hidden");
      }
    }
    if (selectedJobId) {
      try {
        const j = await api(`/api/jobs/${selectedJobId}`);
        renderJobDetail(j);
        if (!["queued", "running"].includes(j.status)) {
          const anyActive =
            document.querySelector("#foldTaskList .status-queued, #foldTaskList .status-running") ||
            document.querySelector("#mdJobList .status-queued, #mdJobList .status-running");
          if (!anyActive) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      } catch (e) {
        selectedJobId = null;
        loadedStructureJobId = null;
        clearViewer();
        document.getElementById("detailPanel").classList.add("hidden");
        document.getElementById("detailEmpty").classList.remove("hidden");
      }
    }
  }, pollIntervalMs());
}

function renderMdStageBar(stage, status) {
  const steps = ["prep", "topo", "equil", "prod", "analysis", "done"];
  const current = stage || "queued";
  const currentIdx = steps.indexOf(current);
  return steps
    .map((s, i) => {
      let cls = "md-stage-pill";
      if (status === "done" || i < currentIdx) cls += " done";
      else if (s === current || (current === "queued" && s === "prep" && status === "running")) cls += " active";
      return `<span class="${cls}">${MD_STAGE_LABELS[s] || s}</span>`;
    })
    .join("");
}

async function loadMdParentOptions() {
  const sel = document.getElementById("mdParentJob");
  if (!sel) return;
  try {
    const data = await api("/api/jobs?limit=100&singles_only=true");
    const done = data.items.filter((j) => j.status === "done" && isFoldEngine(j.engine));
    const cur = sel.value;
    sel.innerHTML =
      '<option value="">— 选择折叠任务 —</option>' +
      done
        .map((j) => {
          const label = j.name || j.id.slice(0, 8);
          const iptm = j.iptm != null ? ` ipTM=${j.iptm.toFixed(2)}` : "";
          return `<option value="${j.id}">${escapeHtml(label)}${iptm}</option>`;
        })
        .join("");
    if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
  } catch (e) {
    console.error(e);
  }
}

async function loadMdJobs() {
  const list = document.getElementById("mdJobList");
  if (!list) return;
  try {
    const data = await api("/api/md-jobs?limit=50");
    if (!data.items.length) {
      list.innerHTML = '<div class="empty-state">暂无 MD 任务</div>';
      return;
    }
    list.innerHTML = data.items.map(renderMdJobItem).join("");
    list.querySelectorAll(".md-job-item").forEach((el) => {
      el.addEventListener("click", () => selectMdJob(el.dataset.id));
    });
    list.querySelectorAll(".md-job-delete-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteMdJob(btn.dataset.id, btn.dataset.name);
      });
    });
    const active = data.items.find((j) => ["queued", "running"].includes(j.status));
    if (active && !pollTimer) startPolling();
  } catch (e) {
    console.error(e);
  }
}

function renderMdJobItem(j) {
  const title = j.name || j.id.slice(0, 8);
  const stage = j.stage ? ` · ${MD_STAGE_LABELS[j.stage] || j.stage}` : "";
  const active = j.id === selectedMdJobId ? " active" : "";
  const time = j.created_at
    ? new Date(j.created_at).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "";
  return `<div class="job-item task-item md-job-item${active}" data-id="${j.id}">
    <div class="job-item-top">
      <div class="title"><span class="task-kind-badge kind-md">MD</span>${escapeHtml(title)}</div>
      <div class="job-item-actions">
        ${statusBadge(j.status)}
        <button class="job-delete-btn md-job-delete-btn" data-id="${j.id}" data-name="${escapeHtml(title)}" type="button" title="删除">×</button>
      </div>
    </div>
    <div class="meta">GROMACS MD${stage}${time ? ` · ${time}` : ""}</div>
  </div>`;
}

async function selectMdJob(id) {
  selectedMdJobId = id;
  selectedJobId = null;
  selectedBatchId = null;
  setModule("md");
  document.getElementById("detailPanel").classList.add("hidden");
  document.getElementById("batchPanel").classList.add("hidden");
  document.querySelectorAll(".md-job-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  document.querySelectorAll(".task-item:not(.md-job-item)").forEach((el) => el.classList.remove("active"));
  try {
    const j = await api(`/api/md-jobs/${id}`);
    renderMdDetail(j);
  } catch (e) {
    alert(e.message);
  }
}

function renderMdDetail(j) {
  document.getElementById("detailEmpty").classList.add("hidden");
  document.getElementById("detailPanel").classList.add("hidden");
  document.getElementById("batchPanel").classList.add("hidden");
  document.getElementById("mdDetailPanel").classList.remove("hidden");

  document.getElementById("mdDetailTitle").textContent = j.name || j.id;
  const params = j.params_json || {};
  document.getElementById("mdDetailMeta").textContent = [
    `${params.production_ns ?? "?"} ns × ${params.replicas ?? "?"} 复本`,
    params.antigen_chain && params.binder_chain ? `链 ${params.binder_chain}+${params.antigen_chain}` : null,
    j.parent_job_id ? `来源折叠 ${j.parent_job_id.slice(0, 8)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const statusEl = document.getElementById("mdDetailStatus");
  statusEl.className = `status-badge status-${j.status}`;
  statusEl.textContent = statusLabel(j.status);

  document.getElementById("mdStageBar").innerHTML = renderMdStageBar(j.stage, j.status);

  const metrics = [
    ["阶段", MD_STAGE_LABELS[j.stage] || j.stage || "—", false],
    ["生产 (ns)", params.production_ns, false],
    ["复本数", params.replicas, false],
    ["耗时", j.runtime_seconds != null ? `${Math.round(j.runtime_seconds)}s` : null, false],
  ];
  document.getElementById("mdMetricsGrid").innerHTML = metrics
    .map(([lbl, val]) => {
      const display = val != null ? val : "—";
      return `<div class="metric"><div class="val">${display}</div><div class="lbl">${lbl}</div></div>`;
    })
    .join("");

  const errBox = document.getElementById("mdErrorBox");
  if (j.error_message) {
    errBox.textContent = j.error_message;
    errBox.classList.remove("hidden");
  } else {
    errBox.classList.add("hidden");
  }

  const summaryBox = document.getElementById("mdSummaryBox");
  if (j.results_json) {
    summaryBox.textContent = JSON.stringify(j.results_json, null, 2);
  } else if (j.status === "running") {
    summaryBox.textContent = "模拟进行中，完成后将显示界面分析摘要…";
  } else {
    summaryBox.textContent = "暂无分析结果";
  }

  document.getElementById("mdDeleteBtn").onclick = () => deleteMdJob(j.id, j.name || j.id);
}

async function submitMdJob() {
  const btn = document.getElementById("submitMdBtn");
  setButtonLoading(btn, true, "提交中…");
  try {
    const parentId = document.getElementById("mdParentJob").value;
    const name = document.getElementById("mdJobName").value.trim() || null;
    const production_ns = parseFloat(document.getElementById("mdProductionNs").value);
    const replicas = parseInt(document.getElementById("mdReplicas").value, 10);
    const antigen_chain = document.getElementById("mdAntigenChain").value.trim() || "A";
    const binder_chain = document.getElementById("mdBinderChain").value.trim() || "H";

    let job;
    if (mdUploadFile) {
      const fd = new FormData();
      fd.append("structure", mdUploadFile);
      if (name) fd.append("name", name);
      fd.append("production_ns", String(production_ns));
      fd.append("replicas", String(replicas));
      fd.append("antigen_chain", antigen_chain);
      fd.append("binder_chain", binder_chain);
      job = await api("/api/md-jobs/upload", { method: "POST", body: fd, headers: {} });
    } else if (parentId) {
      job = await api("/api/md-jobs", {
        method: "POST",
        body: JSON.stringify({
          parent_job_id: parentId,
          name,
          production_ns,
          replicas,
          antigen_chain,
          binder_chain,
        }),
      });
    } else {
      throw new Error("请选择已完成折叠任务或上传结构文件");
    }

    mdUploadFile = null;
    document.getElementById("mdFileName").textContent = "";
    setModule("md");
    await loadMdJobs();
    selectMdJob(job.id);
    startPolling();
  } catch (e) {
    alert(e.message);
  } finally {
    setButtonLoading(btn, false, "提交 MD 任务");
  }
}

async function startMdFromFoldJob(foldJobId, foldName) {
  setModule("md");
  const sel = document.getElementById("mdParentJob");
  if (sel) sel.value = foldJobId;
  const nameEl = document.getElementById("mdJobName");
  if (nameEl && !nameEl.value.trim()) nameEl.value = `md_${foldName || foldJobId.slice(0, 8)}`;
  await submitMdJob();
}

async function deleteMdJob(jobId, jobName) {
  const label = jobName || jobId.slice(0, 8);
  if (!confirm(`确定删除 MD 任务「${label}」吗？`)) return;
  try {
    await api(`/api/md-jobs/${jobId}`, { method: "DELETE" });
    if (selectedMdJobId === jobId) {
      selectedMdJobId = null;
      document.getElementById("mdDetailPanel").classList.add("hidden");
      document.getElementById("detailEmpty").classList.remove("hidden");
    }
    await loadMdJobs();
  } catch (e) {
    alert(e.message || "删除失败");
  }
}

function initMdPanel() {
  const fileInput = document.getElementById("mdStructureFile");
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      mdUploadFile = file || null;
      document.getElementById("mdFileName").textContent = file ? file.name : "";
      if (file) document.getElementById("mdParentJob").value = "";
      fileInput.value = "";
    });
  }
  const parentSel = document.getElementById("mdParentJob");
  if (parentSel) {
    parentSel.addEventListener("change", () => {
      if (parentSel.value) {
        mdUploadFile = null;
        document.getElementById("mdFileName").textContent = "";
      }
    });
  }
}

function setHeavyTab(tab) {
  document.getElementById("heavyCsvPanel").classList.toggle("hidden", tab !== "csv");
  document.getElementById("heavyFastaPanel").classList.toggle("hidden", tab !== "fasta");
  document.querySelectorAll("[data-hc-tab]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.hcTab === tab);
  });
  updatePanelPreview();
}

function looksLikeSequence(raw) {
  const seq = raw.replace(/[\s\d]/g, "").toUpperCase();
  if (seq.length < 5) return false;
  return /^[ACDEFGHIKLMNPQRSTVWY]+$/.test(seq);
}

function formatHeavyChainDisplay(rows, fmt) {
  if (!rows.length) return "";
  if (fmt === "fasta") {
    return rows.map((r) => `>${r.id}\n${r.sequence}`).join("\n") + "\n";
  }
  return ["vhh_id,sequence", ...rows.map((r) => `${r.id},${r.sequence}`)].join("\n");
}

function parseHeavyChainText(text) {
  text = stripBom(text.trim());
  if (!text) return { rows: [], format: "csv" };
  if (text.trimStart().startsWith(">")) {
    return { rows: parseHeavyFastaClient(text), format: "fasta" };
  }

  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  let start = 0;
  const h = lines[0]?.toLowerCase() || "";
  if (h.includes("vhh_id") || h.includes("sequence") || h.includes("重链") || h.includes("序列")
      || h.startsWith("id,") || h.startsWith("id;") || h.startsWith("id\t")) {
    start = 1;
  }
  const rows = [];
  let autoIdx = 1;
  for (const line of lines.slice(start)) {
    const parts = splitCsvLine(line);
    if (parts.length >= 2) {
      const id = parts[0].trim().replace(/^"|"$/g, "");
      const seqRaw = (parts.length > 2 ? parts.slice(1).join(",") : parts[1]).trim().replace(/^"|"$/g, "");
      const sequence = seqRaw.replace(/\s/g, "").toUpperCase();
      if (id && looksLikeSequence(sequence)) rows.push({ id, sequence });
      continue;
    }
    const ws = line.match(/^(\S+)\s+([ACDEFGHIKLMNPQRSTVWY\s]+)$/i);
    if (ws) {
      const id = ws[1].trim();
      const sequence = ws[2].replace(/\s/g, "").toUpperCase();
      if (looksLikeSequence(sequence)) rows.push({ id, sequence });
      continue;
    }
    if (looksLikeSequence(line)) {
      rows.push({ id: `VHH_${String(autoIdx).padStart(3, "0")}`, sequence: line.replace(/\s/g, "").toUpperCase() });
      autoIdx += 1;
    }
  }
  return { rows, format: "csv" };
}

function parseHeavyCsvClient(text) {
  return parseHeavyChainText(text).rows;
}

function parseHeavyFastaClient(text) {
  const rows = [];
  let id = null;
  let parts = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith(">")) {
      if (id) rows.push({ id, sequence: parts.join("").toUpperCase() });
      id = line.slice(1).split(/\s/)[0];
      parts = [];
    } else {
      parts.push(line.replace(/\s/g, ""));
    }
  }
  if (id) rows.push({ id, sequence: parts.join("").toUpperCase() });
  return rows.filter((r) => r.sequence.length >= 5);
}

function getHeavyChainsFromForm() {
  const csvActive = !document.getElementById("heavyCsvPanel").classList.contains("hidden");
  if (csvActive) {
    return parseHeavyCsvClient(document.getElementById("heavyCsvInput").value);
  }
  return parseHeavyFastaClient(document.getElementById("heavyFastaInput").value);
}

function updatePanelPreview() {
  const el = document.getElementById("panelPreview");
  if (!el) return;
  const target = document.getElementById("targetSeq").value.trim();
  const chains = getHeavyChainsFromForm();
  const tname = document.getElementById("targetName").value.trim() || "靶点";
  if (!target || !chains.length) {
    el.textContent = "填写靶点序列与至少 1 条重链后将显示预览";
    return;
  }
  const engine = getSelectedFoldEngine(true);
  el.textContent = `将创建 ${chains.length} 个 ${tname} × 重链 复合物预测（${document.getElementById("heavyChainId").value || "H"}+${document.getElementById("targetChainId").value || "A"}）· ${engineLabel(engine)}${engine === "esmfold2" ? ` · ${formatEsmfoldParams(getEsmfoldParams(true))}` : ""}`;
}

async function submitVhhPanel() {
  const targetName = document.getElementById("targetName").value.trim();
  const targetSeq = document.getElementById("targetSeq").value.trim();
  const heavyChains = getHeavyChainsFromForm();
  if (!targetName) { alert("请填写靶点名称"); return; }
  if (!targetSeq) { alert("请填写抗原序列"); return; }
  if (!heavyChains.length) { alert("请提供至少一条重链（CSV 或 FASTA）"); return; }

  const msg = `确认提交批量预测？\n\n靶点：${targetName}\n重链数：${heavyChains.length}\n\n任务将依次排队运行。`;
  if (!confirm(msg)) return;

  const btn = document.getElementById("submitPanelBtn");
  setButtonLoading(btn, true, "提交中…");
  try {
    const engine = getSelectedFoldEngine(true);
    const body = {
      batch_name: document.getElementById("batchName").value.trim() || null,
      target: {
        name: targetName,
        chain_id: document.getElementById("targetChainId").value.trim() || "A",
        sequence: targetSeq.replace(/\s/g, ""),
      },
      heavy_chain_id: document.getElementById("heavyChainId").value.trim() || "H",
      heavy_chains: heavyChains,
      engine,
      use_msa_server: engine === "boltz2",
    };
    if (engine === "esmfold2") body.esmfold_params = getEsmfoldParams(true);
    const data = await api("/api/batches/vhh-panel", { method: "POST", body: JSON.stringify(body) });
    let note = `已创建批次「${data.batch.name}」，共 ${data.job_ids.length} 个任务。`;
    if (data.skipped_duplicates) note += `\n（跳过 ${data.skipped_duplicates} 条重复序列）`;
    alert(note);
    document.getElementById("heavyCsvInput").value = "";
    document.getElementById("heavyFastaInput").value = "";
    updatePanelPreview();
    await refreshFoldTasks();
    startPolling();
    selectBatch(data.batch.id);
  } catch (e) {
    alert(e.message || "提交失败");
  } finally {
    setButtonLoading(btn, false, "开始批量预测");
  }
}

async function selectBatch(id, silent) {
  selectedBatchId = id;
  selectedMdJobId = null;
  if (!silent) {
    selectedJobId = null;
    jobDetailReturnContext = null;
    batchJobsPage = 0;
    setModule("fold");
  }
  document.getElementById("mdDetailPanel").classList.add("hidden");
  document.querySelectorAll(".task-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.kind === "batch" && el.dataset.id === id);
  });
  try {
    const b = await api(`/api/batches/${id}`);
    batchDetailCache = b;
    renderBatchDetailHeader(b);
    await loadBatchJobsPage(id, silent ? batchJobsPage : 0);
    if (!silent) {
      document.getElementById("detailPanel").classList.add("hidden");
    }
    restartPollingTimer();
  } catch (e) {
    if (!silent) alert(e.message);
  }
}

async function refreshBatchPanel() {
  if (!selectedBatchId) return;
  const b = await api(`/api/batches/${selectedBatchId}`);
  batchDetailCache = b;
  updateBatchProgress(b);
  if (batchJobsPage === 0) {
    await loadBatchJobsPage(selectedBatchId, 0);
  }
}

function renderBatchDetailHeader(b) {
  document.getElementById("detailEmpty").classList.add("hidden");
  document.getElementById("detailPanel").classList.add("hidden");
  document.getElementById("mdDetailPanel").classList.add("hidden");
  document.getElementById("batchPanel").classList.remove("hidden");

  document.getElementById("batchTitle").textContent = b.name;
  document.getElementById("batchMeta").textContent =
    `靶点 ${b.target_name}（${b.target_chain_id}，${b.target_sequence.length} aa）· 重链链 ID ${b.heavy_chain_id} · 提交于 ${new Date(b.created_at).toLocaleString("zh-CN")}`;

  updateBatchProgress(b);
}

function updateBatchProgress(b) {
  const st = document.getElementById("batchStatus");
  st.className = `status-badge status-${b.status === "partial" ? "running" : b.status}`;
  st.textContent = BATCH_STATUS_LABELS[b.status] || b.status;

  const total = b.heavy_chain_count;
  const pct = total ? Math.round((b.done_count / total) * 100) : 0;
  document.getElementById("batchProgress").innerHTML =
    `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>` +
    `<p class="hint">进度 ${b.done_count}/${total} 完成 · 运行 ${b.running_count} · 排队 ${b.queued_count} · 失败 ${b.failed_count}</p>`;
}

async function loadBatchJobsPage(batchId, page) {
  const offset = page * BATCH_JOBS_PAGE_SIZE;
  const data = await api(`/api/batches/${batchId}/jobs?limit=${BATCH_JOBS_PAGE_SIZE}&offset=${offset}`);
  batchJobsPage = page;
  const prevTotal = batchJobsTotal;
  batchJobsTotal = data.total;
  renderBatchJobsTable(data.items);
  renderBatchPager();
  if (prevTotal !== batchJobsTotal) restartPollingTimer();
  return data;
}

async function goBatchJobsPage(page) {
  if (!selectedBatchId || page < 0) return;
  const totalPages = Math.ceil(batchJobsTotal / BATCH_JOBS_PAGE_SIZE);
  if (page >= totalPages) return;
  try {
    await loadBatchJobsPage(selectedBatchId, page);
  } catch (e) {
    alert(e.message);
  }
}

function renderBatchPager() {
  const el = document.getElementById("batchJobsPager");
  if (!el) return;
  if (batchJobsTotal <= BATCH_JOBS_PAGE_SIZE) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.classList.remove("hidden");
  const start = batchJobsPage * BATCH_JOBS_PAGE_SIZE + 1;
  const end = Math.min((batchJobsPage + 1) * BATCH_JOBS_PAGE_SIZE, batchJobsTotal);
  const totalPages = Math.ceil(batchJobsTotal / BATCH_JOBS_PAGE_SIZE);
  el.innerHTML =
    `<button type="button" class="btn btn-secondary btn-sm" id="batchJobsPrev" ${batchJobsPage <= 0 ? "disabled" : ""}>上一页</button>` +
    `<span class="batch-pager-info">第 ${batchJobsPage + 1}/${totalPages} 页 · ${start}–${end} / ${batchJobsTotal}</span>` +
    `<button type="button" class="btn btn-secondary btn-sm" id="batchJobsNext" ${batchJobsPage >= totalPages - 1 ? "disabled" : ""}>下一页</button>`;
  document.getElementById("batchJobsPrev")?.addEventListener("click", () => goBatchJobsPage(batchJobsPage - 1));
  document.getElementById("batchJobsNext")?.addEventListener("click", () => goBatchJobsPage(batchJobsPage + 1));
}

function renderBatchJobsTable(jobs) {
  const tbody = document.getElementById("batchJobsBody");
  tbody.innerHTML = jobs.map((j) => {
    const iptm = j.iptm != null ? j.iptm.toFixed(3) : "—";
    const pdockq = j.pdockq != null ? j.pdockq.toFixed(3) : "—";
    const plddt = j.complex_plddt != null ? j.complex_plddt.toFixed(3) : "—";
    const conf = j.confidence_score != null ? j.confidence_score.toFixed(3) : "—";
    const sec = j.runtime_seconds != null ? `${Math.round(j.runtime_seconds)}s` : "—";
    const active = j.id === selectedJobId ? " batch-row active" : " batch-row";
    return `<tr class="${active.trim()}" data-id="${j.id}">
      <td><strong>${escapeHtml(j.heavy_chain_id || j.name || "—")}</strong></td>
      <td>${statusBadge(j.status)}</td>
      <td class="num">${iptm}</td>
      <td class="num">${pdockq}</td>
      <td class="num">${plddt}</td>
      <td class="num">${conf}</td>
      <td class="num">${sec}</td>
      <td><button type="button" class="btn btn-secondary btn-sm batch-view-btn" data-id="${j.id}">查看</button></td>
    </tr>`;
  }).join("");
}

function updateJobDetailBackButton() {
  const bar = document.getElementById("detailBackBar");
  const btn = document.getElementById("backFromJobBtn");
  if (!bar || !btn) return;
  const ctx = jobDetailReturnContext;
  if (ctx?.type === "batch" && batchDetailCache) {
    bar.classList.remove("hidden");
    btn.textContent = `← 返回批次「${batchDetailCache.name}」`;
  } else {
    bar.classList.add("hidden");
  }
}

async function backFromJobDetail() {
  const ctx = jobDetailReturnContext;
  if (!ctx || ctx.type !== "batch") return;
  const batchId = ctx.batchId;
  const page = ctx.page || 0;
  jobDetailReturnContext = null;
  selectedJobId = null;
  loadedStructureJobId = null;
  clearViewer();
  document.getElementById("detailPanel").classList.add("hidden");
  document.getElementById("sequencePanel")?.classList.add("hidden");
  await selectBatch(batchId);
  if (page > 0) {
    await goBatchJobsPage(page);
  }
}

function viewBatchJob(jobId) {
  if (selectedBatchId) {
    jobDetailReturnContext = {
      type: "batch",
      batchId: selectedBatchId,
      page: batchJobsPage,
    };
  }
  selectJob(jobId, { fromBatch: true });
}

async function exportBatchCsv(batchId, batchName) {
  const btn = document.getElementById("exportBatchBtn");
  setButtonLoading(btn, true, "导出中…");
  try {
    const data = await api(`/api/batches/${batchId}/jobs?limit=5000&offset=0`);
    const header = ["heavy_chain_id", "job_name", "status", "iptm", "pdockq", "pdockq2", "ptm", "complex_plddt", "confidence_score", "runtime_seconds", "job_id"];
    const lines = [header.join(",")];
    for (const j of data.items) {
      lines.push([
        j.heavy_chain_id || "",
        j.name || "",
        j.status,
        j.iptm ?? "",
        j.pdockq ?? "",
        j.pdockq2 ?? "",
        j.ptm ?? "",
        j.complex_plddt ?? "",
        j.confidence_score ?? "",
        j.runtime_seconds ?? "",
        j.id,
      ].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${batchName}_results.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert(e.message || "导出失败");
  } finally {
    setButtonLoading(btn, false, "导出 CSV");
  }
}

async function deleteBatch(batchId, batchName) {
  if (!confirm(`确定删除批次「${batchName}」吗？\n\n将删除该批次下全部任务及输出文件。`)) return;
  try {
    await api(`/api/batches/${batchId}`, { method: "DELETE" });
    if (selectedBatchId === batchId) {
      selectedBatchId = null;
      document.getElementById("batchPanel").classList.add("hidden");
      document.getElementById("detailEmpty").classList.remove("hidden");
    }
    await refreshFoldTasks();
  } catch (e) {
    alert(e.message || "删除失败");
  }
}

async function deleteBatch(batchId, batchName) {
  if (!confirm(`确定删除批次「${batchName}」吗？\n\n将删除该批次下全部任务及输出文件。`)) return;
  try {
    await api(`/api/batches/${batchId}`, { method: "DELETE" });
    if (selectedBatchId === batchId) {
      selectedBatchId = null;
      document.getElementById("batchPanel").classList.add("hidden");
      document.getElementById("detailEmpty").classList.remove("hidden");
    }
    await refreshFoldTasks();
  } catch (e) {
    alert(e.message || "删除失败");
  }
}

function initDetailPanel() {
  document.getElementById("backFromJobBtn")?.addEventListener("click", () => backFromJobDetail());
  document.getElementById("viewerColorMode")?.addEventListener("change", () => refreshMainViewerStyles());
  document.getElementById("clearSeqSelectionBtn")?.addEventListener("click", () => clearSequenceResidueSelection());
  document.getElementById("sequenceChains")?.addEventListener("click", (e) => {
    const cell = e.target.closest(".res-cell[data-chain-id][data-resi]");
    if (!cell) return;
    selectSequenceResidue(cell.dataset.chainId, cell.dataset.resi, cell, e);
  });
}

function initBatchPanel() {
  document.getElementById("deleteBatchBtn")?.addEventListener("click", () => {
    if (batchDetailCache) deleteBatch(batchDetailCache.id, batchDetailCache.name);
  });
  document.getElementById("exportBatchBtn")?.addEventListener("click", () => {
    if (batchDetailCache) exportBatchCsv(batchDetailCache.id, batchDetailCache.name);
  });
  document.getElementById("batchJobsBody")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".batch-view-btn");
    if (btn?.dataset.id) {
      viewBatchJob(btn.dataset.id);
    }
  });
}

function initVhhPanel() {
  ["targetName", "targetSeq", "targetChainId", "heavyChainId", "batchName", "heavyCsvInput", "heavyFastaInput"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", updatePanelPreview);
  });
  const hf = document.getElementById("heavyCsvFile");
  if (hf) {
    hf.addEventListener("change", async () => {
      const file = hf.files?.[0];
      if (!file) return;
      try {
        const data = await importHeavyChainFile(file);
        applyHeavyChainImport(data, file.name);
      } catch (e) {
        alert(e.message || "CSV 读取失败");
      }
      hf.value = "";
    });
  }
}

const EXAMPLE_FASTA = `>H
DVQLVESGGGSVQAGGSLRLSCAASGYIASINYLGWFRQAPGKEREGVAAVSPAGGTPYYADSVKGRFTVSLDNAENTVYLQMNSLKPEDTALYYCAAARQGWYIPLNSYGYNYWGQGTQVTVSSRGRHHHHHH
>A
KVFGRCELAAAMKRHGLDNYRGYSLGNWVCAAKFESNFNTQATNRNTDGSTDYGILQINSRWWCNDGRTPGSRNLCNIPCSALLSSDITASVNCAKKIVSDGNGMNAWVAWRNRCKGTDVQAWIRGCRL`;

document.addEventListener("DOMContentLoaded", () => {
  setAuthTab("login");
  initFastaUpload();
  initDetailPanel();
  initBatchPanel();
  initVhhPanel();
  initMdPanel();
  onFoldEngineChange();
  onPanelEngineChange();
  bootstrapSession();
});

async function bootstrapSession() {
  if (!getToken()) {
    showAuth();
    return;
  }
  showApp();
  try {
    await api("/api/auth/me");
  } catch (e) {
    if (getToken()) clearAuth();
    showAuth();
  }
}
