from __future__ import annotations

from pathlib import Path

from webapp.template_files import copy_template, upgrade_template


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_upgrade_updates_untouched_file_and_reports_conflict(tmp_path: Path):
    template = tmp_path / "template"
    workspace = tmp_path / "workspace"
    write(template / "README.md", "v1")
    write(template / "build_resumes.py", "print('v1')")
    write(template / "master.md", "template personal")
    write(template / "TEMPLATE_VERSION", "v1")
    old_hashes = copy_template(template, workspace)

    write(workspace / "build_resumes.py", "print('user changed')")
    write(workspace / "master.md", "my private facts")
    write(template / "README.md", "v2")
    write(template / "build_resumes.py", "print('v2')")
    write(template / "master.md", "new template personal")
    write(template / "TEMPLATE_VERSION", "v2")

    result = upgrade_template(template, workspace, old_hashes)
    assert (workspace / "README.md").read_text() == "v2"
    assert (workspace / "build_resumes.py").read_text() == "print('user changed')"
    assert "build_resumes.py" in result["conflicts"]
    assert (workspace / "master.md").read_text() == "my private facts"
    assert "master.md" in result["skipped"]
    assert result["version"] == "v2"

