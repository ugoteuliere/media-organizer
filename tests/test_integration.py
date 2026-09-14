import os
import sys
import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import main
from src import ui, files, utils, mail, api
from src.config import ConfigManager
from src.tags import TagManager


@pytest.fixture
def media_env(tmp_path, monkeypatch):
    """Sets up a complete realistic media library environment."""
    downloads = tmp_path / "downloads"
    movies = tmp_path / "movies"
    tv_shows = tmp_path / "tv_shows"
    config_dir = tmp_path / "config"
    downloads.mkdir()
    movies.mkdir()
    tv_shows.mkdir()
    config_dir.mkdir()

    config_file = config_dir / "config.ini"
    cm = ConfigManager(custom_path=str(config_file))
    cm.set("paths.movies_folder", str(movies))
    cm.set("paths.tv_shows_folder", str(tv_shows))
    cm.set("paths.not_sorted_media_files_folder", str(downloads))
    cm.set("options.bypass", "true")
    cm.set("mail.mail", "test@example.com")
    cm.set("mail.mail_pswd", "abcdefghijklmnop")

    monkeypatch.setattr("src.config.config", cm)
    monkeypatch.setattr("src.ui.config", cm)
    monkeypatch.setattr("src.utils.config", cm)
    monkeypatch.setattr("src.files.config", cm)
    monkeypatch.setattr("src.tags.config", cm)
    monkeypatch.setattr("src.mail.config", cm)
    monkeypatch.setattr("src.ui.MAIL", "test@example.com")
    monkeypatch.setattr("src.ui.MAIL_PSWD", "abcdefghijklmnop")

    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", str(tv_shows))
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads))
    monkeypatch.setattr(files, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(files, "TV_SHOWS_FOLDER", str(tv_shows))
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads))
    monkeypatch.setattr(ui, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(ui, "TV_SHOWS_FOLDER", str(tv_shows))

    return {
        "downloads": downloads,
        "movies": movies,
        "tv_shows": tv_shows,
        "config_dir": config_dir,
        "config_manager": cm,
    }


def test_integration_full_rename_and_move_pipeline(media_env, monkeypatch):
    """End-to-end integration test: Discovery -> TMDB Identification -> Renaming -> Moving -> Cleanup."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]
    tv_shows = media_env["tv_shows"]

    # 1. Create realistic files in downloads folder (including nested subfolder)
    movie_file = downloads / "Gladiator.2000.1080p.BluRay.x264.VFF.mkv"
    movie_file.write_text("dummy movie content", encoding="utf-8")

    sub_dir = downloads / "SeriesSubfolder"
    sub_dir.mkdir()
    tv_file = sub_dir / "Dark.S01E01.1080p.WEBRip.mkv"
    tv_file.write_text("dummy episode content", encoding="utf-8")

    # 2. Mock TMDB API call to return realistic official metadata
    def mock_tmdb(name, year, language, media_type):
        if "Gladiator" in name:
            return [True, "Gladiator", "2000", "movie"]
        if "Dark" in name:
            return [True, "Dark", "2017", "tv"]
        return [False, None, None, None]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-b"])

    with patch("src.mail.send_media_success_email") as mock_mail:
        exit_code = main.main()
        assert exit_code == 0

    # 3. Verify destination directories and files on disk
    expected_movie = movies / "Gladiator (2000).mkv"
    expected_tv = tv_shows / "Dark" / "Season 01" / "Dark - S01E01.mkv"

    assert expected_movie.is_file(), f"Expected movie file missing at {expected_movie}"
    assert expected_tv.is_file(), f"Expected TV show file missing at {expected_tv}"
    assert expected_movie.read_text(encoding="utf-8") == "dummy movie content"
    assert expected_tv.read_text(encoding="utf-8") == "dummy episode content"

    # 4. Verify cleanup: original files gone and empty subfolder removed
    assert not movie_file.exists()
    assert not tv_file.exists()
    assert not sub_dir.exists()


def test_integration_standalone_rename_only_with_custom_path(tmp_path, monkeypatch):
    """End-to-end integration test: Standalone rename-only targeting custom path without library folders."""
    custom_dir = tmp_path / "MyCustomDownloads"
    custom_dir.mkdir()
    raw_file = custom_dir / "The.Matrix.1999.REMASTERED.1080p.mkv"
    raw_file.write_text("matrix content", encoding="utf-8")

    # Clear library folders completely
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", None)
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", None)

    def mock_tmdb(name, year, language, media_type):
        return [True, "The Matrix", "1999", "movie"]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-r", f"--path={custom_dir}", "-b"])

    exit_code = main.main()
    assert exit_code == 0

    # Verify file was renamed in-place in custom_dir
    expected_file = custom_dir / "The Matrix (1999).mkv"
    assert expected_file.is_file()
    assert not raw_file.exists()
    assert expected_file.read_text(encoding="utf-8") == "matrix content"


def test_integration_simulation_mode_dry_run(media_env, monkeypatch):
    """End-to-end integration test: Simulation mode prevents any disk changes or moves."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    sample_file = downloads / "Interstellar.2014.1080p.mkv"
    sample_file.write_text("interstellar data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Interstellar", "2014", "movie"]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-s", "-b"])

    with patch("src.mail.send_media_success_email") as mock_mail:
        exit_code = main.main()
        assert exit_code == 0
        mock_mail.assert_not_called()

    # Verify disk state is completely unmodified
    assert sample_file.is_file()
    assert len(list(movies.iterdir())) == 0


def test_integration_daemon_multi_cycle(media_env, monkeypatch):
    """End-to-end integration test: Background daemon processes files, ignores locked files, and stays alive."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    # File 1: Valid finished download
    f1 = downloads / "Inception.2010.720p.mkv"
    f1.write_text("inception data", encoding="utf-8")

    # File 2: In-progress browser download (should be skipped by lock/extension detector)
    f2_partial = downloads / "HugeMovie.2024.mkv.crdownload"
    f2_partial.write_text("partial data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        if "Inception" in name:
            return [True, "Inception", "2010", "movie"]
        return [False, None, None, None]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)

    args = MagicMock()
    args.path = None
    args.only_rename = False
    args.simulate = False

    # Run 2 cycles
    ui.POLLING_INTERVAL = 1
    ui.BYPASS_ENABLED = True
    current_time = 0.0
    def mock_time():
        nonlocal current_time
        current_time += 100.0
        return current_time
    monkeypatch.setattr("time.time", mock_time)

    exit_code = main.run_daemon_loop(args, max_cycles=2)
    assert exit_code == 0

    # Inception should be processed and moved
    assert (movies / "Inception (2010).mkv").is_file()
    assert not f1.exists()

    # Incomplete download should still be untouched in downloads
    assert f2_partial.is_file()


def test_integration_3_tier_tags_and_gemini_learning(media_env, monkeypatch):
    """End-to-end integration test: 3-tier tag loading, cleaning, and Gemini learning with -L flag."""
    config_dir = media_env["config_dir"]
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    # 1. User config contains custom_tags.json with a private tracker name
    custom_tags_file = config_dir / "custom_tags.json"
    custom_tags_file.write_text(json.dumps(["PrivateTrackerXYZ", "CustomTeamTag"]), encoding="utf-8")

    # 2. File with core tag (1080p, BluRay), user tag (PrivateTrackerXYZ), and unknown tag (CrypticGroup)
    cryptic_file = downloads / "PrivateTrackerXYZ.Arrival.2016.1080p.BluRay.x264.CrypticGroup.mkv"
    cryptic_file.write_text("arrival content", encoding="utf-8")

    tm = TagManager(config_dir=str(config_dir))
    monkeypatch.setattr("src.tags.tag_manager", tm)
    monkeypatch.setattr("src.utils.tag_manager", tm)
    monkeypatch.setattr("src.api.tag_manager", tm)

    # 3. TMDB fails initially, triggering real Gemini fallback
    def mock_tmdb(name, year, language, media_type):
        return [False, None, None, None]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "success": 1,
        "name": "Arrival",
        "year": "2016",
        "original_language": "en",
        "missing_tags": ["CrypticGroup", "the"]  # "the" is a stopword to test guardrail
    })
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)
    monkeypatch.setattr("src.api.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("src.ui.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(sys, "argv", ["main.py", "-L", "-b", "-t"])

    with patch("src.mail.send_tag_learned_email") as mock_tag_mail:
        exit_code = main.main()
        assert exit_code == 0
        mock_tag_mail.assert_called_once()
        call_kwargs = mock_tag_mail.call_args.kwargs
        assert "CrypticGroup" in call_kwargs["tags"]
        assert "PrivateTrackerXYZ.Arrival.2016.1080p.BluRay.x264.CrypticGroup.mkv" in call_kwargs["filename"]
        assert call_kwargs["media_title"] == "Arrival"

    # 4. Verify movie was processed and moved
    assert (movies / "Arrival (2016).mkv").is_file()

    # 5. Verify gemini_tags.json was created and contains CrypticGroup, but NOT the stopword 'the'
    gemini_file = config_dir / "gemini_tags.json"
    assert gemini_file.is_file()
    gemini_content = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert "CrypticGroup" in gemini_content["tags"]
    assert "the" not in gemini_content["tags"]


def test_integration_gemini_learning_disabled(media_env, monkeypatch):
    """Integration test: When learning is disabled (no -L, options.learn=false), tags are NOT saved to gemini_tags.json."""
    config_dir = media_env["config_dir"]
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    cryptic_file = downloads / "UnknownGroup.Arrival.2016.1080p.mkv"
    cryptic_file.write_text("arrival content", encoding="utf-8")

    tm = TagManager(config_dir=str(config_dir))
    monkeypatch.setattr("src.tags.tag_manager", tm)
    monkeypatch.setattr("src.utils.tag_manager", tm)
    monkeypatch.setattr("src.api.tag_manager", tm)

    def mock_tmdb(name, year, language, media_type):
        return [False, None, None, None]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "success": 1,
        "name": "Arrival",
        "year": "2016",
        "original_language": "en",
        "missing_tags": ["UnknownGroup"]
    })
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)
    monkeypatch.setattr("src.api.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("src.ui.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(sys, "argv", ["main.py", "-a", "-b"])

    with patch("src.mail.send_email") as mock_email:
        exit_code = main.main()
        assert exit_code == 0
        mock_email.assert_not_called()

    # Movie processed and moved
    assert (movies / "Arrival (2016).mkv").is_file()

    # gemini_tags.json must NOT exist
    gemini_file = config_dir / "gemini_tags.json"
    assert not gemini_file.exists()


def test_integration_simulation_with_learning(media_env, monkeypatch):
    """Integration test: In simulation mode with -L, tags are learned, but media files are untouched on disk."""
    config_dir = media_env["config_dir"]
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    cryptic_file = downloads / "SimLearnedGroup.Arrival.2016.1080p.mkv"
    cryptic_file.write_text("arrival content", encoding="utf-8")

    tm = TagManager(config_dir=str(config_dir))
    monkeypatch.setattr("src.tags.tag_manager", tm)
    monkeypatch.setattr("src.utils.tag_manager", tm)
    monkeypatch.setattr("src.api.tag_manager", tm)

    def mock_tmdb(name, year, language, media_type):
        return [False, None, None, None]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "success": 1,
        "name": "Arrival",
        "year": "2016",
        "original_language": "en",
        "missing_tags": ["SimLearnedGroup"]
    })
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)
    monkeypatch.setattr("src.api.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("src.ui.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(sys, "argv", ["main.py", "-s", "-L", "-b"])

    with patch("src.mail.send_tag_learned_email"):
        exit_code = main.main()
        assert exit_code == 0

    # Media file untouched
    assert cryptic_file.is_file()
    assert len(list(movies.iterdir())) == 0

    # But tag was learned into gemini_tags.json
    gemini_file = config_dir / "gemini_tags.json"
    assert gemini_file.is_file()
    gemini_content = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert "SimLearnedGroup" in gemini_content["tags"]


def test_integration_rename_only_with_learning(media_env, monkeypatch):
    """Integration test: In rename-only mode (-r) with -L, tags are learned and file is renamed in-place."""
    config_dir = media_env["config_dir"]
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    cryptic_file = downloads / "RenameOnlyGroup.Arrival.2016.1080p.mkv"
    cryptic_file.write_text("arrival content", encoding="utf-8")

    tm = TagManager(config_dir=str(config_dir))
    monkeypatch.setattr("src.tags.tag_manager", tm)
    monkeypatch.setattr("src.utils.tag_manager", tm)
    monkeypatch.setattr("src.api.tag_manager", tm)

    def mock_tmdb(name, year, language, media_type):
        return [False, None, None, None]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "success": 1,
        "name": "Arrival",
        "year": "2016",
        "original_language": "en",
        "missing_tags": ["RenameOnlyGroup"]
    })
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)
    monkeypatch.setattr("src.api.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("src.ui.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(sys, "argv", ["main.py", "-r", "-L", "-b"])

    with patch("src.mail.send_tag_learned_email"):
        exit_code = main.main()
        assert exit_code == 0

    # File renamed in place
    expected = downloads / "Arrival (2016).mkv"
    assert expected.is_file()
    assert not cryptic_file.exists()
    assert len(list(movies.iterdir())) == 0

    # Tag learned
    gemini_file = config_dir / "gemini_tags.json"
    assert gemini_file.is_file()
    gemini_content = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert "RenameOnlyGroup" in gemini_content["tags"]


def test_integration_daemon_with_learning(media_env, monkeypatch):
    """Integration test: In daemon mode with config.LEARN=True, tags are learned across cycles."""
    config_dir = media_env["config_dir"]
    downloads = media_env["downloads"]
    movies = media_env["movies"]
    cm = media_env["config_manager"]
    cm.set("options.learn", "true")

    cryptic_file = downloads / "AutoLearnGroup.Arrival.2016.1080p.mkv"
    cryptic_file.write_text("arrival content", encoding="utf-8")

    tm = TagManager(config_dir=str(config_dir))
    monkeypatch.setattr("src.tags.tag_manager", tm)
    monkeypatch.setattr("src.utils.tag_manager", tm)
    monkeypatch.setattr("src.api.tag_manager", tm)

    def mock_tmdb(name, year, language, media_type):
        return [False, None, None, None]

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "success": 1,
        "name": "Arrival",
        "year": "2016",
        "original_language": "en",
        "missing_tags": ["AutoLearnGroup"]
    })
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("google.genai.Client", lambda api_key: mock_client)
    monkeypatch.setattr("src.api.GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("src.ui.GEMINI_API_KEY", "dummy_key")

    args = MagicMock()
    args.path = None
    args.only_rename = False
    args.simulate = False
    args.learn = False  # Enabled via config.LEARN!

    ui.POLLING_INTERVAL = 1
    ui.BYPASS_ENABLED = True
    ui.LEARN_ENABLED = True
    ui.AI_FALLBACK_ENABLED = True

    current_time = 0.0
    def mock_time():
        nonlocal current_time
        current_time += 100.0
        return current_time
    monkeypatch.setattr("time.time", mock_time)

    with patch("src.mail.send_tag_learned_email"):
        exit_code = main.run_daemon_loop(args, max_cycles=1)
        assert exit_code == 0

    assert (movies / "Arrival (2016).mkv").is_file()
    gemini_file = config_dir / "gemini_tags.json"
    assert gemini_file.is_file()
    gemini_content = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert "AutoLearnGroup" in gemini_content["tags"]


def test_integration_config_cli_subcommands(media_env, monkeypatch, capsys):
    """End-to-end integration test: CLI config --set, --get, --list, --unset."""
    cm = media_env["config_manager"]
    monkeypatch.setattr("src.config.config", cm)
    monkeypatch.setattr("src.ui.config", cm)

    # 1. config --set
    monkeypatch.setattr(sys, "argv", ["main.py", "config", "--set", "options.polling_interval", "42"])
    main.main()
    cm.load()
    assert int(cm.get("options.polling_interval")) == 42

    # 2. config --get
    monkeypatch.setattr(sys, "argv", ["main.py", "config", "--get", "options.polling_interval"])
    main.main()
    out = capsys.readouterr().out
    assert "42" in out

    # 3. config --list
    monkeypatch.setattr(sys, "argv", ["main.py", "config", "--list"])
    main.main()
    list_out = capsys.readouterr().out
    assert "paths" in list_out or "options" in list_out

    # 4. config --unset
    monkeypatch.setattr(sys, "argv", ["main.py", "config", "--unset", "options.polling_interval"])
    main.main()
    cm.load()
    assert cm.parser.has_option("options", "polling_interval") is False


def test_integration_resolution_and_quality_tags(media_env, monkeypatch):
    """End-to-end integration test: -R and -q append resolution and quality tags to renamed files on disk."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    sample_movie = downloads / "Dune.Part.Two.2024.1080p.BluRay.x264.mkv"
    sample_movie.write_text("movie data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Dune Part Two", "2024", "movie"]

    real_which = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda cmd: "/usr/bin/ffprobe" if "ffprobe" in cmd else real_which(cmd)
    )
    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-R", "-q", "-b"])

    exit_code = main.main()
    assert exit_code == 0

    expected_file = movies / "Dune Part Two (2024) [Blu-ray FullHD].mkv"
    assert expected_file.is_file()
    assert expected_file.read_text(encoding="utf-8") == "movie data"
    assert not sample_movie.exists()


