# 04 — Idle Nudge（空闲主动联系）+ Silent Skip 哨兵

## 功能

用户长时间未发言时，AI 主动发消息联系。随机间隔（20–90 分钟可配置），夜间勿扰（北京时间 02:00–07:30），连续未回复上限（默认 3 次）。

`__SILENT__` 哨兵配合使用：agent 收到 nudge 后如果决定不打扰，回复 `__SILENT__` 即可静默跳过，不会向 QQ 发送任何消息。

配合 skill 文件：`hermes/skills/qq-idle-nudge/SKILL.md`

## 涉及文件

`gateway/platforms/qqbot/adapter.py`

## 前置修改

`timedelta` 导入：`_idle_nudge_loop()` 中 `timezone(timedelta(hours=8))` 需要 `timedelta`。

```python
from datetime import datetime, timezone, timedelta
```

## 实现细节

### 1. `__init__` 配置读取

```python
self._idle_nudge_enabled = _env_bool("QQ_IDLE_NUDGE_ENABLED")
self._idle_nudge_min_minutes = max(1, _env_int("QQ_IDLE_NUDGE_MIN_MINUTES") or 20)
self._idle_nudge_max_minutes = max(min_minutes + 1, _env_int("QQ_IDLE_NUDGE_MAX_MINUTES") or 90)
self._idle_nudge_max_consecutive = max(0, _env_int("QQ_IDLE_NUDGE_MAX_CONSECUTIVE") or 3)
self._idle_nudge_prompt = os.getenv("QQ_IDLE_NUDGE_PROMPT", "") or default_prompt
```

默认 prompt 包含防重复策略和 `__SILENT__` 跳过说明：

```
如果当前时段不适合打扰用户（深夜、用户可能忙等），
只回复 __SILENT__（注意是双下划线）即可跳过本轮，不会发送任何消息给用户。
```

### 2. `_idle_nudge_loop()` — 后台协程

每 30 秒扫描一次：

- **夜间检查**：北京时间 02:00–07:30 → 重置所有聊天计时器，不发送 nudge
- **跳过活跃自动继续的会话**：`chat_id in _auto_continue_timers` 时跳过
- **随机阈值**：每个 chat 生成 `[min_minutes, max_minutes]` 随机空闲时间，达到后才 nudge
- **防重复**：两次 nudge 间隔 ≥ min_s，避免短时间内连续打扰
- **连续上限**：连续 N 次未收到回复后停止，等用户说话再重置
- **dispatch**：构造 internal `MessageEvent`，通过 `handle_message()` 投递给 agent

nudge 消息包含当前北京时间，供 agent 选择上下文合适的策略（早安/午餐/晚安等）。

### 3. `handle_message()` — 活动记录

```python
chat_id = event.source.chat_id if event.source else None
if chat_id and not getattr(event, "internal", False):
    self._last_user_activity[chat_id] = time.time()
    self._idle_nudge_consecutive.pop(chat_id, None)  # 用户回复 → 重置计数
```

仅记录非 internal 事件（真正的用户消息），nudge 自身不重置倒计时。

### 4. connect() / disconnect() — 任务生命周期

- `connect()` 中：如果 `_idle_nudge_enabled`，`asyncio.create_task(self._idle_nudge_loop())`
- `disconnect()` 中：cancel idle nudge task

### 5. `send()` — `__SILENT__` 哨兵

在空内容检查之后、MEDIA 提取之前插入：

```python
if content.strip() == "__SILENT__":
    return SendResult(success=True)
```

整个 content 完全等于 `__SILENT__` 时才拦截，避免正常对话中出现该字符串被误杀。

## 环境变量

```bash
QQ_IDLE_NUDGE_ENABLED=true          # 启用
QQ_IDLE_NUDGE_MIN_MINUTES=20        # 最短空闲（默认 20）
QQ_IDLE_NUDGE_MAX_MINUTES=90        # 最长空闲（默认 90）
QQ_IDLE_NUDGE_MAX_CONSECUTIVE=3     # 连续未回复上限（0=不限）
QQ_IDLE_NUDGE_PROMPT="..."          # 自定义 prompt（可选）
```

## 外部依赖

- **11-wol**（待开发）：`_wake_pc_and_wait()` — nudge dispatch 前唤醒 PC
