# Hermes 微信语音

`hermes-weixin-voice` 是 Hermes 微信 Agent 的双向语音 I/O 层：
让 Agent 能够**听懂**微信语音消息，并将回复**以语音发送**回对话。

本地 Python 包，集成了神经网络 TTS、神经网络 STT、腾讯 SILK_V3 编解码器以及 iLink Bot 传输协议，构成完整的语音处理流水线。同时附有证据，记录了公开 iLink Bot 路径无法渲染原生语音气泡的原因，以及现有的替代方案。

## 功能说明

```
┌──────────────────────── 入站 (STT) ────────────────────────┐
  微信语音消息  →  SILK_V3  →  16 kHz PCM  →  faster-whisper  →  文本
└────────────────────────────────────────────────────────────┘

┌──────────────────────── 出站 (TTS) ────────────────────────┐
  Agent 回复文本  →  Piper（本地）| edge-tts（云端，免费）  →
                     24 kHz PCM  →  SILK_V3（腾讯格式）
                                       ↓
                                  AES-128-ECB 加密
                                       ↓
                               iLink CDN 上传
                                       ↓
                          ITEM_VOICE / ITEM_FILE 发送
└────────────────────────────────────────────────────────────┘
```

### 端到端演示（真实输出）

```text
$ python -c "..."  # 合成 → 编码 → 转录 往返测试
IN:  今天天气真好,我们一起去公园散步吧
OUT: 今天天氣真好,我們一起去公園散步吧。
duration_ms: 3900
```

TTS 流水线生成的腾讯 SILK_V3 文件结构合法（`\x02#!SILK_V3` 魔数头、约 24 kHz、时长与播放一致），iLink 层可正常上传并发送至目标 wxid。

## 功能状态

