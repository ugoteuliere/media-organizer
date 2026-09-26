from unittest.mock import patch
from src import mail, ui
from src.config import config


def test_build_html_and_text_email_formatting():
    rows = [
        ("Media Type", "Movie 🎥", False, False),
        ("New Filename", "Inception (2010).mkv", False, True),
        ("Original Filename", "inception.2010.mkv", True, False),
    ]
    html = mail._build_html_email(
        title="Successfully Processed: Inception (2010).mkv", badge_text="SUCCESS", badge_bg="#10b981", rows=rows
    )
    text = mail._build_text_email(title="Successfully Processed: Inception (2010).mkv", badge_text="SUCCESS", rows=rows)

    # HTML assertions
    assert "<!DOCTYPE html>" in html
    assert "SUCCESS" in html
    assert "#10b981" in html
    assert "Inception (2010).mkv" in html
    assert "inception.2010.mkv" in html
    assert "media-organizer" in html

    # Text assertions
    assert "[SUCCESS]" in text
    assert "Media Type        : Movie 🎥" in text
    assert "New Filename      : Inception (2010).mkv" in text
    assert "Generated automatically" in text


def test_send_media_success_email_movie(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_SUCCESS", True)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_media_success_email(
            media_name="Dune Part Two (2024).mkv",
            original_name="dune.part.two.2024.1080p.mkv",
            media_type="movie",
            destination_path="//nas/Movies/Dune Part Two (2024).mkv",
            resolution="1080p",
            quality="BluRay",
        )
        mock_dispatch.assert_called_once()
        sent_msg = mock_dispatch.call_args[0][0]
        assert "🎬 [media-organizer] Successfully Processed: Dune Part Two (2024).mkv" == sent_msg["Subject"]
        assert sent_msg["From"] == "testuser@gmail.com"
        assert sent_msg["To"] == "testuser@gmail.com"

        # Check multipart content
        assert sent_msg.is_multipart()
        parts = [p.get_content_type() for p in sent_msg.iter_parts()]
        assert "text/plain" in parts
        assert "text/html" in parts


def test_send_media_success_email_tv(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_SUCCESS", True)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_media_success_email(
            media_name="Severance - S01E01.mkv",
            original_name="severance.s01e01.web.mkv",
            media_type="tv",
            destination_path="//nas/TV/Severance/Season 01/Severance - S01E01.mkv",
        )
        mock_dispatch.assert_called_once()
        sent_msg = mock_dispatch.call_args[0][0]
        assert "📺 [media-organizer] Successfully Processed: Severance - S01E01.mkv" == sent_msg["Subject"]


def test_send_media_success_email_disabled_when_flag_false(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_SUCCESS", False)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_media_success_email(
            media_name="Test.mkv", original_name="test.mkv", media_type="movie", destination_path="/test"
        )
        mock_dispatch.assert_not_called()


def test_send_error_email_formatted(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_ERROR", True)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_error_email(
            error_message="Network connection to TMDB timed out", affected_file="Difficult.Movie.2024.mkv"
        )
        mock_dispatch.assert_called_once()
        sent_msg = mock_dispatch.call_args[0][0]
        assert "⚠️ [media-organizer] Error Processing: Difficult.Movie.2024.mkv" == sent_msg["Subject"]
        assert sent_msg.is_multipart()


def test_send_error_email_disabled_when_flag_false(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_ERROR", False)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_error_email(error_message="Crash", affected_file="Faulty.mkv")
        mock_dispatch.assert_not_called()


def test_mail_disabled_when_credentials_missing(monkeypatch):
    monkeypatch.setattr(mail, "MAIL", None)
    monkeypatch.setattr(mail, "MAIL_PSWD", None)
    monkeypatch.setattr(config, "NOTIFY_ON_SUCCESS", True)
    monkeypatch.setattr(config, "NOTIFY_ON_ERROR", True)
    monkeypatch.setattr(config, "NOTIFY_ON_TAG", True)

    assert mail.is_mail_configured() is False
    assert mail.is_success_mail_enabled() is False
    assert mail.is_error_mail_enabled() is False
    assert mail.is_tag_mail_enabled() is False


def test_mail_override_variables(monkeypatch):
    monkeypatch.setattr(ui, "NOTIFY_SUCCESS_ENABLED", True)
    monkeypatch.setattr(ui, "NOTIFY_ERROR_ENABLED", True)
    monkeypatch.setattr(ui, "NOTIFY_TAG_ENABLED", True)
    with patch("src.mail.is_mail_configured", return_value=True):
        assert mail.is_success_mail_enabled() is True
        assert mail.is_error_mail_enabled() is True
        assert mail.is_tag_mail_enabled() is True


def test_send_tag_learned_email_formatted(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_TAG", True)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_tag_learned_email(
            tags=["CustomGroup", "x265"],
            filename="Cryptic.Movie.2024.mkv",
            media_title="Cryptic Movie",
            file_path="/downloads/Cryptic.Movie.2024.mkv",
        )
        mock_dispatch.assert_called_once()
        sent_msg = mock_dispatch.call_args[0][0]
        assert "🏷️ [media-organizer] New AI Tag(s) Learned: CustomGroup, x265" == sent_msg["Subject"]
        assert sent_msg["From"] == "testuser@gmail.com"
        assert sent_msg["To"] == "testuser@gmail.com"

        assert sent_msg.is_multipart()
        parts = [p.get_content_type() for p in sent_msg.iter_parts()]
        assert "text/plain" in parts
        assert "text/html" in parts


def test_send_tag_learned_email_disabled_when_flag_false(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_TAG", False)
    monkeypatch.setattr(ui, "NOTIFY_TAG_ENABLED", False)

    with patch("src.mail._dispatch_email") as mock_dispatch:
        mail.send_tag_learned_email(tags=["CustomGroup"], filename="Movie.mkv")
        mock_dispatch.assert_not_called()


def test_send_tag_learned_email_dispatch_exception(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_TAG", True)

    with (
        patch("src.mail._dispatch_email", side_effect=RuntimeError("SMTP failed")),
        patch("src.ui.print_log") as mock_log,
    ):
        mail.send_tag_learned_email(tags=["CustomGroup"], filename="Movie.mkv")
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "Error while trying to send the email" in logged


def test_send_error_email_dispatch_exception(monkeypatch):
    monkeypatch.setattr(ui, "MAIL_ENABLED", True)
    monkeypatch.setattr(mail, "MAIL", "testuser@gmail.com")
    monkeypatch.setattr(mail, "MAIL_PSWD", "test_app_pass_12")
    monkeypatch.setattr(config, "NOTIFY_ON_ERROR", True)

    with (
        patch("src.mail._dispatch_email", side_effect=RuntimeError("SMTP failed")),
        patch("src.ui.print_log") as mock_log,
    ):
        mail.send_error_email(error_message="Something failed")
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "Error while trying to send the email" in logged
