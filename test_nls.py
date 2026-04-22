"""
Aliyun NLS smoke test — run directly:
    python test_nls.py

Tests:
  1. Token fetch  — calls nls-meta.cn-shanghai.aliyuncs.com with your credentials
  2. WS handshake — connects to nls-gateway and sends StartTranscription
  3. PCM ping     — sends 1 second of silent 16 kHz PCM and waits for TranscriptionStarted
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import websockets

# ── credentials ───────────────────────────────────────────────────────────────
# Override with env vars to avoid editing this file:
#   NLS_ACCESS_KEY_ID=xxx NLS_ACCESS_KEY_SECRET=yyy python test_nls.py
ACCESS_KEY_ID     = os.getenv("NLS_ACCESS_KEY_ID",     "REMOVED_OSS_KEY_ID")
ACCESS_KEY_SECRET = os.getenv("NLS_ACCESS_KEY_SECRET", "REMOVED_OSS_KEY_SECRET")
APP_KEY           = os.getenv("NLS_APP_KEY",           "nuaHPUJwH1r9l6Ch")

NLS_META_URL = "https://nls-meta.cn-shanghai.aliyuncs.com/"
NLS_WS_URL   = "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


# ── helpers ───────────────────────────────────────────────────────────────────

def _percent_encode(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _build_signature(secret: str, params: dict) -> str:
    sorted_params = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_params)
    string_to_sign = f"POST&{_percent_encode('/')}&{_percent_encode(canonical)}"
    key = (secret + "&").encode()
    digest = hmac.new(key, string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _silent_pcm(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate silent (zero-filled) 16-bit mono PCM."""
    n_samples = int(sample_rate * duration_s)
    return struct.pack(f"<{n_samples}h", *([0] * n_samples))


# ── test 1: token fetch ───────────────────────────────────────────────────────

def test_fetch_token() -> str | None:
    print("\n[1] Token fetch ...")
    params: dict[str, str] = {
        "Action":           "CreateToken",
        "AccessKeyId":      ACCESS_KEY_ID,
        "Format":           "JSON",
        "RegionId":         "cn-shanghai",
        "SignatureMethod":  "HMAC-SHA1",
        "SignatureNonce":   str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp":        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version":          "2019-02-28",
    }
    params["Signature"] = _build_signature(ACCESS_KEY_SECRET, params)
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        NLS_META_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"  {FAIL}  HTTP {e.code}: {body_text}")
        return None
    except Exception as e:
        print(f"  {FAIL}  {e}")
        return None

    if "Token" not in result:
        print(f"  {FAIL}  unexpected response: {result}")
        return None

    token = result["Token"]["Id"]
    expire = result["Token"]["ExpireTime"]
    print(f"  {PASS}  token={token[:12]}...  expire_time={expire}")
    return token


# ── test 2: WS handshake + TranscriptionStarted ───────────────────────────────

async def test_ws(token: str) -> bool:
    print("\n[2] WebSocket handshake ...")
    task_id = str(uuid.uuid4()).replace("-", "")
    url = f"{NLS_WS_URL}?token={token}"

    start_msg = json.dumps({
        "header": {
            "message_id": str(uuid.uuid4()).replace("-", ""),
            "task_id":    task_id,
            "namespace":  "SpeechTranscriber",
            "name":       "StartTranscription",
            "appkey":     APP_KEY,
        },
        "payload": {
            "format":                          "pcm",
            "sample_rate":                     16000,
            "enable_intermediate_result":      True,
            "enable_punctuation_prediction":   True,
            "enable_inverse_text_normalization": True,
        },
    })

    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            print(f"  connected to {NLS_WS_URL}")
            await ws.send(start_msg)

            # Wait for TranscriptionStarted (or error) with 8 s timeout
            async with asyncio.timeout(8):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    name = msg.get("header", {}).get("name", "")
                    print(f"  <- {name}")
                    if name == "TranscriptionStarted":
                        print(f"  {PASS}  WS handshake OK")
                        return True
                    status = msg.get("header", {}).get("status", 0)
                    if status != 20000000:
                        print(f"  {FAIL}  server error: {msg}")
                        return False
    except TimeoutError:
        print(f"  {FAIL}  timed out waiting for TranscriptionStarted")
    except Exception as e:
        print(f"  {FAIL}  {e}")
    return False


# ── test 3: send PCM + wait for any result ────────────────────────────────────

async def test_pcm(token: str) -> bool:
    print("\n[3] PCM send (1 s silent audio) ...")
    task_id = str(uuid.uuid4()).replace("-", "")
    url = f"{NLS_WS_URL}?token={token}"

    start_msg = json.dumps({
        "header": {
            "message_id": str(uuid.uuid4()).replace("-", ""),
            "task_id":    task_id,
            "namespace":  "SpeechTranscriber",
            "name":       "StartTranscription",
            "appkey":     APP_KEY,
        },
        "payload": {
            "format":                          "pcm",
            "sample_rate":                     16000,
            "enable_intermediate_result":      True,
            "enable_punctuation_prediction":   True,
            "enable_inverse_text_normalization": True,
        },
    })
    stop_msg = json.dumps({
        "header": {
            "message_id": str(uuid.uuid4()).replace("-", ""),
            "task_id":    task_id,
            "namespace":  "SpeechTranscriber",
            "name":       "StopTranscription",
            "appkey":     APP_KEY,
        },
    })

    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            await ws.send(start_msg)

            # Wait for TranscriptionStarted
            async with asyncio.timeout(8):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    name = msg.get("header", {}).get("name", "")
                    if name == "TranscriptionStarted":
                        break
                    if msg.get("header", {}).get("status", 0) != 20000000:
                        print(f"  {FAIL}  handshake error: {msg}")
                        return False

            # Send 1 s of silent PCM in 200 ms chunks
            pcm = _silent_pcm(1.0)
            chunk_size = 16000 * 2 // 5  # 200 ms × 2 bytes/sample
            for i in range(0, len(pcm), chunk_size):
                await ws.send(pcm[i:i + chunk_size])
                await asyncio.sleep(0.2)

            await ws.send(stop_msg)
            print("  PCM sent, waiting for TranscriptionCompleted ...")

            async with asyncio.timeout(8):
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    name = msg.get("header", {}).get("name", "")
                    print(f"  <- {name}")
                    if name == "TranscriptionCompleted":
                        print(f"  {PASS}  full round-trip OK")
                        return True
    except TimeoutError:
        print(f"  {FAIL}  timed out")
    except Exception as e:
        print(f"  {FAIL}  {e}")
    return False


# ── main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 50)
    print("Aliyun NLS smoke test")
    print(f"  AccessKeyId : {ACCESS_KEY_ID[:8]}...")
    print(f"  AppKey      : {APP_KEY}")
    print("=" * 50)

    token = test_fetch_token()
    if not token:
        print("\nToken fetch failed — skipping WS tests.")
        print("Fix: grant AliyunNLSFullAccess to this AccessKey in Aliyun RAM console.")
        return

    ws_ok = await test_ws(token)
    if not ws_ok:
        print("\nWS handshake failed — check AppKey or network.")
        return

    await test_pcm(token)


if __name__ == "__main__":
    asyncio.run(main())
