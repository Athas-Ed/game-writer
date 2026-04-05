# Game-writer：游戏编剧工作台（Streamlit + Tool/Skill Agent）

面向“游戏编剧/世界观设定”场景的个人工作台：用 **对话式 Agent** 串联 **设定库检索** 与 **技能插件**，把“写作、校对、导出、版本管理”等动作做成可重复的工作流。

- **我做了什么**
  - 约 **一周**内完成从 0→1：**技术选型、整体方案、主导落地**（AI 辅助开发：Cursor）。
  - **需求拆解、架构分层**；敲定 **JSON-only 协议**、工具/技能边界、**RAG 可选与降级**、skills 迭代等关键约束。
  - 对生成代码持续 **审阅、集成与回归**，保证功能可用、行为可控、结构可扩展。

- **交付物**
  - 可下载 **zip**：解压后按 README 配置 **`.env`**，**`run.bat` 一键启动**。
  - 使用者自备：**LLM API**；若需访问外网则自行配置 **代理**。

- **验收标准**
  - **`run.bat`** 可启动并正常打开网页端。
  - **`pytest` 全绿**。
  - **RAG 关闭**时核心能力仍可用（不依赖向量链路）。
  - **技能诊断**通过：Runner 可加载、**`run()`** 可调用。
  - 网页端实操：能生成指定内容并 **保存为 Markdown**。

## 核心亮点（面试官可快速扫读）

- **JSON-only ReAct**
  - 每步仅一个 JSON：`action`（调工具）或 `final`（收束输出）。
  - 读写/检索等真实动作须先 `action`，经 **Observation** 回写后再 `final`（避免未调用工具却声称已写入）。
  - 最大步数、历史截断与日志 → **可复现、可调试、可追踪**。
- **设定库证据检索**
  - `data/**/*.md` **分块 + 元数据**；关键词检索 + **SettingsRoute**（`list` / `files` / `chunks` / `search`）。
  - 结果带稳定 **`chunk_ref`**，便于证据驱动写作与改设定。
- **RAG 可选 + 降级**
  - 默认：**分块 + 关键词**；按需开 **Chroma + 本地 embedding**。
  - 依赖缺失、加载失败、证书等问题时 **自动退回关键词检索**，主流程不绑死向量能力。
- **工具注册**
  - 读/写/检索/技能/偏好等集中在统一 **registry**，入参协议一致（例：`WriteFile=相对路径|正文`）。
- **技能插件与 UI 闭环**
  - 约定 **`skills/*/SKILL.md` + `scripts/run.py`**（`run(input_text) -> str`），**增技能不改引擎**。
  - UI 自动扫描；中文别名、Runner 诊断；多方案结果可用按钮继续细化。

## Demo（先留占位）

> README 支持直接放截图/GIF（相对路径或外链都可以）。你确认要放之后，我再帮你补上素材与排版。

- 截图/GIF：`docs/demo.gif`（待补）
- 30 秒体验：见下方「快速开始（Docker）」。

## 功能概览

- **对话式 Agent**：根据你的需求选择工具/技能，必要时写入文件
- **资料库**：只读预览 `data/**/*.md`
- **技能目录**：扫描 `skills/*/SKILL.md` 并展示调用方式（含中文别名）
- **开发工具（可选）**：健康检查、API 最小请求测试、技能 Runner 诊断、RAG 开关等

## 内置技能一览

> 技能由 `skills/*/SKILL.md` 定义，运行入口由 `skills/*/scripts/run.py` 实现（约定 `run(input_text: str) -> str`）。

- `outline-writer`：生成剧情大纲（多方案）
- `dialogue-voice`：对白风格/口吻方案（多方案）
- `consistency-checker`：一致性检查（设定/角色/时间线等）
- `version-control`：版本/变更管理相关动作
- `setting-splitter`：将设定拆分成更可检索/可复用的结构

## 架构速览

```text
Streamlit UI (src/ui/streamlit_app.py)
  └─ run_agent(...)
      └─ Agent Engine (src/core/engine.py)  # JSON-only ReAct 循环
          ├─ Tool Registry (src/core/tool_registry.py)
          ├─ Skills Catalog / Runner (skills/*)
          └─ Data & Preferences
              ├─ data/**/*.md               # 设定库（只读预览 + 检索）
              └─ config/preferences.md      # 偏好（可选写入，受开关控制）
```

**Agent 对话主循环（示意）**：

```mermaid
graph LR
    A[用户输入] --> B[Agent 引擎<br/>JSON-only ReAct]
    B --> C{决策类型}
    C -->|action| D[工具/技能执行]
    D --> E[Observation 回写]
    E --> B
    C -->|final| F[输出结果]
    F --> G[Streamlit UI]
```

## 配置环境变量（.env）

项目使用 `.env`（由 `python-dotenv` 自动读取）来配置 LLM 访问。

也可以先复制模板：`.env.example -> .env`，再编辑成你的实际值。

至少包含：

