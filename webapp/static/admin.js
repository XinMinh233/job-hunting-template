const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
let csrf = sessionStorage.getItem("csrf") || "";

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 3000);
}

async function api(url, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(url, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { location.href = "/login"; throw new Error("请重新登录"); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || "请求失败");
  return data;
}

function shortId(value) { return value ? value.slice(0, 8) : "—"; }
function stateLabel(state) {
  return {queued: "排队", running: "运行中", completed: "完成", failed: "失败", cancelled: "已停止", interrupted: "中断"}[state] || state;
}

async function loadAll() {
  const me = await api("/api/auth/me");
  if (me.role !== "admin") { location.href = "/"; return; }
  csrf = me.csrf_token;
  sessionStorage.setItem("csrf", csrf);
  const [users, jobs, audits] = await Promise.all([api("/api/admin/users"), api("/api/admin/jobs"), api("/api/admin/audit")]);
  renderUsers(users);
  renderJobs(jobs);
  renderAudit(audits);
  $("#metric-users").textContent = users.length;
  $("#metric-active").textContent = users.filter((user) => user.is_active).length;
  $("#metric-jobs").textContent = jobs.filter((job) => ["queued", "running"].includes(job.state)).length;
}

function button(label, handler, className = "") {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = label;
  node.className = className;
  node.addEventListener("click", () => {
    Promise.resolve()
      .then(handler)
      .catch((error) => toast(error.message || "操作失败"));
  });
  return node;
}

function renderUsers(users) {
  const table = $("#users-table");
  table.replaceChildren();
  for (const user of users) {
    const row = document.createElement("tr");
    row.innerHTML = `<td><strong></strong><small></small></td><td><span class="badge"></span></td><td></td><td></td><td></td><td><div class="row-actions"></div></td>`;
    $("td strong", row).textContent = user.username;
    $("td small", row).textContent = user.role === "admin" ? "超级管理员" : user.linux_username || "待配置";
    const badge = $(".badge", row);
    badge.textContent = user.is_active ? "正常" : "已停用";
    badge.classList.add(user.is_active ? "success" : "muted-badge");
    row.children[2].textContent = `${user.jobs_today} 次 · ${user.tokens_today.toLocaleString()} token`;
    row.children[3].textContent = `${user.daily_job_limit} 次 · ${user.daily_token_limit.toLocaleString()}`;
    row.children[4].textContent = user.template_version;
    const actions = $(".row-actions", row);
    if (user.role !== "admin") {
      actions.append(
        button("额度", () => editQuota(user)),
        button("重置密码", () => resetPassword(user)),
        button("升级模板", () => upgrade(user)),
        user.is_active
          ? button("停用", () => disableUser(user), "danger-text")
          : button("启用", () => enableUser(user)),
      );
    }
    table.append(row);
  }
}

function renderJobs(jobs) {
  const table = $("#jobs-table");
  table.replaceChildren();
  for (const job of jobs.slice(0, 30)) {
    const row = document.createElement("tr");
    row.innerHTML = `<td><code></code></td><td><code></code></td><td><span class="badge"></span></td><td></td><td class="job-error"></td><td><div class="row-actions"></div></td>`;
    row.children[0].querySelector("code").textContent = shortId(job.id);
    row.children[1].querySelector("code").textContent = shortId(job.user_id);
    $(".badge", row).textContent = stateLabel(job.state);
    row.children[3].textContent = new Date(job.created_at).toLocaleString();
    row.children[4].textContent = job.error || "—";
    if (job.error) row.children[4].title = job.error;
    if (["queued", "running"].includes(job.state)) {
      $(".row-actions", row).append(button("停止", async () => {
        await api(`/api/admin/jobs/${job.id}/stop`, {method: "POST"});
        await loadAll();
      }, "danger-text"));
    }
    table.append(row);
  }
}

function renderAudit(items) {
  const list = $("#audit-list");
  list.replaceChildren();
  for (const item of items.slice(0, 50)) {
    const row = document.createElement("article");
    row.innerHTML = `<span></span><div><strong></strong><small></small></div><time></time>`;
    $("span", row).textContent = "·";
    $("strong", row).textContent = item.action;
    $("small", row).textContent = item.target || "system";
    $("time", row).textContent = new Date(item.created_at).toLocaleString();
    list.append(row);
  }
}

async function editQuota(user) {
  const values = await window.JobHuntDialog.collect({
    eyebrow: "EDIT QUOTA",
    title: `调整 ${user.username} 的额度`,
    message: "新额度会立即应用，不会清空用户今天已经产生的用量。",
    confirmLabel: "保存额度",
    fields: [
      {
        name: "daily_job_limit",
        label: "每日任务数",
        type: "number",
        min: 1,
        value: user.daily_job_limit,
      },
      {
        name: "daily_token_limit",
        label: "每日 Token",
        type: "number",
        min: 10000,
        value: user.daily_token_limit,
      },
    ],
  });
  if (!values) return;
  await api(`/api/admin/users/${user.id}/quota`, {
    method: "PUT",
    body: JSON.stringify({
      daily_job_limit: Number(values.daily_job_limit),
      daily_token_limit: Number(values.daily_token_limit),
    }),
  });
  await loadAll();
  toast("额度已更新");
}

async function resetPassword(user) {
  const confirmed = await window.JobHuntDialog.ask({
    eyebrow: "RESET PASSWORD",
    title: `重置 ${user.username} 的密码？`,
    message: "现有登录会话将失效，新临时密码只显示一次；用户下次登录必须修改密码。",
    confirmLabel: "重置密码",
    danger: true,
  });
  if (!confirmed) return;
  const result = await api(`/api/admin/users/${user.id}/reset-password`, {method: "POST", body: JSON.stringify({force_change: true})});
  showSecret(result.temporary_password);
}

async function disableUser(user) {
  const confirmed = await window.JobHuntDialog.ask({
    eyebrow: "DISABLE ACCOUNT",
    title: `停用 ${user.username}？`,
    message: "用户将无法继续登录，当前正在运行或排队的任务也会停止。",
    confirmLabel: "停用用户",
    danger: true,
  });
  if (!confirmed) return;
  await api(`/api/admin/users/${user.id}/disable`, {method: "POST"});
  await loadAll();
  toast("用户已停用");
}

async function enableUser(user) {
  await api(`/api/admin/users/${user.id}/enable`, {method: "POST"});
  await loadAll();
}

async function upgrade(user) {
  const confirmed = await window.JobHuntDialog.ask({
    eyebrow: "UPGRADE TEMPLATE",
    title: `升级 ${user.username} 的模板？`,
    message: "工作区必须保持干净。个人文件不会被覆盖，有冲突的模板文件将跳过并生成报告。",
    confirmLabel: "开始升级",
  });
  if (!confirmed) return;
  const result = await api(`/api/admin/users/${user.id}/upgrade-template`, {method: "POST"});
  toast(result.conflicts?.length ? `升级完成，跳过 ${result.conflicts.length} 个冲突文件` : "模板升级完成");
  await loadAll();
}

function showSecret(password) {
  $("#temporary-password").textContent = password;
  $("#secret-dialog").showModal();
}

$("#open-create").addEventListener("click", () => $("#create-dialog").showModal());
$$("[data-close]").forEach((node) => node.addEventListener("click", () => node.closest("dialog").close()));
$("#create-user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  const values = Object.fromEntries(new FormData(form));
  submit.disabled = true;
  let result;
  try {
    result = await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({username: values.username, daily_job_limit: Number(values.daily_job_limit), daily_token_limit: Number(values.daily_token_limit)}),
    });
  } catch (exc) {
    toast(exc.message);
    submit.disabled = false;
    return;
  }

  $("#create-dialog").close();
  form.reset();
  submit.disabled = false;
  showSecret(result.temporary_password);
  try {
    await loadAll();
  } catch (exc) {
    toast(`用户已创建，但列表刷新失败：${exc.message}`);
  }
});
$("#logout").addEventListener("click", async () => {
  await api("/api/auth/logout", {method: "POST"});
  sessionStorage.clear();
  location.href = "/login";
});

loadAll().catch((exc) => toast(exc.message));
