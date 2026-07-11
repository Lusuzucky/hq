# WOL Server — WOL 桥接服务

## 用途

运行在 VPS 上，将本地的 WOL 触发请求（`/tmp/wol_trigger` 文件写入）安全转发给路由器，由路由器发送实际的 WOL 魔术包唤醒 PC。

## 架构

```
adapter.py         wol-proxy.py       pc_utils.py
    │                    │                  │
    └──────────┬─────────┴──────────────────┘
               │ write("MAC\n")
               ▼
        /tmp/wol_trigger
               │ watch (poll every 1s)
               ▼
        wol-server.py  :19999  ◄── Ed25519 auth ──►  路由器客户端
                                                      │
                                                      │ 发送 WOL 魔术包
                                                      ▼
                                                     PC 唤醒
```

## 安全模型

- 路由器客户端通过 **Ed25519 挑战-应答** 认证
- 服务端发送随机 nonce，客户端用 usign 私钥签名后回传
- 服务端用 `/etc/wol.pub` 公钥验签，失败则断开连接
- 只有通过认证的长连接才会收到 WOL 指令

## 部署

### 1. 准备公钥

将路由器的 usign 公钥文件复制到 VPS：

```bash
# 路由器上：
cat /etc/wol.pub

# VPS 上：
# 粘贴内容到 /etc/wol.pub
```

### 2. 安装依赖和文件

```bash
pip3 install pynacl

cp infra/wol-server/wol-server.py /opt/wol-server.py
cp infra/wol-server/wol-server.service /etc/systemd/system/wol-server.service
```

### 3. 启动服务

```bash
systemctl daemon-reload
systemctl enable --now wol-server
```

## 触发方式

任何进程往 `/tmp/wol_trigger` 写入 MAC 地址即可触发：

```bash
echo "AA:BB:CC:DD:EE:FF" > /tmp/wol_trigger
```

wol-server 每秒检查该文件，读取到内容后立即通过已认证连接下发 `wake:<MAC>` 指令，然后删除文件。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `WOL_PORT` | 监听端口 | 19999 |
| `WOL_HEARTBEAT` | 心跳间隔（秒） | 60 |
| `WOL_PUBKEY` | usign 公钥文件路径 | `/etc/wol.pub` |

## 上层依赖

以下服务依赖 wol-server 运行：
- `wol-proxy@ollama` / `wol-proxy@honcho` — WOL-aware HTTP 代理
- `pc_utils.py` / Hermes adapter — 应用层 WOL 触发
