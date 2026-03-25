import os
import re
import difflib
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# 项目根目录：当前文件位于 src/tools/ 下，向上两级
PROJECT_ROOT = Path(__file__).parent.parent.parent

_SUPPORTED_READ_EXTS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".log",
}

_FILE_INDEX: Optional[List[str]] = None
_FILE_INDEX_MTIME: Optional[float] = None


def _norm_rel_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    # 允许像 "./data/xxx" 这种写法
    while p.startswith("./"):
        p = p[2:]
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ValueError("不允许读取绝对路径。请使用相对路径（例如 data/角色设定/xxx.md）。")
    if ".." in p.split("/"):
        raise ValueError("不允许使用 '..' 路径穿越。")
    return p


def _norm_key(s: str) -> str:
    # 为模糊匹配做“软标准化”：统一大小写/去掉常见分隔符
    s = (s or "").lower().strip()
    s = re.sub(r"[\s\-_.·]+", "", s)
    return s


def _build_file_index() -> List[str]:
    """
    建立相对路径索引，用于模糊匹配。
    说明：仓库通常不大，直接全量扫描是可接受的；同时跳过常见无关目录。
    """
    global _FILE_INDEX_MTIME
    skip_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".cursor",
        "dist",
        "build",
        "target",
    }

    # 以项目根目录 mtime 作为轻量“缓存失效”信号（足够应付本项目）
    try:
        _FILE_INDEX_MTIME = PROJECT_ROOT.stat().st_mtime
    except Exception:
        _FILE_INDEX_MTIME = None

    idx: List[str] = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 原地修改 dirs，避免进入跳过目录
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel_dir = Path(root).relative_to(PROJECT_ROOT)
        if any(part in skip_dirs for part in rel_dir.parts):
            continue

        for fn in files:
            ext = Path(fn).suffix.lower()
            if ext not in _SUPPORTED_READ_EXTS:
                continue
            rel_path = (rel_dir / fn).as_posix()
            idx.append(rel_path)
    return idx


def _get_file_index() -> List[str]:
    global _FILE_INDEX, _FILE_INDEX_MTIME
    if _FILE_INDEX is not None:
        return _FILE_INDEX
    _FILE_INDEX = _build_file_index()
    return _FILE_INDEX


def _read_directory_contents(rel_dir: str, *, max_files: int = 20, max_total_chars: int = 60_000) -> str:
    dir_path = PROJECT_ROOT / rel_dir
    if not dir_path.exists() or not dir_path.is_dir():
        return f"文件不存在: {rel_dir}"

    files = sorted(
        [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in _SUPPORTED_READ_EXTS]
    )
    if not files:
        return f"目录内未找到可读文件: {rel_dir}"

    chunks: List[str] = []
    total_chars = 0
    used = 0
    for f in files:
        if used >= max_files:
            break
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as e:
            content = f"[读取失败: {e}]"
        rel = f.relative_to(PROJECT_ROOT).as_posix()
        header = f"### 文件: {rel}"
        block = f"{header}\n{content}"
        chunks.append(block)
        total_chars += len(content)
        used += 1
        if total_chars >= max_total_chars:
            chunks.append("### 目录内容已截断（内容过长）")
            break

    return (
        f"请求路径是目录：{rel_dir}。\n"
        f"已合并读取目录内部分内容（用于模糊检索/定位目标文件）。\n\n"
        + "\n\n".join(chunks)
    )


def read_settings_bundle(
    *,
    settings_dirs: Sequence[str] = ("角色设定", "背景设定"),
    pattern: str = "*.md",
    max_files_per_dir: int = 200,
    max_total_chars: int = 120_000,
) -> str:
    """
    读取 data/ 下常用“设定目录”的内容并合并为上下文（供技能/LLM使用）。
    - 默认读取：data/角色设定/*.md + data/背景设定/*.md
    - 返回：合并后的 Markdown 文本（带文件小标题）
    """
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        return "未找到设定文件。"

    parts: List[str] = []
    total_chars = 0

    for dir_name in settings_dirs:
        dir_path = data_dir / str(dir_name)
        if not dir_path.exists() or not dir_path.is_dir():
            continue
        used = 0
        for file in sorted(dir_path.glob(pattern)):
            if used >= max_files_per_dir:
                parts.append(f"## {dir_name}/（已截断：文件过多）")
                break
            if not file.is_file():
                continue
            try:
                content = file.read_text(encoding="utf-8")
            except Exception as e:
                content = f"读取失败：{e}"
            rel = file.relative_to(PROJECT_ROOT).as_posix()
            block = f"## {rel}\n{content}\n"
            parts.append(block)
            used += 1
            total_chars += len(content)
            if total_chars >= max_total_chars:
                parts.append("## （设定内容已截断：总内容过长）")
                return "\n".join(parts).strip()

    if not parts:
        return "未找到设定文件。"
    return "\n".join(parts).strip()


