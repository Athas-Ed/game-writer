import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Union
import shutil

# 项目根目录：.../skills/version_control/scripts -> parents[3] 即项目根
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def backup_file(file_path: str) -> Dict[str, str]:
    """
    备份单个文件到其所在目录的「历史版本/」下。

    Args:
        file_path: 原文件相对项目根目录路径，例如 "data/角色设定/艾莉丝·温特菲尔德.md"

    Returns:
        {"backup_path": "...", "backup_name": "..."} 或 {"error": "..."}
    """
    src = PROJECT_ROOT / file_path
    if not src.exists() or not src.is_file():
        return {"error": f"文件不存在：{file_path}"}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = src.parent / "历史版本"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{src.stem}_{ts}{src.suffix}"
    dst = backup_dir / backup_name
    shutil.copy2(src, dst)
    return {
        "backup_path": str(dst.relative_to(PROJECT_ROOT)),
        "backup_name": backup_name,
    }


def append_modification_record(file_path: str, summary: str, backup_name: str, when: datetime | None = None) -> Dict[str, str]:
    """
    在文件中追加「## 修改记录」章节与一条记录。

    记录格式（与 SKILL.md 约定尽量一致）：
      - YYYY-MM-DD HH:MM:SS：{修改摘要}，备份：[备份文件名](/<原目录>/历史版本/<备份文件名>)
    """
    p = PROJECT_ROOT / file_path
    if not p.exists() or not p.is_file():
        return {"error": f"文件不存在：{file_path}"}

    when = when or datetime.now()
    ts = when.strftime("%Y-%m-%d %H:%M:%S")
    # 使用相对路径，便于在编辑器/仓库中直接跳转（同目录下的历史版本文件夹）
    link = f"历史版本/{backup_name}"
    line = f"  - {ts}：{summary}，备份：[{backup_name}]({link})"

    text = p.read_text(encoding="utf-8", errors="replace")
    if "\n## 修改记录" in text or text.startswith("## 修改记录"):
        # 插入到「## 修改记录」章节末尾：找到章节起点后，在末尾追加一条
        parts = text.split("## 修改记录", 1)
        head = parts[0]
        rest = parts[1]
        # 确保章节标题存在且后面有换行
        if not head.endswith("\n"):
            head += "\n"
        body = "## 修改记录" + rest
        # 直接在文件末尾追加（简单可靠；不尝试定位“章节末尾”）
        new_text = (head + body).rstrip("\n") + "\n" + line + "\n"
    else:
        new_text = text.rstrip("\n") + "\n\n## 修改记录\n" + line + "\n"

    p.write_text(new_text, encoding="utf-8")
    return {"ok": "1"}


def clean_old_backups(
    target_dir: str,
    older_than_days: int = 90,
    dry_run: bool = False
) -> Dict[str, Union[List[str], str]]:
    """
    清理 target_dir 下所有“历史版本”子文件夹中超过指定天数的备份文件。

    Args:
        target_dir: 要扫描的目录（相对项目根目录），例如 "data/角色设定"
        older_than_days: 保留最近多少天内的备份，默认 90 天
        dry_run: 如果为 True，只列出将删除的文件，不实际删除

    Returns:
        包含以下键的字典：
            "deleted": 实际删除的文件路径列表
            "failed": 删除失败或无法解析的文件列表
            "error": 如果 target_dir 不存在，返回错误信息
    """
    full_target = PROJECT_ROOT / target_dir
    if not full_target.exists():
        return {"error": f"目录不存在：{target_dir}"}

    cutoff = datetime.now() - timedelta(days=older_than_days)
    deleted = []
    failed = []

    # 递归查找所有“历史版本”文件夹
    for hist_dir in full_target.rglob("历史版本"):
        if not hist_dir.is_dir():
            continue
        for file_path in hist_dir.iterdir():
            if not file_path.is_file():
                continue

            # 解析文件名中的时间戳（格式：*_YYYYMMDD_HHMMSS.ext）
            match = re.search(r"_(\d{8}_\d{6})\.", file_path.name)
            if match:
                try:
                    file_time = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
                    if file_time < cutoff:
                        if dry_run:
                            deleted.append(str(file_path.relative_to(PROJECT_ROOT)))
                        else:
                            file_path.unlink()
                            deleted.append(str(file_path.relative_to(PROJECT_ROOT)))
                except ValueError:
                    # 文件名符合模式但解析失败，跳过但记录
                    failed.append(str(file_path.relative_to(PROJECT_ROOT)))
            else:
                # 文件名不符合预期模式，跳过（不处理）
                pass

    return {
        "deleted": deleted,
        "failed": failed,
        "dry_run": dry_run
    }


def list_backups(file_path: str) -> List[str]:
    """
    列出指定文件的所有历史备份（按时间倒序）。

    Args:
        file_path: 原文件的相对路径，例如 "data/角色设定/林夕.md"

    Returns:
        备份文件路径列表（相对项目根目录），按时间戳从新到旧排序。
        如果没有历史版本文件夹或没有备份，返回空列表。
    """
    full_path = PROJECT_ROOT / file_path
    backup_dir = full_path.parent / "历史版本"
    if not backup_dir.exists():
        return []

    # 获取与原文件同名的所有备份
    stem = full_path.stem
    suffix = full_path.suffix
    pattern = f"{stem}_*{suffix}"
    backups = list(backup_dir.glob(pattern))

    # 按时间戳排序（从新到旧）
    def timestamp_key(p: Path):
        match = re.search(r"_(\d{8}_\d{6})\.", p.name)
        if match:
            return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        return datetime.min

    backups.sort(key=timestamp_key, reverse=True)
    return [str(b.relative_to(PROJECT_ROOT)) for b in backups]


# 可选：根据备份文件恢复原文件（留作辅助函数，可被 Agent 直接调用）
def restore_from_backup(backup_path: str) -> str:
    """
    从备份文件恢复原文件（仅用于回滚操作）。
    假设备份文件位于原文件所在目录的“历史版本”下，原文件位于其父目录中。

    Args:
        backup_path: 备份文件的相对路径，例如 "data/角色设定/历史版本/林夕_20250327_143022.md"

    Returns:
        恢复结果消息。
    """
    backup_full = PROJECT_ROOT / backup_path
    if not backup_full.exists():
        return f"错误：备份文件不存在 {backup_path}"

    # 推断原文件路径：去掉时间戳后缀，并去掉“历史版本”部分
    # 例如：data/角色设定/历史版本/林夕_20250327_143022.md -> data/角色设定/林夕.md
    parent = backup_full.parent.parent
    stem = backup_full.stem
    # 去除末尾的时间戳部分（_YYYYMMDD_HHMMSS）
    original_stem = re.sub(r"_\d{8}_\d{6}$", "", stem)
    original_name = original_stem + backup_full.suffix
    original_path = parent / original_name

    shutil.copy2(backup_full, original_path)

    # 添加回滚记录（需要调用 Agent 的 add_modification_record，此处只做文件恢复）
    # 建议由 Agent 在调用此函数后自行添加记录，因此这里只返回恢复信息。
    return f"已从 {backup_path} 恢复到 {original_path.relative_to(PROJECT_ROOT)}"