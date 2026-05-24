import pilk

from .errors import (
    AudioError,
    HermesVoiceError,
    ILinkError,
    STTError,
    TTSError,
    VoiceTooLongError,
)
from .ilink import ILinkClient, ILinkFakeClient, ILinkHttpClient
from .pipeline import SendResult, send_voice_from_text, send_voice_from_text_sync
from .stt import transcribe

__all__ = [
    "AudioError",
    "HermesVoiceError",
    "ILinkClient",
    "ILinkError",
    "ILinkFakeClient",
    "ILinkHttpClient",
    "STTError",
    "SendResult",
    "TTSError",
    "VoiceTooLongError",
    "send_voice_from_text",
    "send_voice_from_text_sync",
    "transcribe",
]


def main() -> None:
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(
        prog="hermes-voice",
        description="Send a WeChat native voice bubble through Hermes/iLink.",
    )
    parser.add_argument("to_wxid", help="Target WeChat wxid.")
    parser.add_argument("text", nargs="*", help="Text to synthesize and send.")
    parser.add_argument(
        "--send-silk",
        dest="silk_path",
        help="Experiment: send an existing .silk file as a native voice bubble.",
    )
    parser.add_argument(
        "--send-audio-file",
        dest="audio_file_path",
        help="Send an existing audio file as a Weixin file attachment fallback.",
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=None,
        help="Playback duration for --send-silk experiments. Defaults to the real SILK duration.",
    )
    args = parser.parse_args()

    if args.silk_path:
        duration_ms = args.duration_ms
        if duration_ms is None:
            duration_ms = pilk.get_duration(args.silk_path)
            if duration_ms <= 0:
                parser.error("Could not determine duration from SILK file; pass --duration-ms explicitly")
        client = ILinkHttpClient()
        msg_id = asyncio.run(
            client.send_silk_file_experiment(args.to_wxid, args.silk_path, duration_ms)
        )
        print({"msg_id": msg_id, "silk_path": args.silk_path, "duration_ms": duration_ms})
        return

    if args.audio_file_path:
        client = ILinkHttpClient()
        msg_id = asyncio.run(
            client.send_audio_file_attachment(args.to_wxid, args.audio_file_path)
        )
        print({"msg_id": msg_id, "audio_file_path": args.audio_file_path})
        return

    if not args.text:
        parser.error("text is required unless --send-silk or --send-audio-file is used")

    text = " ".join(args.text)
    result = send_voice_from_text_sync(text, args.to_wxid)
    print(result)
