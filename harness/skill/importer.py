"""Import Skill packages from uploaded zip archives."""

from __future__ import annotations

import posixpath
import shutil
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from harness.skill.manifest import parse_skill_md


class SkillImportError(ValueError):
    """Raised when an uploaded Skill package is invalid."""


@dataclass
class SkillImportResult:
    """Result returned after importing a Skill zip package."""

    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def import_skill_zip(content: bytes, extension_dir: Path, overwrite: bool = True) -> SkillImportResult:
    """Import one or more Skills from a zip archive into the extension directory."""
    extension_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(content)) as zf:
        members = _validated_members(zf)
        skill_roots = _find_skill_roots(members)
        if not skill_roots:
            raise SkillImportError("Skill zip must contain at least one SKILL.md")

        result = SkillImportResult()
        for root in skill_roots:
            skill_name = _skill_name_for_root(zf, root)
            target_root = extension_dir / skill_name
            if target_root.exists():
                if not overwrite:
                    result.skipped.append(skill_name)
                    continue
                shutil.rmtree(target_root)
            target_root.mkdir(parents=True, exist_ok=True)

            root_prefix = "" if root == "." else f"{root}/"
            for member in members:
                if root != "." and not member.startswith(root_prefix):
                    continue
                relative = member if root == "." else member[len(root_prefix):]
                if not relative or relative.endswith("/"):
                    continue
                _write_zip_member(zf, member, target_root / Path(*relative.split("/")))

            if not parse_skill_md(target_root / "SKILL.md"):
                shutil.rmtree(target_root, ignore_errors=True)
                raise SkillImportError(f"Invalid SKILL.md for skill '{skill_name}'")
            result.imported.append(skill_name)
        return result


def _validated_members(zf: zipfile.ZipFile) -> list[str]:
    members = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/").strip()
        if not name or name.endswith("/"):
            continue
        normalized = posixpath.normpath(name)
        parts = normalized.split("/")
        if (
            normalized.startswith("../")
            or normalized == ".."
            or normalized.startswith("/")
            or any(":" in p for p in parts)
        ):
            raise SkillImportError(f"unsafe zip path: {info.filename}")
        members.append(normalized)
    return members


def _find_skill_roots(members: list[str]) -> list[str]:
    roots = []
    for member in members:
        if member == "SKILL.md":
            roots.append(".")
        elif member.endswith("/SKILL.md"):
            roots.append(member.rsplit("/", 1)[0])
    return sorted(set(roots))


def _skill_name_for_root(zf: zipfile.ZipFile, root: str) -> str:
    skill_md = "SKILL.md" if root == "." else f"{root}/SKILL.md"
    content = zf.read(skill_md).decode("utf-8", errors="replace")
    name = _frontmatter_value(content, "name")
    if name:
        return _safe_skill_name(name)
    return _safe_skill_name(Path(root).name)


def _frontmatter_value(content: str, key: str) -> str:
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        k, value = line.split(":", 1)
        if k.strip() == key:
            return value.strip().strip("\"'")
    return ""


def _safe_skill_name(name: str) -> str:
    safe = name.strip().replace("\\", "/")
    if not safe or "/" in safe or safe in (".", "..") or ":" in safe:
        raise SkillImportError(f"Invalid skill name: {name}")
    return safe


def _write_zip_member(zf: zipfile.ZipFile, member: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(zf.read(member))
