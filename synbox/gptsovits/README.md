# GPT-SoVITS GPU 热迁移 & 自动生命周期管理

在 GPT-SoVITS API 上实现 ComfyUI 风格的"闲时自动释放显存、请求时自动载入"。

## 修改的文件

| 文件 | 改动 |
|------|------|
| `api_v2.py` | ModelGuard、对称清 cache、加强显存回收、save=False、cuBLAS workspace 清理 |
| `TTS.py` | `set_device()` 补 `text_preprocessor.device` 同步 + `sv_model` 重建 |

## 部署

```bash
# 1. 传输文件到远程
scp api_v2.py root@10.10.10.5:/home/hermes/GPT-SoVITS/api_v2.py
scp TTS.py root@10.10.10.5:/home/hermes/GPT-SoVITS/GPT_SoVITS/TTS_infer_pack/TTS.py

# 2. 确保设备配置为 cuda（首次部署需要）
ssh root@10.10.10.5 "sed -i 's/device: cpu/device: cuda/' /home/hermes/GPT-SoVITS/GPT_SoVITS/configs/tts_infer.yaml"

# 3. 重启服务
ssh root@10.10.10.5 "systemctl restart gpt-sovits"
```

## 工作原理

```
启动 → GPU (模型载入, ~3 GB 显存)

  ↓ 请求到达
ModelGuard.acquire()
  ├─ 取消 pending offload
  ├─ 如果模型在 CPU → 自动 reload 到 GPU (2-3s)
  └─ 计数 +1

  ↓ 推理 (0.6s 非流式 / 流式持续)

ModelGuard.release()
  ├─ 计数 -1
  └─ 如果无活跃请求 → 调度延迟 offload (默认 3s)

  ↓ 空闲 N 秒
_do_gpu_offload()
  ├─ set_device(cpu)  → 模型参数移回 CPU
  ├─ 清空 prompt_cache  → 避免 device mismatch
  ├─ gc + empty_cache x2
  ├─ _cuda_clearCublasWorkspaces  → 释放 cuBLAS workspace
  └─ 显存释放到 ~600 MB
```

## API 端点

### 推理（自动管理生命周期）

```bash
# GET
curl "http://10.10.10.5:9880/tts?text=你好&emotion=普通&text_lang=zh"

# POST
curl -X POST http://10.10.10.5:9880/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "你好", "emotion": "普通", "text_lang": "zh"}'
```

### 状态查询

```bash
curl http://10.10.10.5:9880/status
# {"device":"cuda","active_requests":0,"offload_delay":3.0,"pending_offload":false}
```

### 调整空闲超时

```bash
curl "http://10.10.10.5:9880/set_offload_delay?seconds=10"  # 10 秒后 offload
curl "http://10.10.10.5:9880/set_offload_delay?seconds=0"   # 请求结束立即 offload
```

### 手动控制

```bash
curl http://10.10.10.5:9880/gpu_offload   # 立即卸载到 CPU
curl http://10.10.10.5:9880/gpu_reload    # 立即加载到 GPU
```

## 修复的 Bug

1. **device mismatch** — `set_device()` 搬了 6 个模型但漏了 `sv_model`（ProPlus 模型），且 `text_preprocessor.device` 未同步
2. **prompt_cache 残留在旧 device** — offload/reload 时未完整清空，导致 "Expected all tensors to be on the same device" 报错
3. **重复的 `/gpu_reload` 端点** — 代码里有两份，其中一份 cache 清了但不完整
4. **`/reload_config` 缺少装饰器** — `@APP.get` 掉了

## 环境要求

- 已在 synbox (10.10.10.5) 上部署
- RTX 4060 8GB
- PyTorch 2.6.0 + CUDA 12.4
- systemd 服务: `gpt-sovits`
- 启动参数: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
