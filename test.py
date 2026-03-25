import os
import sys
import types
from collections.abc import Iterator

import certifi
from langchain_core.documents import Document
from dotenv import load_dotenv

# 兼容旧版 modelscope_agent 对 langchain.schema 的导入路径。
langchain_schema = types.ModuleType("langchain.schema")
langchain_schema.Document = Document
sys.modules.setdefault("langchain.schema", langchain_schema)

# 降低 modelscope-agent 日志级别，避免 INFO 中输出敏感信息。
os.environ.setdefault("LOG_LEVEL", "ERROR")

# 优先使用系统证书（Windows 证书库），其次回退到 certifi。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())

from modelscope_agent.agents.role_play import RolePlay

load_dotenv()

# 当前安装版本无 create_agent_skill，改用 RolePlay 直接创建 Agent。
agent = RolePlay(
    llm={
        "model": "deepseek-chat",
        "model_server": "openai",
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "api_base": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    },
    instruction="你是一个写作助手。",
    stream=False,
)

# 测试
response = agent.run(
    "帮我创建一个名叫林夕的女主角，设定是温柔学姐，写一段200字的出场描写"
)

try:
    if isinstance(response, Iterator):
        response = "".join(str(chunk) for chunk in response)
    print("结果：", response)
except Exception as e:
    print("调用失败：", e)
    print("提示：如果报 SSL 证书错误，请在系统中安装/更新根证书，或检查代理证书配置。")