def _fuzzy_resolve_paths(rel_request: str, *, top_k: int = 8) -> List[Tuple[float, str]]:
    """
    在仓库内做相似度检索，返回 (score, rel_path)。
    """
    idx = _get_file_index()
    req_norm = _norm_key(rel_request)
    req_base = Path(rel_request).name
    # 模糊匹配时基于“去后缀文件名”，避免 'xxx.md' 拉低相似度
    req_stem_norm = _norm_key(Path(req_base).stem)

    scored: List[Tuple[float, str]] = []
    for cand in idx:
        cand_norm = _norm_key(cand)
        cand_stem_norm = _norm_key(Path(cand).stem)

        # 基于“去分隔符”的相似度
        ratio_full = difflib.SequenceMatcher(None, req_norm, cand_norm).ratio()
        ratio_base = difflib.SequenceMatcher(None, req_stem_norm, cand_stem_norm).ratio()

        # 如果候选路径包含请求（片段），给一点额外权重
        contains_bonus = 0.0
        if req_norm and req_norm in cand_norm:
            contains_bonus = 0.12

        prefix_bonus = 0.0
        if cand.replace("\\", "/").lower().startswith(rel_request.replace("\\", "/").lower().rstrip("/") + "/"):
            prefix_bonus = 0.08

        score = (0.55 * ratio_base) + (0.35 * ratio_full) + contains_bonus + prefix_bonus
        scored.append((score, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]

def read_file(file_path: str) -> str:
    rel_request = _norm_rel_path(file_path)
    full_path = PROJECT_ROOT / rel_request

    if full_path.exists():
        if full_path.is_file():
            try:
                return full_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"读取失败: {rel_request}，错误: {e}"
        if full_path.is_dir():
            return _read_directory_contents(rel_request)
        return f"无法读取（不是文件/目录）: {rel_request}"

    # 精确路径不存在：进行模糊解析
    candidates = _fuzzy_resolve_paths(rel_request, top_k=8)
    if not candidates:
        return f"文件不存在: {file_path}"

    best_score, best_path = candidates[0]
    # 阈值偏保守，避免把“角色设定”目录下的任意角色误匹配到某一个
    if best_score >= 0.68:
        full_best = PROJECT_ROOT / best_path
        try:
            return full_best.read_text(encoding="utf-8")
        except Exception as e:
            return f"读取失败: {best_path}，错误: {e}"

    # 返回候选文件列表，给 LLM 做二次选择（而不是原地重复 ReadFile）
    lines = [f"文件不存在: {file_path}。未找到足够高置信度的匹配文件。"]
    lines.append("可能的匹配文件如下：")
    for score, p in candidates[:6]:
        lines.append(f"- {p}（相似度 {score:.2f}）")
    return "\n".join(lines)

def write_file(file_path: str, content: str) -> str:
    rel_request = _norm_rel_path(file_path)
    full_path = PROJECT_ROOT / rel_request

    # 目录不允许直接写入（避免把目录当文件）
    if full_path.exists() and full_path.is_dir():
        return f"写入失败：目标是目录（请指定具体文件）：{rel_request}"

    target_path = full_path
    if not full_path.exists():
        # 如果请求像“部分文件名/无后缀”，尝试先匹配已有文件，优先“修改已有文件”
        candidates = _fuzzy_resolve_paths(rel_request, top_k=5)
        if candidates:
            best_score, best_rel = candidates[0]
            # 和 read_file 保持一致的“偏保守”，避免把目录下无关角色写错
            if best_score >= 0.68:
                target_path = PROJECT_ROOT / best_rel
            else:
                # 尝试补全常见后缀（例如：data/角色设定/艾莉丝 -> data/角色设定/艾莉丝.md）
                if target_path.suffix == "":
                    for ext in (".md", ".txt"):
                        probe = Path(str(target_path) + ext)
                        if probe.exists() and probe.is_file():
                            target_path = probe
                            break

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入: {target_path.relative_to(PROJECT_ROOT).as_posix()}"
    except Exception as e:
        return f"写入失败: {rel_request}，错误: {e}"


def _ensure_deletable_rel_path(rel_path: str, *, allowed_prefixes: Sequence[str]) -> str:
    """
    安全校验：只允许删除相对路径、且限定在 allowed_prefixes 下。
    返回：清洗后的 rel_path；抛错：ValueError
    """
    rp = _norm_rel_path(rel_path)

    # 限定只能删除 data/ 下（默认），避免误删代码/依赖/配置
    ok = any(rp.startswith(prefix) for prefix in allowed_prefixes)
    if not ok:
        raise ValueError(f"禁止删除：仅允许删除 {', '.join(allowed_prefixes)} 下的文件。当前为：{rp}")
    if rp.endswith("/"):
        raise ValueError("禁止删除目录：请指定具体文件路径（不要以 / 结尾）。")
    return rp


def delete_file(file_path: str, *, allowed_prefixes: Sequence[str] = ("data/",)) -> str:
    """
    删除单个文件（相对项目根目录）。
    默认仅允许删除 data/ 下的文件。
    """
    try:
        rel_request = _ensure_deletable_rel_path(file_path, allowed_prefixes=allowed_prefixes)
    except Exception as e:
        return f"删除失败: {e}"

    full_path = PROJECT_ROOT / rel_request
    if not full_path.exists():
        return f"未找到文件：{rel_request}"
    if full_path.is_dir():
        return f"删除失败：目标是目录而非文件：{rel_request}"

    try:
        full_path.unlink()
        return f"已删除：{rel_request}"
    except Exception as e:
        return f"删除失败：{rel_request}，错误：{e}"


def delete_files(payload: str, *, allowed_prefixes: Sequence[str] = ("data/",)) -> str:
    """
    删除多个文件。
    输入可以是：
    - 多行：data/...\\n
    - 逗号/分号/管道分隔
    - 带数字序号/markdown 列表（会自动清洗）
    """
    raw = (payload or "").replace("\r\n", "\n").strip()
    if not raw:
        return "删除失败：未提供文件列表。"

    # 先用分隔符粗切，再做清洗
    parts = re.split(r"[\n,;|，]+", raw)
    cands: List[str] = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        # 去掉常见的列表前缀/包裹字符
        s = s.lstrip("0123456789. )、-•* ")
        s = s.strip("`\"' ")
        if not s:
            continue
        cands.append(s)

    # 去重保持顺序
    seen = set()
    uniq: List[str] = []
    for p in cands:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)

    if not uniq:
        return "删除失败：解析不到有效的文件路径。"

    deleted: List[str] = []
    not_found: List[str] = []
    failed: List[str] = []

    for rel in uniq:
        # 安全校验
        try:
            safe_rel = _ensure_deletable_rel_path(rel, allowed_prefixes=allowed_prefixes)
        except Exception as e:
            failed.append(f"{rel}（校验失败：{e}）")
            continue

        full_path = PROJECT_ROOT / safe_rel
        if not full_path.exists():
            not_found.append(safe_rel)
            continue
        if full_path.is_dir():
            failed.append(f"{safe_rel}（是目录）")
            continue

        try:
            full_path.unlink()
            deleted.append(safe_rel)
        except Exception as e:
            failed.append(f"{safe_rel}（删除失败：{e}）")

    lines: List[str] = ["DeleteFiles 结果："]
    if deleted:
        lines.append("已删除：")
        lines.extend([f"- {p}" for p in deleted])
    if not_found:
        lines.append("未找到：")
        lines.extend([f"- {p}" for p in not_found])
    if failed:
        lines.append("失败：")
        lines.extend([f"- {p}" for p in failed])

    return "\n".join(lines).strip()