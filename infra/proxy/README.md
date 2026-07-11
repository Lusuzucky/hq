# WOL Proxy — WOL-aware HTTP 反向代理

## 用途

为 PC 上的服务（Ollama、Honcho）提供透明 HTTP 反向代理。当 PC 离线时自动通过 WOL 唤醒，等待上线后重试请求，对调用方完全透明。

## 架构

```
VPS 上调用方               VPS (proxy)                 PC (synbox)
Hermes ──→ ollama:11435 ──→ wol-proxy@ollama ──→ 10.10.10.5:11434 (Ollama)
Hermes ──→ honcho:8001  ──→ wol-proxy@honcho ──→ 10.10.10.5:8000  (Honcho)
                                 │
                                 │ PC 离线时
                                 ├── 写 /tmp/wol_trigger
                                 ├── 等待 PC TCP 端口就绪
                                 └── retry 请求
```

## 部署

### 1. 安装文件

```bash
cp infra/proxy/wol-proxy.py /usr/local/bin/wol-proxy.py
cp infra/proxy/wol-proxy@.service /etc/systemd/system/wol-proxy@.service
mkdir -p /etc/wol-proxy
```

### 2. 配置环境变量

```bash
# Ollama 代理
cp infra/proxy/ollama.env.example /etc/wol-proxy/ollama.env
# 编辑 /etc/wol-proxy/ollama.env，填入真实 WOL_MAC

# Honcho 代理
cp infra/proxy/honcho.env.example /etc/wol-proxy/honcho.env
# 编辑 /etc/wol-proxy/honcho.env，填入真实 WOL_MAC
```

### 3. 启动服务

```bash
systemctl daemon-reload
systemctl enable --now wol-proxy@ollama
systemctl enable --now wol-proxy@honcho
```

## 工作流程

1. 收到 HTTP 请求 → 转发到 `PROXY_BACKEND`
2. 连接失败（PC 离线）→ 写 `/tmp/wol_trigger` 触发 WOL
3. 轮询 PC 的 11434/8000 端口，等待上线（最长 120s）
4. PC 上线后等待 5s grace period，重试请求
5. 最多重试 3 次，失败返回 502

HTTP 4xx/5xx 正常透传，不触发 WOL。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PROXY_LISTEN` | 代理监听地址 | 必填 |
| `PROXY_BACKEND` | PC 后端 URL | 必填 |
| `PC_IP` | PC 的 EasyTier IP | 必填 |
| `WOL_MAC` | PC 的 MAC 地址 | 必填 |
| `PROXY_CONNECT_RETRIES` | 连接重试次数 | 3 |
| `PROXY_RETRY_GRACE` | 上线后等待秒数 | 5 |
| `PC_BOOT_TIMEOUT` | PC 启动最长等待 | 120 |
| `PROXY_MAX_BODY` | 请求体最大字节数 | 10 MB |

## 依赖

- `wol-server.py` 必须已在运行（监听 `/tmp/wol_trigger`）
- Python 3 标准库，无额外依赖
