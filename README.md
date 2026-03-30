# 游戏编剧工作台

一个基于 Streamlit 的“游戏编剧助手”工作台：支持对话式 Agent（ReAct 循环），从本地 `data/` 读取 Markdown 资料，并通过 `skills/` 目录扩展技能（例如 `outline-writer` 生成剧情大纲）。

## 功能概览

- 聊天式 Agent：根据你的需求调用工具/技能，必要时写入文件
- 资料库：只读预览 `data/**/*.md`
- 技能目录：扫描 `skills/*/SKILL.md` 并展示调用方式
- 开发工具（可选）：健康检查、API 最小请求测试等

## 依赖安装

**版本锁定以 `pyproject.toml` 为准**（`requirements.txt` / `requirements-dev.txt` 仅一行可编辑安装，避免与 `pyproject.toml` 重复维护）。

1. 准备 Python（推荐 3.10+；Docker 镜像使用 3.11）
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

## 配置环境变量（.env）

项目使用 `.env`（由 `python-dotenv` 自动读取）来配置 LLM 访问。

也可以先复制模板：` .env.example -> .env`，再编辑成你的实际值。

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

## 运行方式

### Windows 一键启动

直接运行：

```bat
run.bat
```

启动后浏览器打开：`http://localhost:8501`

### Docker（可选）

在项目根目录构建并运行（需自行准备 `.env`，勿提交到仓库）：

```bat
docker build -t personal-agent .
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  personal-agent
```

说明：

- 将本地 `data/` 挂载到容器内 `/app/data`，便于读写资料。
- API 密钥等通过 `--env-file .env` 或 `-e KEY=val` 传入。
- 若修改了 `skills/` 或 `config/`，可重新 `docker build`，或额外挂载 `-v "%CD%\skills:/app/skills"` 等目录做开发调试。

#### Docker Compose（更稳：只挂载 `data/`）

一条命令启动（需自行准备 `.env`）：

```bat
docker compose up --build
```

停止并清理容器：

```bat
docker compose down
```

#### 预构建镜像（面试官拉取即跑）

你可以把镜像发布到镜像仓库，让面试官无需源码就能跑。

**推荐：GitHub Container Registry（GHCR）+ GitHub Actions 自动发布**（本仓库已提供工作流：`.github/workflows/docker-ghcr.yml`）。

- **发布方式（你自己做）**：
  - 推送到 `master`：自动发布 `ghcr.io/athas-ed/personal-agent:latest`
  - 打 tag（例如 `v0.1.0`）并 push：自动发布 `ghcr.io/athas-ed/personal-agent:v0.1.0`

```bat
git tag v0.1.0
git push origin v0.1.0
```

- **运行命令（面试官侧）**：

```bat
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  ghcr.io/athas-ed/personal-agent:v0.1.0
```

也可以直接跑最新版（不固定版本）：

```bat
docker run --rm -p 8501:8501 ^
  -v "%CD%\data:/app/data" ^
  --env-file .env ^
  ghcr.io/athas-ed/personal-agent:latest
```

建议在 README 里写死一个“面试官一键命令”，并在发布时同步 tag（例如 `v0.1.0`、`latest`）。

### 手动启动（等价）

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
3. Agent 会优先选择合适技能（当前内置：`outline-writer`）。
4. 若技能需要读取本地设定，会从 `data/` 汇总读取相关 Markdown。

## 技能扩展说明

技能由 `skills/*/SKILL.md` 定义，运行入口由技能目录中的 `scripts/run.py` 实现：

- `skills/outline_writer/SKILL.md`：技能描述与使用示例
- `skills/outline_writer/scripts/run.py`：实现 `run(input_text: str) -> str`

Agent 通过 `RunSkill` 工具调用技能，并将返回内容展示到聊天里。

## 额外脚本（可选）

- `test.py`：用 `modelscope-agent` 方式发起测试（用于验证环境）

## 测试

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

