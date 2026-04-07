from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

SkillMeta = Dict[str, Any]


@dataclass
class SkillsState:
    loaded: Dict[str, SkillMeta]


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


def _parse_aliases_line(text: str) -> List[str]:
    """
    解析 frontmatter 中的 aliases / 别名 行，支持逗号、顿号、分号等分隔。
    """
    m = re.search(r"^(?:aliases|别名)\s*[:：]\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw or raw.lower() in {"[]", "null", "~", "none"}:
        return []
    parts = re.split(r"[,，、;；|｜/]+", raw)
    return [p.strip() for p in parts if p.strip()]


def build_alias_map(catalog: Dict[str, SkillMeta]) -> Dict[str, str]:
    """别名（含小写英文）→ 规范技能 id。先注册的别名优先，重复别名忽略后续。"""
    out: Dict[str, str] = {}
    for canonical, meta in catalog.items():
        if canonical not in out:
            out[canonical] = canonical
        cl = canonical.lower()
        if cl not in out:
            out[cl] = canonical
        for a in meta.get("aliases") or []:
            if not isinstance(a, str):
                continue
            key = a.strip()
            if not key:
                continue
            if key not in out:
                out[key] = canonical
            kl = key.lower()
            # 仅当别名全为 ASCII 时小写键才有意义，避免误伤中文
            if kl != key and kl not in out:
                out[kl] = canonical
    return out


def dialogue_voice_scheme_pick_payload(user_request: str) -> bool:
    """
    识别「对白 dialogue-voice」两套方案点选后，Streamlit 注入的续写指令。
    此类请求若误入 outline-writer，会错当成大纲选型续写（历史里往往仍有大纲方案在更早轮次）。
    """
    u = user_request or ""
    if "【对白】" in u:
        return True
    if "不要使用 outline-writer" in u or "不要使用大纲写手" in u:
        return True
    return False


def outline_writer_request_is_selection_followup(user_request: str) -> bool:
    """
    判断是否为「已生成多套大纲之后」的选型/展开请求。
    此类输入不应再作为 outline-writer 的「一句话剧情」执行，否则会生成无关新大纲。
    """
    u = (user_request or "").strip()
    if not u or len(u) > 1600:
        return False
    # dialogue-voice 点选续写：不得按「大纲选型」处理
    if dialogue_voice_scheme_pick_payload(u):
        return False
    # 与 Streamlit「方案选择」按钮文案一致（大纲 3 方案）
    if re.search(r"根据上一轮助手回复继续", u):
        return True
    if re.search(r"(我选择|我要|就选|采用|选定|选).{0,24}方案\s*[123一二三四五六七八九十]", u):
        return True
    if re.search(r"(展开|细化|扩充|续写).{0,16}该方案", u):
        return True
    if re.search(r"(展开|细化).{0,12}方案\s*[123一二三四五六七八九十]", u):
        return True
    return False


def last_assistant_content(
    conversation_history: Optional[List[Dict[str, Any]]],
) -> Optional[str]:
    """取历史中最后一条非空助手消息正文。"""
    if not conversation_history:
        return None
    for m in reversed(conversation_history):
        if not isinstance(m, dict):
            continue
        if m.get("role") != "assistant":
            continue
        c = m.get("content")
        if c is None:
            continue
        s = str(c).strip()
        if s:
            return s
    return None


def assistant_message_is_dialogue_voice_two_schemes(text: str) -> bool:
    """
    判断助手上一句是否来自 dialogue-voice（两套对白），用于手写「选方案1/2」时自动打【对白】标。
    """
    if not (text or "").strip():
        return False
    low = text.lower()
    if "dialogue-voice" in low:
        return True
    if re.search(r"2\s*组对白", text):
        return True
    if "已执行技能" in text and "对白" in text and "方案" in text:
        return True
    return False


def user_message_needs_dialogue_scheme_implicit_tag(user_input: str) -> bool:
    """用户手写选型/续写，且尚未带【对白】等显式标记时返回 True（需结合上一句助手是否为对白）。"""
    if dialogue_voice_scheme_pick_payload(user_input):
        return False
    u = (user_input or "").strip()
    if not u:
        return False
    # 仅方案3、无方案1/2：更像大纲第三案，不自动标对白
    if re.search(r"方案\s*3", u) and not re.search(r"方案\s*[12]", u):
        return False
    if re.search(r"(我选择|我要|就选|采用|选定).{0,40}方案\s*[12]", u):
        return True
    if "根据上一轮助手回复继续" in u and re.search(r"方案\s*[12]", u):
        return True
    if re.search(r"(展开|细化|扩充|续写).{0,24}该方案", u):
        return True
    return False


def augment_user_input_if_implicit_dialogue_scheme_pick(
    user_input: str,
    conversation_history: Optional[List[Dict[str, Any]]],
) -> str:
    """
    若上一轮助手为 dialogue-voice 两套对白，而用户本条像选型续写但未带【对白】，
    则在 用户需求 末尾追加说明，避免模型结合更早轮次的大纲误判 outline-writer。
    """
    last = last_assistant_content(conversation_history)
    if not last or not assistant_message_is_dialogue_voice_two_schemes(last):
        return user_input
    if not user_message_needs_dialogue_scheme_implicit_tag(user_input):
        return user_input
    suffix = (
        "\n\n【对白】【由系统根据上一轮助手输出自动标注】"
        "上一轮为 dialogue-voice 两套对白方案；请仅续写/润色选定对白，需要保存时用 WriteFile 写入 data/关键对话/。"
        "不要使用 outline-writer / 大纲写手。"
    )
    return (user_input or "").rstrip() + suffix


def resolve_skill_key(raw_name: str, catalog: Dict[str, SkillMeta]) -> Optional[str]:
    """
    将用户或模型输入的技能名（含中文别名、大小写变体）解析为 catalog 中的规范 name。
    找不到则返回 None。
    """
    r = (raw_name or "").strip()
    if not r:
        return None
    if r in catalog:
        return r
    rl = r.lower()
    for k in catalog:
        if k.lower() == rl:
            return k
    amap = build_alias_map(catalog)
    if r in amap:
        return amap[r]
    if rl in amap:
        return amap[rl]
    return None


def scan_skills(skills_root: Path) -> Dict[str, SkillMeta]:
    skills: Dict[str, SkillMeta] = {}
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
        alias_list = _parse_aliases_line(text)
        skills[skill_name] = {
            "name": skill_name,
            "description": skill_desc,
            "path": str(skill_md.parent),
            "runner": "scripts/run.py",
            "aliases": alias_list,
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
        als = meta.get("aliases") or []
        aliases_display = "、".join(str(a) for a in als) if isinstance(als, list) else ""
        row: Dict[str, Any] = {
            "name": name,
            "aliases": aliases_display,
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


def _skill_listing_with_aliases(catalog: Dict[str, SkillMeta]) -> str:
    lines = ["可用技能（规范 id，含中文别名）："]
    for k in sorted(catalog.keys()):
        meta = catalog[k]
        als = meta.get("aliases") or []
        extra = f"；别名：{'、'.join(als)}" if als else ""
        lines.append(f"- {k}{extra}")
    return "\n".join(lines)


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

    resolved = resolve_skill_key(skill_name, state.loaded)
    if resolved is None:
        hint = _skill_listing_with_aliases(state.loaded)
        return f"未找到技能: {skill_name}。\n{hint}"
    skill_name = resolved

    if skill_name == "outline-writer" and dialogue_voice_scheme_pick_payload(user_request):
        return (
            "【请勿调用大纲写手】本轮请求标题为对白 dialogue-voice 的「方案1/方案2」点选续写，不是剧情大纲选型。"
            "请根据历史对话中助手刚给出的两组对白之一，用 LLM 润色扩写（可加旁白/动作）；需要保存时用 WriteFile 写入"
            " `data/关键对话/` 或用户指定路径。禁止调用 RunSkill 的 outline-writer。"
        )

    if skill_name == "outline-writer" and outline_writer_request_is_selection_followup(user_request):
        return (
            "【请勿重复调用大纲写手技能】当前输入属于「已在上一轮生成多个大纲方案后，选定某一案并要求展开/细化/保存」。"
            "大纲写手技能只接受「完整故事构思」以批量生成新方案，不能把「我选择方案几」当作新剧情。"
            "请在本轮直接输出 type=final 的最终答复：根据历史对话中助手已给出的方案正文，撰写细化内容（章节结构、关键场景、伏笔回收等）；"
            "需要写入仓库时再单独调用 WriteFile。"
        )

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

