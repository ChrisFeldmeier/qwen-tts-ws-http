# Qwen-TTS-WS-HTTP

该项目将阿里云 DashScope 的 Qwen-TTS 实时 WebSocket 接口封装为易于使用的 HTTP 接口，支持标准音频文件下载和 SSE (Server-Sent Events) 流式音频推送。

## 功能特性

- **简单 HTTP POST**: 一次性获取完整音频（自动封装为 WAV 格式）。
- **SSE 流式支持**: 实时推送音频分片（Base64 编码的 PCM），降低首包延迟。
- **自动格式转换**: 内部处理 PCM 到 WAV 的转换，方便播放器直接调用。
- **健康检查**: 提供 `/health` 接口用于服务监控。

## 环境要求

- Python 3.13+
- 阿里云 DashScope API Key

## 安装

1. 克隆项目到本地。
2. 安装依赖：
   ```bash
   pip install dashscope fastapi uvicorn
   # 或者使用项目自带的 uv (推荐)
   uv sync
   ```

## 配置

在运行项目之前，需要设置 `DASHSCOPE_API_KEY` 环境变量。你可以通过以下方式设置：

### macOS/Linux
```bash
export DASHSCOPE_API_KEY="您的_DASHSCOPE_API_KEY"
```

### Windows (PowerShell)
```powershell
$env:DASHSCOPE_API_KEY="您的_DASHSCOPE_API_KEY"
```

## 运行

执行以下命令启动服务：

```bash
python main.py
```

服务默认监听 `0.0.0.0:9000`。

## API 文档

### 1. 文本转语音 (返回 WAV 文件)

将文本转换为完整的 WAV 音频文件。

- **URL**: `/tts`
- **方法**: `POST`
- **Content-Type**: `application/json`

**请求体**:

| 字段 | 类型 | 必填 | 默认值 | 说明                                                                                                                                                                                                                                                         |
| :--- | :--- | :--- | :--- |:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `text` | string | 是 | - | 需要合成的文本内容                                                                                                                                                                                                                                                  |
| `model` | string | 是 | - | 使用的模型名称， `qwen3-tts-vd-realtime-2025-12-16`、`qwen3-tts-vc-realtime-2026-01-15`、`qwen3-tts-flash-realtime`。具体信息参考：https://bailian.console.aliyun.com/cn-beijing/?spm=5176.12818093_47.overview_recent.1.67fe16d0rXJopC&tab=doc#/doc/?type=model&url=2938790 |
| `voice` | string | 否 | `Cherry` | 选用的音色名称                                                                                                                                                                                                                                                    |

**示例请求 (cURL)**:

```bash
curl -X POST http://localhost:9000/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，欢迎使用通义千问语音合成服务。",
    "model": "qwen3-tts-flash-realtime",
    "voice": "Cherry"
  }' --output output.wav
```

### 2. 流式文本转语音 (SSE)

通过 SSE 协议实时获取音频片段。

- **URL**: `/tts_stream`
- **方法**: `POST`
- **Content-Type**: `application/json`

**请求体**: 同上。

**示例请求 (cURL)**:

```bash
curl -X POST http://localhost:9000/tts_stream \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是一个流式输出测试。",
    "model": "qwen3-tts-flash-realtime",
    "voice": "Cherry"
  }'
```

**返回内容示例**:

```text
data: {"audio": "...", "is_end": false}
data: {"audio": "...", "is_end": false}
...
data: {"is_end": true}
```
*注：`audio` 字段为 Base64 编码的 PCM (24000Hz, Mono, 16bit) 数据。*

### 3. 健康检查

- **URL**: `/health`
- **方法**: `GET`

**返回**: `{"status": "ok"}`

## 响应头信息

在 `/tts` 接口返回时，会包含以下自定义响应头：
- `X-Session-Id`: 本次合成的会话 ID。
- `X-First-Audio-Delay`: 首包音频延迟（毫秒）。
