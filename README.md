# Personal Agent：游戏编剧工作台（Streamlit + Tool/Skill Agent）

面向“游戏编剧/世界观设定”场景的个人工作台：用 **对话式 Agent** 串联 **设定库检索** 与 **技能插件**，把“写作、校对、导出、版本管理”等动作做成可重复的工作流。

- **我做了什么**：在约一周时间内，我主导了该工作台从 0 到 1 的技术选型与整体方案设计，并采用 AI 辅助开发（Cursor）快速落地实现。我主要负责需求拆解、架构分层与关键约束（如 JSON-only Agent 协议、工具/技能边界、RAG 可选与降级策略）、测试与可交付形态（Windows 一键启动脚本、Docker、CI 镜像发布）。在实现过程中，我对 AI 生成代码进行持续审阅、集成与回归验证，确保功能可用、行为可控、结构可扩展。
- **交付物**：提供可下载的 zip 包（解压后按 README 配置 `.env`，使用 `run.bat` 一键启动；使用者需自行配置 LLM API 与网络代理）。
- **验收标准**：
  - `run.bat` 可一键启动并正常打开网页端
  - `pytest` 全绿
  - **RAG 关闭**时基础能力可用（不被向量依赖绑死）
  - 技能诊断通过（Runner 可加载、`run()` 可调用）
  - 网页端实操成功：生成指定内容并保存为 Markdown 文件

## 核心亮点（面试官可快速扫读）

- **可控的 Agent 引擎（JSON-only ReAct）**：模型每一步**只能输出一个 JSON**，且只能是 `action`（请求工具）或 `final`（最终输出）。涉及真实操作（读写文件/检索/技能执行）时，必须先 `action` 调工具并等待 **Observation** 回写（例如：未看到 `WriteFile` 的 Observation 之前不得在 `final` 声称已写入）。配合最大步数/历史轮数与 INFO/DEBUG 日志，整体 **可复现、可调试、可追踪**。
- **能力边界清晰的工具注册**：工具集中在统一 registry 中（读/写/检索/技能/偏好等），输入输出协议一致（例如 `WriteFile=相对路径|正文`），便于审计与扩展。
- **设定库“证据检索”底座**：对 `data/**/*.md` 做分块 + 元数据，支持关键词证据检索与结构化路由（files/chunks/search），输出附带稳定引用，便于“证据驱动”的写作与改设定。
- **RAG 做成“可选增强”且具备失败降级**：以“分块底座 + 关键词证据检索”为默认能力（输出自带证据与定位锚点 `chunk_ref`），在设定库变大/语义检索需求更强时再按需开启向量检索（Chroma + embedding）。启用时优先本地 embedding 模型；依赖缺失/加载失败/证书异常等会**自动降级**回关键词证据检索，避免“增强能力”绑死基础体验，强调稳健交付。
- **技能插件化 + UI 工作流闭环**：采用 `skills/*/SKILL.md` + `scripts/run.py` 的轻量插件协议（约定 `run(input_text: str) -> str`），新增技能**无需改动核心引擎**，UI 自动扫描展示；支持中文别名与 Runner 诊断（入口存在/可导入/`run()` 可调用）。多方案输出可在 UI 中按钮选择继续细化，把“生成内容”变成“可操作流程”。

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

## 快速开始（推荐 Docker）

适合面试官/快速体验：无需本地装 Python，只需要 Docker。

### 方式 A：拉取预构建镜像（最快）

先准备一个 `.env`（不要提交到仓库），并在当前目录准备一个 `data/` 文件夹（可为空）。

```bat
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  ghcr.io/athas-ed/personal-agent:latest
```

浏览器打开：`http://localhost:8501`

### 方式 B：从源码构建镜像

```bat
docker build -t personal-agent .
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  personal-agent
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

## 额外脚本（可选）

- `test.py`：用 `modelscope-agent` 方式发起测试（用于验证环境）

## 发布镜像（GHCR / GitHub Actions）

本仓库已提供工作流：`.github/workflows/docker-ghcr.yml`。

- 推送到 `master`：自动发布 `ghcr.io/athas-ed/personal-agent:latest`
- 打 tag（例如 `v0.1.0`）并 push：自动发布 `ghcr.io/athas-ed/personal-agent:v0.1.0`

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
- **简历**：`（待填：PDF/在线简历链接）`
- **Email**：`（待填）`
- **GitHub**：`（待填）`
- **作品集/博客**：`（可选，待填）`

