"""
游戏编剧综合工作台：对话 Agent + 资料浏览 + 技能目录 + 设置。
开发模式（含健康检查）可由侧边栏切换，或由环境变量 APP_MODE 锁定。
"""
import os
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"
PREFERENCES_PATH = CONFIG_ROOT / "preferences.md"

from src.core.agent import (
    diagnose_skills,
    get_llm_env_summary,
    get_skills_catalog,
    run_agent,
)
from src.tools.file_tools import read_file


def _app_mode_from_env() -> str:
    return os.getenv("APP_MODE", "").strip().lower()


def _init_session() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "dev_mode_choice" not in st.session_state:
        st.session_state.dev_mode_choice = False
    if "prefs_write_enabled" not in st.session_state:
        st.session_state.prefs_write_enabled = True


def _render_chat(max_steps: int, history_turns: int) -> None:
    st.subheader("对话")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("输入需求，Agent 会选择工具或技能…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Agent 运行中…"):
                response = run_agent(
                    prompt,
                    max_steps=max_steps,
                    conversation_history=st.session_state.messages[:-1],
                    history_turns=history_turns,
                )
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})


def _collect_markdown_files(limit: int = 80) -> list[Path]:
    data_root = PROJECT_ROOT / "data"
    if not data_root.exists():
        return []
    paths: list[Path] = []
    for p in sorted(data_root.rglob("*.md")):
        paths.append(p)
        if len(paths) >= limit:
            break
    return paths


def _rel_project(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _render_data_tab() -> None:
    st.subheader("资料库")
    st.caption("浏览项目 `data/` 下的 Markdown，只读预览。")
    files = _collect_markdown_files()
    if not files:
        st.info("未找到 `data/**/*.md`。可在项目根下创建 `data/角色设定/` 等目录。")
        return
    labels = [_rel_project(f) for f in files]
    choice = st.selectbox("选择文件", range(len(labels)), format_func=lambda i: labels[i])
    rel = labels[choice]
    content = read_file(rel)
    st.text_area("内容预览", value=content, height=420, disabled=True)


def _render_skills_tab() -> None:
    st.subheader("技能")
    catalog = get_skills_catalog()
    if not catalog:
        st.info("未发现技能。请在 `skills/*/SKILL.md` 下添加技能。")
        return
    for name, meta in sorted(catalog.items(), key=lambda x: x[0]):
        with st.expander(f"**{name}**", expanded=False):
            st.markdown(meta.get("description", "—"))
            st.caption(f"目录： `{meta.get('path', '')}`")
            st.caption("调用方式：`RunSkill`，例如 `" + f"`{name}|你的需求..." + "`")


def _render_settings_tab(max_steps: int) -> None:
    st.subheader("设置与说明")
    st.markdown(
        """
- **工作模式**：侧边栏关闭「开发模式」时，主界面聚焦对话与资料；开发向面板隐藏。
- **开发模式**：显示额外技能诊断、环境与健康检查等。
- **锁定模式**：设置环境变量 `APP_MODE=work` 或 `APP_MODE=dev` 可锁定界面模式（适合交付给他人时使用工作版）。
        """
    )
    st.metric("当前 Agent 最大步数", max_steps)


def _render_dev_tab() -> None:
    st.subheader("开发工具")
    st.caption("仅供本机/开发使用；不会显示完整 API Key。")

    st.markdown("##### 偏好写入开关")
    st.session_state.prefs_write_enabled = st.checkbox(
        "允许 Agent 写入偏好（UpdatePreferences）",
        value=st.session_state.prefs_write_enabled,
        help="默认开启。关闭后，Agent 仍可提出偏好建议，但不会实际写入到 config/preferences.md。",
    )
    os.environ["PREFERENCES_WRITE_ENABLED"] = "1" if st.session_state.prefs_write_enabled else "0"

    st.markdown("##### 偏好文件预览 / 编辑")
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    if not PREFERENCES_PATH.exists():
        PREFERENCES_PATH.write_text("## 默认偏好\n\n", encoding="utf-8")
    current = PREFERENCES_PATH.read_text(encoding="utf-8", errors="replace")
    edited = st.text_area(
        "config/preferences.md",
        value=current,
        height=260,
    )
    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("保存偏好文件", type="primary"):
            PREFERENCES_PATH.write_text(edited, encoding="utf-8")
            st.success("已保存到 config/preferences.md")
    with col_b:
        if st.button("重新加载偏好文件"):
            st.rerun()

    st.markdown("##### 环境与 LLM")
    env_info = get_llm_env_summary()
    st.json(env_info)

    if st.button("发送最小请求测试 API（会消耗少量额度）", type="primary"):
        from src.tools.llm_tools import llm_generate

        try:
            reply = llm_generate("只回复一个字：好", temperature=0)
            st.success("API 可用。")
            st.code(reply[:500], language="text")
        except Exception as e:
            st.error(f"API 调用失败：{e}")

    st.markdown("##### 技能 Runner 检查")
    rows = diagnose_skills()
    st.dataframe(rows, width="stretch", hide_index=True)


def main() -> None:
    _init_session()
    st.set_page_config(
        page_title="游戏编剧工作台",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 让偏好写入开关在所有模式下生效（工作/开发模式都读取该变量）
    os.environ["PREFERENCES_WRITE_ENABLED"] = "1" if st.session_state.prefs_write_enabled else "0"

    app_mode = _app_mode_from_env()

    with st.sidebar:
        st.title("编剧工作台")
        st.caption(str(PROJECT_ROOT))

        if app_mode == "work":
            dev_mode = False
            st.info("**工作模式**（`APP_MODE=work` 锁定）")
        elif app_mode == "dev":
            dev_mode = True
            st.warning("**开发模式**（`APP_MODE=dev` 锁定）")
        else:
            dev_mode = st.checkbox(
                "开发模式",
                value=st.session_state.dev_mode_choice,
                help="开启后显示「开发工具」Tab、API 测试与技能 Runner 检查。",
            )
            st.session_state.dev_mode_choice = dev_mode

        max_steps = st.slider("Agent 最大步数", min_value=3, max_value=24, value=8, step=1)
        history_turns = st.slider("上下文保留轮数", min_value=0, max_value=20, value=6, step=1)

        if st.button("清空对话记录"):
            st.session_state.messages = []
            st.rerun()

    tab_labels = ["工作台", "资料库", "技能", "设置"] + (["开发工具"] if dev_mode else [])
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_chat(max_steps=max_steps, history_turns=history_turns)

    with tabs[1]:
        _render_data_tab()

    with tabs[2]:
        _render_skills_tab()

    with tabs[3]:
        _render_settings_tab(max_steps=max_steps)

    if dev_mode:
        with tabs[4]:
            _render_dev_tab()


if __name__ == "__main__":
    main()