def test_integration_interactive_confirmation_accepted(media_env, monkeypatch):
    """End-to-end integration test: Interactive user confirmation (pressing Enter) executes renames."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]
    cm = media_env["config_manager"]
    cm.set("options.bypass", "false")

    sample_movie = downloads / "Oppenheimer.2023.720p.mkv"
    sample_movie.write_text("oppenheimer data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Oppenheimer", "2023", "movie"]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py"])  # Notice: NO -b / --bypass!
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    exit_code = main.main()
    assert exit_code == 0
    assert (movies / "Oppenheimer (2023).mkv").is_file()
    assert not sample_movie.exists()


def test_integration_interactive_confirmation_rejected(media_env, monkeypatch):
    """End-to-end integration test: Cancelling via Ctrl+C (KeyboardInterrupt) exits cleanly without modifying files."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]
    cm = media_env["config_manager"]
    cm.set("options.bypass", "false")

    sample_movie = downloads / "Oppenheimer.2023.720p.mkv"
    sample_movie.write_text("oppenheimer data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Oppenheimer", "2023", "movie"]

    def mock_cancel(prompt=""):
        raise KeyboardInterrupt()

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py"])  # NO -b!
    monkeypatch.setattr("builtins.input", mock_cancel)

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
    assert sample_movie.is_file()
    assert not (movies / "Oppenheimer (2023).mkv").exists()


