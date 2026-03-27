import os
import json
import httpx
import time
from dotenv import load_dotenv

load_dotenv()

proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
api_key = os.getenv("DEEPSEEK_API_KEY")
base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

def _build_timeout() -> httpx.Timeout:
    # 默认给较宽松的读超时，避免生成较长内容时频繁 ReadTimeout
    connect = float(os.getenv("LLM_TIMEOUT_CONNECT", "10"))
    read = float(os.getenv("LLM_TIMEOUT_READ", "180"))
    write = float(os.getenv("LLM_TIMEOUT_WRITE", "30"))
    pool = float(os.getenv("LLM_TIMEOUT_POOL", "30"))
    return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)


TIMEOUT = _build_timeout()
RETRIES = int(os.getenv("LLM_RETRIES", "2"))
RETRY_BACKOFF_BASE = float(os.getenv("LLM_RETRY_BACKOFF_BASE", "0.8"))

# 创建带代理且禁用 SSL 验证的客户端
if proxy:
    client = httpx.Client(proxy=proxy, verify=False, timeout=TIMEOUT)
else:
    client = httpx.Client(verify=False, timeout=TIMEOUT)

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
    last_err: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = e
            if attempt >= RETRIES:
                raise
            time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
        except httpx.HTTPStatusError as e:
            # 5xx/429 可重试；其他状态码直接抛出
            last_err = e
            status = getattr(e.response, "status_code", None)
            if status in {429, 500, 502, 503, 504} and attempt < RETRIES:
                time.sleep(RETRY_BACKOFF_BASE * (2**attempt))
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("LLM 调用失败：未知错误")