```env
DEEPSEEK_API_KEY=你的_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

如你需要代理（例如访问外网需走本地代理），可以额外设置：

```env
HTTP_PROXY=http://127.0.0.1:26561
HTTPS_PROXY=http://127.0.0.1:26561
```

注意：请不要把真实 `.env` 配到公共仓库/聊天记录里。

可选：当对话里曾出现大段设定原文、且已拆分进 `data/` 后，Agent 引擎会**自动缩短**历史消息与多步回溯里的超长 JSON/Observation，减少重复计费。默认值一般够用；若要调整（字符数，`0` 表示不限制该项）：

```env
AGENT_HISTORY_MESSAGE_MAX_CHARS=4000
AGENT_SCRATCHPAD_ACTION_INPUT_MAX_CHARS=2500
AGENT_OBSERVATION_MAX_CHARS=16000
```

## 快速开始

适合面试官/快速体验：无需本地装 Python，只需要 Docker。

### 方式 A：拉取预构建镜像（最快）

先准备一个 `.env`（不要提交到仓库），并在当前目录准备一个 `data/` 文件夹（可为空）。

```bat
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  ghcr.io/athas-ed/game-writer:latest
```

浏览器打开：`http://localhost:8501`

### 方式 B：从源码构建镜像

```bat
docker build -t game-writer .
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  game-writer
```

### 方式 C：Docker Compose（更稳：只挂载 data）

```bat
docker compose up --build
```

停止并清理容器：

```bat
docker compose down
```

## 体验建议（给面试官/评审的 3 个入口）

- **写作**：在“对话”输入一句需求，例如“帮我写一个剧情大纲：主角在废弃车站发现一封旧信。”
- **设定库**：把设定放进 `data/`（如 `data/角色设定/`、`data/背景设定/`），在“资料库”里只读预览并检索。
- **技能**：在“技能”页查看技能说明与调用格式；支持中文别名。

## 本地运行（Windows / Python）

**版本锁定以 `pyproject.toml` 为准**（`requirements.txt` / `requirements-dev.txt` 仅作为可编辑安装入口，避免重复维护）。

### 依赖安装

1. 准备 Python（推荐 3.10+）
2. 创建虚拟环境：

   ```bat
   python -m venv venv
   ```

3. 安装项目与运行时依赖（二选一，等价）：

   ```bat
   venv\Scripts\python -m pip install -e .
   ```

   或：

   ```bat
   venv\Scripts\python -m pip install -r requirements.txt
   ```

4. 开发/测试依赖（可选）：

   ```bat
   venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

   等价于：

   ```bat
   venv\Scripts\python -m pip install -e ".[dev]"
   ```

### Windows 一键启动（已安装环境下）

> 前置条件：已创建 `venv/`，并在其中安装了至少 `python-dotenv` 与 `streamlit`（见上方“依赖安装”）。

直接运行：

```bat
run.bat
```

启动后浏览器打开：`http://localhost:8501`

### 手动启动（等价，适合排障）

```bat
venv\Scripts\python -m streamlit run src\ui\streamlit_app.py ^
  --server.address=localhost --browser.gatherUsageStats=false
```

## 使用方法

1. 在网页左侧选择模式：
   - 工作模式：聚焦聊天、资料库和技能
   - 开发模式：额外显示 API 测试与技能 Runner 检查
2. 在“对话”输入你的需求，例如：
   - “帮我写一个剧情大纲：主角在废弃车站发现一封旧信。”
3. Agent 会优先选择合适技能（见「内置技能一览」）。
4. 若技能需要读取本地设定，会从 `data/` 汇总读取相关 Markdown。

## 技能扩展说明

技能由 `skills/*/SKILL.md` 定义，运行入口由技能目录中的 `scripts/run.py` 实现：

- `skills/outline_writer/SKILL.md`：技能描述与使用示例
- `skills/outline_writer/scripts/run.py`：实现 `run(input_text: str) -> str`

Agent 通过 `RunSkill` 工具调用技能，并将返回内容展示到聊天里。

## 发布镜像（GHCR / GitHub Actions）

本仓库已提供工作流：`.github/workflows/docker-ghcr.yml`。

- 推送到 `master`：自动发布 `ghcr.io/athas-ed/game-writer:latest`
- 打 tag（例如 `v0.1.0`）并 push：自动发布 `ghcr.io/athas-ed/game-writer:v0.1.0`

```bat
git tag v0.1.0
git push origin v0.1.0
```

## 测试

项目包含单元测试；建议用 `pytest -q` 本地运行。

### 单元测试（默认，不走网络）

```bat
venv\Scripts\python -m pytest -q
```

### 集成测试（可选，会走网络/消耗额度）

本项目的集成测试放在 `tests/integration/` 下，默认跳过。需要显式开启：

```bat
set RUN_INTEGRATION_TESTS=1
venv\Scripts\python -m pytest -q
```

说明：
- 集成测试可能依赖真实的 `DEEPSEEK_API_KEY`、代理网络环境、以及第三方库版本兼容性。
- 若环境不满足，测试会以 `skip` 的形式跳过，不阻塞单元测试。
- 更多说明见：`tests/integration/README.md`

## Roadmap / Limitations（可选，待你决定是否保留）

> **Roadmap**：后续计划做什么（1–5 条即可，偏“用户价值/工程能力”）。  
> **Limitations**：当前版本的边界与已知限制（让评审更信任你“知道自己没做什么”，也便于面试时展开）。

- Roadmap（待补）
- Limitations（待补）

## 联系方式
- **Email**：`zhoumi383@foxmail.com`
- **GitHub**：`https://github.com/Athas-Ed/`
- **QQ**：`1392830348`
