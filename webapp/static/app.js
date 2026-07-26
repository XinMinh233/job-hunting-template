const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let csrf = sessionStorage.getItem("csrf") || "";
let currentChat = null;
let currentJob = null;
let eventSource = null;

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2800);
}

async function api(url, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(url, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { location.href = "/login"; throw new Error("请重新登录"); }
  if (response.status === 403 && data.detail?.code === "password_change_required") {
    location.href = "/password"; throw new Error("请先修改密码");
  }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || "请求失败");
  return data;
}

function formatTokens(value) {
  return value >= 1000000 ? `${(value / 1000000).toFixed(1)}m` : value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
}

function addMessage(role, content, pending = false) {
  $(".empty-state")?.remove();
  const article = document.createElement("article");
  article.className = `message ${role}${pending ? " pending" : ""}`;
  const label = document.createElement("span");
  label.textContent = role === "user" ? "你" : "Claude";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = content;
  article.append(label, body);
  $("#messages").append(article);
  $("#messages").scrollTop = $("#messages").scrollHeight;
  return body;
}

async function loadMe() {
  const me = await api("/api/auth/me");
  csrf = me.csrf_token;
  sessionStorage.setItem("csrf", csrf);
  $("#current-user").textContent = me.username;
  $("#admin-link").hidden = me.role !== "admin";
  return me;
}

async function loadChats(selectFirst = true) {
  const chats = await api("/api/chats");
  const list = $("#chat-list");
  list.replaceChildren();
  for (const chat of chats) {
    const button = document.createElement("button");
    button.className = chat.id === currentChat ? "active" : "";
    button.textContent = chat.title;
    button.addEventListener("click", () => selectChat(chat));
    list.append(button);
  }
  if (selectFirst && !currentChat && chats.length) await selectChat(chats[0]);
}

async function newChat() {
  const chat = await api("/api/chats", {method: "POST", body: JSON.stringify({title: "新会话"})});
  currentChat = chat.id;
  await loadChats(false);
  await selectChat(chat);
}

async function selectChat(chat) {
  currentChat = chat.id;
  $("#chat-title").textContent = chat.title;
  $("#job-status").textContent = chat.claude_session_id ? "已连接 Claude 会话" : "新的 Claude 会话";
  $("#prompt").disabled = false;
  $("#composer button").disabled = false;
  const messages = await api(`/api/chats/${chat.id}/messages`);
  $("#messages").replaceChildren();
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state simple";
    empty.innerHTML = "<p class='eyebrow'>NEW CHAT</p><h2>从一个具体目标开始。</h2><p>描述职位、粘贴 JD，或输入 /onboard。</p>";
    $("#messages").append(empty);
  }
  messages.forEach((item) => addMessage(item.role, item.content));
  if (chat.active_job_id) {
    currentJob = chat.active_job_id;
    $("#stop-job").hidden = false;
    const assistant = addMessage("assistant", "正在恢复任务进度…", true);
    streamJob(chat.active_job_id, assistant);
  }
  await loadChats(false);
  if (innerWidth < 900) $(".sidebar").classList.remove("open");
}

async function sendPrompt(value) {
  if (!currentChat || currentJob || !value.trim()) return;
  const text = value.trim();
  $("#prompt").value = "";
  addMessage("user", text);
  const assistant = addMessage("assistant", "正在排队…", true);
  try {
    const result = await api(`/api/chats/${currentChat}/messages`, {method: "POST", body: JSON.stringify({content: text})});
    currentJob = result.job_id;
    $("#stop-job").hidden = false;
    $("#job-status").textContent = "任务排队中";
    streamJob(result.job_id, assistant);
  } catch (exc) {
    assistant.textContent = exc.message;
    assistant.parentElement.classList.add("error");
  }
}

