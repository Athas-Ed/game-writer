import os
from typing import Any, Dict


def get_llm_env_summary() -> Dict[str, Any]:
    key = os.getenv("DEEPSEEK_API_KEY") or ""
    if not key:
        masked = "未设置"
    elif len(key) <= 8:
        masked = "已设置（长度过短，请检查）"
    else:
        masked = f"{key[:4]}…{key[-4:]}"
    return {
        "api_key_status": masked,
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "proxy_configured": bool(os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")),
    }

