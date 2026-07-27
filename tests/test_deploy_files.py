from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_preserves_user_traversal_and_caddy_logging() -> None:
    script = (ROOT / "deploy/install-ubuntu.sh").read_text(encoding="utf-8")

    assert "-m 0711 /var/lib/jobhunt/users" in script
    assert "-o caddy -g caddy -m 0750 /var/log/caddy" in script


def test_runner_can_update_system_accounts() -> None:
    unit = (
        ROOT / "deploy/systemd/jobhunt-runner.service"
    ).read_text(encoding="utf-8")

    assert "ProtectSystem=true" in unit
    assert "ProtectSystem=full" not in unit
    assert "ReadWritePaths=/etc " in unit


def test_caddy_has_default_sni_for_ip_testing() -> None:
    caddyfile = (ROOT / "deploy/Caddyfile").read_text(encoding="utf-8")

    assert "default_sni {$JOBHUNT_DOMAIN}" in caddyfile
    assert "output file /var/log/caddy/jobhunt-access.log" in caddyfile
