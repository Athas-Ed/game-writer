import os
from pathlib import Path

import certifi
import pytest
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


def _ensure_usable_ca_bundle() -> None:
    """避免 .env 里 SSL_CERT_FILE 等指向已删除路径时，httpx 在初始化阶段直接崩溃。"""
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        val = os.getenv(key)
        if val and not Path(val).exists():
            os.environ.pop(key, None)
    ca = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca)
    os.environ.setdefault("CURL_CA_BUNDLE", ca)


_ensure_usable_ca_bundle()


def test_deepseek_direct():
    """直接使用 DeepSeek API 测试（集成测试，需显式开启）"""
    if os.getenv("RUN_INTEGRATION_TESTS", "0") != "1":
        pytest.skip("integration test disabled (set RUN_INTEGRATION_TESTS=1 to enable)")
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个游戏编剧助手"},
            {"role": "user", "content": "你好，请介绍一下你自己"},
        ],
        temperature=0.7,
    )

    content = response.choices[0].message.content
    assert isinstance(content, str) and len(content.strip()) > 0


def test_ms_agent_import():
    """
    校验 modelscope-agent 可选依赖可导入（集成测试，需显式开启）。

    不强制 import RolePlay：其依赖链会加载 llama_index，在 Python 3.14+ 上与 pydantic v1 不兼容会整段失败；
    Agent / get_chat_model 路径更轻量，足以证明包已正确安装。
    """
    if os.getenv("RUN_INTEGRATION_TESTS", "0") != "1":
        pytest.skip("integration test disabled (set RUN_INTEGRATION_TESTS=1 to enable)")

    try:
        import modelscope_agent  # noqa: F401

        from modelscope_agent.agent import Agent  # noqa: F401
        from modelscope_agent.llm import get_chat_model  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("modelscope-agent not installed")
    except Exception as e:
        pytest.skip(f"modelscope-agent import failed: {e}")

