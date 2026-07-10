"""
# WebAPI文档

` python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml `

## 执行参数:
    `-a` - `绑定地址, 默认"127.0.0.1"`
    `-p` - `绑定端口, 默认9880`
    `-c` - `TTS配置文件路径, 默认"GPT_SoVITS/configs/tts_infer.yaml"`

## JSON 配置文件 (api_v2_config.json):

所有 TTS 参数的默认值从 `api_v2_config.json` 读取，启动时加载。
API 请求中的参数若显式传入（非 null），会覆盖 JSON 中的默认值。

若 `gpt_weights_path` / `sovits_weights_path` 非空，启动时自动加载对应模型。

## 调用:

### 推理

endpoint: `/tts`
GET（只需传 text 和语言，其余使用 JSON 默认值）:
```
http://127.0.0.1:9880/tts?text=先帝创业未半而中道崩殂&text_lang=zh&prompt_lang=zh
```

任何 JSON 配置中的参数都可在请求中覆盖:
```
http://127.0.0.1:9880/tts?text=你好&text_lang=zh&prompt_lang=zh&speed_factor=1.5&top_k=10
```

POST（所有参数可选，未传则使用 JSON 配置默认值）:
```json
{
    "text": "",                   # str.(required) text to be synthesized
    "text_lang: "",               # str.(optional) 默认从 JSON 配置读取
    "ref_audio_path": "",         # str.(optional) 默认从 JSON 配置读取
    "aux_ref_audio_paths": [],    # list.(optional) auxiliary reference audio paths for multi-speaker tone fusion
    "prompt_text": "",            # str.(optional) 默认从 prompt_text_file 文件读取
    "prompt_lang": "",            # str.(optional) 默认从 JSON 配置读取
    "top_k": 15,                  # int. top k sampling
    "top_p": 1,                   # float. top p sampling
    "temperature": 1,             # float. temperature for sampling
    "text_split_method": "cut5",  # str. text split method, see text_segmentation_method.py for details.
    "batch_size": 1,              # int. batch size for inference
    "batch_threshold": 0.75,      # float. threshold for batch splitting.
    "split_bucket": True,         # bool. whether to split the batch into multiple buckets.
    "speed_factor":1.0,           # float. control the speed of the synthesized audio.
    "fragment_interval":0.3,      # float. to control the interval of the audio fragment.
    "seed": -1,                   # int. random seed for reproducibility.
    "parallel_infer": True,       # bool. whether to use parallel inference.
    "repetition_penalty": 1.35,   # float. repetition penalty for T2S model.
    "sample_steps": 32,           # int. number of sampling steps for VITS model V3.
    "super_sampling": False,      # bool. whether to use super-sampling for audio when using VITS model V3.
    "streaming_mode": False,      # bool or int. return audio chunk by chunk.T he available options are: 0,1,2,3 or True/False (0/False: Disabled | 1/True: Best Quality, Slowest response speed (old version streaming_mode) | 2: Medium Quality, Slow response speed | 3: Lower Quality, Faster response speed )
    "overlap_length": 2,          # int. overlap length of semantic tokens for streaming mode.
    "min_chunk_length": 16,       # int. The minimum chunk length of semantic tokens for streaming mode. (affects audio chunk size)
}
```

RESP:
成功: 直接返回 wav 音频流， http code 200
失败: 返回包含错误信息的 json, http code 400

### 命令控制

endpoint: `/control`

command:
"restart": 重新运行
"exit": 结束运行

GET:
```
http://127.0.0.1:9880/control?command=restart
```
POST:
```json
{
    "command": "restart"
}
```

RESP: 无


### 设置全局语速

endpoint: `/set_speed`

GET:
```
http://127.0.0.1:9880/set_speed?speed_factor=1.5
```

RESP:
成功: 返回包含成功信息的 json, http code 200
失败: 返回包含错误信息的 json, http code 400

注意: 语速因子 `speed_factor` 也可以在 `/tts` 请求中逐次指定，`/set_speed` 设置的是全局默认值并持久化到 JSON 文件。


### 动态修改/查看配置

endpoint: `/set_config`
修改任意配置项并持久化到 JSON 文件。
GET:
```
http://127.0.0.1:9880/set_config?key=temperature&value=0.8
http://127.0.0.1:9880/set_config?key=ref_audio_path&value=new_ref.wav
```

endpoint: `/get_config`
查看当前全部配置（GET）。
```
http://127.0.0.1:9880/get_config
```

endpoint: `/reload_config`
从 JSON 文件重新加载配置（GET）。
```
http://127.0.0.1:9880/reload_config
```


### 切换GPT模型

endpoint: `/set_gpt_weights`

GET:
```
http://127.0.0.1:9880/set_gpt_weights?weights_path=GPT_SoVITS/pretrained_models/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt
```
RESP:
成功: 返回"success", http code 200
失败: 返回包含错误信息的 json, http code 400


### 切换Sovits模型

endpoint: `/set_sovits_weights`

GET:
```
http://127.0.0.1:9880/set_sovits_weights?weights_path=GPT_SoVITS/pretrained_models/s2G488k.pth
```

RESP:
成功: 返回"success", http code 200
失败: 返回包含错误信息的 json, http code 400

"""

import copy
import json
import os
import sys
import traceback
from typing import Generator, Union

now_dir = os.getcwd()
sys.path.append(now_dir)
sys.path.append("%s/GPT_SoVITS" % (now_dir))

import argparse
import subprocess
import wave
import signal
import numpy as np
import soundfile as sf
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn
from io import BytesIO
from tools.i18n.i18n import I18nAuto
from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config


