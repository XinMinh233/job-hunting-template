const byId = (id) => document.getElementById(id);

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || "请求失败");
  return data;
}

const loginForm = byId("login-form");
if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = loginForm.querySelector("button");
    const error = byId("login-error");
    button.disabled = true;
    error.hidden = true;
    try {
      const values = Object.fromEntries(new FormData(loginForm));
      const data = await jsonRequest("/api/auth/login", {method: "POST", body: JSON.stringify(values)});
      sessionStorage.setItem("csrf", data.csrf_token);
      location.href = data.must_change_password ? "/password" : "/";
    } catch (exc) {
      error.textContent = exc.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
}

const passwordForm = byId("password-form");
if (passwordForm) {
  (async () => {
    try {
      const me = await jsonRequest("/api/auth/me");
      sessionStorage.setItem("csrf", me.csrf_token);
    } catch {
      location.href = "/login";
    }
  })();
  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(passwordForm));
    const error = byId("password-error");
    error.hidden = true;
    if (values.new_password !== values.confirmation) {
      error.textContent = "两次输入的新密码不一致";
      error.hidden = false;
      return;
    }
    try {
      await jsonRequest("/api/auth/change-password", {
        method: "POST",
        headers: {"X-CSRF-Token": sessionStorage.getItem("csrf") || ""},
        body: JSON.stringify({current_password: values.current_password, new_password: values.new_password}),
      });
      location.href = "/";
    } catch (exc) {
      error.textContent = exc.message;
      error.hidden = false;
    }
  });
}