def test_integration_notify_success_flag(media_env, monkeypatch):
    """End-to-end integration test: --notify-success sends email upon successful file processing."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]

    sample_movie = downloads / "Gladiator.2000.mkv"
    sample_movie.write_text("gladiator content", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Gladiator", "2000", "movie"]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-b", "--notify-success"])

    with patch("src.mail.send_media_success_email") as mock_mail:
        exit_code = main.main()
        assert exit_code == 0
        mock_mail.assert_called_once()
        assert "Gladiator (2000).mkv" in mock_mail.call_args.kwargs.get("media_name", "")


def test_integration_notify_error_flag(media_env, monkeypatch):
    """End-to-end integration test: --notify-error sends error notification when an exception occurs."""
    downloads = media_env["downloads"]
    sample_movie = downloads / "Broken.2020.mkv"
    sample_movie.write_text("data", encoding="utf-8")

    def mock_tmdb(name, year, language, media_type):
        return [True, "Broken", "2020", "movie"]

    def mock_rename_fail(df):
        raise RuntimeError("Simulated disk write failure")

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr("src.files.rename_media_files", mock_rename_fail)
    monkeypatch.setattr(sys, "argv", ["main.py", "-b", "--notify-error"])

    with patch("src.mail.send_error_email") as mock_err_mail, pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 1
    mock_err_mail.assert_called_once()


def test_integration_logging_flag(media_env, monkeypatch, tmp_path):
    """End-to-end integration test: -l activates file logging in log directory."""
    downloads = media_env["downloads"]
    sample_movie = downloads / "LogTest.2021.mkv"
    sample_movie.write_text("data", encoding="utf-8")

    custom_log = tmp_path / "custom_log"
    custom_log.mkdir(parents=True, exist_ok=True)

    def mock_tmdb(name, year, language, media_type):
        return [True, "LogTest", "2021", "movie"]

    monkeypatch.setattr("src.api.api_call", mock_tmdb)
    monkeypatch.setattr(sys, "argv", ["main.py", "-l", "-s", "-b"])
    monkeypatch.setattr("src.ui.get_log_dir", lambda: custom_log)

    exit_code = main.main()
    assert exit_code == 0
    assert custom_log.is_dir()
    log_files = list(custom_log.glob("*.txt"))
    assert len(log_files) >= 1


def test_integration_top_level_gui_entrypoint(monkeypatch):
    """End-to-end integration test: --gui directly launches the configuration GUI."""
    monkeypatch.setattr(sys, "argv", ["main.py", "--gui"])
    with patch("src.config.config.run_gui") as mock_gui:
        exit_code = main.main()
        assert exit_code == 0
        mock_gui.assert_called_once()


def test_integration_configure_subcommands_dispatch(monkeypatch):
    """End-to-end integration test: configure --options / --paths dispatches cleanly."""
    monkeypatch.setattr(sys, "argv", ["main.py", "configure", "--options"])
    with patch("src.config.ConfigManager.run_wizard") as mock_wizard:
        exit_code = main.main()
        assert exit_code == 0
        mock_wizard.assert_called_once_with(section="options", interactive_menu=False)


def test_integration_daemon_clean_file_with_tags_no_infinite_loop(media_env, monkeypatch):
    """End-to-end integration test: An already clean title missing tags is enriched, moved, and next cycle reports idle."""
    downloads = media_env["downloads"]
    movies = media_env["movies"]
    cm = media_env["config_manager"]

    cm.set("options.resolution", "true")
    cm.set("options.quality", "true")

    clean_movie = downloads / "Inception (2010).mkv"
    clean_movie.write_text("movie data", encoding="utf-8")

    monkeypatch.setattr(utils, "RESOLUTION", True)
    monkeypatch.setattr(utils, "QUALITY", True)
    monkeypatch.setattr(ui, "RESOLUTION_ENABLED", True)
    monkeypatch.setattr(ui, "QUALITY_ENABLED", True)

    args = MagicMock(path=str(downloads), only_rename=False, simulate=False)

    logs = []
    def mock_log(msg):
        logs.append(str(msg))

    with patch("src.files.get_file_quality_resolution", return_value=("1080p", "BluRay")), \
         patch("src.mail.send_media_success_email"), \
         patch("src.ui.print_log", side_effect=mock_log):

        # Cycle 1: Discovers clean file missing tags, renames with tags, and moves to movies library
        ret1 = main.process_media(args, daemon=True, cycle=1)
        assert ret1 == 0

        dest_file = movies / "Inception (2010) [BluRay FullHD].mkv"
        assert dest_file.exists()
        assert not clean_movie.exists()
        assert any("Successfully processed 1 file(s)" in l for l in logs)

        # Cycle 2: Downloads folder is now empty, next cycle reports 'No media to process' without looping
        ret2 = main.process_media(args, daemon=True, cycle=2)
        assert ret2 == 0
        assert any("Check 2 : No media to process" in l for l in logs)