function streamJob(jobId, body) {
  let text = "";
  eventSource?.close();
  eventSource = new EventSource(`/api/jobs/${jobId}/events`);
  for (const type of ["status", "text_delta", "tool", "artifact", "done", "error"]) {
    eventSource.addEventListener(type, async (event) => {
      const envelope = JSON.parse(event.data);
      const data = envelope.data || {};
      if (type === "status") {
        $("#job-status").textContent = data.message || data.state;
        if (!text) body.textContent = data.message || "处理中…";
      } else if (type === "text_delta") {
        if (!text) body.textContent = "";
        text += data.text || "";
        body.textContent = text;
        body.parentElement.classList.remove("pending");
      } else if (type === "tool") {
        $("#job-status").textContent = data.message || "正在使用工具";
      } else if (type === "artifact") {
        toast("产生了新文件");
        await loadFiles();
      } else if (type === "done" || type === "error") {
        if (type === "error") {
          body.textContent = text || data.message || "任务失败";
          body.parentElement.classList.add("error");
        }
        body.parentElement.classList.remove("pending");
        eventSource.close();
        currentJob = null;
        $("#stop-job").hidden = true;
        $("#job-status").textContent = type === "done" ? "任务完成" : "任务失败";
        await Promise.all([loadUsage(), loadFiles(), loadChats(false)]);
      }
    });
  }
  eventSource.onerror = () => {
    $("#job-status").textContent = "连接中断，正在重连…";
  };
}

async function loadUsage() {
  const usage = await api("/api/usage");
  $("#job-usage").textContent = `${usage.jobs} / ${usage.job_limit}`;
  $("#token-usage").textContent = `${formatTokens(usage.tokens)} / ${formatTokens(usage.token_limit)}`;
}

function fileIcon(name) {
  const suffix = name.split(".").pop().toUpperCase();
  return suffix.length <= 5 ? suffix : "FILE";
}

async function loadFiles() {
  const files = await api("/api/files");
  const list = $("#file-list");
  list.replaceChildren();
  if (!files.length) {
    list.innerHTML = "<p class='muted empty-files'>还没有文件。上传简历或让 Claude 生成产物。</p>";
    return;
  }
  for (const file of files) {
    const row = document.createElement("article");
    const path = typeof file === "string" ? file : file.relative_path;
    const size = typeof file === "string" ? "" : file.size;
    row.innerHTML = `<span class="file-icon">${fileIcon(path)}</span><div><strong></strong><small>${size ? `${Math.ceil(size / 1024)} KB` : ""}</small></div><div class="file-actions"><a target="_blank">预览</a><a>下载</a></div>`;
    $("strong", row).textContent = path.split("/").pop();
    const links = $$("a", row);
    links[0].href = `/api/files/download?inline=true&path=${encodeURIComponent(path)}`;
    links[1].href = `/api/files/download?path=${encodeURIComponent(path)}`;
    list.append(row);
  }
}

$("#new-chat").addEventListener("click", newChat);
$("#composer").addEventListener("submit", (event) => { event.preventDefault(); sendPrompt($("#prompt").value); });
$("#prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendPrompt(event.currentTarget.value); }
});
$("#messages").addEventListener("click", (event) => {
  const button = event.target.closest("[data-prompt]");
  if (button) { $("#prompt").value = button.dataset.prompt; $("#prompt").focus(); }
});
$("#stop-job").addEventListener("click", async () => {
  if (!currentJob) return;
  await api(`/api/jobs/${currentJob}/stop`, {method: "POST"});
});
$("#choose-file").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", async () => {
  const file = $("#file-input").files[0];
  if (!file) return;
  const data = new FormData();
  data.append("upload", file);
  try {
    const result = await api("/api/files/upload", {method: "POST", body: data});
    toast(result.message);
    await loadFiles();
  } catch (exc) { toast(exc.message); }
  $("#file-input").value = "";
});
$("#logout").addEventListener("click", async () => {
  await api("/api/auth/logout", {method: "POST"});
  sessionStorage.clear();
  location.href = "/login";
});
$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));

(async () => {
  try {
    await loadMe();
    await Promise.all([loadChats(), loadUsage(), loadFiles()]);
  } catch (exc) {
    toast(exc.message);
  }
})();
