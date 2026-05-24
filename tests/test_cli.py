import pytest


def test_main_send_silk_infers_duration(monkeypatch, tmp_path, capsys):
    import hermes_voice as cli_mod

    silk_path = tmp_path / "sample.silk"
    silk_path.write_bytes(b"\x02#!SILK_V3\x01\x00")
    captured = {}

    class FakeClient:
        async def send_silk_file_experiment(self, to_wxid, path, duration_ms):
            captured["to_wxid"] = to_wxid
            captured["path"] = path
            captured["duration_ms"] = duration_ms
            return "hermes-voice-test"

    monkeypatch.setattr(cli_mod, "ILinkHttpClient", lambda: FakeClient())
    monkeypatch.setattr(cli_mod.pilk, "get_duration", lambda path: 1234)
    monkeypatch.setattr(
        cli_mod,
        "send_voice_from_text_sync",
        lambda text, to_wxid: pytest.fail("text path should not be used"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["hermes-voice", "wxid_test", "--send-silk", str(silk_path)],
    )

    cli_mod.main()

    out = capsys.readouterr().out
    assert captured["to_wxid"] == "wxid_test"
    assert captured["path"] == str(silk_path)
    assert captured["duration_ms"] == 1234
    assert "hermes-voice-test" in out
    assert "1234" in out
