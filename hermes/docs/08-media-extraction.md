# 08 — MEDIA 标签提取

## 功能

Agent 回复中的 `MEDIA:<path>` 标签在发送前被提取并转为实际的媒体消息（图片/语音/视频/文件），用户看到的是原生附件而非文本标签。

关键场景：TTS 工具生成的语音、image_generate 生成的图片、以及 skill 输出的文件，都通过 `MEDIA:` 标签标记路径，由 `send()` 统一投递。

## 三条发送路径与提取位置

Hermes 中有多条路径到达 `adapter.send()`：

| # | 路径 | 时机 | MEDIA 提取 |
|---|------|------|-----------|
| 1 | Agent 内部 `send_message` 工具 | tool call **之前**的文本 | ✅ `send()` 自行提取 |
| 2 | `_process_message_background` 最终回复 | tool call **之后** | ✅ `send()` 自行提取 |
| 3 | base dispatch（`_handle_tool_call_response` 等） | tool 返回结果 | base.py 调用 `extract_media` |

路径 1 是关键——tool call message 中嵌入的 `MEDIA:` 标签（如 TTS 工具返回 `MEDIA:/tmp/audio.ogg`）走路径 1，此时 base dispatch 的 `extract_media` 还未执行，必须由 `send()` 独立提取。

## 两处提取点

### 1. 段落分割前（主提取）

```python
if 'MEDIA:' in content:
    media_files, content = self.extract_media(content)
    media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)
    for media_path, is_voice in media_files:
        # 路由到 send_voice / send_image / send_video / send_document
    if not content.strip():
        return SendResult(success=True)
```

覆盖全部内容中的 MEDIA 标签。若提取后文本为空（纯媒体消息），直接返回成功不发送空文本。

### 2. 段落分割循环内（逐段提取）

段落分割后，每个段落独立检查 `MEDIA:` 并提取。这样媒体文件紧跟引用它的文字段落发送，而非全部堆在开头。

## 媒体路由

基于扩展名分发到不同平台方法：

| 扩展名集合 | 目标方法 | 典型格式 |
|-----------|---------|---------|
| `_IMG_EXTS` | `send_image()` | jpg, png, webp, gif, bmp, tiff, svg |
| `_VID_EXTS` | `send_video()` | mp4, mov, avi, mkv, webm |
| `_AUDIO_EXTS` 或 `is_voice=True` | `send_voice()` | mp3, ogg, wav, m4a, aac, flac, opus |
| 其他（document 类） | `send_document()` | pdf, docx, xlsx, zip, html, md, json 等 |

三个扩展名集合定义在 `adapter.py` 模块级，是 `MEDIA_DELIVERY_EXTS`（base.py 中 40+ 种扩展名）的子集分区。

## 安全验证链

每次提取后调用 `BasePlatformAdapter.filter_media_delivery_paths()` 过滤：

1. **安全根目录**：`MEDIA_DELIVERY_SAFE_ROOTS`（Hermes 媒体目录、系统临时目录、XGD 缓存目录等）
2. **额外允许目录**：环境变量 `HERMES_MEDIA_ALLOW_DIRS`
3. **拒绝列表**：`/etc`, `/proc`, `/sys`, `~/.ssh`, `~/.aws` 等敏感路径
4. **近期文件信任**：`HERMES_MEDIA_TRUST_RECENT_SECONDS`（默认 600s）内创建的文件可绕过根目录限制
5. **严格模式**：`HERMES_MEDIA_DELIVERY_STRICT=1` 要求文件必须在安全根目录下

不安全路径被跳过并记录 warning，不会阻止其他合法文件的投递。

## `extract_media()` 实现要点

位于 `base.py:3584`，是静态方法：

1. **指令检测**：识别 `[[audio_as_voice]]`（强制语音发送）和 `[[as_document]]`（强制文件发送），从文本中剥离
2. **保护区域遮罩**：在扫描 `MEDIA:` 标签前，用空格替换 fenced code block、inline code、blockquote 和 JSON 字符串值中的内容，防止示例/历史记录中的 MEDIA 路径被误提取
3. **正则提取**：`MEDIA_TAG_CLEANUP_RE` 匹配带已知扩展名的路径；`MEDIA_EXTENSIONLESS_TAG_RE` 额外匹配无扩展名路径（如 Caddyfile、Dockerfile），需通过安全验证才投递
4. **标签清理**：投递后从用户可见文本中删除对应标签，压缩多余空行

## 涉及文件

| 文件 | 改动 |
|------|------|
| `gateway/platforms/qqbot/adapter.py` | 扩展名常量 + send() 中两处提取 + `Path` import |
| `gateway/platforms/base.py` | `extract_media()`, `filter_media_delivery_paths()`, 安全验证函数, `MEDIA_DELIVERY_EXTS`, `MEDIA_TAG_CLEANUP_RE`（上游已有，未修改） |

## 调试经验

1. MEDIA 标签在 tool call message 中不生效 → 检查 `send()` 的第一个提取点是否被执行（路径 1 不经过 base dispatch）
2. 文件投递成功但出现两次 → 两个提取点都在工作正常，但如果 base dispatch 也提取了一次，media 列表可能重复；`extract_media` 内部按路径去重
3. MEDIA 标签裸露在文本中未被提取 → 检查扩展名是否在 `MEDIA_DELIVERY_EXTS` 中，未知扩展名的标签会被保留在文本中供人工排查
