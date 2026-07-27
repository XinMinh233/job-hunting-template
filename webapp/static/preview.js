(() => {
  "use strict";

  const params = new URLSearchParams(location.search);
  const path = params.get("path") || "";
  const title = document.querySelector("#preview-title");
  const content = document.querySelector("#markdown-preview");
  const download = document.querySelector("#preview-download");

  function showError(message) {
    content.classList.remove("markdown-body");
    content.classList.add("preview-error");
    content.textContent = message;
  }

  async function loadPreview() {
    if (!path) {
      showError("没有指定要预览的 Markdown 文件。");
      return;
    }
    const filename = path.split("/").pop();
    title.textContent = filename;
    document.title = `${filename} · Markdown 预览`;
    download.href = `/api/files/download?path=${encodeURIComponent(path)}`;

    try {
      const response = await fetch(`/api/files/preview?path=${encodeURIComponent(path)}`, {
        headers: {"Accept": "application/json"},
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        location.href = "/login";
        return;
      }
      if (response.status === 403 && data.detail?.code === "password_change_required") {
        location.href = "/password";
        return;
      }
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "预览加载失败");
      }
      window.JobHuntMarkdown.render(content, data.content);
    } catch (error) {
      showError(error.message || "预览加载失败");
    }
  }

  loadPreview();
})();
