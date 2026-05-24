import re

from .config import settings

_RE_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_RE_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_RE_MD_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_RE_MD_HEADER = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_RE_MD_LIST = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_RE_MD_QUOTE = re.compile(r"^\s*>\s+", re.MULTILINE)
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_URL = re.compile(r"https?://\S+")
_RE_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "☀-⛿"
    "✀-➿"
    "]+",
    flags=re.UNICODE,
)
_RE_WHITESPACE = re.compile(r"[ \t]+")
_RE_BLANK_LINES = re.compile(r"\n{3,}")


def clean_for_tts(text: str, max_chars: int | None = None) -> str:
    """Strip markdown, emoji, html, urls, and collapse whitespace so the TTS engine
    speaks naturally instead of reading symbols. Truncates over-long input."""
    if not text:
        return ""

    s = _RE_CODE_FENCE.sub(" 代码省略。 ", text)
    s = _RE_INLINE_CODE.sub(r"\1", s)
    s = _RE_MD_IMAGE.sub("", s)
    s = _RE_MD_LINK.sub(r"\1", s)
    s = _RE_HTML_TAG.sub("", s)
    s = _RE_MD_BOLD.sub(r"\1", s)
    s = _RE_MD_ITALIC.sub(r"\1", s)
    s = _RE_MD_HEADER.sub("", s)
    s = _RE_MD_LIST.sub("", s)
    s = _RE_MD_QUOTE.sub("", s)
    s = _RE_URL.sub(" 链接 ", s)
    s = _RE_EMOJI.sub("", s)
    s = _RE_WHITESPACE.sub(" ", s)
    s = _RE_BLANK_LINES.sub("\n\n", s)
    s = s.strip()

    limit = max_chars if max_chars is not None else settings.max_text_chars
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "……等等。"
    return s
