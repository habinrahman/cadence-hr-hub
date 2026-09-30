"""Mail delivery. Local demo uses SMTP to Mailpit. Graph and SES implement the same method later."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings

LOCAL_SMTP_HOSTS = frozenset({"localhost", "127.0.0.1", "mailpit"})


@dataclass(frozen=True)
class OutboundEmail:
    to: str
    subject: str
    body: str


class MailSender(Protocol):
    def send(self, message: OutboundEmail) -> None: ...


class MailUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SmtpMailSender:
    def __init__(self, host: str, port: int, sender: str) -> None:
        self.host = host
        self.port = port
        self.sender = sender

    def send(self, message: OutboundEmail) -> None:
        payload = EmailMessage()
        payload["From"] = self.sender
        payload["To"] = message.to
        payload["Subject"] = message.subject
        payload.set_content(message.body)
        with smtplib.SMTP(self.host, self.port, timeout=10) as client:
            client.send_message(payload)


class GraphMailSender:
    """Microsoft Graph sender. It does not send until a production mailbox is configured."""

    def send(self, message: OutboundEmail) -> None:
        del message
        raise MailUnavailable("graph_not_configured")


class SesMailSender:
    """Amazon SES sender. It does not send until a production identity is configured."""

    def send(self, message: OutboundEmail) -> None:
        del message
        raise MailUnavailable("ses_not_configured")


def get_mail_sender() -> MailSender:
    settings = get_settings()
    if settings.environment in {"local", "demo"}:
        if settings.mail_destination != "smtp" or settings.smtp_host not in LOCAL_SMTP_HOSTS:
            raise MailUnavailable("external_mail_blocked")
        return SmtpMailSender(settings.smtp_host, settings.smtp_port, settings.smtp_from)
    if settings.mail_destination == "graph":
        return GraphMailSender()
    if settings.mail_destination == "ses":
        return SesMailSender()
    if settings.mail_destination == "smtp":
        return SmtpMailSender(settings.smtp_host, settings.smtp_port, settings.smtp_from)
    raise MailUnavailable("mail_provider_unavailable")
