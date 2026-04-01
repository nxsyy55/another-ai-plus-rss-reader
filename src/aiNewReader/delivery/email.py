from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from ..config import get_config


def send_digest(digest_path: Path, subject: str | None = None) -> bool:
    cfg = get_config().delivery.email
    if not cfg.enabled:
        return False
    if not cfg.smtp_user or not cfg.to:
        print("  [WARN] Email delivery: smtp_user or to address not configured")
        return False

    import os
    password = os.environ.get("SMTP_PASSWORD", "")
    if not password:
        print("  [WARN] Email delivery: SMTP_PASSWORD env var not set")
        return False

    body = digest_path.read_text(encoding="utf-8")
    if subject is None:
        from datetime import datetime
        subject = f"AI News Digest — {datetime.now().strftime('%Y-%m-%d')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_user
    msg["To"] = cfg.to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
            server.starttls()
            server.login(cfg.smtp_user, password)
            server.sendmail(cfg.smtp_user, cfg.to, msg.as_string())
        return True
    except Exception as exc:
        print(f"  [WARN] Email delivery failed: {exc}")
        return False
