from __future__ import annotations

from pathlib import Path
import sys
import re

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 兼容不同加载方式：确保可 import skills.* / src.*
PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from version_manager import (
    append_modification_record,
    backup_file,
    clean_old_backups,
    list_backups,
    restore_from_backup,
)


def _pick_int(text: str, default: int) -> int:
    m = re.search(r"(?:days|day|天)\s*=\s*(\d+)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)\s*(?:days|day|天)", text, re.IGNORECASE)
    return int(m.group(1)) if m else default


def _pick_path(text: str) -> str | None:
    m = re.search(r"(?:path|file|dir|target)\s*=\s*([^\s]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 兼容中文自然语言：直接抓取 data/...(.md) 路径
    m2 = re.search(r"(data[\\/][^\s\"']+?\.md)", text, re.IGNORECASE)
    if m2:
        return m2.group(1).replace("\\", "/")
    # 也支持传入历史版本文件
    m3 = re.search(r"(data[\\/][^\s\"']+?_[0-9]{8}_[0-9]{6}\.[A-Za-z0-9]+)", text, re.IGNORECASE)
    if m3:
        return m3.group(1).replace("\\", "/")
    return None


def _pick_summary(text: str) -> str | None:
    # summary=... backup=... 这种场景：summary 只取到下一个键之前
    m = re.search(
        r"(?:summary|reason|摘要)\s*=\s*(.+?)(?:\s+(?:backup|备份)\s*=|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # 允许「…：xxx」这种格式
    m2 = re.search(r"(?:修改摘要|摘要)[:：]\s*(.+)$", text)
    return m2.group(1).strip() if m2 else None


def run(input_text: str) -> str:
    """
    version-control 技能统一入口。

    约定输入（尽量宽松）：
    - list path=data/xxx.md
    - restore path=data/.../历史版本/xxx_YYYYMMDD_HHMMSS.md
    - backup path=data/xxx.md
    - record path=data/xxx.md summary=... backup=xxx_YYYYMMDD_HHMMSS.md
    - clean target=data/角色设定 days=180 [dry_run]
    """
    req = (input_text or "").strip()
    if not req:
        return (
            "version-control 输入为空。示例：\n"
            "- list path=data/角色设定/林夕.md\n"
            "- restore path=data/角色设定/历史版本/林夕_20250327_143022.md\n"
            "- clean target=data/角色设定 days=180 dry_run"
        )

    low = req.lower()

    if low.startswith("list") or "list_backups" in low or "列出" in req:
        p = _pick_path(req)
        if not p:
            return "用法：list path=data/角色设定/林夕.md"
        backups = list_backups(p)
        if not backups:
            return f"未找到历史版本：{p}"
        lines = [f"已找到 {len(backups)} 个备份（新→旧）："]
        lines += [f"- {b}" for b in backups]
        return "\n".join(lines)

    if low.startswith("restore") or "restore_from_backup" in low or "回滚" in req or "恢复" in req:
        p = _pick_path(req)
        if not p:
            return "用法：restore path=data/角色设定/历史版本/林夕_20250327_143022.md"
        return restore_from_backup(p)

    if low.startswith("backup") or "备份" in req:
        p = _pick_path(req)
        if not p:
            return "用法：backup path=data/角色设定/艾莉丝·温特菲尔德.md"
        res = backup_file(p)
        if "error" in res:
            return str(res["error"])
        return f"已备份：{p}\n- 备份文件：{res['backup_path']}"

    if low.startswith("record") or "修改记录" in req or "记录" in req:
        p = _pick_path(req)
        if not p:
            return "用法：record path=data/角色设定/艾莉丝·温特菲尔德.md summary=将年龄从18岁改为16岁 backup=艾莉丝·温特菲尔德_YYYYMMDD_HHMMSS.md"
        summary = _pick_summary(req) or "修改设定"
        m_bk = re.search(r"(?:backup|备份)\s*=\s*([^\s]+)", req, re.IGNORECASE)
        backup_name = m_bk.group(1).strip() if m_bk else ""
        if not backup_name:
            return "record 需要提供备份文件名：backup=xxx_YYYYMMDD_HHMMSS.md"
        res = append_modification_record(p, summary=summary, backup_name=backup_name)
        if "error" in res:
            return str(res["error"])
        return f"已写入修改记录：{p}\n- 摘要：{summary}\n- 备份：{backup_name}"

    if low.startswith("clean") or "clean_old_backups" in low or "清理" in req:
        target = _pick_path(req) or "data"
        days = _pick_int(req, default=90)
        dry_run = ("dry_run" in low) or ("dry-run" in low) or ("预览" in req) or ("不删除" in req)
        res = clean_old_backups(target_dir=target, older_than_days=days, dry_run=dry_run)
        if "error" in res:
            return str(res["error"])
        deleted = res.get("deleted", []) or []
        failed = res.get("failed", []) or []
        mode = "预览" if dry_run else "已删除"
        lines = [f"历史版本清理完成（{mode}，阈值：{days} 天，范围：{target}）"]
        lines.append(f"- {mode}数量：{len(deleted)}")
        if deleted:
            lines += [f"  - {p}" for p in deleted[:50]]
            if len(deleted) > 50:
                lines.append(f"  - ... 其余 {len(deleted) - 50} 项略")
        lines.append(f"- 失败数量：{len(failed)}")
        if failed:
            lines += [f"  - {p}" for p in failed[:50]]
            if len(failed) > 50:
                lines.append(f"  - ... 其余 {len(failed) - 50} 项略")
        return "\n".join(lines)

    return (
        "未识别的 version-control 指令。\n"
        "支持：list / restore / backup / record / clean\n"
        "示例：clean target=data/角色设定 days=180 dry_run"
    )

