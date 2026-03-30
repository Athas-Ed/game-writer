"""
从 Markdown 中抽取：GFM 表格、轻小说/剧本式「角色：台词」行、任务块（### 标题 + 目标/奖励）。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# 不参与「角色：」解析的行首词（避免把说明句当成对白）
_SPEAKER_BLOCKLIST = frozenset(
    {
        "注意",
        "说明",
        "注",
        "备注",
        "提示",
        "例如",
        "参考",
        "详见",
        "本文",
        "以下",
        "上文",
        "下文",
    }
)


def split_pipe_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def extract_first_gfm_table(text: str) -> Optional[Tuple[List[str], List[List[str]]]]:
    """取文中第一个 GFM 风格表格（表头 + 分隔行 + 数据行）。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" not in line or i + 1 >= len(lines):
            i += 1
            continue
        sep = lines[i + 1].strip()
        if "|" not in sep or "-" not in sep.replace("|", "").replace(":", "").replace(" ", ""):
            i += 1
            continue
        header = split_pipe_row(line)
        if not header or not all(header):
            i += 1
            continue
        ncols = len(header)
        i += 2
        rows: List[List[str]] = []
        while i < len(lines):
            ln = lines[i].strip()
            if not ln or "|" not in ln:
                break
            row = split_pipe_row(ln)
            if len(row) < ncols:
                row = row + [""] * (ncols - len(row))
            elif len(row) > ncols:
                row = row[:ncols]
            rows.append(row)
            i += 1
        if rows:
            return header, rows
        i += 1
    return None


def extract_all_gfm_tables(text: str) -> List[Tuple[List[str], List[List[str]]]]:
    """文中所有 GFM 表格（按出现顺序）。"""
    lines = text.splitlines()
    i = 0
    tables: List[Tuple[List[str], List[List[str]]]] = []
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if "|" not in line or i + 1 >= n:
            i += 1
            continue
        sep = lines[i + 1].strip()
        if "|" not in sep or "-" not in sep.replace("|", ""):
            i += 1
            continue
        header = split_pipe_row(line)
        if not header:
            i += 1
            continue
        ncols = len(header)
        i += 2
        rows: List[List[str]] = []
        while i < n:
            ln = lines[i].strip()
            if not ln:
                break
            if "|" not in ln:
                break
            row = split_pipe_row(ln)
            if len(row) < ncols:
                row = row + [""] * (ncols - len(row))
            elif len(row) > ncols:
                row = row[:ncols]
            rows.append(row)
            i += 1
        if rows:
            tables.append((header, rows))
        else:
            i += 1
    return tables


def _clean_dialogue_line(s: str) -> str:
    s = s.strip()
    if s.startswith("「") and s.endswith("」"):
        s = s[1:-1]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s.strip()


def extract_dialogue_rows(text: str) -> List[Tuple[str, str]]:
    """
    抽取「角色：台词」行（支持中文冒号、可选引号）。
    角色名长度约 1～24，不含换行。
    """
    rows: List[Tuple[str, str]] = []
    pat = re.compile(r"^([^：:\#\n]{1,24}?)[：:]\s*(.+)$")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("|") and line.endswith("|"):
            continue
        m = pat.match(line)
        if not m:
            continue
        speaker = m.group(1).strip().strip("*").strip()
        content = _clean_dialogue_line(m.group(2))
        if not speaker or not content:
            continue
        if speaker in _SPEAKER_BLOCKLIST:
            continue
        if len(speaker) > 20:
            continue
        rows.append((speaker, content))
    return rows


def extract_task_rows(text: str) -> List[Dict[str, str]]:
    """
    优先按 ### / ## 小节解析任务；否则尝试 `- **任务名**` 列表。
    每条：任务名、目标、奖励、摘要（正文前 300 字）。
    """
    tasks: List[Dict[str, str]] = []
    chunks = re.split(r"(?=^#{2,3}\s+)", text, flags=re.MULTILINE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("#"):
            continue
        first_line, _, rest = chunk.partition("\n")
        first_line = first_line.strip()
        m = re.match(r"^(#{2,3})\s+(.+)$", first_line)
        if not m:
            continue
        title = m.group(2).strip()
        body = rest.strip()
        goal_m = re.search(r"(?:^|\n)\s*[-*]?\s*目标\s*[:：]\s*(.+?)(?=\n|$)", body)
        reward_m = re.search(r"(?:^|\n)\s*[-*]?\s*奖励\s*[:：]\s*(.+?)(?=\n|$)", body)
        goal = goal_m.group(1).strip() if goal_m else ""
        reward = reward_m.group(1).strip() if reward_m else ""
        summary = body.replace("\n", " ").strip()[:300]
        tasks.append(
            {
                "name": title,
                "goal": goal,
                "reward": reward,
                "summary": summary,
            }
        )

    if tasks:
        return tasks

    for m in re.finditer(r"^[-*]\s*\*\*(.+?)\*\*\s*$", text, re.MULTILINE):
        name = m.group(1).strip()
        tasks.append({"name": name, "goal": "", "reward": "", "summary": ""})
    return tasks
