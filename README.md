# Hermes Weixin Voice

`hermes-weixin-voice` is the bidirectional voice I/O layer for the
Hermes WeChat agent: it lets the agent **hear**
incoming WeChat voice messages and **speak** replies back into a chat.

It is a local Python package that combines neural TTS, neural STT, the
Tencent SILK_V3 codec, and the iLink bot transport protocol into a single
pipeline. It also documents — with evidence — where the public iLink bot
path stops being able to render outbound *native* voice bubbles, and what
the remaining options are.

## What it does

```
┌──────────────────────── inbound (STT) ────────────────────────┐
  WeChat voice message  →  SILK_V3  →  16 kHz PCM  →  faster-whisper  →  text
└───────────────────────────────────────────────────────────────┘

┌──────────────────────── outbound (TTS) ───────────────────────┐
  agent reply text  →  Piper (local) | edge-tts (cloud, free)   →
                       24 kHz PCM    →  SILK_V3 (Tencent)
                                          ↓
                                     AES-128-ECB
                                          ↓
                                  iLink CDN upload
                                          ↓
                           ITEM_VOICE / ITEM_FILE send
└───────────────────────────────────────────────────────────────┘
```

### End-to-end demo (real output)

```text
$ python -c "..."  # synthesize → encode → transcribe round trip
IN:  今天天气真好,我们一起去公园散步吧
OUT: 今天天氣真好,我們一起去公園散步吧。
duration_ms: 3900
```

Same TTS path produces a structurally valid Tencent SILK_V3 file
(`\x02#!SILK_V3` magic, ~24 kHz, duration matches playback), which the
iLink layer can upload and send to a target wxid.

## Status

