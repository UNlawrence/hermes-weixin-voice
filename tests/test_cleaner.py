from hermes_voice.cleaner import clean_for_tts


def test_strips_markdown_bold_and_links():
    out = clean_for_tts("Hello **world**, see [docs](https://x.com/a) please.")
    assert "**" not in out
    assert "[" not in out
    assert "https://" not in out
    assert "world" in out
    assert "docs" in out


def test_strips_code_blocks():
    src = "before\n```python\nprint('x')\n```\nafter"
    out = clean_for_tts(src)
    assert "print" not in out
    assert "代码省略" in out
    assert "before" in out and "after" in out


def test_strips_emoji():
    out = clean_for_tts("好的 👍🎉 收到")
    assert "👍" not in out and "🎉" not in out
    assert "好的" in out and "收到" in out


def test_truncates_long_text():
    long = "啊" * 2000
    out = clean_for_tts(long, max_chars=100)
    assert len(out) <= 120
    assert out.endswith("等等。")


def test_empty():
    assert clean_for_tts("") == ""
    assert clean_for_tts("   ") == ""


def test_headers_and_lists():
    src = "# Title\n- one\n- two\n\n> quote"
    out = clean_for_tts(src)
    assert "#" not in out
    assert "- " not in out
    assert "> " not in out
    assert "Title" in out and "one" in out
