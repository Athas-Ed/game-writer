# 可选容器运行：构建后映射 data/ 与 .env，见 README「Docker」。
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先复制元数据与源码，利用层缓存
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install --no-cache-dir -e .

# 技能与配置在运行时由卷挂载或 COPY；镜像内带一份默认目录结构
COPY skills ./skills
COPY config ./config
RUN mkdir -p data && touch data/.gitkeep

EXPOSE 8501

ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

CMD ["streamlit", "run", "src/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