| Capability | State | Notes |
|---|---|---|
| **TTS** (text → speech) | ✅ verified | Piper (local, ONNX) or edge-tts (Microsoft cloud, free) → 24 kHz mono → SILK_V3 Tencent variant |
| **STT** (speech → text) | ✅ verified | SILK / WAV / MP3 → faster-whisper (`base`, int8, CPU) |
| **WeChat file attachment send** | ✅ verified | `ITEM_FILE` reaches the target chat end-to-end |
| **WeChat native voice bubble** | ⚠️ unresolved | `ITEM_VOICE` API call succeeds, personal WeChat client does not render — see [analysis](#engineering-findings) |
| **Doctor / local diagnostics** | ✅ verified | ffmpeg, base URL, token, context token preflight |

Test suite: `27 passed, 1 skipped` (the skip is a network-gated TTS test that
runs with `HV_RUN_NETWORK_TESTS=1`).

## Quick start

macOS:

```bash
git clone https://github.com/UNlawrence/hermes-weixin-voice-clean.git hermes-voice
cd hermes-voice
./install.command   # or: ./scripts/install.sh
```

The installer:

- installs `uv` if missing
- installs `ffmpeg` via Homebrew if available
- installs the `hermes-voice`, `hermes-voice-doctor`, and `hermes-voice-stt` commands
- copies the Hermes skill into `~/.hermes/skills/hermes-voice`

During install you'll be prompted to pick a Piper TTS voice model
(default: `zh_CN-huayan-medium`, ~63 MB). First STT call downloads
the faster-whisper `base` model (~145 MB) from HuggingFace. Both
caches are local — after first install the agent runs **fully offline**.

To run setup again or change voice later:

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-setup
```

## Commands

### TTS — send a synthesized reply

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice wxid_xxx "今天天气真好"
```

Output: synthesizes the text, encodes to SILK_V3, uploads via iLink, and
prints `{msg_id, duration_ms, silk_size, silk_md5, cleaned_text}`.

### STT — transcribe an audio file

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-stt /path/to/voice.silk --language zh
```

Auto-detects SILK by header bytes; otherwise hands the file to ffmpeg
(WAV/MP3/M4A/OGG all work).

### Generate a real `.silk` test file

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/generate_test_silk.py \
    --text "这是一条测试语音" --keep-wav
```

Prints `md5`, `first16_hex`, `duration_ms`. Useful for debugging the
SILK encoder independently of the network path.

### Doctor — check local prerequisites

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice-doctor
UV_CACHE_DIR=.uv-cache uv run hermes-voice-doctor wxid_xxx
```

Checks ffmpeg, iLink base URL, token, Hermes account config, and
optionally whether a context token for the target wxid is present.

### File-attachment fallback (verified reliable)

```bash
UV_CACHE_DIR=.uv-cache uv run hermes-voice wxid_xxx \
    --send-audio-file /tmp/voice.wav
```

Sends the audio as `ITEM_FILE`. This is the currently reliable delivery
shape — see findings below.

## Programmatic API

```python
import asyncio
from hermes_voice import (
    send_voice_from_text,   # TTS → SILK → iLink send
    transcribe,             # SILK/WAV/MP3 bytes → text
)

async def main():
    # Outbound
    result = await send_voice_from_text("你好,我是 Hermes", "wxid_xxx")
    print(result.msg_id, result.duration_ms)

    # Inbound
    voice_bytes = open("/path/to/wechat_voice.silk", "rb").read()
    text = await transcribe(voice_bytes, language="zh")
    print(text)

asyncio.run(main())
```

## Engineering findings

This project was used to trace the full outbound voice path for personal
WeChat accounts through the public iLink bot infrastructure. The full
write-up is in [WEIXIN_VOICE_ANALYSIS.md](WEIXIN_VOICE_ANALYSIS.md);
the short version:

1. **Local encoding is correct.** Generated `.silk` files have valid
   Tencent `SILK_V3` headers, expected duration, and stable size/md5.
2. **The native voice payload is correct.** `ITEM_VOICE` requests with
   `voice_item.media` AES-128-ECB ciphertext upload through the iLink
   CDN cleanly; `sendmessage` returns `ret=0`.
3. **The personal WeChat client still doesn't render it.** A controlled
   A/B test (marker text + immediate voice send) showed the text
   arriving and the voice not appearing in the recipient's client.
4. **`ITEM_FILE` audio attachments do arrive.** Same media bytes, same
   target, different `item.type` — delivered every time.

The reduced conclusion: `ITEM_VOICE` over the public iLink bot path is
accepted at the API layer but is not currently rendered by personal
WeChat clients. The audio-file attachment path is the verified-reliable
shape today.

## Roadmap / open hypotheses

These are the remaining hypotheses worth testing:

1. Public iLink bot outbound `ITEM_VOICE` is accepted by API
   infrastructure but filtered before personal-client rendering.
2. Public reference implementations expose the voice payload schema
   without guaranteeing personal-client delivery support.
3. Additional private/internal fields may be required for true
   outbound voice bubble support.
4. If the product requirement is strictly "WeChat voice bubble,"
   the most credible remaining path is WeChat client automation:
   drive the official client to record and send the audio itself.

## Configuration

Priority order:

1. `HV_*` values in `.env`
2. local Hermes Weixin account config in `~/.hermes/weixin/accounts/*.json`
3. fallback defaults

Example `.env`:

```env
HV_ILINK_BASE_URL=http://127.0.0.1:8080
HV_ILINK_TOKEN=

# TTS engine: "piper" (local, offline) or "edge" (Microsoft cloud, free, no key).
HV_TTS_ENGINE=piper

# Piper config (when HV_TTS_ENGINE=piper). Set by `hermes-voice-setup`.
HV_TTS_MODEL_PATH=

# edge-tts config (when HV_TTS_ENGINE=edge)
HV_TTS_VOICE=zh-CN-XiaoxiaoNeural
HV_TTS_RATE=+0%
HV_TTS_PITCH=+0Hz

# STT (local faster-whisper, fully offline)
HV_STT_MODEL=base                  # tiny / base / small / medium / large-v3
HV_STT_COMPUTE_TYPE=int8           # int8 / int8_float16 / float16 / float32
HV_STT_DEVICE=cpu                  # cpu / cuda / auto
```

If you already use Hermes Weixin, the iLink fields are auto-loaded from
the existing account config; you typically don't need to fill them
manually.

## Development

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```

The `slow` marker covers the STT round-trip test (TTS → SILK → STT)
which downloads the Whisper model on first run.

## Scope

This repository is:

- a working bidirectional voice I/O layer for the Hermes WeChat agent
- a reproducible SILK / iLink experiment harness
- an evidence-backed analysis of where public-iLink-bot outbound voice
  delivery currently stops working for personal WeChat clients

It is **not** a turnkey native-voice-bubble sender — that path remains
unresolved and the document above explains why.

## License

MIT — see [LICENSE](LICENSE).
