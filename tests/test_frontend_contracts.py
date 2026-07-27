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
