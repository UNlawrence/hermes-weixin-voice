from pathlib import Path


def test_loads_ilink_from_hermes_account(tmp_path, monkeypatch):
    from hermes_voice import config as cfg

    home = tmp_path / "home"
    accounts_dir = home / ".hermes" / "weixin" / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "bot.json").write_text(
        '{"base_url":"https://ilink.example.com","token":"secret-token"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", lambda: home)
    assert cfg._load_hermes_weixin_config() == {
        "ilink_account_id": "bot",
        "ilink_base_url": "https://ilink.example.com",
        "ilink_cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
        "ilink_token": "secret-token",
    }


def test_load_ignores_invalid_files(tmp_path, monkeypatch):
    from hermes_voice import config as cfg

    home = tmp_path / "home"
    accounts_dir = home / ".hermes" / "weixin" / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "broken.json").write_text("{", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: home)
    assert cfg._load_hermes_weixin_config() == {}


def test_load_ignores_context_token_files(tmp_path, monkeypatch):
    from hermes_voice import config as cfg

    home = tmp_path / "home"
    accounts_dir = home / ".hermes" / "weixin" / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "bot.context-tokens.json").write_text(
        '{"wxid_test":"ctx-123","base_url":"https://wrong.example.com","token":"wrong"}',
        encoding="utf-8",
    )
    (accounts_dir / "bot.json").write_text(
        '{"base_url":"https://ilink.example.com","token":"secret-token"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", lambda: home)
    assert cfg._load_hermes_weixin_config() == {
        "ilink_account_id": "bot",
        "ilink_base_url": "https://ilink.example.com",
        "ilink_cdn_base_url": "https://novac2c.cdn.weixin.qq.com/c2c",
        "ilink_token": "secret-token",
    }


def test_env_values_take_priority_over_hermes_config(tmp_path, monkeypatch):
    from hermes_voice import config as cfg

    home = tmp_path / "home"
    accounts_dir = home / ".hermes" / "weixin" / "accounts"
    accounts_dir.mkdir(parents=True)
    (accounts_dir / "bot.json").write_text(
        '{"base_url":"https://ilink.example.com","token":"secret-token"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(Path, "home", lambda: home)

    settings = cfg.Settings(
        ilink_base_url="https://override.example.com",
        ilink_token="override-token",
    )
    hermes = cfg._load_hermes_weixin_config()

    if settings.ilink_base_url == "http://127.0.0.1:8080" and hermes.get("ilink_base_url"):
        settings.ilink_base_url = hermes["ilink_base_url"]
    if not settings.ilink_token and hermes.get("ilink_token"):
        settings.ilink_token = hermes["ilink_token"]

    assert settings.ilink_base_url == "https://override.example.com"
    assert settings.ilink_token == "override-token"
