import asyncio
import os

import pytest

from hermes_voice import ILinkFakeClient, send_voice_from_text


pytestmark = pytest.mark.skipif(
    os.environ.get("HV_RUN_NETWORK_TESTS") != "1",
    reason="needs a Piper model installed via `hermes-voice-setup`; set HV_RUN_NETWORK_TESTS=1 to run",
)


def test_send_voice_from_text_with_fake_client():
    fake = ILinkFakeClient()
    result = asyncio.run(
        send_voice_from_text(
            "你好,这是一段测试语音。", "fake_wxid_123", client=fake
        )
    )
    assert result.msg_id.startswith("fake-")
    assert result.duration_ms > 0
    assert result.silk_size > 100
    assert len(result.silk_md5) == 32
    assert fake.last_path is not None
    assert fake.last_path.exists()
    head = fake.last_path.read_bytes()[:12]
    assert head.startswith(b"\x02#!SILK_V3"), f"bad silk header: {head!r}"
