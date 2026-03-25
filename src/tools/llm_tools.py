import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
api_key = os.getenv("DEEPSEEK_API_KEY")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# 创建带代理且禁用 SSL 验证的客户端
if proxy:
    client = httpx.Client(proxy=proxy, verify=False, timeout=60.0)
else:
    client = httpx.Client(verify=False, timeout=60.0)

def llm_generate(prompt: str, temperature: float = 0.7) -> str:
    """调用 DeepSeek API 生成文本"""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }
    response = client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]