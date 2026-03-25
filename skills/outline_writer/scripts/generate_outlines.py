# skills/outline_writer/scripts/generate_outlines.py
from src.tools.llm_tools import llm_generate

def generate_outlines(one_line: str, context: str, num_options: int = 3) -> list:
    prompt = f"""你是一个游戏编剧助手。以下是当前项目的角色、背景设定：
{context}

现在用户提供了一句话剧情描述：“{one_line}”
请根据设定，创作{num_options}个不同风格的剧情大纲方案。每个方案用简短的几段文字描述核心情节、冲突和悬念。
请用编号1、2、3...列出，每个方案后空一行。不要添加额外评价。
"""
    response = llm_generate(prompt, temperature=0.8)
    # 解析编号
    lines = response.split("\n")
    outlines = []
    current = []
    for line in lines:
        if line.strip().startswith(("1", "2", "3", "4", "5")) and line.strip()[0].isdigit():
            if current:
                outlines.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        outlines.append("\n".join(current))
    return outlines