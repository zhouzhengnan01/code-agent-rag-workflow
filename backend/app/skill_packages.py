import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

from .db import new_id, resource_save
from .workspace import BASE_WORKSPACE


PACKAGE_ROOT = BASE_WORKSPACE / ".codezzn-skills"
MAX_FILES, MAX_UNPACKED = 500, 20 * 1024 * 1024


def _frontmatter(text):
    result = {}
    if not text.startswith("---\n"): return result
    block = text.split("---\n", 2)[1]
    for line in block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1); result[key.strip()] = value.strip().strip('"\'')
    return result


def import_package(filename, raw):
    package_id = new_id("skillpkg"); destination = PACKAGE_ROOT / package_id
    destination.mkdir(parents=True, exist_ok=False)
    try:
        if filename.lower().endswith(".zip"):
            archive_path = destination / ".upload.zip"; archive_path.write_bytes(raw)
            with zipfile.ZipFile(archive_path) as archive:
                files = [item for item in archive.infolist() if not item.is_dir()]
                if len(files) > MAX_FILES or sum(item.file_size for item in files) > MAX_UNPACKED: raise ValueError("Skill 包过大")
                for item in files:
                    target = (destination / item.filename).resolve()
                    if destination.resolve() not in target.parents or item.filename.startswith(("/", "\\")): raise ValueError("Skill 包包含不安全路径")
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(archive.read(item))
            archive_path.unlink()
        else:
            (destination / "SKILL.md").write_bytes(raw)
        candidates = list(destination.rglob("SKILL.md"))
        if len(candidates) != 1: raise ValueError("Skill 包必须且只能包含一个 SKILL.md")
        skill_md = candidates[0]; root = skill_md.parent
        if root != destination:
            for child in list(root.iterdir()): shutil.move(str(child), destination / child.name)
            shutil.rmtree(root, ignore_errors=True)
        content = (destination / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        meta = _frontmatter(content); manifest_path = destination / "skill.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        version = str(manifest.get("version") or meta.get("version") or "0.1.0")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version): raise ValueError("Skill version 必须使用 SemVer，例如 1.2.3")
        dependencies = manifest.get("dependencies") or []
        if not isinstance(dependencies, list) or any(not isinstance(item, (str, dict)) for item in dependencies): raise ValueError("Skill dependencies 必须是字符串或对象数组")
        file_list = sorted(path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file())
        digest = hashlib.sha256("".join(hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in file_list).encode()).hexdigest()
        payload = {
            "name": manifest.get("name") or meta.get("name") or Path(filename).stem,
            "description": manifest.get("description") or meta.get("description") or "Imported Skill package",
            "content": content, "enabled": True, "package_id": package_id,
            "version": version,
            "dependencies": dependencies, "files": file_list, "integrity": digest,
            "scripts": [name for name in file_list if name.startswith("scripts/")],
            "assets": [name for name in file_list if name.startswith("assets/")],
            "references": [name for name in file_list if name.startswith("references/")],
        }
        return resource_save("skills", payload)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True); raise


def package_path(skill, relative=""):
    package_id = str(skill.get("package_id") or "")
    if not re.fullmatch(r"skillpkg_[a-f0-9]{16}", package_id): raise ValueError("该技能不是已安装的 Skill 包")
    root = (PACKAGE_ROOT / package_id).resolve(); target = (root / relative).resolve()
    if target != root and root not in target.parents: raise ValueError("Skill 路径越界")
    return target


def read_package_file(skill, relative):
    path = package_path(skill, relative)
    if not path.is_file(): raise FileNotFoundError(relative)
    return {"path":relative,"content":path.read_text(encoding="utf-8",errors="replace")[:200000]}


def verify_package(skill):
    root = package_path(skill)
    files = list(skill.get("files") or [])
    if not files or any(not package_path(skill, name).is_file() for name in files):
        raise ValueError("Skill 包缺少已登记文件")
    digest = hashlib.sha256("".join(hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(files)).encode()).hexdigest()
    if digest != skill.get("integrity"):
        raise ValueError("Skill 包完整性校验失败；文件可能已被篡改")
    return {"ok": True, "version": skill.get("version"), "dependencies": skill.get("dependencies") or [], "integrity": digest}
