# 01 — 段落自动分割 + 打字延迟

## 功能

Agent 回复时，按双空行 `\n\n` 拆分段落为独立 QQ 消息，每条消息间加入打字延迟，模拟真人聊天节奏。

**fenced code block 保护**：`💭 Reasoning:\n```...``` 包裹的推理块内部不拆分。

## Agent 文本的三条发送路径

Hermes Gateway 中 Agent 的文本根据所处阶段走不同路径到达 `adapter.send()`：

| # | 路径 | 时机 | meta 值 |
|---|------|------|---------|
| 1 | Agent 内部 `send_message` 工具 | tool call **之前**的文本 | `None` |
| 2 | `_process_message_background` | tool call **之后**的最终回复 | `{notify: True}` |
| 3 | `GatewayStreamConsumer` | 流式输出（QQ 平台 streaming 关闭，不使用）| 动态构建 |

## 分割策略

采用「**默认分割，显式豁免**」策略，确保三条路径全被覆盖：

- 只要 `\n\n` 存在就分割
- 仅当 metadata 标记 `non_conversational: True` 时不分割（系统命令回复）

## 涉及文件

| 文件 | 改动 |
|------|------|
| `gateway/platforms/qqbot/adapter.py` | `_split_preserving_fences()` + send() 中的 split loop |
| `gateway/platforms/base.py` | `_mark_notify_metadata()` + 命令回复标记 `non_conversational` |
| `tools/send_message_tool.py` | `_send_via_adapter()` 加 `message_category: "agent"` |

## 改动详情

### 1. adapter.py — `_split_preserving_fences()` 函数

状态机识别 `\`\`\`` fenced block，block 内的 `\n\n` 不切割。插入在 `class QQAdapter` 之前。

### 2. adapter.py — `send()` 方法

```python
# 分割条件：默认分割，除非显示标记为 non_conversational
_is_system = (metadata or {}).get("non_conversational") if metadata else False
split_ok = split_paragraphs or not _is_system
if split_ok:
    paragraphs = _split_preserving_fences(content)
    ...
```

关键变更：从「只有 `message_category=="agent"` 才分」改为「没标记 `non_conversational` 就分」。
`meta=None`（路径 1）时 `_is_system=False`，正常分割。

### 3. adapter.py — `send()` 签名

```python
async def send(self, chat_id, content, reply_to=None, metadata=None,
               split_paragraphs=False) -> SendResult:
```

新增 `split_paragraphs` 参数供显式控制。

### 4. adapter.py — `connect()` 签名

```python
async def connect(self, **kwargs) -> bool:
```

上游 v0.18.0 的 `BasePlatformAdapter.connect()` 新增了 `is_reconnect` 参数，
QQ adapter 需加 `**kwargs` 兼容，否则启动报错。

### 5. base.py — `_mark_notify_metadata()`

```python
def _mark_notify_metadata(metadata, message_category=None) -> dict:
    notify_metadata = dict(metadata) if metadata else {}
    notify_metadata["notify"] = True
    if message_category:
        notify_metadata["message_category"] = message_category
    return notify_metadata
```

### 6. base.py — `_process_message_background()`

```python
_is_command_response = bool(event.get_command())
_final_thread_metadata = _mark_notify_metadata(
    _thread_metadata,
    message_category="agent" if not _is_command_response else None,
)
if _is_command_response:
    _final_thread_metadata["non_conversational"] = True
```

- 普通消息：`event.get_command()` → `None` → 标记 `"agent"`，不设 `non_conversational` → 分割
- 命令回复（`/model`、`/status`）：`event.get_command()` 返回命令名 → 设 `non_conversational: True` → 不分割

### 7. send_message_tool.py — `_send_via_adapter()`

```python
metadata = {}
metadata["message_category"] = "agent"
```

确保 `metadata` 不为空字典，避免被 `if not metadata: metadata = None` 清空。

### 打字延迟

| 字数 | 延迟 |
|------|------|
| ≤5 | 1.5s |
| ≤10 | 2.5s |
| ≤15 | 4.0s |
| >15 | 5.0s |

## 重新打补丁

```bash
# 1. 恢复 upstream 版本
cp upstream/adapter.py /usr/local/lib/hermes-agent/gateway/platforms/qqbot/
cp upstream/base.py       /usr/local/lib/hermes-agent/gateway/platforms/

# 2. 打补丁
cd /usr/local/lib/hermes-agent
patch -p1 < patches/adapter-split-only.diff
patch -p1 < patches/base.diff
patch -p1 tools/send_message_tool.py < patches/send_message_tool.diff

# 3. 重启
hermes gateway restart -p gf
```

## 调试经验

1. Agent 回复文本走多条路径到达 `adapter.send()`，metadata 各不相同
2. 用 `traceback.print_stack()` 在 `send()` 中打印调用栈是定位路径的最快方法
3. QQ 平台 streaming 关闭，`GatewayStreamConsumer` 不参与
4. 上游 v0.18.0 的 `base.py` 有 `is_reconnect` 参数但 QQ adapter 未适配
