from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Iterable

TEMPLATE_DIRS = (
    ".claude",
    "base",
    "data",
    "docs/web",
    "prompts",
    "render",
    "tailored",
)
TEMPLATE_FILES = (
    ".gitignore",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "START-HERE.md",
    "build_career_tree.py",
    "build_dashboard.py",
    "build_resumes.py",
    "check_links.py",
    "master.md",
    "resume_lint.py",
)
PRESERVED_PREFIXES = (
    "base/",
    "data/",
    "tailored/",
    "uploads/",
    "dist/",
)
PRESERVED_FILES = {"master.md", "CLAUDE.md"}


def template_version(template_root: Path) -> str:
    version_file = template_root / "TEMPLATE_VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return "v1"


def iter_template_files(template_root: Path) -> Iterable[tuple[Path, Path]]:
    for name in TEMPLATE_FILES:
        source = template_root / name
        if source.is_file():
            yield source, Path(name)
    for name in TEMPLATE_DIRS:
        source_dir = template_root / name
        if not source_dir.is_dir():
            continue
        for source in source_dir.rglob("*"):
            if (
                source.is_file()
                and ".git" not in source.parts
                and source.name != "settings.local.json"
            ):
                yield source, source.relative_to(template_root)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def template_hashes(template_root: Path) -> dict[str, str]:
    return {
        relative.as_posix(): sha256_file(source)
        for source, relative in iter_template_files(template_root)
    }


def copy_template(template_root: Path, workspace: Path) -> dict[str, str]:
    workspace.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for source, relative in iter_template_files(template_root):
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative.as_posix()] = sha256_file(source)
    return hashes


def is_preserved(relative: str) -> bool:
    return relative in PRESERVED_FILES or relative.startswith(PRESERVED_PREFIXES)


def upgrade_template(
    template_root: Path,
    workspace: Path,
    old_hashes: dict[str, str],
) -> dict[str, object]:
    new_hashes = template_hashes(template_root)
    updated: list[str] = []
    conflicts: list[str] = []
    skipped: list[str] = []
    for relative, new_hash in new_hashes.items():
        if is_preserved(relative):
            skipped.append(relative)
            continue
        target = workspace / relative
        old_hash = old_hashes.get(relative)
        if target.exists() and old_hash and sha256_file(target) != old_hash:
            conflicts.append(relative)
            continue
        source = template_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        updated.append(relative)

    carried_hashes = dict(old_hashes)
    for relative in updated:
        carried_hashes[relative] = new_hashes[relative]
    for relative in skipped:
        if relative in new_hashes and relative not in carried_hashes:
            carried_hashes[relative] = new_hashes[relative]
    return {
        "updated": updated,
        "conflicts": conflicts,
        "skipped": skipped,
        "hashes": carried_hashes,
        "version": template_version(template_root),
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)
