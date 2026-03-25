import os

import pytest
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


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
    """仅测试 modelscope-agent 是否能正常导入（集成测试，需显式开启）"""
    if os.getenv("RUN_INTEGRATION_TESTS", "0") != "1":
        pytest.skip("integration test disabled (set RUN_INTEGRATION_TESTS=1 to enable)")

    try:
        import modelscope_agent  # noqa: F401

        from modelscope_agent.agent import AgentExecutor  # noqa: F401
        from modelscope_agent.agents import RolePlay  # noqa: F401
        from modelscope_agent.llm import LLMFactory  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("modelscope-agent not installed")
    except Exception as e:
        pytest.skip(f"modelscope-agent import failed: {e}")

