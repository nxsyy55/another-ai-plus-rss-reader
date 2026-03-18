from __future__ import annotations

from pathlib import Path

import httpx

from ..config import get_config

TELEGRAM_API = "https://api.telegram.org"
MAX_MSG_LEN = 4096


def _chunk(text: str, size: int = MAX_MSG_LEN) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


async def send_digest(digest_path: Path) -> bool:
    cfg = get_config().delivery.telegram
    if not cfg.enabled:
        return False
    if not cfg.bot_token or not cfg.chat_id:
        print("  [WARN] Telegram delivery: bot_token or chat_id not configured")
        return False

    body = digest_path.read_text(encoding="utf-8")
    url = f"{TELEGRAM_API}/bot{cfg.bot_token}/sendMessage"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in _chunk(body):
            try:
                resp = await client.post(url, json={
                    "chat_id": cfg.chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                })
                resp.raise_for_status()
            except Exception as exc:
                print(f"  [WARN] Telegram delivery failed: {exc}")
                return False

    return True
