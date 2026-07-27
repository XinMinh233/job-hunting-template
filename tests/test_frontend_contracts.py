from pathlib import Path

from fastapi.testclient import TestClient

from webapp.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_uses_one_enabled_welcome_composer():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert '<template id="welcome-template">' in response.text
    assert response.text.count('data-prompt="/onboard"') == 1
    assert 'id="prompt"' in response.text
    assert 'id="prompt" rows="1" maxlength="100000"' in response.text
    assert 'type="submit" disabled' not in response.text


def test_frontend_guards_enter_during_ime_composition():
    script = (ROOT / "webapp/static/app.js").read_text()
    assert 'event.isComposing' in script
    assert 'event.keyCode !== 229' in script
    assert 'addEventListener("compositionstart"' in script
    assert 'addEventListener("compositionend"' in script


def test_new_chat_is_created_only_when_first_prompt_is_sent():
    script = (ROOT / "webapp/static/app.js").read_text()
    new_chat_body = script.split("async function newChat()", 1)[1].split(
        "async function archiveChat", 1
    )[0]
    send_prompt_body = script.split("async function sendPrompt(value)", 1)[1]
    assert 'api("/api/chats", {method: "POST"' not in new_chat_body
    assert 'api("/api/chats", {method: "POST"' in send_prompt_body


def test_admin_jobs_surface_sanitized_failure_reason():
    with TestClient(app) as client:
        response = client.get("/admin")
    script = (ROOT / "webapp/static/admin.js").read_text()
    assert response.status_code == 200
    assert "<th>失败原因</th>" in response.text
    assert 'job.error || "—"' in script


def test_workspace_loads_safe_markdown_renderer_and_scroll_constraints():
    with TestClient(app) as client:
        response = client.get("/")
        preview = client.get("/files/preview")
    script = (ROOT / "webapp/static/app.js").read_text()
    renderer = (ROOT / "webapp/static/markdown.js").read_text()
    styles = (ROOT / "webapp/static/style.css").read_text()

    assert response.status_code == 200
    assert '<script src="/static/markdown.js"></script>' in response.text
    assert response.text.index("/static/markdown.js") < response.text.index(
        "/static/app.js"
    )
    assert preview.status_code == 200
    assert 'id="markdown-preview"' in preview.text
    assert "window.JobHuntMarkdown.render" in script
    assert "document.createElement" in renderer
    assert ".innerHTML" not in renderer
    assert '"javascript:"' not in renderer
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in styles
    assert ".messages { min-height: 0; overflow-y: auto" in styles


def test_file_actions_only_offer_preview_for_supported_types():
    script = (ROOT / "webapp/static/app.js").read_text()
    preview_logic = script.split("function filePreviewUrl(path)", 1)[1].split(
        "async function loadFiles", 1
    )[0]

    assert '["md", "markdown"]' in preview_logic
    assert '["pdf", "html", "htm"]' in preview_logic
    assert "txt" not in preview_logic
    assert "csv" not in preview_logic
    assert "docx" not in preview_logic