| 功能 | 状态 | 备注 |
|---|---|---|
| **TTS**（文本→语音） | ✅ 已验证 | Piper（本地 ONNX）或 edge-tts（微软云，免费）→ 24 kHz 单声道 → SILK_V3 腾讯格式 |
| **STT**（语音→文本） | ✅ 已验证 | SILK / WAV / MP3 → faster-whisper（`base`，int8，CPU） |
| **微信文件附件发送** | ✅ 已验证 | `ITEM_FILE` 可端到端到达目标对话 |
| **微信原生语音气泡** | ⚠️ 未解决 | `ITEM_VOICE` API 调用成功，但个人微信客户端不渲染 — 详见[工程发现](#工程发现) |
| **Doctor / 本地诊断** | ✅ 已验证 | ffmpeg、Base URL、Token、Context token 预检 |

测试套件：`27 passed, 1 skipped`（skipped 为网络测试，设置 `HV_RUN_NETWORK_TESTS=1` 启用）。

## 快速开始

macOS：

```bash
git clone https://github.com/UNlawrence/hermes-weixin-voice-clean.git hermes-voice
cd hermes-voice
./install.command   # 或：./scripts/install.sh
```

安装脚本会：

- 自动安装 `uv`（如未安装）
- 通过 Homebrew 安装 `ffmpeg`（如已安装 Homebrew）
- 安装 `hermes-voice`、`hermes-voice-doctor`、`hermes-voice-stt` 命令
- 将 Hermes Skill 复制到 `~/.hermes/skills/hermes-voice`

安装过程中会提示选择 Piper TTS 语音模型（默认：`zh_CN-huayan-medium`，约 63 MB）。
首次 STT 调用时会从 HuggingFace 下载 faster-whisper `base` 模型（约 145 MB）。
两个缓存均为本地缓存 — 安装完成后 Agent **可完全离线运行**。

如需重新设置或更换语音：

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-setup
```

## 命令行

### TTS — 发送合成语音

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice wxid_xxx "今天天气真好"
```

输出：将文本合成为语音，编码为 SILK_V3，通过 iLink 上传并发送，打印 `{msg_id, duration_ms, silk_size, silk_md5, cleaned_text}`。

### STT — 转录音频文件

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-stt /path/to/voice.silk --language zh
```

通过文件头字节自动识别 SILK 格式；其他格式（WAV/MP3/M4A/OGG）交由 ffmpeg 处理。

### 生成真实 `.silk` 测试文件

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/generate_test_silk.py \
    --text "这是一条测试语音" --keep-wav
```

输出 `md5`、`first16_hex`、`duration_ms`，可独立调试 SILK 编码器（不依赖网络路径）。

### Doctor — 检查本地环境

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-doctor
UV_CACHE_DIR=.uv-cache uv run hermes-voice-doctor wxid_xxx
```

检查 ffmpeg、iLink Base URL、Token、Hermes 账号配置，以及目标 wxid 的 context token 是否存在（可选）。

### 文件附件备选方案（已验证可靠）

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice wxid_xxx \
    --send-audio-file /tmp/voice.wav
```

以 `ITEM_FILE` 形式发送音频。这是目前经过验证的可靠发送方式 — 详见下文。

## 编程 API

```python
import asyncio
from hermes_voice import (
    send_voice_from_text,   # TTS → SILK → iLink 发送
    transcribe,             # SILK/WAV/MP3 字节 → 文本
)

async def main():
    # 出站
    result = await send_voice_from_text("你好,我是 Hermes", "wxid_xxx")
    print(result.msg_id, result.duration_ms)

    # 入站
    voice_bytes = open("/path/to/wechat_voice.silk", "rb").read()
    text = await transcribe(voice_bytes, language="zh")
    print(text)

asyncio.run(main())
```

## 工程发现

本项目用于追踪个人微信账号通过公开 iLink Bot 基础设施的完整出站语音路径。完整分析见 [WEIXIN_VOICE_ANALYSIS.md](WEIXIN_VOICE_ANALYSIS.md)；简要结论：

1. **本地编码正确。** 生成的 `.silk` 文件具有合法的腾讯 `SILK_V3` 头部、正确的时长、稳定的 size/md5。
2. **原生语音负载正确。** 携带 `voice_item.media`（AES-128-ECB 密文）的 `ITEM_VOICE` 请求可通过 iLink CDN 正常上传；`sendmessage` 返回 `ret=0`。
3. **个人微信客户端仍不渲染。** 对照实验（标记文本 + 立即发送语音）显示文本可到达，语音在接收端客户端中不出现。
4. **`ITEM_FILE` 音频附件可正常到达。** 相同媒体字节、相同目标、仅 `item.type` 不同 — 每次均可送达。

简短结论：`ITEM_VOICE` 在公开 iLink Bot 路径上被 API 层接受，但目前不被个人微信客户端渲染。音频文件附件路径是目前经过验证的可靠方案。

## 路线图 / 待验证假设

以下是值得继续探索的假设：

1. 公开 iLink Bot 的出站 `ITEM_VOICE` 被 API 基础设施接受，但在到达个人客户端渲染前被过滤。
2. 公开参考实现暴露了语音负载 Schema，但不保证个人客户端的送达支持。
3. 真正的出站语音气泡支持可能需要额外的私有/内部字段。
4. 如果产品需求严格要求"微信语音气泡"，目前最可信的路径是微信客户端自动化：驱动官方客户端自行录制并发送音频。

## 配置

优先级顺序：

1. `.env` 中的 `HV_*` 配置项
2. `~/.hermes/weixin/accounts/*.json` 中的本地 Hermes 微信账号配置
3. 默认值

`.env` 示例：

```env
HV_ILINK_BASE_URL=http://127.0.0.1:8080
HV_ILINK_TOKEN=

# TTS 引擎："piper"（本地，离线）或 "edge"（微软云，免费，无需 API Key）
HV_TTS_ENGINE=piper

# Piper 配置（HV_TTS_ENGINE=piper 时使用），由 `hermes-voice-setup` 写入
HV_TTS_MODEL_PATH=

# edge-tts 配置（HV_TTS_ENGINE=edge 时使用）
HV_TTS_VOICE=zh-CN-XiaoxiaoNeural
HV_TTS_RATE=+0%
HV_TTS_PITCH=+0Hz

# STT（本地 faster-whisper，完全离线）
HV_STT_MODEL=base                  # tiny / base / small / medium / large-v3
HV_STT_COMPUTE_TYPE=int8           # int8 / int8_float16 / float16 / float32
HV_STT_DEVICE=cpu                  # cpu / cuda / auto
```

如果已在使用 Hermes 微信，iLink 相关字段会从现有账号配置中自动加载，通常无需手动填写。

## 开发

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

`slow` 标记涵盖 STT 往返测试（TTS → SILK → STT），首次运行时会下载 Whisper 模型。

## 范围说明

本仓库是：

- Hermes 微信 Agent 的可用双向语音 I/O 层
- 可复现的 SILK / iLink 实验套件
- 对公开 iLink Bot 出站语音在个人微信客户端不可用原因的有据可查的分析

它**不是**开箱即用的原生语音气泡发送工具 — 该路径目前仍未解决，原因已在上文说明。

## 许可证

MIT — 见 [LICENSE](LICENSE)。