from GPT_SoVITS.TTS_infer_pack.text_segmentation_method import get_method_names as get_cut_method_names
from pydantic import BaseModel
import threading
import asyncio

# print(sys.path)
i18n = I18nAuto()
cut_method_names = get_cut_method_names()

parser = argparse.ArgumentParser(description="GPT-SoVITS api")
parser.add_argument("-c", "--tts_config", type=str, default="GPT_SoVITS/configs/tts_infer.yaml", help="tts_infer路径")
parser.add_argument("-a", "--bind_addr", type=str, default="127.0.0.1", help="default: 127.0.0.1")
parser.add_argument("-p", "--port", type=int, default="9880", help="default: 9880")
args = parser.parse_args()
config_path = args.tts_config
# device = args.device
port = args.port
host = args.bind_addr
argv = sys.argv

if config_path in [None, ""]:
    config_path = "GPT-SoVITS/configs/tts_infer.yaml"

tts_config = TTS_Config(config_path)
print(tts_config)
tts_pipeline = TTS(tts_config)

APP = FastAPI()

# ===================== JSON 配置系统 =====================

CONFIG_FILE = "api_v2_config.json"

# 运行时 schema（完整 JSON 结构，含 description/type/options 等元数据）
tts_config_schema: dict = {}

# 内置 fallback（当 JSON 文件不存在或损坏时使用）
_FALLBACK_SCHEMA: dict = {
    "parameters": {
        "ref_audio_path":      {"value": "reference.wav", "type": "file_path", "description": "参考音频路径"},
        "prompt_text_file":    {"value": "ref.txt",       "type": "file_path", "description": "参考文本文件路径"},
        "prompt_lang":         {"value": "zh",            "type": "enum",      "description": "参考文本语言",     "options": ["zh","ja","en","ko","yue","auto"]},
        "text_lang":           {"value": "zh",            "type": "enum",      "description": "合成文本语言",     "options": ["zh","ja","en","ko","yue","auto"]},
        "top_k":               {"value": 15,              "type": "int",       "description": "Top-K 采样",       "range": [1, 100]},
        "top_p":               {"value": 1.0,             "type": "float",     "description": "Top-P 采样",       "range": [0.0, 1.0]},
        "temperature":         {"value": 1.0,             "type": "float",     "description": "温度参数",         "range": [0.0, 2.0]},
        "speed_factor":        {"value": 1.0,             "type": "float",     "description": "语速因子",         "range": [0.3, 3.0]},
        "text_split_method":   {"value": "cut5",          "type": "enum",      "description": "文本切分方法。cut0=不切 | cut1=凑四句 | cut2=凑50字 | cut3=按。切 | cut4=按.切 | cut5=按所有标点切", "options": ["cut0","cut1","cut2","cut3","cut4","cut5"]},
        "batch_size":          {"value": 1,               "type": "int",       "description": "推理批大小",       "range": [1, 64]},
        "batch_threshold":     {"value": 0.75,            "type": "float",     "description": "批次切分阈值",     "range": [0.0, 1.0]},
        "split_bucket":        {"value": True,            "type": "bool",      "description": "是否按长度分桶"},
        "fragment_interval":   {"value": 0.3,             "type": "float",     "description": "片段间隔(秒)",     "range": [0.0, 5.0]},
        "seed":                {"value": -1,              "type": "int",       "description": "随机种子"},
        "media_type":          {"value": "wav",           "type": "enum",      "description": "输出音频格式",     "options": ["wav","raw","ogg","aac"]},
        "streaming_mode":      {"value": False,           "type": "enum",      "description": "流式模式",         "options": [False, True, 0, 1, 2, 3]},
        "parallel_infer":      {"value": True,            "type": "bool",      "description": "并行推理"},
        "repetition_penalty":  {"value": 1.35,            "type": "float",     "description": "重复惩罚",         "range": [0.5, 5.0]},
        "sample_steps":        {"value": 32,              "type": "int",       "description": "V3 采样步数",      "range": [4, 128]},
        "super_sampling":      {"value": False,           "type": "bool",      "description": "V3 超采样"},
        "overlap_length":      {"value": 2,               "type": "int",       "description": "流式重叠长度",     "range": [0, 10]},
        "min_chunk_length":    {"value": 16,              "type": "int",       "description": "流式最小chunk",    "range": [4, 64]},
    },
    "models": {
        "gpt_weights_path":    {"value": "",              "type": "file_path", "description": "GPT/T2S 模型权重路径，启动时自动加载"},
        "sovits_weights_path": {"value": "",              "type": "file_path", "description": "SoVITS/VITS 模型权重路径，启动时自动加载"},
    },
    "reference": {
        "reference_config":    {"value": "Reference/夏/Reference.json", "type": "file_path", "description": "语气→参考音频映射表 (Reference.json) 路径"},
    },
}


# ----------  schema ↔ flat 互转 ----------

def schema_to_flat(schema: dict) -> dict:
    """从 schema 提取纯 {key: value} 字典，供 tts_handle 做参数合并"""
    flat = {}
    for section in ("parameters", "models", "reference"):
        for key, meta in schema.get(section, {}).items():
            flat[key] = meta.get("value")
    return flat


def flat_to_schema(flat: dict, schema: dict) -> dict:
    """将 flat {key: value} 写回 schema 的 .value 字段（仅更新已存在的 key）"""
    result = copy.deepcopy(schema)
    for section in ("parameters", "models", "reference"):
        for key, meta in result.get(section, {}).items():
            if key in flat:
                meta["value"] = flat[key]
    return result


# ----------  文件读写 ----------

