import html
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from src import ui
from src.config import config

# Module-level references for test mocking compatibility
MAIL_PSWD = getattr(config, "MAIL_PSWD", None)
MAIL = getattr(config, "MAIL", None)


def _safe_header(text: str) -> str:
    """Sanitizes text for email header fields, stripping newlines to prevent header injection crashes."""
    return re.sub(r"[\r\n]+", " ", str(text)).strip()


def _get_credentials():
    """Retrieve current email and app password dynamically."""
    sender_email = MAIL or getattr(config, "MAIL", None)
    password = MAIL_PSWD or getattr(config, "MAIL_PSWD", None)
    return sender_email, password


def is_mail_configured() -> bool:
    """Check whether email credentials are present."""
    sender, pswd = _get_credentials()
    return bool(sender and pswd)


def is_success_mail_enabled() -> bool:
    """Check if success notifications are enabled and configured."""
    if not is_mail_configured():
        return False
    from src import ui

    if getattr(ui, "NOTIFY_SUCCESS_ENABLED", False):
        return True
    return bool(getattr(config, "NOTIFY_ON_SUCCESS", False))


def is_error_mail_enabled() -> bool:
    """Check if error notifications are enabled and configured."""
    if not is_mail_configured():
        return False
    from src import ui

    if getattr(ui, "NOTIFY_ERROR_ENABLED", False):
        return True
    return bool(getattr(config, "NOTIFY_ON_ERROR", True))


def is_tag_mail_enabled() -> bool:
    """Check if tag learning notifications are enabled and configured."""
    if not is_mail_configured():
        return False
    from src import ui

    if getattr(ui, "NOTIFY_TAG_ENABLED", False):
        return True
    return bool(getattr(config, "NOTIFY_ON_TAG", False))


def _build_html_email(title: str, badge_text: str, badge_bg: str, rows: list, error_details: str = None) -> str:
    """Generate a clean, modern, responsive HTML email with escaped HTML content."""
    safe_title = html.escape(str(title))
    safe_badge_text = html.escape(str(badge_text))
    safe_badge_bg = html.escape(str(badge_bg))

    rows_html = ""
    for label, val, is_code, is_highlight in rows:
        escaped_label = html.escape(str(label))
        escaped_val = html.escape(str(val))
        if is_highlight:
            val_content = f'<strong style="color: #059669; font-size: 15px;">{escaped_val}</strong>'
        elif is_code:
            val_content = f'<span style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; background-color: #f1f5f9; padding: 4px 8px; border-radius: 4px; font-size: 13px; color: #334155; word-break: break-all;">{escaped_val}</span>'
        else:
            val_content = f"<span>{escaped_val}</span>"

        rows_html += f"""
        <tr>
          <td style="width: 140px; color: #64748b; font-size: 13px; font-weight: 600; padding: 10px 0; border-bottom: 1px solid #f1f5f9; vertical-align: top;">{escaped_label}</td>
          <td style="color: #1e293b; font-size: 14px; padding: 10px 0; border-bottom: 1px solid #f1f5f9; vertical-align: top;">{val_content}</td>
        </tr>
        """

    error_html = ""
    if error_details:
        escaped_error = html.escape(str(error_details))
        error_html = f"""
        <div style="margin-top: 18px;">
          <div style="font-size: 13px; font-weight: 600; color: #991b1b; margin-bottom: 6px;">Error Details:</div>
          <div style="background-color: #0f172a; color: #f87171; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; padding: 14px; border-radius: 8px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-all;">{escaped_error}</div>
        </div>
        """

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px 12px; color: #1e293b; line-height: 1.5;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 14px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
    <!-- Header -->
    <div style="background-color: #0f172a; padding: 24px; text-align: left;">
      <div style="font-size: 12px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;">🎬 media-organizer</div>
      <div style="margin-bottom: 8px;">
        <span style="display: inline-block; background-color: {safe_badge_bg}; color: #ffffff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; padding: 4px 10px; border-radius: 9999px;">{safe_badge_text}</span>
      </div>
      <h1 style="margin: 0; font-size: 20px; font-weight: 700; color: #ffffff;">{safe_title}</h1>
    </div>

    <!-- Body -->
    <div style="padding: 24px;">
      <table style="width: 100%; border-collapse: collapse;">
        {rows_html}
      </table>
      {error_html}
    </div>

    <!-- Footer -->
    <div style="background-color: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
      Generated automatically by <strong>media-organizer</strong> • {current_time}
    </div>
  </div>
