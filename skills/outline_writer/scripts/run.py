from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 兼容不同加载方式：确保可 import src.*（项目根目录在 skills/ 的上一级）
PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate_outlines import generate_outlines
from read_settings import read_all_settings


def run(input_text: str) -> str:
    """
    统一技能入口：接收用户输入并返回可展示文本。
    """
    user_request = (input_text or "").strip()
    if not user_request:
        return "outline-writer 输入为空，请提供一句话剧情描述。"

    context = read_all_settings()
    outlines = generate_outlines(user_request, context, num_options=3)
    if not outlines:
        return "outline-writer 执行完成，但未生成任何大纲。"

    lines = ["已执行技能 outline-writer，生成 3 个大纲方案："]
    for i, item in enumerate(outlines[:3], start=1):
        lines.append(f"\n方案{i}:\n{item.strip()}")
    return "\n".join(lines)