def load_schema(filepath: str = CONFIG_FILE) -> dict:
    """从 JSON 加载完整 schema，缺失 key 用 fallback 补全"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception as e:
        print(f"[Config] Warning: failed to load {filepath}: {e}, using fallback")
        loaded = {}
    # 深度合并：确保每个 section 下每个 key 都存在
    result = {}
    for section in ("parameters", "models", "reference"):
        result[section] = {}
        fallback_section = _FALLBACK_SCHEMA.get(section, {})
        loaded_section = loaded.get(section, {})
        for key, fallback_meta in fallback_section.items():
            entry = loaded_section.get(key, {})
            merged = dict(fallback_meta)  # 复制 fallback 元数据
            if "value" in entry:
                merged["value"] = entry["value"]  # 用 JSON 中的 value 覆盖
            if "description" in entry:
                merged["description"] = entry["description"]  # 允许 JSON 覆盖描述
            if "options" in entry:
                merged["options"] = entry["options"]
            if "range" in entry:
                merged["range"] = entry["range"]
            result[section][key] = merged
    # 保留顶级 _comment
    if "_comment" in loaded:
        result["_comment"] = loaded["_comment"]
    elif "_comment" in _FALLBACK_SCHEMA:
        result["_comment"] = _FALLBACK_SCHEMA["_comment"]
    print(f"[Config] Loaded schema from {filepath} (parameters: {len(result.get('parameters',{}))}, models: {len(result.get('models',{}))})")
    return result


def save_schema(schema: dict, filepath: str = CONFIG_FILE):
    """将当前 schema 写回 JSON 文件"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
        print(f"[Config] Saved schema to {filepath}")
    except Exception as e:
        print(f"[Config] Warning: failed to save {filepath}: {e}")


# ----------  查找/更新 ----------

def find_param_entry(key: str) -> tuple:
    """在 schema 中查找参数，返回 (section_name, meta_dict) 或 (None, None)"""
    for section in ("parameters", "models", "reference"):
        if key in tts_config_schema.get(section, {}):
            return section, tts_config_schema[section][key]
    return None, None


def set_param_value(key: str, new_value):
    """设置某个参数的 value 并持久化。找不到 key 抛 KeyError。"""
    section, meta = find_param_entry(key)
    if section is None:
        raise KeyError(f"unknown config key: {key}")
    old = meta["value"]
    meta["value"] = new_value
    save_schema(tts_config_schema)
    print(f"[Config] {key}: {old} → {new_value}")
    return old, new_value


# ----------  参考文本 ----------

