# vLLM 部署说明

119 受理服务自己不加载大模型权重。它作为客户端，请求本机 vLLM 的 OpenAI 接口 `http://127.0.0.1:8000/v1/chat/completions`。

本仓库没有 `vllm serve` 启动脚本。启动命令以本文为准。模型自带说明在权重目录的 `README.md`（官方示例是 8 卡、上下文 262144），119 实际用的是下面这一组较短的参数。

## 当前模型

| 项 | 值 |
| --- | --- |
| 权重目录 | `/home/cvmax/autodl-tmp/models/Qwen3.6-35B-A3B-FP8` |
| 格式 | Hugging Face（`config.json` + `*.safetensors`），不是 GGUF |
| vLLM | 单独 conda 环境，本机为 `0.31.0`（官方建议 `>= 0.19.0`） |
| 环境路径 | `/home/cvmax/autodl-tmp/conda/envs/vllm` |
| 监听 | `127.0.0.1:8000` |
| 本机显卡 | 两张 5090，`--tensor-parallel-size 2` |

代码里的默认模型名就是这个目录路径，见 `llm_extractor_119.py` 的 `DEFAULT_VLLM_MODEL`。不要另写 `--served-model-name`，否则客户端对不上。

## 换一台机器时先做这些

1. 安装 NVIDIA 驱动和 CUDA，确认 `nvidia-smi` 能看到卡。
2. 新建一个干净的 conda 环境，只装 vLLM，不要装进已经有 torch 的业务环境：

```bash
conda create -n vllm python=3.12 -y
conda activate vllm
pip install "vllm>=0.19.0"
```

3. 把整个模型目录拷过去（含 `config.json`、`tokenizer`、`chat_template.jinja`、全部 `safetensors`）。路径自定，下面用 `MODEL_DIR` 表示。
4. 按目标机器的显卡数量改 `--tensor-parallel-size`。本机是 2。单卡就写成 1。显存不够时先保持 `--max-model-len 4096` 和 `--language-model-only`，不要改成官方 README 里的 262144。

## 启动 vLLM

119 只做文字抽取，上下文 4096。加上 `--language-model-only` 是为了不加载视觉编码器，把显存留给 KV cache。

```bash
conda activate vllm
vllm serve "$MODEL_DIR" \
  --host 127.0.0.1 --port 8000 \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --language-model-only \
  --reasoning-parser qwen3 \
  --gpu-memory-utilization 0.90
```

思考模式由 119 的请求关掉（`chat_template_kwargs.enable_thinking=false`），启动命令里不用再加。

确认服务起来：

```bash
curl http://127.0.0.1:8000/v1/models
```

返回的 `id` 必须和下面的 `VLLM_MODEL` 完全一致。不写 `--served-model-name` 时，这个 `id` 就是 `vllm serve` 后面的目录路径。

## 启动 119

在另一个终端、用业务自己的 Python 环境（本机是 `qwen` 环境，不是 `vllm` 环境）：

```bash
cd /path/to/119_0904_addrflow
export LLM_BACKEND=vllm
export VLLM_BASE_URL=http://127.0.0.1:8000/v1
export VLLM_MODEL="$MODEL_DIR"
uvicorn sop_api_server:app --host 0.0.0.0 --port 8200
```

抽取只連 vLLM。不設 `VLLM_MODEL` 時，程式用 `/home/cvmax/autodl-tmp/models/Qwen3.6-35B-A3B-FP8`。換機器或換目錄後必須改成同一個路徑。

健康检查：`curl http://127.0.0.1:8200/health`。

## 换一个新模型

1. 新模型必须是 vLLM 能直接加载的 Hugging Face 目录（`config.json` 和 `*.safetensors`）。119 的抽取不会加载 GGUF。
2. 停掉旧的 `vllm serve`，用新目录重新执行上面的启动命令。
3. 把 `VLLM_MODEL` 改成同一个新目录，重启 `uvicorn`。
4. 再看一次 `/v1/models`，确认 `id` 与 `VLLM_MODEL` 相同。
5. Qwen3.6 这一类带思考的模型，保持 `--reasoning-parser qwen3`。119 会在请求里关闭思考；如果新模型没有这套模板，抽取结果里出现 `<think>` 时再按该模型的说明调整 parser。
