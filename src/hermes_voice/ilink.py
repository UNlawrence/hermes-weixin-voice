import asyncio
import base64
import hashlib
import json
import secrets
import struct
import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import settings
from .errors import ILinkError, ILinkRateLimitedError

ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"

MEDIA_VOICE = 4
MEDIA_FILE = 3
ITEM_VOICE = 3
ITEM_FILE = 4
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2
API_TIMEOUT_MS = 30_000


class ILinkClient(Protocol):
    async def send_voice(
        self, to_wxid: str, silk: bytes, duration_ms: int
    ) -> str: ...


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _base_info() -> dict[str, str]:
    return {"channel_version": CHANNEL_VERSION}


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _headers(token: str | None, body: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _aes128_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize()


def _aes_padded_size(size: int) -> int:
    return ((size + 1 + 15) // 16) * 16


def _context_token_path(account_id: str) -> Path:
    return Path.home() / ".hermes" / "weixin" / "accounts" / f"{account_id}.context-tokens.json"


def _target_id_candidates(to_wxid: str) -> list[str]:
    candidates = [to_wxid]
    if to_wxid.startswith("wxid_"):
        candidates.append(to_wxid.removeprefix("wxid_"))
    return candidates


def _resolve_context_token(account_id: str, to_wxid: str) -> tuple[str, str] | None:
    path = _context_token_path(account_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    for candidate in _target_id_candidates(to_wxid):
        token = data.get(candidate)
        if token:
            return candidate, str(token).strip()
    return None


def _load_context_token(account_id: str, to_wxid: str) -> str | None:
    resolved = _resolve_context_token(account_id, to_wxid)
    return resolved[1] if resolved else None


class ILinkHttpClient:
    """Hermes-compatible iLink Weixin client."""

    def __init__(
        self,
        account_id: str | None = None,
        base_url: str | None = None,
        cdn_base_url: str | None = None,
        token: str | None = None,
        timeout_ms: int = API_TIMEOUT_MS,
    ):
        self.account_id = (account_id or settings.ilink_account_id).strip()
        self.base_url = (base_url or settings.ilink_base_url).rstrip("/")
        self.cdn_base_url = (cdn_base_url or settings.ilink_cdn_base_url).rstrip("/")
        self.token = token if token is not None else settings.ilink_token
        self.timeout_ms = timeout_ms

    async def _api_post(self, cli: httpx.AsyncClient, endpoint: str, payload: dict) -> dict:
        body = _json_dumps({**payload, "base_info": _base_info()})
        url = f"{self.base_url}/{endpoint}"
        try:
            resp = await cli.post(url, content=body.encode("utf-8"), headers=_headers(self.token, body))
        except httpx.HTTPError as e:
            raise ILinkError(f"iLink request failed: {e}") from e
        if resp.status_code != 200:
            raise ILinkError(f"iLink HTTP {resp.status_code} {endpoint}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ILinkError(f"iLink returned non-JSON from {endpoint}: {resp.text[:200]}") from e

        ret = data.get("ret")
        if ret is not None and ret != 0:
            errmsg = data.get("errmsg") or data.get("errMsg") or ""
            if ret == -2 or "rate" in str(errmsg).lower():
                raise ILinkRateLimitedError(endpoint, errmsg)
            errcode = data.get("errcode")
            raise ILinkError(
                f"iLink {endpoint} ret={ret} errcode={errcode} errmsg={errmsg}"
            )
        return data

    async def _upload_ciphertext(self, cli: httpx.AsyncClient, upload_url: str, ciphertext: bytes) -> str:
        try:
            resp = await cli.post(
                upload_url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=120.0,
            )
        except httpx.HTTPError as e:
            raise ILinkError(f"CDN upload failed: {e}") from e
        if resp.status_code != 200:
            raise ILinkError(f"CDN upload HTTP {resp.status_code}: {resp.text[:200]}")
        encrypted_param = resp.headers.get("x-encrypted-param")
        if not encrypted_param:
            raise ILinkError(f"CDN upload missing x-encrypted-param header: {resp.text[:200]}")
        return encrypted_param

    def _build_voice_item(
        self,
        *,
        encrypt_query_param: str,
        aes_key_for_api: str,
        duration_ms: int,
    ) -> dict:
        return {
            "type": ITEM_VOICE,
            "voice_item": {
                "media": {
                    "encrypt_query_param": encrypt_query_param,
                    "aes_key": aes_key_for_api,
                    "encrypt_type": 1,
                },
                "encode_type": 6,
                "bits_per_sample": 16,
                "sample_rate": 24000,
                "playtime": max(0, duration_ms),
            },
        }

    def _preview_silk_file_send(
        self,
        silk_path: str | Path,
        duration_ms: int,
        *,
        force_file_attachment: bool = False,
    ) -> tuple[int, dict]:
        path = Path(silk_path)
        suffix = path.suffix.lower()
        media_type = MEDIA_VOICE if suffix == ".silk" and not force_file_attachment else -1
        item = self._build_voice_item(
            encrypt_query_param="preview-encrypt-query-param",
            aes_key_for_api="preview-aes-key",
            duration_ms=duration_ms,
        )
        log_payload = {
            "file_path": str(path),
            "suffix": suffix,
            "selected_media_type": media_type,
            "is_item_voice": item.get("type") == ITEM_VOICE,
            "item_type": item.get("type"),
            "has_voice_item": "voice_item" in item,
        }
        print("DEBUG silk send preview:", json.dumps(log_payload, ensure_ascii=False))
        print("DEBUG silk send item:", json.dumps(item, ensure_ascii=False))
        return media_type, item

    async def send_silk_file_experiment(
        self,
        to_wxid: str,
        silk_path: str | Path,
        duration_ms: int,
    ) -> str:
        path = Path(silk_path)
        media_type, _ = self._preview_silk_file_send(
            path,
            duration_ms,
            force_file_attachment=False,
        )
        if media_type != MEDIA_VOICE:
            raise ILinkError(
                f"Experiment requires a .silk file that resolves to MEDIA_VOICE, got {path}"
            )
        silk = path.read_bytes()
        return await self.send_voice(to_wxid, silk, duration_ms)

    def _build_file_item(
        self,
        *,
        encrypt_query_param: str,
        aes_key_for_api: str,
        filename: str,
        rawsize: int,
        rawfilemd5: str,
    ) -> dict:
        return {
            "type": ITEM_FILE,
            "file_item": {
                "media": {
                    "encrypt_query_param": encrypt_query_param,
                    "aes_key": aes_key_for_api,
                    "encrypt_type": 1,
                },
                "file_name": filename,
                "md5": rawfilemd5,
                "len": str(rawsize),
            },
        }

    async def send_audio_file_attachment(
        self,
        to_wxid: str,
        audio_path: str | Path,
    ) -> str:
        if not self.token:
            raise ILinkError("iLink token missing")
        if not self.account_id:
            raise ILinkError("iLink account_id missing")

        resolved_context = _resolve_context_token(self.account_id, to_wxid)
        if not resolved_context:
            raise ILinkError(
                "No Weixin context_token for this target. Ask the target to send "
                "one message to the Hermes Weixin bot first, wait for the gateway "
                "to receive it, then retry."
            )
        resolved_to_wxid, context_token = resolved_context
        path = Path(audio_path)
        payload = path.read_bytes()
        filekey = secrets.token_hex(16)
        aes_key = secrets.token_bytes(16)
        rawsize = len(payload)
        rawfilemd5 = hashlib.md5(payload).hexdigest()
        ciphertext = _aes128_ecb_encrypt(payload, aes_key)

        timeout = httpx.Timeout(self.timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            upload_meta = await self._api_post(
                cli,
                EP_GET_UPLOAD_URL,
                {
                    "filekey": filekey,
                    "media_type": MEDIA_FILE,
                    "to_user_id": resolved_to_wxid,
                    "rawsize": rawsize,
                    "rawfilemd5": rawfilemd5,
                    "filesize": _aes_padded_size(rawsize),
                    "no_need_thumb": True,
                    "aeskey": aes_key.hex(),
                },
            )
            upload_url = str(upload_meta.get("upload_full_url") or "").strip()
            if not upload_url:
                upload_param = str(upload_meta.get("upload_param") or "").strip()
                if not upload_param:
                    raise ILinkError("getuploadurl returned neither upload_full_url nor upload_param")
                upload_url = (
                    f"{self.cdn_base_url}/upload"
                    f"?encrypted_query_param={upload_param}&filekey={filekey}"
                )

            encrypted_query_param = await self._upload_ciphertext(cli, upload_url, ciphertext)
            aes_key_for_api = base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii")
            message_id = f"hermes-audio-file-{uuid4().hex}"
            msg = {
                "from_user_id": "",
                "to_user_id": resolved_to_wxid,
                "client_id": message_id,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [
                    self._build_file_item(
                        encrypt_query_param=encrypted_query_param,
                        aes_key_for_api=aes_key_for_api,
                        filename=path.name,
                        rawsize=rawsize,
                        rawfilemd5=rawfilemd5,
                    )
                ],
                "context_token": context_token,
            }
            body = await self._api_post(cli, EP_SEND_MESSAGE, {"msg": msg})
            print("DEBUG sendmessage response:", json.dumps(body, indent=2, ensure_ascii=False))
            return message_id

    async def send_voice(
        self, to_wxid: str, silk: bytes, duration_ms: int
    ) -> str:
        if not self.token:
            raise ILinkError("iLink token missing")
        if not self.account_id:
            raise ILinkError("iLink account_id missing")

        resolved_context = _resolve_context_token(self.account_id, to_wxid)
        if not resolved_context:
            raise ILinkError(
                "No Weixin context_token for this target. Ask the target to send "
                "one message to the Hermes Weixin bot first, wait for the gateway "
                "to receive it, then retry."
            )
        upload_to_wxid, context_token = resolved_context
        filekey = secrets.token_hex(16)
        aes_key = secrets.token_bytes(16)
        rawsize = len(silk)
        rawfilemd5 = hashlib.md5(silk).hexdigest()
        ciphertext = _aes128_ecb_encrypt(silk, aes_key)

        timeout = httpx.Timeout(self.timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            upload_meta = await self._api_post(
                cli,
                EP_GET_UPLOAD_URL,
                {
                    "filekey": filekey,
                    "media_type": MEDIA_VOICE,
                    "to_user_id": upload_to_wxid,
                    "rawsize": rawsize,
                    "rawfilemd5": rawfilemd5,
                    "filesize": _aes_padded_size(rawsize),
                    "no_need_thumb": True,
                    "aeskey": aes_key.hex(),
                },
            )
            upload_url = str(upload_meta.get("upload_full_url") or "").strip()
            if not upload_url:
                upload_param = str(upload_meta.get("upload_param") or "").strip()
                if not upload_param:
                    raise ILinkError("getuploadurl returned neither upload_full_url nor upload_param")
                upload_url = (
                    f"{self.cdn_base_url}/upload"
                    f"?encrypted_query_param={upload_param}&filekey={filekey}"
                )

            encrypted_query_param = await self._upload_ciphertext(cli, upload_url, ciphertext)
            aes_key_for_api = base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii")
            message_id = f"hermes-voice-{uuid4().hex}"
            msg = {
                "from_user_id": "",
                "to_user_id": to_wxid,
                "client_id": message_id,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [
                    self._build_voice_item(
                        encrypt_query_param=encrypted_query_param,
                        aes_key_for_api=aes_key_for_api,
                        duration_ms=duration_ms,
                    )
                ],
            }
            if context_token:
                msg["context_token"] = context_token

            backoffs = (2.0, 5.0, 12.0)
            for attempt, delay in enumerate((0.0, *backoffs)):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    body = await self._api_post(cli, EP_SEND_MESSAGE, {"msg": msg})
                except ILinkRateLimitedError:
                    if attempt == len(backoffs):
                        raise
                    continue
                print("DEBUG sendmessage response:", json.dumps(body, indent=2, ensure_ascii=False))
                return message_id


class ILinkFakeClient:
    """Test client — writes silk to WORK_DIR and returns a fake msg id."""

    def __init__(self, dump_dir: Path | None = None):
        self.dump_dir = dump_dir or settings.work_dir
        self.last_path: Path | None = None
        self.last_duration_ms: int = 0

    async def send_voice(
        self, to_wxid: str, silk: bytes, duration_ms: int
    ) -> str:
        ts = int(time.time() * 1000)
        out = self.dump_dir / f"fake_{to_wxid}_{ts}.silk"
        out.write_bytes(silk)
        self.last_path = out
        self.last_duration_ms = duration_ms
        return f"fake-{ts}"
