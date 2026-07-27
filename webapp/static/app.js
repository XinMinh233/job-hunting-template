const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let csrf = sessionStorage.getItem("csrf") || "";
let currentChat = null;
let currentJob = null;
let eventSource = null;
let submittingPrompt = false;
let composingPrompt = false;

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

function setComposerEnabled(enabled) {
  $("#prompt").disabled = !enabled;
  $("#composer button").disabled = !enabled;
}

function renderWelcome() {
  const content = $("#welcome-template").content.cloneNode(true);
  $("#messages").replaceChildren(content);
}

function showNewChatState({clearPrompt = true, focus = false} = {}) {
  currentChat = null;
  $("#chat-title").textContent = "开始一段求职工作";
  $("#job-status").textContent = "选择一个命令，或直接输入消息";
  $("#stop-job").hidden = true;
  if (clearPrompt) $("#prompt").value = "";
  setComposerEnabled(!currentJob && !submittingPrompt);
  renderWelcome();
  if (focus) $("#prompt").focus();
}

function messagesNearBottom() {
  const messages = $("#messages");
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 120;
}

function scrollMessagesToBottom() {
  const messages = $("#messages");
  requestAnimationFrame(() => {
    messages.scrollTop = messages.scrollHeight;
  });
}

function renderAssistantContent(body, content, defer = false) {
  body._markdownSource = content;
  if (!defer) {
    if (body._markdownFrame) cancelAnimationFrame(body._markdownFrame);
    body._markdownFrame = null;
    window.JobHuntMarkdown.render(body, content);
    return;
  }

  body._followMessages = body._followMessages || messagesNearBottom();
  if (body._markdownFrame) return;
  body._markdownFrame = requestAnimationFrame(() => {
    const follow = body._followMessages;
    body._markdownFrame = null;
    body._followMessages = false;
    window.JobHuntMarkdown.render(body, body._markdownSource);
    if (follow) scrollMessagesToBottom();
  });
}

function addMessage(role, content, pending = false) {
  $(".empty-state")?.remove();
  const article = document.createElement("article");
  article.className = `message ${role}${pending ? " pending" : ""}`;
  const label = document.createElement("span");
  label.textContent = role === "user" ? "你" : "Claude";
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant" && !pending) {
    renderAssistantContent(body, content);
  } else {
    body.textContent = content;
  }
  article.append(label, body);
  $("#messages").append(article);
  scrollMessagesToBottom();
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
    const row = document.createElement("div");
    row.className = `chat-list-item${chat.id === currentChat ? " active" : ""}`;
    const selectButton = document.createElement("button");
    selectButton.className = "chat-select";
    selectButton.textContent = chat.title;
    selectButton.title = chat.title;
    selectButton.addEventListener("click", () => selectChat(chat));
    const archiveButton = document.createElement("button");
    archiveButton.className = "chat-archive";
    archiveButton.type = "button";
    archiveButton.textContent = "×";
    archiveButton.title = `删除会话：${chat.title}`;
    archiveButton.setAttribute("aria-label", `删除会话：${chat.title}`);
    archiveButton.addEventListener("click", () => archiveChat(chat));
    row.append(selectButton, archiveButton);
    list.append(row);
  }
  const selectedChat = chats.find((chat) => chat.id === currentChat);
  if (selectedChat) {
    $("#chat-title").textContent = selectedChat.title;
  } else if (selectFirst && !currentChat && chats.length) {
    await selectChat(chats[0]);
  } else if (!currentChat) {
    showNewChatState({clearPrompt: false});
  } else {
    showNewChatState();
  }
}

async function newChat() {
  if (currentJob || submittingPrompt) {
    toast("请等待当前任务结束后再新建会话");
    return;
  }
  showNewChatState({focus: true});
  await loadChats(false);
  if (innerWidth < 900) $(".sidebar").classList.remove("open");
}

