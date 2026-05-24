import asyncio
import hashlib
from dataclasses import dataclass

from .audio import audio_to_silk
from .cleaner import clean_for_tts
from .ilink import ILinkClient, ILinkHttpClient
from .tts import synthesize


@dataclass(slots=True)
class SendResult:
    msg_id: str
    duration_ms: int
    silk_size: int
    silk_md5: str
    cleaned_text: str


_default_client: ILinkClient | None = None


def _get_default_client() -> ILinkClient:
    global _default_client
    if _default_client is None:
        _default_client = ILinkHttpClient()
    return _default_client


async def send_voice_from_text(
    text: str,
    to_wxid: str,
    client: ILinkClient | None = None,
) -> SendResult:
    cleaned = clean_for_tts(text)
    mp3 = await synthesize(cleaned)
    silk, duration_ms = audio_to_silk(mp3)
    cli = client or _get_default_client()
    msg_id = await cli.send_voice(to_wxid, silk, duration_ms)
    return SendResult(
        msg_id=msg_id,
        duration_ms=duration_ms,
        silk_size=len(silk),
        silk_md5=hashlib.md5(silk).hexdigest(),
        cleaned_text=cleaned,
    )


def send_voice_from_text_sync(
    text: str,
    to_wxid: str,
    client: ILinkClient | None = None,
) -> SendResult:
    return asyncio.run(send_voice_from_text(text, to_wxid, client))
