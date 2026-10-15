import os
import smtplib
from email.message import EmailMessage
from sqlalchemy.orm import Session
from . import models


def _backend() -> str:
    return os.getenv("EMAIL_BACKEND", "log").lower()


class EmailService:
    """Pluggable email service.

    Default backend ("log") stores every email in the EmailLog table and
    prints a line to stdout. Set EMAIL_BACKEND=smtp plus SMTP_HOST,
    SMTP_PORT, SMTP_USER, SMTP_PASSWORD and SMTP_FROM to send for real.
    """

    @classmethod
    def send(
        cls,
        db: Session,
        to_email: str,
        subject: str,
        body: str,
        related_order_id: int | None = None,
    ) -> models.EmailLog:
        log = models.EmailLog(
            to_email=to_email,
            subject=subject,
            body=body,
            related_order_id=related_order_id,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        backend = _backend()
        print(f"[email:{backend}] to={to_email} subject={subject}", flush=True)
        if backend == "smtp":
            cls._send_smtp(to_email, subject, body)
        return log

    @staticmethod
    def _send_smtp(to_email: str, subject: str, body: str):
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")
        from_addr = os.getenv("SMTP_FROM", user or "noreply@blogreach.com")
        if not host or not user:
            print("[email:smtp] missing SMTP_HOST or SMTP_USER, skipping real send", flush=True)
            return
        msg = EmailMessage()
        msg["From"] = from_addr
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
