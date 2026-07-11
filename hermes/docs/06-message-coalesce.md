# 06 — 消息合并（Coalesce）

## 功能

用户在 N 秒内连续发送多条消息时，adapter 合并为一条再交给 agent，避免 agent 正在处理时被新消息打断。

斜杠命令始终立即处理，不参与合并。

## 涉及文件

`gateway/platforms/qqbot/adapter.py`

## 改动

### 类属性 — `COALESCE_DELAY`

```python
COALESCE_DELAY: float = 10.0  # seconds; 0 = disabled
```

默认 10 秒窗口。通过 `QQ_COALESCE_DELAY_SECONDS` 环境变量覆盖，设为 0 禁用合并。

### `__init__` — 配置读取

```python
_coalesce_raw = os.getenv("QQ_COALESCE_DELAY_SECONDS", "").strip()
if _coalesce_raw:
    try:
        self.COALESCE_DELAY = max(0.0, float(_coalesce_raw))
    except ValueError:
        pass
self._coalesce_timers: Dict[str, asyncio.Task] = {}
self._coalesce_events: Dict[str, MessageEvent] = {}
```

### `handle_message()` — 合并判断

新消息到达时：
- 斜杠命令 → 取消等待中的合并，立即 dispatch
- 已有合并计时器 → 取消旧计时器，累积消息文本（`\n` 拼接），合并 `media_urls` / `media_types`，更新 `message_type`，重启计时器
- 无计时器 → 存储 event，启动计时器，到期后 dispatch

**图片 + 文字合并**：先发图再发文字时，图的 `media_urls` 和 `media_types` 会追加到 pending event，`message_type` 根据合并后的 media 重新计算，确保图片不丢失。

### `_coalesce_dispatch(chat_id)`

等待 `COALESCE_DELAY` 秒后从 dict 中取出累积的 event，调用 `super().handle_message(event)` 进入正常处理流程。

`COALESCE_DELAY <= 0` 时跳过 sleep，立即 dispatch。

### `_cancel_coalesce(chat_id)`

取消计时器并清理两个 dict。

### `disconnect()` — 清理

断开连接时取消所有等待中的 coalesce 计时器。

## 环境变量

```bash
QQ_COALESCE_DELAY_SECONDS=10   # 默认 10 秒
QQ_COALESCE_DELAY_SECONDS=0    # 禁用合并
```

## 重新打补丁

搜索 "coalesce" 找到相关代码。
