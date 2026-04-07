"""
游戏编剧综合工作台：对话 Agent + 资料浏览 + 技能目录 + 设置。
开发模式（含健康检查）可由侧边栏切换，或由环境变量 APP_MODE 锁定。
"""
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"
PREFERENCES_PATH = CONFIG_ROOT / "preferences.md"
DATA_ROOT = PROJECT_ROOT / "data"

from src.core.agent import (
    diagnose_skills,
    get_llm_env_summary,
    get_skills_catalog,
    run_agent,
)
from src.tools.file_tools import read_file
from src.ui.scheme_options import assistant_message_dict, message_scheme_options

def _app_mode_from_env() -> str:
    return os.getenv("APP_MODE", "").strip().lower()


def _init_session() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "dev_mode_choice" not in st.session_state:
        st.session_state.dev_mode_choice = False
    if "prefs_write_enabled" not in st.session_state:
        st.session_state.prefs_write_enabled = True
    if "rag_enabled" not in st.session_state:
        st.session_state.rag_enabled = False
    if "chat_scroll_nonce" not in st.session_state:
        st.session_state.chat_scroll_nonce = 0
    if "_pending_agent_prompt" not in st.session_state:
        st.session_state._pending_agent_prompt = None


def _run_agent_safe(
    prompt: str,
    *,
    max_steps: int,
    history_turns: int,
    conversation_history: list,
) -> str:
    try:
        return run_agent(
            prompt,
            max_steps=max_steps,
            conversation_history=conversation_history,
            history_turns=history_turns,
        )
    except httpx.TimeoutException:
        return (
            "LLM 请求超时（ReadTimeout）。\n\n"
            "建议：\n"
            "- 稍后重试（网络/代理波动时常见）\n"
            "- 或在 `.env` 中调大超时，例如设置 `LLM_TIMEOUT_READ=240`"
        )


