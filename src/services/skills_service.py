from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional


@dataclass
class SkillsState:
    loaded: Dict[str, Dict[str, str]]


def _safe_read_text(path: Path) -> str:
    try:
        # 优先按 UTF-8（含 BOM）读取
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        try:
            # 兼容部分 Windows 环境中被保存为本地代码页（如 GBK）的 Markdown
            return path.read_text(encoding="gbk", errors="replace")
        except Exception:
            return ""


def _load_module(module_name: str, file_path: Path):
    spec = spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {file_path}")
    module = module_from_spec(spec)
    # 兼容 dataclasses / typing 等在导入期依赖 sys.modules 的场景。
    # module_from_spec 不会自动注册到 sys.modules；但正常 import 会。
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # 避免残留半初始化模块影响后续诊断/重试
        sys.modules.pop(module_name, None)
        raise
    return module


def scan_skills(skills_root: Path) -> Dict[str, Dict[str, str]]:
    skills: Dict[str, Dict[str, str]] = {}
    if not skills_root.exists():
        return skills
    for skill_md in skills_root.glob("*/SKILL.md"):
        text = _safe_read_text(skill_md)
        if not text:
            continue
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        skill_name = (name_match.group(1).strip() if name_match else skill_md.parent.name)
        skill_desc = (
            desc_match.group(1).strip()
            if desc_match
            else f"{skill_name}（来自 {skill_md.as_posix()}）"
        )
        skills[skill_name] = {
            "name": skill_name,
            "description": skill_desc,
            "path": str(skill_md.parent),
            "runner": "scripts/run.py",
        }
    return skills


def diagnose_skills(project_root: Path, skills_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for name, meta in sorted(scan_skills(skills_root).items()):
        skill_dir = Path(meta["path"])
        runner_rel = meta.get("runner", "scripts/run.py")
        runner_file = skill_dir / runner_rel
        try:
            runner_display = str(runner_file.relative_to(project_root))
        except ValueError:
            runner_display = str(runner_file)
        row: Dict[str, Any] = {
            "name": name,
            "runner": runner_display,
            "runner_exists": runner_file.exists(),
            "run_callable": False,
            "load_error": None,
        }
        if not runner_file.exists():
            rows.append(row)
            continue
        try:
            mod = _load_module(f"diag_skill_{name.replace('-', '_')}", runner_file)
            row["run_callable"] = callable(getattr(mod, "run", None))
        except Exception as e:
            row["load_error"] = str(e)
        rows.append(row)
    return rows


def ensure_loaded(state: SkillsState, skills_root: Path) -> SkillsState:
    if state.loaded:
        return state
    return SkillsState(loaded=scan_skills(skills_root))


def run_skill(payload: str, state: SkillsState, skills_root: Path) -> str:
    state = ensure_loaded(state, skills_root)

    if "|" not in payload:
        return "RunSkill 输入格式错误：需要「技能名|用户需求」。"

    skill_name, user_request = payload.split("|", 1)
    skill_name = skill_name.strip()
    user_request = user_request.strip()
    if not skill_name or not user_request:
        return "RunSkill 输入无效：技能名和用户需求都不能为空。"

    if skill_name not in state.loaded:
        return f"未找到技能: {skill_name}。可用技能：{', '.join(sorted(state.loaded.keys())) or '无'}"

    try:
        skill_dir = Path(state.loaded[skill_name]["path"])
        runner_rel = state.loaded[skill_name].get("runner", "scripts/run.py")
        runner_file = skill_dir / runner_rel
        if not runner_file.exists():
            return (
                f"技能 {skill_name} 缺少执行入口：{runner_rel}。"
                "请在该文件中实现 run(input_text: str) -> str。"
            )

        module_name = f"skill_runner_{skill_name.replace('-', '_')}"
        runner_mod = _load_module(module_name, runner_file)
        run_func = getattr(runner_mod, "run", None)
        if run_func is None or not callable(run_func):
            return (
                f"技能 {skill_name} 执行入口无效：{runner_rel} 中未找到可调用的 run(input_text) 函数。"
            )

        result = run_func(user_request)
        if result is None:
            return f"技能 {skill_name} 执行完成，但未返回结果。"
        return str(result)
    except Exception as e:
        return f"技能 {skill_name} 执行失败：{e}"

