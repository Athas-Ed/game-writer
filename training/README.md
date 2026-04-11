## QLoRA + Transformers（学习实践用）

这一目录用于**学习/实践** Hugging Face Transformers 的微调流程（以 **QLoRA** 为主）。
它与主应用（Streamlit 写作工作台）解耦：不改动主流程、不要求每个用户都安装训练依赖。

### 推荐环境（Windows）

- **推荐**：WSL2（Ubuntu）+ NVIDIA CUDA（能最省心地用 `bitsandbytes`）
- **不推荐**：原生 Windows 直接跑 QLoRA（`bitsandbytes` 兼容性常见问题）

如果你只有 CPU，也可以先用脚本熟悉数据/参数结构，但训练会非常慢。

### 安装

在虚拟环境中执行（与项目根目录一致）：

```bash
pip install -e ".[train]"
```

### 训练（QLoRA SFT）

默认用一个很小的公开指令数据集做演示（首次会联网下载）：

```bash
python -m training.qlora_sft ^
  --model_name_or_path "Qwen/Qwen2.5-0.5B-Instruct" ^
  --dataset_name "tatsu-lab/alpaca" ^
  --output_dir "training_outputs/qwen2_5_0_5b_alpaca_qlora"
```

你也可以换成更适合中文/写作的数据集，或者后续把你自己的 `data/**/*.md` 转成指令数据再训练。

### 常见坑

- **显存不足**：把 `--per_device_train_batch_size` 调小、增大 `--gradient_accumulation_steps`，或改用更小模型（0.5B/1.5B）
- **bitsandbytes 报错**：优先在 WSL2 + CUDA 环境跑；确认 `nvidia-smi` 正常、CUDA/PyTorch 匹配
- **下载失败/证书/代理**：与主项目类似，可配置 `HTTP_PROXY/HTTPS_PROXY`；必要时设置 HF 镜像或离线缓存