def _inject_chat_ui_css() -> None:
    """
    让提问框贴底，避免长对话时需要反复滚动找输入框。
    注意：Streamlit 的 DOM 结构可能随版本变化；这里用 data-testid 做尽量稳的选择器。
    """
    st.markdown(
        """
<style>
/* 给页面底部留出空间，避免固定输入框遮挡内容 */
section.main > div.block-container {
  padding-bottom: 7.5rem;
}

/* 让 chat_input 与主内容区同宽（自动避开侧栏） */
div[data-testid="stChatInput"] {
  position: sticky;
  bottom: 0;
  z-index: 999;
  width: 100%;
  padding: 0.75rem 0 1rem 0;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(49, 51, 63, 0.14);
}

/* 深色模式背景适配 */
@media (prefers-color-scheme: dark) {
  div[data-testid="stChatInput"] {
    background: rgba(14, 17, 23, 0.92);
    border-top: 1px solid rgba(250, 250, 250, 0.12);
  }
}

/* 方案选择按钮行：与气泡对齐、略紧凑 */
div.scheme-choice-row {
  margin-top: 0.35rem;
  margin-bottom: 0.25rem;
}
div.scheme-choice-row button {
  font-size: 0.9rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _auto_scroll_to_chat_bottom() -> None:
    """
    在 Streamlit rerun 后，把视口滚到最新消息。
    通过 nonce 触发组件更新，避免被缓存。
    """
    nonce = int(st.session_state.chat_scroll_nonce)
    components.html(
        f"""
<div id="chat-bottom-anchor"></div>
<script>
  (function() {{
    const nonce = {nonce};
    // 给布局一点时间渲染再滚动
    setTimeout(() => {{
      const el = document.getElementById("chat-bottom-anchor");
      if (el && el.scrollIntoView) {{
        el.scrollIntoView({{behavior: "smooth", block: "end"}});
      }} else {{
        window.scrollTo(0, document.body.scrollHeight);
      }}
    }}, 60);
  }})();
</script>
        """,
        height=0,
        width=0,
    )


def _render_chat(max_steps: int, history_turns: int) -> None:
    st.subheader("对话")
    _inject_chat_ui_css()

    pending = st.session_state.get("_pending_agent_prompt")
    if pending is not None and str(pending).strip():
        prompt = str(pending).strip()
        st.session_state._pending_agent_prompt = None
        hist = st.session_state.messages[:-1] if st.session_state.messages else []
        with st.spinner("Agent 运行中…"):
            response = _run_agent_safe(
                prompt,
                max_steps=max_steps,
                history_turns=history_turns,
                conversation_history=hist,
            )
        st.session_state.messages.append(assistant_message_dict(response))
        st.session_state.chat_scroll_nonce += 1
        st.rerun()

    n = len(st.session_state.messages)
    last_idx = n - 1
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and idx == last_idx:
                opts = message_scheme_options(msg)
                if opts:
                    st.caption("点击选择方案（等同发送一条用户消息）：")
                    st.markdown('<div class="scheme-choice-row">', unsafe_allow_html=True)
                    cols = st.columns(len(opts))
                    for cj, opt in enumerate(opts):
                        with cols[cj]:
                            label = opt["label"]
                            help_txt = opt.get("preview") or ""
                            if st.button(
                                label,
                                key=f"scheme_pick_{idx}_{opt['id']}",
                                use_container_width=True,
                                help=help_txt[:300] if help_txt else None,
                            ):
                                # 仅 2 个方案：dialogue-voice；否则通常为 outline-writer（3 案）。
                                # 不得共用「展开该方案细节」，否则历史里仍有旧大纲时模型易误调用 outline-writer。
                                if len(opts) == 2:
                                    choice = (
                                        f"我选择{opt['label']}，请根据上一轮助手回复继续："
                                        "【对白】对选定方案润色、扩写（可加旁白与动作），需要保存时用 WriteFile 写入 "
                                        "data/关键对话/；不要使用 outline-writer / 大纲写手。"
                                    )
                                else:
                                    choice = (
                                        f"我选择{opt['label']}，请根据上一轮助手回复继续："
                                        "展开该方案细节（或按上一轮说明保存/细化）。"
                                    )
                                st.session_state.messages.append({"role": "user", "content": choice})
                                st.session_state._pending_agent_prompt = choice
                                st.session_state.chat_scroll_nonce += 1
                                st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

    # anchor：用于自动滚动到最新消息（必须在 messages 之后）
    st.markdown('<div id="chat-bottom-anchor"></div>', unsafe_allow_html=True)
    _auto_scroll_to_chat_bottom()

    if prompt := st.chat_input("输入需求，Agent 会选择工具或技能…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.chat_scroll_nonce += 1
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Agent 运行中…"):
                response = _run_agent_safe(
                    prompt,
                    max_steps=max_steps,
                    history_turns=history_turns,
                    conversation_history=st.session_state.messages[:-1],
                )
            st.markdown(response)
            st.session_state.messages.append(assistant_message_dict(response))
            st.session_state.chat_scroll_nonce += 1
        st.rerun()


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


def _norm_rel_posix(p: str) -> str:
    return (p or "").replace("\\", "/").strip()


def _data_rel(path: Path) -> str:
    try:
        return path.relative_to(DATA_ROOT).as_posix()
    except ValueError:
        return str(path)


def _render_data_breadcrumb(rel_dir: str) -> str:
    rel_dir = _norm_rel_posix(rel_dir).strip("/")
    parts = [p for p in rel_dir.split("/") if p]
    crumb_labels = ["data"] + parts
    crumb_paths = [""]  # "" 表示 data/
    acc = ""
    for part in parts:
        acc = f"{acc}/{part}" if acc else part
        crumb_paths.append(acc)

    cols = st.columns(len(crumb_labels))
    chosen: str | None = None
    for i, (label, pth) in enumerate(zip(crumb_labels, crumb_paths)):
        with cols[i]:
            if st.button(label, key=f"data_crumb_{i}_{pth}", use_container_width=True):
                chosen = pth
    return chosen if chosen is not None else rel_dir


def _list_data_dir(rel_dir: str) -> tuple[list[str], list[str]]:
    """
    返回 (subdirs, md_files)：
    - subdirs: 目录名（不含路径）
    - md_files: 相对 data/ 的路径（posix）
    """
    rel_dir = _norm_rel_posix(rel_dir).strip("/")
    dir_path = (DATA_ROOT / rel_dir) if rel_dir else DATA_ROOT
    if not dir_path.exists() or not dir_path.is_dir():
        return ([], [])

    subdirs: list[str] = []
    md_files: list[str] = []
    for p in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
        if p.is_dir():
            subdirs.append(p.name)
        elif p.is_file() and p.suffix.lower() == ".md":
            md_files.append(_data_rel(p))
    return (subdirs, md_files)


def _render_data_tab() -> None:
    st.subheader("资料库")
    st.caption("按目录分层检索 `data/` 下的 Markdown（只读预览）。")

    if not DATA_ROOT.exists():
        st.info("未找到 `data/` 目录。可在项目根下创建 `data/角色设定/`、`data/背景设定/` 等目录。")
        return

    if "data_browser_dir" not in st.session_state:
        st.session_state.data_browser_dir = ""
    if "data_browser_selected" not in st.session_state:
        st.session_state.data_browser_selected = ""

    rel_dir = _norm_rel_posix(st.session_state.data_browser_dir)

    col_left, col_right = st.columns([0.42, 0.58], vertical_alignment="top")
    with col_left:
        st.markdown("##### 目录导航")
        rel_dir = _render_data_breadcrumb(rel_dir)
        st.session_state.data_browser_dir = rel_dir

        query = st.text_input("过滤（目录/文件名）", value="", placeholder="例如：背景设定 / 关键地点 / 岚")
        query_norm = query.strip().lower()

        subdirs, md_files = _list_data_dir(rel_dir)
        if query_norm:
            subdirs = [d for d in subdirs if query_norm in d.lower()]
            md_files = [f for f in md_files if query_norm in f.lower()]

        if rel_dir:
            parent = "/".join([p for p in rel_dir.split("/") if p][:-1])
            if st.button("返回上级", use_container_width=True):
                st.session_state.data_browser_dir = parent
                st.session_state.data_browser_selected = ""
                st.rerun()

        if subdirs:
            with st.expander("子目录", expanded=True):
                for d in subdirs:
                    if st.button(d, key=f"data_dir_{rel_dir}_{d}", use_container_width=True):
                        st.session_state.data_browser_dir = f"{rel_dir}/{d}".strip("/")
                        st.session_state.data_browser_selected = ""
                        st.rerun()
        else:
            st.caption("当前目录无子目录。")

        st.markdown("##### 文件")
        if not md_files:
            st.info("当前目录未找到 Markdown 文件。")
        else:
            labels = [f.split("/")[-1] if "/" in f else f for f in md_files]
            default_idx = 0
            if st.session_state.data_browser_selected in md_files:
                default_idx = md_files.index(st.session_state.data_browser_selected)
            selected = st.selectbox(
                "选择文件",
                options=md_files,
                index=default_idx,
                format_func=lambda p: labels[md_files.index(p)],
            )
            st.session_state.data_browser_selected = selected

    with col_right:
        st.markdown("##### 内容预览")
        selected = _norm_rel_posix(st.session_state.data_browser_selected)
        if not selected:
            st.info("在左侧选择一个文件进行预览。")
            return
        rel = f"data/{selected}".replace("//", "/")
        content = read_file(rel)
        st.text_area("内容", value=content, height=520, disabled=True)


def _render_skills_tab() -> None:
    st.subheader("技能")
    catalog = get_skills_catalog()
    if not catalog:
        st.info("未发现技能。请在 `skills/*/SKILL.md` 下添加技能。")
        return
    for name, meta in sorted(catalog.items(), key=lambda x: x[0]):
        with st.expander(f"**{name}**", expanded=False):
            st.markdown(meta.get("description", "—"))
            als = meta.get("aliases") or []
            if isinstance(als, list) and als:
                st.caption("中文别名（可直接用于 RunSkill 技能名）：" + "、".join(str(a) for a in als))
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

    st.markdown("##### RAG 增强模式")
    st.session_state.rag_enabled = st.checkbox(
        "启用 RAG 增强（向量检索 + 上下文增强）",
        value=st.session_state.rag_enabled,
        help=(
            "默认关闭。关闭时 VectorSearch 会退回关键词证据检索（SearchDocs 的分块索引）；"
            "开启后才使用 Chroma + embedding 的向量语义检索（失败仍会自动降级）。"
        ),
    )
    os.environ["RAG_ENABLED"] = "1" if st.session_state.rag_enabled else "0"

    # RAG 开启时，优先引导使用项目内离线本地模型，避免在线拉取失败（证书/代理环境常见）。
    default_local_model = str(PROJECT_ROOT / "models" / "bge-small-zh-v1.5")
    if st.session_state.rag_enabled:
        os.environ.setdefault("VECTOR_EMBED_MODEL", default_local_model)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    st.caption(
        "当前 RAG 环境变量："
        f" RAG_ENABLED={os.environ.get('RAG_ENABLED','0')}"
        f" | VECTOR_EMBED_MODEL={os.environ.get('VECTOR_EMBED_MODEL','(unset)')}"
        f" | HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE','(unset)')}"
        f" | TRANSFORMERS_OFFLINE={os.environ.get('TRANSFORMERS_OFFLINE','(unset)')}"
    )

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
    # RAG 默认关闭；仅开发工具面板打开时写入环境变量（但此处也保持一致，避免跨 rerun 丢失）
    os.environ["RAG_ENABLED"] = "1" if st.session_state.rag_enabled else "0"

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
