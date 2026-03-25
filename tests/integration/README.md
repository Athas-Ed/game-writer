# 集成测试说明（Integration Tests）

本目录下的测试会访问外部服务/网络环境（例如 DeepSeek API），**默认跳过**，需要显式开启。

## 如何运行

在项目根目录执行：

```bat
set RUN_INTEGRATION_TESTS=1
venv\Scripts\python -m pytest -q
```

## 必要环境变量

- `DEEPSEEK_API_KEY`: DeepSeek API Key（必需）
- `DEEPSEEK_BASE_URL`: 可选，默认 `https://api.deepseek.com/v1`
- `HTTP_PROXY` / `HTTPS_PROXY`: 可选（如你的网络需要代理）

## 注意事项

- **会消耗额度**：部分测试会发起真实请求。
- **可能受环境影响**：网络/代理/证书/第三方依赖版本（例如 `modelscope-agent` 的依赖链）都会影响结果。
- 约定：当环境不满足时，测试应使用 `pytest.skip(...)` 跳过，而不是让单元测试失败。