</body>
</html>
"""


def _build_text_email(title: str, badge_text: str, rows: list, error_details: str = None) -> str:
    """Generate a clean, structured plaintext email."""
    lines = [
        "==================================================",
        f"  🎬 media-organizer - [{badge_text}]",
        f"  {title}",
        "==================================================",
        "",
    ]
    for label, val, _, _ in rows:
        lines.append(f"{label.ljust(18)}: {val}")

    if error_details:
        lines.extend(
            [
                "",
                "----------------- ERROR DETAILS -----------------",
                error_details.strip(),
                "-------------------------------------------------",
            ]
        )

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.extend(["", f"Generated automatically at {current_time}"])
    return "\n".join(lines)


def _dispatch_email(msg: EmailMessage, purpose: str = "notification email"):
    """Deliver EmailMessage using Gmail SMTP over SSL."""
    from src.runtime_config import runtime

    sender_email, password = _get_credentials()
    if not sender_email or not password:
        return

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    if not runtime.daemon_enabled:
        ui.print_log("Connecting to server...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, password)
            server.send_message(msg)
            if runtime.daemon_enabled:
                ui.log_info(f"Success: {purpose} sent successfully")
            else:
                ui.print_log(f"Success: {purpose} sent successfully!")
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(ui.print_error(" ❌ Error: Authentication failed. Check your email and password", e))
    except Exception as e:
        raise RuntimeError(ui.print_error(" ❌ Error: An unexpected error occurred while trying to send an email", e))


def send_media_success_email(
    media_name: str,
    original_name: str,
    media_type: str,
    destination_path: str,
    resolution: str = None,
    quality: str = None,
):
    """
    Send a beautifully formatted notification when a media file is successfully processed.
    """
    if not is_success_mail_enabled():
        return

    sender_email, _ = _get_credentials()
    type_display = "TV Show 📺" if str(media_type).lower() in ("tv", "tvshow", "tv_show") else "Movie 🎥"
    subject_icon = "📺" if str(media_type).lower() in ("tv", "tvshow", "tv_show") else "🎬"
    subject = f"{subject_icon} [media-organizer] Successfully Processed: {media_name}"

    tags = []
    if resolution:
        tags.append(f"[{resolution}]")
    if quality:
        tags.append(f"[{quality}]")
    tags_display = " ".join(tags) if tags else "None"

    rows = [
        ("Media Type", type_display, False, False),
        ("New Filename", media_name, False, True),
        ("Original Filename", original_name, True, False),
        ("Destination", destination_path, True, False),
    ]
    if tags:
        rows.append(("Detected Tags", tags_display, True, False))

    html_content = _build_html_email(
        title=f"Successfully Processed: {media_name}", badge_text="SUCCESS", badge_bg="#10b981", rows=rows
    )
    text_content = _build_text_email(title=f"Successfully Processed: {media_name}", badge_text="SUCCESS", rows=rows)

    msg = EmailMessage()
    msg["Subject"] = _safe_header(subject)
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        _dispatch_email(msg, purpose="success notification")
    except Exception as e:
        ui.print_log(f"⚠️ Warning: Failed to send success email: {e}")


def send_email(message: str, affected_file: str = None, exception: Exception = None):
    """
    Main entry point for error email dispatch.
    """
    if not is_error_mail_enabled():
        return

    sender_email, _ = _get_credentials()
    if affected_file:
        subject = f"⚠️ [media-organizer] Error Processing: {affected_file}"
        title = f"Failed to Process: {affected_file}"
    else:
        subject = "❌ [media-organizer] Execution Error"
        title = "Execution Error Encountered"

    rows = []
    if affected_file:
        rows.append(("Affected File", affected_file, True, False))
    rows.append(("Status", "Processing Failed ❌", False, False))

    details = str(message)
    if exception and str(exception) not in details:
        details += f"\n\nException details: {exception}"

    html_content = _build_html_email(
        title=title, badge_text="ERROR", badge_bg="#ef4444", rows=rows, error_details=details
    )
    text_content = _build_text_email(title=title, badge_text="ERROR", rows=rows, error_details=details)

    msg = EmailMessage()
    msg["Subject"] = _safe_header(subject)
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    _dispatch_email(msg, purpose="error alert")


def send_error_email(error_message: str, affected_file: str = None, exception: Exception = None):
    """Safely dispatches error email without crashing callers if email delivery fails."""
    try:
        send_email(error_message, affected_file=affected_file, exception=exception)
    except Exception as e:
        ui.print_log(f"⚠️ Warning: Failed to send error email: {e}")


def send_tag_learned_email(tags: list[str], filename: str, media_title: str = None, file_path: str = None):
    """
    Send a beautifully formatted notification when new AI keyword tags are learned and saved to gemini_tags.json.
    """
    if not is_tag_mail_enabled():
        return

    sender_email, _ = _get_credentials()
    tags_str = ", ".join(tags)
    subject = f"🏷️ [media-organizer] New AI Tag(s) Learned: {tags_str}"
    title = "New AI Keyword(s) Learned"

    rows = [
        ("Learned Tag(s)", tags_str, True, True),
        ("Found In File", filename, True, False),
    ]
    if media_title:
        rows.append(("Identified Title", media_title, False, False))
    if file_path:
        rows.append(("File Path", str(file_path), True, False))
    rows.append(("Saved Location", "gemini_tags.json", True, False))

    html_content = _build_html_email(title=title, badge_text="AI TAG LEARNED", badge_bg="#8b5cf6", rows=rows)
    text_content = _build_text_email(title=title, badge_text="AI TAG LEARNED", rows=rows)

    msg = EmailMessage()
    msg["Subject"] = _safe_header(subject)
    msg["From"] = sender_email
    msg["To"] = sender_email
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        _dispatch_email(msg, purpose="tag learned notification")
    except Exception as e:
        ui.print_log(f"⚠️ Warning: Failed to send tag learned email: {e}")