def load_ref_text(filepath: str) -> str:
    """从文件中读取参考文本"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content
    except Exception as e:
        print(f"Warning: failed to read ref text from {filepath}: {e}")
        return ""


# ----------  启动加载 ----------

def _print_config_banner():
    """启动时打印 JSON 配置摘要"""
    width = 80
    print("=" * width)
    print("  API Config  (api_v2_config.json)")

    def _v(key):
        section, meta = find_param_entry(key)
        if section:
            val = meta.get("value", "")
            if isinstance(val, bool):
                return "true" if val else "false"
            return str(val)
        return "?"

    rows = [
        ("Models", [
            ("gpt_weights_path",    _v("gpt_weights_path") or "(using YAML default)"),
            ("sovits_weights_path", _v("sovits_weights_path") or "(using YAML default)"),
        ]),
        ("Audio Ref", [
            ("ref_audio_path",      _v("ref_audio_path")),
            ("prompt_text_file",    _v("prompt_text_file")),
            ("prompt_lang",         _v("prompt_lang")),
            ("text_lang",           _v("text_lang")),
        ]),
        ("Generation", [
            ("speed_factor",        _v("speed_factor")),
            ("temperature",         _v("temperature")),
            ("top_k",               _v("top_k")),
            ("top_p",               _v("top_p")),
            ("repetition_penalty",  _v("repetition_penalty")),
        ]),
        ("Inference", [
            ("text_split_method",   _v("text_split_method")),
            ("batch_size",          _v("batch_size")),
            ("streaming_mode",      _v("streaming_mode")),
            ("media_type",          _v("media_type")),
            ("parallel_infer",      _v("parallel_infer")),
            ("sample_steps",        _v("sample_steps")),
            ("super_sampling",      _v("super_sampling")),
        ]),
    ]
    for group, pairs in rows:
        print(f"  [{group}]")
        for label, val in pairs:
            print(f"    {label:<22s} : {val}")
    # 语气列表
    if emotion_map:
        emotions = list(emotion_map.keys())
        print(f"  [Emotions] ({len(emotions)} tones)")
        print(f"    {' '.join(emotions)}")
    print("=" * width)


# ────── emotion map（语气 → {audio, text, speed}）──────

emotion_map: dict = {}          # key: 语气名, value: {"audio": str, "text": str, "speed": float}
emotion_mtime: float = 0        # Reference.json 最后修改时间
emotion_config_path: str = ""   # Reference.json 路径


def load_emotion_map(config_path: str) -> dict:
    """加载 Reference.json，解析相对路径为绝对路径"""
    if not config_path:
        return {}
    try:
        base_dir = os.path.dirname(os.path.abspath(config_path))
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        result = {}
        for name, entry in raw.items():
            audio_rel = entry.get("audio", "")
            audio_abs = os.path.join(base_dir, audio_rel) if audio_rel else ""
            result[name] = {
                "audio": audio_abs,
                "text": entry.get("text", ""),
                "speed": entry.get("speed", 1.0),
            }
        print(f"[Emotion] Loaded {len(result)} tones from {config_path}: {list(result.keys())}")
        return result
    except Exception as e:
        print(f"[Emotion] Warning: failed to load {config_path}: {e}")
        return {}


def ensure_emotion_fresh():
    """如果 Reference.json 已变更（按 mtime），自动重载。返回当前 emotion_map。"""
    global emotion_map, emotion_mtime, emotion_config_path
    if not emotion_config_path:
        return emotion_map
    try:
        mtime = os.path.getmtime(emotion_config_path)
        if mtime != emotion_mtime:
            print(f"[Emotion] Detected change in {emotion_config_path}, auto-reloading...")
            fresh = load_emotion_map(emotion_config_path)
            if fresh:
                emotion_map = fresh
                emotion_mtime = mtime
    except OSError:
        pass  # 文件被删了，保留旧数据
    return emotion_map


def reload_emotion():
    """强制重载 Reference.json"""
    global emotion_map, emotion_mtime, emotion_config_path
    if not emotion_config_path:
        return None
    fresh = load_emotion_map(emotion_config_path)
    if fresh:
        emotion_map = fresh
        try:
            emotion_mtime = os.path.getmtime(emotion_config_path)
        except OSError:
            emotion_mtime = 0
    return fresh


# ────── 加载 schema ──────

tts_config_schema = load_schema(CONFIG_FILE)
tts_defaults = schema_to_flat(tts_config_schema)

# 加载语气映射表
emotion_config_path = tts_config_schema.get("reference", {}).get("reference_config", {}).get("value", "")
emotion_map = load_emotion_map(emotion_config_path)
if emotion_map:
    try:
        emotion_mtime = os.path.getmtime(emotion_config_path)
    except OSError:
        emotion_mtime = 0

# 自动加载配置中指定的模型权重
gpt_path = tts_config_schema.get("models", {}).get("gpt_weights_path", {}).get("value", "")
sovits_path = tts_config_schema.get("models", {}).get("sovits_weights_path", {}).get("value", "")
if gpt_path:
    try:
        tts_pipeline.init_t2s_weights(gpt_path)
        print(f"[Startup] GPT weights overridden: {gpt_path}")
    except Exception as e:
        print(f"[Startup] Failed to load GPT weights [{gpt_path}]: {e}")
if sovits_path:
    try:
        tts_pipeline.init_vits_weights(sovits_path)
        print(f"[Startup] SoVITS weights overridden: {sovits_path}")
    except Exception as e:
        print(f"[Startup] Failed to load SoVITS weights [{sovits_path}]: {e}")

_print_config_banner()

# ===================== End 配置系统 =====================


class TTS_Request(BaseModel):
    text: str = None
    text_lang: str = None
    emotion: str = None
    ref_audio_path: str = None
    aux_ref_audio_paths: list = None
    prompt_lang: str = None
    prompt_text: str = None
    top_k: int = None
    top_p: float = None
    temperature: float = None
    text_split_method: str = None
    batch_size: int = None
    batch_threshold: float = None
    split_bucket: bool = None
    speed_factor: float = None
    fragment_interval: float = None
    seed: int = None
    media_type: str = None
    streaming_mode: Union[bool, int] = None
    parallel_infer: bool = None
    repetition_penalty: float = None
    sample_steps: int = None
    super_sampling: bool = None
    overlap_length: int = None
    min_chunk_length: int = None


def pack_ogg(io_buffer: BytesIO, data: np.ndarray, rate: int):
    # Author: AkagawaTsurunaki
    # Issue:
    #   Stack overflow probabilistically occurs
    #   when the function `sf_writef_short` of `libsndfile_64bit.dll` is called
    #   using the Python library `soundfile`
    # Note:
    #   This is an issue related to `libsndfile`, not this project itself.
    #   It happens when you generate a large audio tensor (about 499804 frames in my PC)
    #   and try to convert it to an ogg file.
    # Related:
    #   https://github.com/RVC-Boss/GPT-SoVITS/issues/1199
    #   https://github.com/libsndfile/libsndfile/issues/1023
    #   https://github.com/bastibe/python-soundfile/issues/396
    # Suggestion:
    #   Or split the whole audio data into smaller audio segment to avoid stack overflow?

    def handle_pack_ogg():
        with sf.SoundFile(io_buffer, mode="w", samplerate=rate, channels=1, format="ogg") as audio_file:
            audio_file.write(data)



    # See: https://docs.python.org/3/library/threading.html
    # The stack size of this thread is at least 32768
    # If stack overflow error still occurs, just modify the `stack_size`.
    # stack_size = n * 4096, where n should be a positive integer.
    # Here we chose n = 4096.
    stack_size = 4096 * 4096
    try:
        threading.stack_size(stack_size)
        pack_ogg_thread = threading.Thread(target=handle_pack_ogg)
        pack_ogg_thread.start()
        pack_ogg_thread.join()
    except RuntimeError as e:
        # If changing the thread stack size is unsupported, a RuntimeError is raised.
        print("RuntimeError: {}".format(e))
        print("Changing the thread stack size is unsupported.")
    except ValueError as e:
        # If the specified stack size is invalid, a ValueError is raised and the stack size is unmodified.
        print("ValueError: {}".format(e))
        print("The specified stack size is invalid.")

    return io_buffer


def pack_raw(io_buffer: BytesIO, data: np.ndarray, rate: int):
    io_buffer.write(data.tobytes())
    return io_buffer


def pack_wav(io_buffer: BytesIO, data: np.ndarray, rate: int):
    io_buffer = BytesIO()
    sf.write(io_buffer, data, rate, format="wav")
    return io_buffer


def pack_aac(io_buffer: BytesIO, data: np.ndarray, rate: int):
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-f",
            "s16le",  # 输入16位有符号小端整数PCM
            "-ar",
            str(rate),  # 设置采样率
            "-ac",
            "1",  # 单声道
            "-i",
            "pipe:0",  # 从管道读取输入
            "-c:a",
            "aac",  # 音频编码器为AAC
            "-b:a",
            "192k",  # 比特率
            "-vn",  # 不包含视频
            "-f",
            "adts",  # 输出AAC数据流格式
            "pipe:1",  # 将输出写入管道
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, _ = process.communicate(input=data.tobytes())
    io_buffer.write(out)
    return io_buffer


def pack_audio(io_buffer: BytesIO, data: np.ndarray, rate: int, media_type: str):
    if media_type == "ogg":
        io_buffer = pack_ogg(io_buffer, data, rate)
    elif media_type == "aac":
        io_buffer = pack_aac(io_buffer, data, rate)
    elif media_type == "wav":
        io_buffer = pack_wav(io_buffer, data, rate)
    else:
        io_buffer = pack_raw(io_buffer, data, rate)
    io_buffer.seek(0)
    return io_buffer


# from https://huggingface.co/spaces/coqui/voice-chat-with-mistral/blob/main/app.py
def wave_header_chunk(frame_input=b"", channels=1, sample_width=2, sample_rate=32000):
    # This will create a wave header then append the frame input
    # It should be first on a streaming wav file
    # Other frames better should not have it (else you will hear some artifacts each chunk start)
    wav_buf = BytesIO()
    with wave.open(wav_buf, "wb") as vfout:
        vfout.setnchannels(channels)
        vfout.setsampwidth(sample_width)
        vfout.setframerate(sample_rate)
        vfout.writeframes(frame_input)

    wav_buf.seek(0)
    return wav_buf.read()


def handle_control(command: str):
    if command == "restart":
        os.execl(sys.executable, sys.executable, *argv)
    elif command == "exit":
        os.kill(os.getpid(), signal.SIGTERM)
        exit(0)



def check_params(req: dict):
    text: str = req.get("text", "")
    text_lang: str = req.get("text_lang", "")
    streaming_mode: bool = req.get("streaming_mode", False)
    media_type: str = req.get("media_type", "wav")
    prompt_lang: str = req.get("prompt_lang", "")
    text_split_method: str = req.get("text_split_method", "cut5")

    if text in [None, ""]:
        print("[check_params] FAIL: text is empty")
        return JSONResponse(status_code=400, content={"message": "text is required"})
    if text_lang in [None, ""]:
        print("[check_params] FAIL: text_lang is empty")
        return JSONResponse(status_code=400, content={"message": "text_lang is required"})
    elif text_lang.lower() not in tts_config.languages:
        print(f"[check_params] FAIL: text_lang={text_lang} not in {tts_config.languages}")
        return JSONResponse(
            status_code=400,
            content={"message": f"text_lang: {text_lang} is not supported in version {tts_config.version}"},
        )
    if prompt_lang in [None, ""]:
        prompt_lang = text_lang
        req["prompt_lang"] = prompt_lang
    if prompt_lang.lower() not in tts_config.languages:
        print(f"[check_params] FAIL: prompt_lang={prompt_lang} not in {tts_config.languages}")
        return JSONResponse(
            status_code=400,
            content={"message": f"prompt_lang: {prompt_lang} is not supported in version {tts_config.version}"},
        )
    if media_type not in ["wav", "raw", "ogg", "aac"]:
        print(f"[check_params] FAIL: media_type={media_type} not supported")
        return JSONResponse(status_code=400, content={"message": f"media_type: {media_type} is not supported"})

    if text_split_method not in cut_method_names:
        print(f"[check_params] FAIL: text_split_method={text_split_method} not in {cut_method_names}")
        return JSONResponse(
            status_code=400, content={"message": f"text_split_method:{text_split_method} is not supported, available: {cut_method_names}"}
        )

    return None


async def tts_handle(req: dict):

    """
    Text to speech handler.

    Args:
        req (dict):
            {
                "text": "",                   # str.(required) text to be synthesized
                "text_lang: "",               # str.(required) language of the text to be synthesized
                "ref_audio_path": "",         # str.(required) reference audio path
                "aux_ref_audio_paths": [],    # list.(optional) auxiliary reference audio paths for multi-speaker tone fusion
                "prompt_text": "",            # str.(optional) prompt text for the reference audio
                "prompt_lang": "",            # str.(required) language of the prompt text for the reference audio
                "top_k": 15,                  # int. top k sampling
                "top_p": 1,                   # float. top p sampling
                "temperature": 1,             # float. temperature for sampling
                "text_split_method": "cut5",  # str. text split method, see text_segmentation_method.py for details.
                "batch_size": 1,              # int. batch size for inference
                "batch_threshold": 0.75,      # float. threshold for batch splitting.
                "split_bucket": True,         # bool. whether to split the batch into multiple buckets.
                "speed_factor":1.0,           # float. control the speed of the synthesized audio.
                "fragment_interval":0.3,      # float. to control the interval of the audio fragment.
                "seed": -1,                   # int. random seed for reproducibility.
                "parallel_infer": True,       # bool. whether to use parallel inference.
                "repetition_penalty": 1.35,   # float. repetition penalty for T2S model.
                "sample_steps": 32,           # int. number of sampling steps for VITS model V3.
                "super_sampling": False,      # bool. whether to use super-sampling for audio when using VITS model V3.
                "streaming_mode": False,      # bool or int. return audio chunk by chunk.T he available options are: 0,1,2,3 or True/False (0/False: Disabled | 1/True: Best Quality, Slowest response speed (old version streaming_mode) | 2: Medium Quality, Slow response speed | 3: Lower Quality, Faster response speed )
                "overlap_length": 2,          # int. overlap length of semantic tokens for streaming mode.
                "min_chunk_length": 16,       # int. The minimum chunk length of semantic tokens for streaming mode. (affects audio chunk size)
            }
    returns:
        StreamingResponse: audio stream response.
    """

    # ▼ 三层合并：JSON 默认 < prompt_text_file < 语气映射 < 请求参数
    # 第1层：JSON 配置默认值
    merged = dict(tts_defaults)

    # 第1.5层：如果配置了 prompt_text_file 且 JSON 默认值里没有 prompt_text，从文件读取
    if merged.get("prompt_text_file") and not merged.get("prompt_text"):
        merged["prompt_text"] = load_ref_text(merged["prompt_text_file"])

    # 第2层：语气映射覆盖（如果指定了 emotion，先确保映射是最新的）
    ensure_emotion_fresh()
    emotion = req.get("emotion")
    if not emotion:
        available = list(emotion_map.keys())
        return JSONResponse(
            status_code=400,
            content={
                "message": "emotion is required, please specify one of: " + ", ".join(available),
                "available_emotions": available
            }
        )
    if emotion and emotion in emotion_map:
        e = emotion_map[emotion]
        merged["ref_audio_path"] = e["audio"]
        merged["prompt_text"] = e["text"]
        merged["speed_factor"] = e["speed"]
        print(f"[Emotion] Using tone '{emotion}': audio={e['audio']}, speed={e['speed']}")
    elif emotion:
        print(f"[Emotion] Warning: unknown tone '{emotion}', available: {list(emotion_map.keys())}")

    # 第3层：请求参数覆盖（非 None 且非空字符串/空列表的值）
    def _has_value(v):
        if v is None:
            return False
        if isinstance(v, str) and v == "":
            return False
        if isinstance(v, list) and len(v) == 0:
            return False
        return True

    for key, value in req.items():
        if _has_value(value):
            merged[key] = value
    req = merged

    streaming_mode = req.get("streaming_mode", False)
    return_fragment = req.get("return_fragment", False)
    media_type = req.get("media_type", "wav")

    check_res = check_params(req)
    if check_res is not None:
        return check_res
    
    if streaming_mode == 0:
        streaming_mode = False
        return_fragment = False
        fixed_length_chunk = False
    elif streaming_mode == 1:
        streaming_mode = False
        return_fragment = True
        fixed_length_chunk = False
    elif streaming_mode == 2:
        streaming_mode = True
        return_fragment = False
        fixed_length_chunk = False
    elif streaming_mode == 3:
        streaming_mode = True
        return_fragment = False
        fixed_length_chunk = True

    else:
        return JSONResponse(status_code=400, content={"message": f"the value of streaming_mode must be 0, 1, 2, 3(int) or true/false(bool)"})

    req["streaming_mode"] = streaming_mode
    req["return_fragment"] = return_fragment
    req["fixed_length_chunk"] = fixed_length_chunk

    print(f"{streaming_mode} {return_fragment} {fixed_length_chunk}")

    streaming_mode = streaming_mode or return_fragment

    model_guard.acquire()

    try:
        tts_generator = tts_pipeline.run(req)

        if streaming_mode:

            def streaming_generator(tts_generator: Generator, media_type: str):
                if_frist_chunk = True
                for sr, chunk in tts_generator:
                    if if_frist_chunk and media_type == "wav":
                        yield wave_header_chunk(sample_rate=sr)
                        media_type = "raw"
                        if_frist_chunk = False
                    yield pack_audio(BytesIO(), chunk, sr, media_type).getvalue()

            def guarded_generator(tts_generator: Generator, media_type: str):
                try:
                    yield from streaming_generator(tts_generator, media_type)
                finally:
                    model_guard.release()

            return StreamingResponse(
                guarded_generator(
                    tts_generator,
                    media_type,
                ),
                media_type=f"audio/{media_type}",
            )

        else:
            sr, audio_data = next(tts_generator)
            audio_data = pack_audio(BytesIO(), audio_data, sr, media_type).getvalue()
            return Response(audio_data, media_type=f"audio/{media_type}")
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=400, content={"message": "tts failed", "Exception": str(e)})
    finally:
        if not streaming_mode:
            model_guard.release()



@APP.get("/control")
async def control(command: str = None):
    if command is None:
        return JSONResponse(status_code=400, content={"message": "command is required"})
    handle_control(command)


@APP.get("/tts")
async def tts_get_endpoint(
    text: str = None,
    text_lang: str = None,
    emotion: str = None,
    ref_audio_path: str = None,
    aux_ref_audio_paths: list = None,
    prompt_lang: str = None,
    prompt_text: str = None,
    top_k: int = None,
    top_p: float = None,
    temperature: float = None,
    text_split_method: str = None,
    batch_size: int = None,
    batch_threshold: float = None,
    split_bucket: bool = None,
    speed_factor: float = None,
    fragment_interval: float = None,
    seed: int = None,
    media_type: str = None,
    parallel_infer: bool = None,
    repetition_penalty: float = None,
    sample_steps: int = None,
    super_sampling: bool = None,
    streaming_mode: Union[bool, int] = None,
    overlap_length: int = None,
    min_chunk_length: int = None,
):
    req = {
        "text": text,
        "text_lang": text_lang.lower() if text_lang else None,
        "emotion": emotion,
        "ref_audio_path": ref_audio_path,
        "aux_ref_audio_paths": aux_ref_audio_paths,
        "prompt_text": prompt_text,
        "prompt_lang": prompt_lang.lower() if prompt_lang else None,
        "top_k": top_k,
        "top_p": top_p,
        "temperature": temperature,
        "text_split_method": text_split_method,
        "batch_size": batch_size,
        "batch_threshold": batch_threshold,
        "speed_factor": speed_factor,
        "split_bucket": split_bucket,
        "fragment_interval": fragment_interval,
        "seed": seed,
        "media_type": media_type,
        "streaming_mode": streaming_mode,
        "parallel_infer": parallel_infer,
        "repetition_penalty": repetition_penalty,
        "sample_steps": sample_steps,
        "super_sampling": super_sampling,
        "overlap_length": overlap_length,
        "min_chunk_length": min_chunk_length,
    }
    return await tts_handle(req)


@APP.post("/tts")
async def tts_post_endpoint(request: TTS_Request):
    req = request.dict()
    print(f"[POST /tts] {json.dumps(req, ensure_ascii=False, default=str)}")
    return await tts_handle(req)


@APP.get("/set_refer_audio")
async def set_refer_aduio(refer_audio_path: str = None):
    try:
        tts_pipeline.set_ref_audio(refer_audio_path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": "set refer audio failed", "Exception": str(e)})
    return JSONResponse(status_code=200, content={"message": "success"})


# @APP.post("/set_refer_audio")
# async def set_refer_aduio_post(audio_file: UploadFile = File(...)):
#     try:
#         # 检查文件类型，确保是音频文件
#         if not audio_file.content_type.startswith("audio/"):
#             return JSONResponse(status_code=400, content={"message": "file type is not supported"})

#         os.makedirs("uploaded_audio", exist_ok=True)
#         save_path = os.path.join("uploaded_audio", audio_file.filename)
#         # 保存音频文件到服务器上的一个目录
#         with open(save_path , "wb") as buffer:
#             buffer.write(await audio_file.read())

#         tts_pipeline.set_ref_audio(save_path)
#     except Exception as e:
#         return JSONResponse(status_code=400, content={"message": f"set refer audio failed", "Exception": str(e)})
#     return JSONResponse(status_code=200, content={"message": "success"})


@APP.get("/set_gpt_weights")
async def set_gpt_weights(weights_path: str = None):
    try:
        if weights_path in ["", None]:
            return JSONResponse(status_code=400, content={"message": "gpt weight path is required"})
        tts_pipeline.init_t2s_weights(weights_path)
        # 同步写入 schema 并持久化
        set_param_value("gpt_weights_path", weights_path)
        global tts_defaults
        tts_defaults = schema_to_flat(tts_config_schema)
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": "change gpt weight failed", "Exception": str(e)})
    return JSONResponse(status_code=200, content={"message": "success"})


@APP.get("/set_sovits_weights")
async def set_sovits_weights(weights_path: str = None):
    try:
        if weights_path in ["", None]:
            return JSONResponse(status_code=400, content={"message": "sovits weight path is required"})
        tts_pipeline.init_vits_weights(weights_path)
        # 同步写入 schema 并持久化
        set_param_value("sovits_weights_path", weights_path)
        global tts_defaults
        tts_defaults = schema_to_flat(tts_config_schema)
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": "change sovits weight failed", "Exception": str(e)})
    return JSONResponse(status_code=200, content={"message": "success"})


@APP.get("/set_speed")
async def set_speed(speed_factor: float = None):
    """动态设置全局语速因子（同时更新 JSON 配置文件）"""
    global tts_defaults, tts_config_schema
    if speed_factor is None:
        return JSONResponse(status_code=400, content={"message": "speed_factor is required"})
    if speed_factor <= 0:
        return JSONResponse(status_code=400, content={"message": "speed_factor must be positive"})
    old, new = set_param_value("speed_factor", speed_factor)
    tts_defaults = schema_to_flat(tts_config_schema)
    return JSONResponse(status_code=200, content={"message": f"speed_factor: {old} → {new}"})


@APP.get("/set_config")
async def set_config(key: str = None, value: str = None):
    """动态修改任意 JSON 配置项（在 parameters 或 models 中查找，同时持久化）"""
    global tts_defaults, tts_config_schema
    if key is None or value is None:
        return JSONResponse(status_code=400, content={"message": "key and value are required"})
    section, meta = find_param_entry(key)
    if section is None:
        return JSONResponse(status_code=400, content={"message": f"unknown config key: {key}"})
    # 根据 schema 中声明的 type 做自动转换
    typ = meta.get("type", "string")
    try:
        if typ == "bool":
            new_val = value.lower() in ("true", "1", "yes")
        elif typ == "int":
            new_val = int(value)
        elif typ == "float":
            new_val = float(value)
        else:
            new_val = value
    except (ValueError, TypeError):
        return JSONResponse(status_code=400, content={"message": f"cannot convert '{value}' to {typ}"})

    # 枚举校验
    if typ == "enum" and "options" in meta:
        if new_val not in meta["options"]:
            return JSONResponse(status_code=400, content={"message": f"'{new_val}' not in options: {meta['options']}"})

    # 范围校验
    if typ in ("int", "float") and "range" in meta:
        lo, hi = meta["range"]
        if not (lo <= new_val <= hi):
            return JSONResponse(status_code=400, content={"message": f"{new_val} out of range [{lo}, {hi}]"})

    old, new = set_param_value(key, new_val)
    tts_defaults = schema_to_flat(tts_config_schema)
    return JSONResponse(status_code=200, content={"message": f"{key}: {old} → {new}"})


@APP.get("/get_config")
async def get_config():
    """查看当前全部配置（含 schema 元数据）"""
    return JSONResponse(status_code=200, content=tts_config_schema)


@APP.get("/reload_emotion")
async def reload_emotion_endpoint():
    """强制重载 Reference.json 语气映射表（改了立即生效，无需重启）"""
    fresh = reload_emotion()
    if fresh is None:
        return JSONResponse(status_code=400, content={"message": "emotion config path not set"})
    if not fresh:
        return JSONResponse(status_code=400, content={"message": "failed to reload emotion map"})
    global emotion_mtime
    return JSONResponse(status_code=200, content={
        "message": f"reloaded {len(fresh)} tones",
        "tones": list(fresh.keys()),
        "mtime": emotion_mtime,
    })


# ===================== GPU/CPU 热迁移 =====================

import torch as _torch
import gc as _gc

OFFLOAD_DELAY = 3.0  # 请求结束后等待 N 秒再 offload，防止连续请求反复切换

_EMPTY_CACHE = {
    "ref_audio_path": None,
    "prompt_semantic": None,
    "refer_spec": [],
    "prompt_text": None,
    "prompt_lang": None,
    "phones": None,
    "bert_features": None,
    "norm_text": None,
    "aux_ref_audio_paths": [],
}


def _do_gpu_offload():
    """同步卸载 GPU 模型到 CPU"""
    tts_pipeline.set_device(_torch.device("cpu"), save=False)
    tts_pipeline.prompt_cache = dict(_EMPTY_CACHE)
    _gc.collect()
    _torch.cuda.synchronize()
    _torch.cuda.empty_cache()
    _gc.collect()
    _torch.cuda.empty_cache()
    # 释放 cuBLAS workspace，清除 GPU Context 残留
    _torch._C._cuda_clearCublasWorkspaces()
    _gc.collect()
    _torch.cuda.empty_cache()
    tts_pipeline.empty_cache()


def _do_gpu_reload():
    """同步加载模型到 GPU"""
    tts_pipeline.set_device(_torch.device("cuda"), save=False)
    if tts_pipeline.configs.is_half:
        tts_pipeline.enable_half_precision(True, save=False)
    tts_pipeline.prompt_cache = dict(_EMPTY_CACHE)
    tts_pipeline.empty_cache()


class ModelGuard:
    """请求级模型生命周期管理：请求到达时自动 reload，空闲后自动 offload"""

    def __init__(self):
        self._active = 0
        self._offload_task: asyncio.Task | None = None
        self.offload_delay: float = OFFLOAD_DELAY

    def acquire(self):
        """请求开始时调用：取消 pending offload，按需 reload"""
        if self._offload_task and not self._offload_task.done():
            self._offload_task.cancel()
            self._offload_task = None
        self._active += 1
        if str(tts_pipeline.configs.device) != "cuda":
            _do_gpu_reload()

    def release(self):
        """请求结束时调用：无活跃请求则调度延迟 offload"""
        self._active -= 1
        if self._active == 0:
            self._schedule_offload()

    def _schedule_offload(self):
        async def _delayed():
            await asyncio.sleep(self.offload_delay)
            if self._active == 0:
                _do_gpu_offload()

        self._offload_task = asyncio.create_task(_delayed())

    def is_gpu_ready(self) -> bool:
        return str(tts_pipeline.configs.device) == "cuda"

    def start_idle_timer(self):
        """启动时调用：如果模型在 GPU 上，开始空闲计时"""
        if self.is_gpu_ready() and self._active == 0:
            self._schedule_offload()


model_guard = ModelGuard()


@APP.on_event("startup")
async def startup_event():
    """服务启动后，触发初始空闲计时"""
    model_guard.start_idle_timer()


@APP.get("/gpu_offload")
async def gpu_offload():
    """手动触发 GPU → CPU"""
    _do_gpu_offload()
    return {"status": "ok", "device": "cpu"}


@APP.get("/gpu_reload")
async def gpu_reload():
    """手动触发 CPU → GPU"""
    _do_gpu_reload()
    return {"status": "ok", "device": "cuda"}


@APP.get("/status")
async def status():
    """查看当前模型状态"""
    return {
        "device": str(tts_pipeline.configs.device),
        "active_requests": model_guard._active,
        "offload_delay": model_guard.offload_delay,
        "pending_offload": model_guard._offload_task is not None and not model_guard._offload_task.done(),
    }


@APP.get("/set_offload_delay")
async def set_offload_delay(seconds: float = None):
    """设置请求结束后的 offload 延迟（秒），0 表示立即 offload"""
    if seconds is None or seconds < 0:
        return JSONResponse(status_code=400, content={"message": "seconds must be >= 0"})
    model_guard.offload_delay = seconds
    return {"message": f"offload_delay set to {seconds}s"}


@APP.get("/reload_config")
async def reload_config():
    """从 JSON 文件重新加载配置（运行时已切换的模型权重路径保留不覆盖）"""
    global tts_defaults, tts_config_schema
    old_gpt = tts_config_schema.get("models", {}).get("gpt_weights_path", {}).get("value", "")
    old_sovits = tts_config_schema.get("models", {}).get("sovits_weights_path", {}).get("value", "")
    new_schema = load_schema(CONFIG_FILE)
    if old_gpt:
        new_schema.setdefault("models", {}).setdefault("gpt_weights_path", {})["value"] = old_gpt
    if old_sovits:
        new_schema.setdefault("models", {}).setdefault("sovits_weights_path", {})["value"] = old_sovits
    tts_config_schema = new_schema
    tts_defaults = schema_to_flat(tts_config_schema)
    return JSONResponse(status_code=200, content={"message": "config reloaded", "config": tts_config_schema})


if __name__ == "__main__":
    try:
        if host == "None":
            host = None
        uvicorn.run(app=APP, host=host, port=port, workers=1)
    except Exception:
        traceback.print_exc()
        os.kill(os.getpid(), signal.SIGTERM)
        exit(0)