async function archiveChat(chat) {
  if (chat.active_job_id || (currentJob && chat.id === currentChat)) {
    toast("运行中的会话不能删除");
    return;
  }
  const confirmed = await window.JobHuntDialog.ask({
    eyebrow: "DELETE CHAT",
    title: "删除这段会话？",
    message: `会话“${chat.title}”将从列表中移除，已经生成的文件不会删除。`,
    confirmLabel: "删除会话",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api(`/api/chats/${chat.id}/archive`, {method: "POST"});
    if (chat.id === currentChat) showNewChatState({focus: true});
    await loadChats(false);
    toast("会话已删除");
  } catch (exc) {
    toast(exc.message);
  }
}

async function selectChat(chat) {
  if (submittingPrompt) return;
  if (currentJob && chat.id !== currentChat) {
    toast("请等待当前任务结束后再切换会话");
    return;
  }
  currentChat = chat.id;
  currentJob = chat.active_job_id || null;
  $("#chat-title").textContent = chat.title;
  $("#job-status").textContent = chat.claude_session_id ? "已连接 Claude 会话" : "新的 Claude 会话";
  setComposerEnabled(!currentJob);
  const messages = await api(`/api/chats/${chat.id}/messages`);
  $("#messages").replaceChildren();
  if (!messages.length) {
    renderWelcome();
  }
  messages.forEach((item) => addMessage(item.role, item.content));
  if (chat.active_job_id) {
    $("#stop-job").hidden = false;
    const assistant = addMessage("assistant", "正在恢复任务进度…", true);
    streamJob(chat.active_job_id, assistant);
  } else {
    $("#stop-job").hidden = true;
  }
  await loadChats(false);
  if (innerWidth < 900) $(".sidebar").classList.remove("open");
}

async function sendPrompt(value) {
  if (currentJob || submittingPrompt || !value.trim()) return;
  const text = value.trim();
  let assistant = null;
  submittingPrompt = true;
  setComposerEnabled(false);
  try {
    if (!currentChat) {
      const chat = await api("/api/chats", {method: "POST", body: JSON.stringify({title: "新会话"})});
      currentChat = chat.id;
      $("#chat-title").textContent = chat.title;
      $("#job-status").textContent = "新的 Claude 会话";
      await loadChats(false);
    }
    $("#prompt").value = "";
    addMessage("user", text);
    assistant = addMessage("assistant", "正在排队…", true);
    const result = await api(`/api/chats/${currentChat}/messages`, {method: "POST", body: JSON.stringify({content: text})});
    currentJob = result.job_id;
    $("#stop-job").hidden = false;
    $("#job-status").textContent = "任务排队中";
    streamJob(result.job_id, assistant);
  } catch (exc) {
    if (assistant) {
      assistant.textContent = exc.message;
      assistant.parentElement.classList.add("error");
    } else {
      toast(exc.message);
    }
  } finally {
    submittingPrompt = false;
    setComposerEnabled(!currentJob);
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
        renderAssistantContent(body, text, true);
        body.parentElement.classList.remove("pending");
      } else if (type === "tool") {
        $("#job-status").textContent = data.message || "正在使用工具";
      } else if (type === "artifact") {
        toast("产生了新文件");
        await loadFiles();
      } else if (type === "done" || type === "error") {
        if (type === "error") {
          if (text) {
            renderAssistantContent(body, text);
          } else {
            body.classList.remove("markdown-body");
            body.textContent = data.message || "任务失败";
          }
          body.parentElement.classList.add("error");
        } else if (text) {
          renderAssistantContent(body, text);
        }
        body.parentElement.classList.remove("pending");
        eventSource.close();
        currentJob = null;
        $("#stop-job").hidden = true;
        setComposerEnabled(true);
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

function filePreviewUrl(path) {
  const suffix = path.includes(".") ? path.split(".").pop().toLowerCase() : "";
  if (["md", "markdown"].includes(suffix)) {
    return `/files/preview?path=${encodeURIComponent(path)}`;
  }
  if (["pdf", "html", "htm"].includes(suffix)) {
    return `/api/files/download?inline=true&path=${encodeURIComponent(path)}`;
  }
  return null;
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
    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = fileIcon(path);
    const metadata = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = path.split("/").pop();
    const fileSize = document.createElement("small");
    fileSize.textContent = size ? `${Math.ceil(size / 1024)} KB` : "";
    metadata.append(name, fileSize);
    const actions = document.createElement("div");
    actions.className = "file-actions";
    const previewUrl = filePreviewUrl(path);
    if (previewUrl) {
      const preview = document.createElement("a");
      preview.href = previewUrl;
      preview.target = "_blank";
      preview.rel = "noopener noreferrer";
      preview.textContent = "预览";
      actions.append(preview);
    }
    const download = document.createElement("a");
    download.href = `/api/files/download?path=${encodeURIComponent(path)}`;
    download.textContent = "下载";
    actions.append(download);
    row.append(icon, metadata, actions);
    list.append(row);
  }
}

$("#new-chat").addEventListener("click", newChat);
$("#composer").addEventListener("submit", (event) => { event.preventDefault(); sendPrompt($("#prompt").value); });
$("#prompt").addEventListener("compositionstart", () => { composingPrompt = true; });
$("#prompt").addEventListener("compositionend", () => { composingPrompt = false; });
$("#prompt").addEventListener("keydown", (event) => {
  if (
    event.key === "Enter"
    && !event.shiftKey
    && !event.isComposing
    && !composingPrompt
    && event.keyCode !== 229
  ) {
    event.preventDefault();
    sendPrompt(event.currentTarget.value);
  }
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

showNewChatState({clearPrompt: false});

(async () => {
  try {
    await loadMe();
    await Promise.all([loadChats(), loadUsage(), loadFiles()]);
  } catch (exc) {
    toast(exc.message);
  }
})();
