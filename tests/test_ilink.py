import asyncio
import base64
import json

import pytest


def test_load_context_token_reads_hermes_store(tmp_path, monkeypatch):
    from hermes_voice import ilink

    home = tmp_path / "home"
    token_path = home / ".hermes" / "weixin" / "accounts" / "acct.context-tokens.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text('{"wxid_test":"ctx-123"}', encoding="utf-8")

    monkeypatch.setattr(ilink.Path, "home", lambda: home)
    assert ilink._load_context_token("acct", "wxid_test") == "ctx-123"


def test_load_context_token_accepts_wxid_prefixed_alias(tmp_path, monkeypatch):
    from hermes_voice import ilink

    home = tmp_path / "home"
    token_path = home / ".hermes" / "weixin" / "accounts" / "acct.context-tokens.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text('{"abc@im.wechat":"ctx-123"}', encoding="utf-8")

    monkeypatch.setattr(ilink.Path, "home", lambda: home)
    assert ilink._load_context_token("acct", "wxid_abc@im.wechat") == "ctx-123"


def test_headers_match_hermes_style():
    from hermes_voice.ilink import _headers

    headers = _headers("secret", "{}")
    assert headers["Authorization"] == "Bearer secret"
    assert headers["AuthorizationType"] == "ilink_bot_token"
    assert headers["iLink-App-Id"] == "bot"
    assert "X-WECHAT-UIN" in headers


def test_build_voice_item_uses_native_voice_payload():
    from hermes_voice.ilink import ILinkHttpClient

    item = ILinkHttpClient()._build_voice_item(
        encrypt_query_param="enc-q",
        aes_key_for_api=base64.b64encode(b"616263").decode("ascii"),
        duration_ms=1500,
    )
    voice = item["voice_item"]
    assert item["type"] == 3
    assert voice["encode_type"] == 6
    assert voice["sample_rate"] == 24000
    assert voice["bits_per_sample"] == 16
    assert voice["playtime"] == 1500


