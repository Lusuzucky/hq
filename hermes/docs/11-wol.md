# 11 — Wake-on-LAN（PC 唤醒）

## 功能

用户发消息或 idle-nudge 触发时，自动通过 Wake-on-LAN 唤醒目标 PC，确保 honcho 记忆服务可用。

**两种策略**：

| 场景 | 方法 | 行为 |
|------|------|------|
| 用户消息（新 coalesce 窗口） | `_wake_pc()` | fire-and-forget，daemon 线程写入 trigger 文件，不阻塞 |
| Idle Nudge | `_wake_pc_and_wait()` | 触发 WOL 后轮询 PC TCP 端口，最长 90s，确保 honcho 在线 |

## 涉及文件

`gateway/platforms/qqbot/adapter.py`

## 实现细节

### 1. `_write_wol_trigger()` — 模块级函数

```python
def _write_wol_trigger(mac: str) -> None:
    WOL_TRIGGER = "/tmp/wol_trigger"
    try:
        with open(WOL_TRIGGER, "w") as f:
            f.write(mac + "\n")
    except Exception:
        pass
```

写入 `/tmp/wol_trigger`，由 `wol-server.py` 监听并发送 WOL 包给路由器。

### 2. `_wake_pc()` — fire-and-forget

```python
def _wake_pc(self) -> None:
    mac = self._wol_mac
    if not mac:
        return
    import threading
    threading.Thread(target=_write_wol_trigger, args=(mac,), daemon=True).start()
```

后台线程写入 trigger 文件，不阻塞事件循环。MAC 为空时直接返回。

### 3. `_wake_pc_and_wait()` — 等待就绪

```python
async def _wake_pc_and_wait(self, timeout: int = 90) -> bool:
```

- 先写 trigger 文件发 WOL 信号
- 通过 `asyncio.to_thread()` 将阻塞式 TCP 轮询放入线程池
- 每 3 秒尝试 `socket.create_connection()` 连接 PC 的 `PC_HEALTH_PORT`
- 上线返回 `True`，超时返回 `False`

### 4. `__init__` — 配置读取

```python
self._wol_mac = os.getenv("WOL_MAC", "").strip()
self._wol_pc_ip = os.getenv("PC_IP", "10.10.10.5").strip()
self._wol_pc_port = int(os.getenv("PC_HEALTH_PORT", "8188"))
```

## 调用点

- `handle_message()` — 新 coalesce 窗口的第一条用户消息（`else` 分支）→ `self._wake_pc()`
- `_idle_nudge_loop()` — nudge dispatch 前 → `await self._wake_pc_and_wait()`

## 环境变量

```bash
WOL_MAC="d8:43:ae:2d:92:3d"     # 目标 PC 的 MAC 地址（必填）
PC_IP="10.10.10.5"               # PC 的 EasyTier IP（默认 10.10.10.5）
PC_HEALTH_PORT=8188              # 健康检查 TCP 端口（默认 8188）
```

## 依赖

- `wol-server.py` — 运行在 VPS 上，监听 `/tmp/wol_trigger` 文件变化，通过 Ed25519 认证后向路由器下发 WOL 指令
- `wol-proxy.py` — 运行在 VPS 上，为 Ollama/Honcho 提供 WOL-aware HTTP 反向代理
- `pc_utils.py`（`plugins/`）— WOL 共享模块（供 ComfyUI/GPT-SoVITS 插件使用）

## 重新打补丁

搜索 "wol" 或 "wake_pc" 找到：
1. `_write_wol_trigger()` 函数
2. `_wake_pc()` 方法
3. `_wake_pc_and_wait()` 方法
4. `__init__` 中的 WOL 配置
5. `handle_message()` 中的 `_wake_pc()` 调用
6. `_idle_nudge_loop()` 中的 `_wake_pc_and_wait()` 调用
