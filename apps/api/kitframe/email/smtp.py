from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from kitframe.settings import Settings

logger = logging.getLogger("kitframe.email")


def send_email(
    settings: Settings,
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    if settings.app_env == "local" and settings.smtp_host in ("localhost", "127.0.0.1", "mailpit"):
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
    logger.info("email_sent", extra={"to": to, "subject": subject})
