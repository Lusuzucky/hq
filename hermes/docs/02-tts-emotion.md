# 02 — TTS emotion 参数支持

## 功能

为 `text_to_speech` 工具添加 `emotion` 参数，支持 GPT-SoVITS 的情感控制。

## 为什么

GPT-SoVITS 是一个声音克隆 TTS 引擎，要求调用时必须指定情感。没有 emotion 参数，GPT-SoVITS API 会拒绝请求。Hermes 内置的 TTS provider 框架通过 `**extra` 支持任意外部参数，但 `tts_tool.py` 需要在调用链上显式传递 emotion。

## 涉及文件

| 文件 | 改动 |
|------|------|
| `tools/tts_tool.py` | `text_to_speech_tool()` 新增 emotion 参数 + schema 注册 |
| `tools/tts_tool.py` | `_dispatch_to_plugin_provider()` 新增 emotion 参数，透传给 plugin |
| `plugins/gptsovits/` | GPT-SoVITS 插件纳入管理 |

## 数据流

```
text_to_speech_tool(emotion="开心")
  → _dispatch_to_plugin_provider(emotion="开心")
    → plugin.synthesize(emotion="开心")
      → requests.post(url, json={"emotion": "开心", ...})
```

如果调用方未指定 emotion，从 `tts_config.get("emotion")` 取默认值。

## GPT-SoVITS 支持的情感

`普通` `平淡` `开心` `撒娇` `夹子` `温柔` `低落` `委屈` `慵懒` `生气` `有气无力`

## 插件安装路径

```
~/.hermes/profiles/gf/plugins/tts/gptsovits/__init__.py
~/.hermes/profiles/gf/plugins/tts/gptsovits/plugin.yaml
~/.hermes/profiles/gf/plugins/tts/pc_utils.py           ← WOL 共享模块
```

## 配置

`hermes/config/config.yaml` 中可配置默认 emotion：

```yaml
tts:
  provider: gptsovits
  emotion: 开心
```

或 `plugins/gptsovits/gptsovits_config.json`（旧版配置方式，作为备用参考）。