def test_send_voice_uses_hermes_endpoints(monkeypatch):
    from hermes_voice import ilink

    calls = []

    async def fake_api_post(self, cli, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == ilink.EP_GET_UPLOAD_URL:
            return {"upload_full_url": "https://cdn.example.com/upload"}
        if endpoint == ilink.EP_SEND_MESSAGE:
            return {"ret": 0}
        raise AssertionError(endpoint)

    async def fake_upload(self, cli, upload_url, ciphertext):
        calls.append(("upload", {"url": upload_url, "size": len(ciphertext)}))
        return "enc-param"

    monkeypatch.setattr(
        ilink,
        "_resolve_context_token",
        lambda account_id, to_wxid: (to_wxid, "ctx-123"),
    )
    monkeypatch.setattr(ilink.ILinkHttpClient, "_api_post", fake_api_post)
    monkeypatch.setattr(ilink.ILinkHttpClient, "_upload_ciphertext", fake_upload)

    client = ilink.ILinkHttpClient(
        account_id="acct",
        base_url="https://ilink.example.com",
        token="secret",
    )
    msg_id = asyncio.run(client.send_voice("wxid_test", b"\x02#!SILK_V3\x01\x00", 900))

    assert msg_id.startswith("hermes-voice-")
    assert calls[0][0] == ilink.EP_GET_UPLOAD_URL
    assert calls[0][1]["media_type"] == ilink.MEDIA_VOICE
    assert calls[1][0] == "upload"
    assert calls[2][0] == ilink.EP_SEND_MESSAGE
    msg = calls[2][1]["msg"]
    assert msg["to_user_id"] == "wxid_test"
    assert msg["context_token"] == "ctx-123"
    assert msg["item_list"][0]["voice_item"]["sample_rate"] == 24000


def test_send_voice_uses_resolved_target_for_upload_and_input_target_for_message(tmp_path, monkeypatch):
    from hermes_voice import ilink

    calls = []
    home = tmp_path / "home"
    token_path = home / ".hermes" / "weixin" / "accounts" / "acct.context-tokens.json"
    token_path.parent.mkdir(parents=True)
    token_path.write_text('{"abc@im.wechat":"ctx-123"}', encoding="utf-8")

    async def fake_api_post(self, cli, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == ilink.EP_GET_UPLOAD_URL:
            return {"upload_full_url": "https://cdn.example.com/upload"}
        if endpoint == ilink.EP_SEND_MESSAGE:
            return {"ret": 0}
        raise AssertionError(endpoint)

    async def fake_upload(self, cli, upload_url, ciphertext):
        return "enc-param"

    monkeypatch.setattr(ilink.Path, "home", lambda: home)
    monkeypatch.setattr(ilink.ILinkHttpClient, "_api_post", fake_api_post)
    monkeypatch.setattr(ilink.ILinkHttpClient, "_upload_ciphertext", fake_upload)

    client = ilink.ILinkHttpClient(
        account_id="acct",
        base_url="https://ilink.example.com",
        token="secret",
    )
    asyncio.run(client.send_voice("wxid_abc@im.wechat", b"\x02#!SILK_V3\x01\x00", 900))

    assert calls[0][1]["to_user_id"] == "abc@im.wechat"
    assert calls[1][1]["msg"]["to_user_id"] == "wxid_abc@im.wechat"
    assert calls[1][1]["msg"]["context_token"] == "ctx-123"


def test_send_audio_file_attachment_uses_file_item(tmp_path, monkeypatch):
    from hermes_voice import ilink

    calls = []
    audio_path = tmp_path / "test.wav"
    audio_path.write_bytes(b"RIFF-audio")

    async def fake_api_post(self, cli, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == ilink.EP_GET_UPLOAD_URL:
            return {"upload_full_url": "https://cdn.example.com/upload"}
        if endpoint == ilink.EP_SEND_MESSAGE:
            return {"ret": 0}
        raise AssertionError(endpoint)

    async def fake_upload(self, cli, upload_url, ciphertext):
        calls.append(("upload", {"url": upload_url, "size": len(ciphertext)}))
        return "enc-param"

    monkeypatch.setattr(
        ilink,
        "_resolve_context_token",
        lambda account_id, to_wxid: ("abc@im.wechat", "ctx-123"),
    )
    monkeypatch.setattr(ilink.ILinkHttpClient, "_api_post", fake_api_post)
    monkeypatch.setattr(ilink.ILinkHttpClient, "_upload_ciphertext", fake_upload)

    client = ilink.ILinkHttpClient(
        account_id="acct",
        base_url="https://ilink.example.com",
        token="secret",
    )
    msg_id = asyncio.run(client.send_audio_file_attachment("wxid_abc@im.wechat", audio_path))

    assert msg_id.startswith("hermes-audio-file-")
    assert calls[0][1]["media_type"] == ilink.MEDIA_FILE
    assert calls[0][1]["to_user_id"] == "abc@im.wechat"
    msg = calls[2][1]["msg"]
    assert msg["to_user_id"] == "abc@im.wechat"
    assert msg["context_token"] == "ctx-123"
    item = msg["item_list"][0]
    assert item["type"] == ilink.ITEM_FILE
    assert item["file_item"]["file_name"] == "test.wav"


def test_send_voice_requires_context_token(monkeypatch):
    from hermes_voice import ilink
    from hermes_voice.errors import ILinkError

    monkeypatch.setattr(ilink, "_load_context_token", lambda account_id, to_wxid: None)
    client = ilink.ILinkHttpClient(
        account_id="acct",
        base_url="https://ilink.example.com",
        token="secret",
    )

    with pytest.raises(ILinkError, match="context_token"):
        asyncio.run(client.send_voice("wxid_test", b"\x02#!SILK_V3\x01\x00", 900))


def test_send_silk_file_experiment_logs_preview_and_sends_voice(tmp_path, monkeypatch, capsys):
    from hermes_voice import ilink

    calls = []
    silk_path = tmp_path / "sample.silk"
    silk_path.write_bytes(b"\x02#!SILK_V3\x01\x00")

    async def fake_api_post(self, cli, endpoint, payload):
        calls.append((endpoint, payload))
        if endpoint == ilink.EP_GET_UPLOAD_URL:
            return {"upload_full_url": "https://cdn.example.com/upload"}
        if endpoint == ilink.EP_SEND_MESSAGE:
            return {"ret": 0}
        raise AssertionError(endpoint)

    async def fake_upload(self, cli, upload_url, ciphertext):
        calls.append(("upload", {"url": upload_url, "size": len(ciphertext)}))
        return "enc-param"

    monkeypatch.setattr(
        ilink,
        "_resolve_context_token",
        lambda account_id, to_wxid: (to_wxid, "ctx-123"),
    )
    monkeypatch.setattr(ilink.ILinkHttpClient, "_api_post", fake_api_post)
    monkeypatch.setattr(ilink.ILinkHttpClient, "_upload_ciphertext", fake_upload)

    client = ilink.ILinkHttpClient(
        account_id="acct",
        base_url="https://ilink.example.com",
        token="secret",
    )
    msg_id = asyncio.run(client.send_silk_file_experiment("wxid_test", silk_path, 900))

    captured = capsys.readouterr().out
    assert msg_id.startswith("hermes-voice-")
    assert '"file_path"' in captured
    assert '"suffix": ".silk"' in captured
    assert f'"selected_media_type": {ilink.MEDIA_VOICE}' in captured
    assert '"is_item_voice": true' in captured
    assert '"type": 3' in captured
    assert '"voice_item"' in captured
    assert calls[0][0] == ilink.EP_GET_UPLOAD_URL
    assert calls[0][1]["media_type"] == ilink.MEDIA_VOICE
