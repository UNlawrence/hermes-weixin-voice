class HermesVoiceError(Exception):
    """Base for all hermes_voice errors."""


class TTSError(HermesVoiceError):
    pass


class STTError(HermesVoiceError):
    pass


class AudioError(HermesVoiceError):
    pass


class VoiceTooLongError(AudioError):
    def __init__(self, duration_ms: int, max_ms: int):
        super().__init__(f"voice {duration_ms}ms exceeds max {max_ms}ms")
        self.duration_ms = duration_ms
        self.max_ms = max_ms


class ILinkError(HermesVoiceError):
    pass


class ILinkRateLimitedError(ILinkError):
    """iLink server returned ret=-2 (rate limited). Caller may retry with backoff."""

    def __init__(self, endpoint: str, errmsg: str | None = None):
        super().__init__(f"rate limited on {endpoint}: {errmsg or ''}".rstrip(": "))
        self.endpoint = endpoint
        self.errmsg = errmsg
