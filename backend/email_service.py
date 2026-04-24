"""Email service. Uses SMTP if configured, else logs to console for dev."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings

logger = logging.getLogger(__name__)

BRAND_NAVY = "#0d2240"
BRAND_GOLD = "#f5a800"


def _html_wrap(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#f7f9fc;font-family:'IBM Plex Sans',Arial,sans-serif;color:#1a2d44">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f9fc;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e2eaf2">
        <tr>
          <td style="background:{BRAND_NAVY};padding:28px 32px">
            <div style="font-family:'Barlow Condensed',Arial,sans-serif;font-weight:700;font-size:22px;letter-spacing:2px;color:#ffffff">
              4<span style="color:{BRAND_GOLD}">X</span>STRUCT · STRUCTMIND AI
            </div>
          </td>
        </tr>
        <tr><td style="padding:32px">{body_html}</td></tr>
        <tr><td style="padding:24px 32px;background:#f7f9fc;border-top:1px solid #e2eaf2;font-size:12px;color:#6b8299">
          Powered by 4XStruct Inc. · Structural Intelligence · STRUCTMIND CORE engine<br/>
          If you did not request this email, you can safely ignore it.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def render_otp_email(first_name: str, otp: str, purpose: str) -> tuple[str, str, str]:
    subject_map = {
        "signup": "Verify your StructMind AI account",
        "login": "Your StructMind AI login code",
        "reset": "Reset your StructMind AI password",
        "change": "Confirm your password change",
    }
    subject = subject_map.get(purpose, "Your StructMind AI verification code")
    title_map = {
        "signup": "Verify your email",
        "login": "Confirm your sign-in",
        "reset": "Reset your password",
        "change": "Confirm password change",
    }
    title = title_map.get(purpose, "Your verification code")
    body = f"""
<h1 style="font-family:'Barlow Condensed',Arial,sans-serif;font-size:28px;letter-spacing:-0.5px;margin:0 0 8px;color:{BRAND_NAVY};text-transform:uppercase">{title}</h1>
<p style="font-size:15px;line-height:1.6;margin:0 0 20px">Hi {first_name or 'there'},</p>
<p style="font-size:15px;line-height:1.6;margin:0 0 20px">Use the 6-digit code below to continue. This code expires in {settings.otp_expiry_seconds // 60} minutes.</p>
<div style="margin:24px 0;padding:24px;background:{BRAND_NAVY};text-align:center">
  <div style="font-family:'JetBrains Mono',Consolas,monospace;font-size:40px;font-weight:700;letter-spacing:14px;color:{BRAND_GOLD}">{otp}</div>
</div>
<p style="font-size:13px;color:#6b8299;margin:0">For your security, never share this code. 4XStruct will never ask for it.</p>
"""
    text = f"Your StructMind AI {purpose} code is: {otp}\nThis code expires in {settings.otp_expiry_seconds // 60} minutes."
    return subject, _html_wrap(subject, body), text


def render_password_changed_email(first_name: str) -> tuple[str, str, str]:
    subject = "Your StructMind AI password has been changed"
    body = f"""
<h1 style="font-family:'Barlow Condensed',Arial,sans-serif;font-size:28px;letter-spacing:-0.5px;margin:0 0 8px;color:{BRAND_NAVY};text-transform:uppercase">Password updated</h1>
<p style="font-size:15px;line-height:1.6;margin:0 0 16px">Hi {first_name or 'there'},</p>
<p style="font-size:15px;line-height:1.6;margin:0 0 16px">Your StructMind AI password was just changed. All your previous sessions have been signed out.</p>
<p style="font-size:13px;color:#6b8299">If this wasn't you, please contact support immediately.</p>
"""
    return subject, _html_wrap(subject, body), "Your StructMind AI password has been changed."


def render_analysis_complete_email(first_name: str, mode_label: str, project_name: str, action_url: str) -> tuple[str, str, str]:
    subject = f"Analysis complete · {mode_label}"
    body = f"""
<h1 style="font-family:'Barlow Condensed',Arial,sans-serif;font-size:28px;letter-spacing:-0.5px;margin:0 0 8px;color:{BRAND_NAVY};text-transform:uppercase">Analysis complete</h1>
<p style="font-size:15px;line-height:1.6;margin:0 0 20px">Hi {first_name or 'there'},</p>
<p style="font-size:15px;line-height:1.6;margin:0 0 20px"><strong>{mode_label}</strong> for project <strong>{project_name}</strong> is ready to review.</p>
<a href="{action_url}" style="display:inline-block;background:{BRAND_GOLD};color:{BRAND_NAVY};padding:14px 28px;text-decoration:none;font-family:'Barlow Condensed',Arial,sans-serif;font-weight:700;letter-spacing:1px;text-transform:uppercase">Open report →</a>
"""
    return subject, _html_wrap(subject, body), f"Analysis complete: {mode_label} for {project_name}. Open: {action_url}"


def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send email via SMTP or fall back to console logging in dev."""
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_pass):
        logger.info(
            "\n[DEV EMAIL — SMTP not configured] ------\n"
            "To: %s\nSubject: %s\nText:\n%s\n---------------------------------------\n",
            to,
            subject,
            text,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from or settings.smtp_user}>"
        msg["To"] = to
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            s.login(settings.smtp_user, settings.smtp_pass)
            s.sendmail(
                settings.smtp_from or settings.smtp_user, [to], msg.as_string()
            )
        logger.info("Email sent to %s · %s", to, subject)
        return True
    except Exception as e:
        logger.error("SMTP send failed to %s: %s", to, e)
        # Fallback: log to console so OTP is still recoverable in dev
        logger.info(
            "\n[DEV EMAIL FALLBACK after SMTP error] ------\n"
            "To: %s\nSubject: %s\nText:\n%s\n---------------------------------------\n",
            to,
            subject,
            text,
        )
        return False
