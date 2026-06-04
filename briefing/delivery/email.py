from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from briefing.compat import dataclass_compat


@dataclass_compat(slots=True)
class EmailDeliveryCheck:
    ok: bool
    message: str


class EmailDelivery:
    def __init__(self) -> None:
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "")
        self.use_ssl = _parse_bool(os.getenv("EMAIL_USE_SSL", "false"))
        self.use_tls = _parse_bool(os.getenv("EMAIL_USE_TLS", "true"))
        default_port = "465" if self.use_ssl else "587"
        self.smtp_port = _parse_port(os.getenv("EMAIL_SMTP_PORT", default_port), int(default_port))
        self.username = os.getenv("EMAIL_SMTP_USERNAME", "")
        self.password = _normalize_password(self.smtp_host, os.getenv("EMAIL_SMTP_PASSWORD", ""))
        self.sender = os.getenv("EMAIL_FROM", "")
        self.recipients = _parse_recipients(os.getenv("EMAIL_TO", ""))
        self.last_error = ""

    @property
    def configured(self) -> bool:
        return not self.missing_settings

    @property
    def missing_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.smtp_host:
            missing.append("EMAIL_SMTP_HOST")
        if not self.sender:
            missing.append("EMAIL_FROM")
        if not self.recipients:
            missing.append("EMAIL_TO")
        if not self.username:
            missing.append("EMAIL_SMTP_USERNAME")
        if not self.password:
            missing.append("EMAIL_SMTP_PASSWORD")
        return missing

    @property
    def validation_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.smtp_host.lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
            if self.username and "@" not in self.username:
                warnings.append("EMAIL_SMTP_USERNAME should be the full Gmail address.")
            if self.sender and "@" not in self.sender:
                warnings.append("EMAIL_FROM should be the full sender email address.")
        if self.use_ssl and self.use_tls:
            warnings.append("Use either EMAIL_USE_SSL=true or EMAIL_USE_TLS=true, not both.")
        return warnings

    def send_markdown(self, markdown: str, subject: str) -> bool:
        if not self.configured:
            self.last_error = "Missing settings: " + ", ".join(self.missing_settings)
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message.set_content(markdown, subtype="plain", charset="utf-8")

        context = ssl.create_default_context()
        try:
            with self._connect(context) as server:
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            self.last_error = _redact_error(exc, self.username, self.password)
            return False
        return True

    def check_connection(self) -> EmailDeliveryCheck:
        missing = self.missing_settings
        if missing:
            return EmailDeliveryCheck(False, "Missing settings: " + ", ".join(missing))
        warnings = self.validation_warnings
        if warnings:
            return EmailDeliveryCheck(False, "Invalid email settings: " + " ".join(warnings))

        context = ssl.create_default_context()
        try:
            with self._connect(context):
                return EmailDeliveryCheck(True, "SMTP connection and login succeeded.")
        except (OSError, smtplib.SMTPException) as exc:
            return EmailDeliveryCheck(False, _redact_error(exc, self.username, self.password))

    def _connect(self, context: ssl.SSLContext) -> smtplib.SMTP:
        if self.use_ssl:
            server = smtplib.SMTP_SSL(
                self.smtp_host, self.smtp_port, timeout=30, context=context
            )
            self._login(server)
            return server

        server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
        try:
            server.ehlo()
            if self.use_tls:
                server.starttls(context=context)
                server.ehlo()
            self._login(server)
            return server
        except Exception:
            server.close()
            raise

    def _login(self, server: smtplib.SMTP) -> None:
        if self.username and self.password:
            server.login(self.username, self.password)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_port(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_password(smtp_host: str, password: str) -> str:
    if smtp_host.lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
        return password.replace(" ", "")
    return password


def _parse_recipients(value: str) -> list[str]:
    separators_normalized = value.replace(";", ",")
    return [item.strip() for item in separators_normalized.split(",") if item.strip()]


def _redact_error(exc: BaseException, username: str, password: str) -> str:
    error = f"{type(exc).__name__}: {exc}"
    if username:
        error = error.replace(username, "<username>")
    if password:
        error = error.replace(password, "<password>")
    return error
