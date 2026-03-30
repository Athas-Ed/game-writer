from __future__ import annotations

import re
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from excel_writer import (
    write_combined_xlsx,
    write_dialogue_xlsx,
    write_table_xlsx,
    write_task_xlsx,
)
from md_extract import (
    extract_all_gfm_tables,
    extract_dialogue_rows,
    extract_first_gfm_table,
    extract_task_rows,
)

from src.tools.file_tools import read_file


def _norm_rel_path(p: str) -> str:
    path = (p or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("不允许使用绝对路径")
    if ".." in path.split("/"):
        raise ValueError("不允许使用 '..' 路径穿越")
    return path


def _parse_export_request(text: str) -> tuple[str, str, str]:
    mode = "dialogue"
    path = ""
    out = ""
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        low = s.lower()
        if low in {"dialogue", "task", "table", "both", "all"} and "=" not in s:
            mode = low
            continue
        if "=" in s:
            k, _, v = s.partition("=")
            k, v = k.strip().lower(), v.strip().strip('"').strip("'")
            if k in {"path", "file", "src", "from"}:
                path = v
            elif k in {"out", "output", "to"}:
                out = v
    return mode, path, out


def run(input_text: str) -> str:
    """
    excel-export：从 Markdown 导出 .xlsx。
    子命令：dialogue / task / table / both / all
    必填：path=data/下的.md
    可选：out=data/exports/xxx.xlsx（默认 data/exports/<文件名>_export.xlsx）
    """
    raw = (input_text or "").strip()
    if not raw:
        return _usage()

    try:
        mode, path, out = _parse_export_request(raw)
        if not path:
            return "excel-export：请指定 path=data/.../某.md\n\n" + _usage()

        rel_md = _norm_rel_path(path)
        md_text = read_file(rel_md)
        if md_text.startswith("文件不存在") or md_text.startswith("读取失败"):
            return f"excel-export：无法读取源文件：{rel_md}\n{md_text}"

        if not out:
            stem = Path(rel_md).stem
            out = f"data/exports/{stem}_export.xlsx"

        rel_out = _norm_rel_path(out)
        if not rel_out.lower().endswith(".xlsx"):
            rel_out += ".xlsx"
        full_out = PROJECT_ROOT / rel_out

        if mode == "dialogue":
            rows = extract_dialogue_rows(md_text)
            if not rows:
                return (
                    f"excel-export：未从 `{rel_md}` 中解析到「角色：台词」行。\n"
                    "请使用 `角色名：台词` 或 `角色名:「台词」` 格式，或改用 mode=table 导出 Markdown 表格。"
                )
            write_dialogue_xlsx(full_out, rows)
            return f"已导出对白 {len(rows)} 条到：`{rel_out}`"

        if mode == "task":
            tasks = extract_task_rows(md_text)
            if not tasks:
                return (
                    f"excel-export：未从 `{rel_md}` 中解析到任务块。\n"
                    "请使用 `## 任务标题` 小节，并在正文中写 `目标：`、`奖励：`（可选），或 `- **任务名**` 列表。"
                )
            write_task_xlsx(full_out, tasks)
            return f"已导出任务 {len(tasks)} 条到：`{rel_out}`"

        if mode == "table":
            tables = extract_all_gfm_tables(md_text)
            if not tables:
                one = extract_first_gfm_table(md_text)
                if not one:
                    return (
                        f"excel-export：未在 `{rel_md}` 中找到 GFM 表格（| 表头 | + 分隔行 + 数据行）。"
                    )
                write_table_xlsx(full_out, one[0], one[1])
                return f"已导出 1 个表格到：`{rel_out}`"
            write_combined_xlsx(full_out, tables=tables)
            return f"已导出 {len(tables)} 个表格（多工作表）到：`{rel_out}`"

        if mode == "both":
            dr = extract_dialogue_rows(md_text)
            tr = extract_task_rows(md_text)
            if not dr and not tr:
                return (
                    "excel-export：both 模式未解析到对白行或任务块，请检查 Markdown 格式。"
                )
            write_combined_xlsx(full_out, dialogue_rows=dr or None, task_rows=tr or None)
            return (
                f"已导出：对白 {len(dr)} 条、任务 {len(tr)} 条（两个工作表）到：`{rel_out}`"
            )

        if mode == "all":
            dr = extract_dialogue_rows(md_text)
            tr = extract_task_rows(md_text)
            tables = extract_all_gfm_tables(md_text)
            if not tables:
                one = extract_first_gfm_table(md_text)
                if one:
                    tables = [one]
            if not dr and not tr and not tables:
                return "excel-export：all 模式未解析到任何可导出内容。"
            write_combined_xlsx(
                full_out,
                dialogue_rows=dr or None,
                task_rows=tr or None,
                tables=tables or None,
            )
            return (
                f"已导出：对白 {len(dr)} 条、任务 {len(tr)} 条、表格 {len(tables)} 个到：`{rel_out}`"
            )

        return _usage()
    except ValueError as e:
        return f"excel-export：路径错误：{e}"
    except Exception as e:
        return f"excel-export 执行失败：{e}"


def _usage() -> str:
    return (
        "excel-export 用法：\n"
        "- 第一行或单独一行写模式：`dialogue`（默认）| `task` | `table` | `both` | `all`\n"
        "- `path=data/.../文件.md`（必填）\n"
        "- `out=data/exports/输出.xlsx`（可选，默认 data/exports/<源文件名>_export.xlsx）\n\n"
        "模式说明：\n"
        "- dialogue：解析 `角色：台词` 行 → 列：序号、角色、台词\n"
        "- task：解析 `##/### 标题` 小节 + 目标/奖励 → 列：序号、任务名、目标、奖励、摘要\n"
        "- table：导出 Markdown 管道表格（可多表多 Sheet）\n"
        "- both：同一文件同时导出对白 Sheet + 任务 Sheet\n"
        "- all：对白 + 任务 + 文中所有表格\n\n"
        "示例：\n"
        "dialogue\npath=data/草稿/对白.md\nout=data/exports/对白.xlsx"
    )
