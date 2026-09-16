import json
from unittest.mock import patch

from src.tags import TagManager
import data.data as legacy_data


def test_tag_manager_default_paths(tmp_path):
    tm = TagManager(config_dir=str(tmp_path))
    assert tm.config_dir == tmp_path
    assert tm.user_tags_path == tmp_path / "custom_tags.json"
    assert tm.gemini_tags_path == tmp_path / "gemini_tags.json"

    # Default fallback when config_dir is None
    with patch("src.tags.config") as mock_cfg:
        mock_cfg.config_path = None
        fallback_tm = TagManager()
        assert ".config" in str(fallback_tm.config_dir) or "AppData" in str(fallback_tm.config_dir)


def test_load_core_tags(tmp_path):
    # Non-existent core file
    missing_file = tmp_path / "missing_tags.json"
    tm = TagManager(core_path=str(missing_file))
    assert tm.load_core_tags() == []

    # Corrupt JSON
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{invalid_json", encoding="utf-8")
    tm = TagManager(core_path=str(corrupt_file))
    with patch("src.ui.print_log") as mock_log:
        assert tm.load_core_tags() == []
        assert mock_log.called

    # Valid core file with non-list categories
    valid_file = tmp_path / "valid.json"
    valid_file.write_text(
        json.dumps(
            {"categories": {"resolutions": ["1080p", "4k"], "empty": "not_a_list", "whitespace": ["  ", "bluray"]}}
        ),
        encoding="utf-8",
    )
    tm = TagManager(core_path=str(valid_file))
    tags = tm.load_core_tags()
    assert "1080p" in tags
    assert "4k" in tags
    assert "bluray" in tags


def test_extract_tags_from_json_formats(tmp_path):
    tm = TagManager(config_dir=str(tmp_path))

    # 1. Non-existent file
    assert tm._extract_tags_from_json(tmp_path / "none.json") == []

    # 2. Corrupt JSON
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("not json", encoding="utf-8")
    assert tm._extract_tags_from_json(corrupt) == []

    # 3. Simple list of strings & dicts
    list_file = tmp_path / "list.json"
    list_file.write_text(
        json.dumps(
            [
                "tag1",
                {"tag": "tag2"},
                {"other": "ignored"},
                123,  # non-string
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert tm._extract_tags_from_json(list_file) == ["tag1", "tag2"]

    # 4. Dict with "tags" list
    dict_file = tmp_path / "dict.json"
    dict_file.write_text(json.dumps({"tags": ["tagA", "tagB", "  "]}), encoding="utf-8")
    assert tm._extract_tags_from_json(dict_file) == ["tagA", "tagB"]

    # 5. Dict with arbitrary categories
    nested_file = tmp_path / "nested.json"
    nested_file.write_text(
        json.dumps({"cat1": ["tagX"], "cat2": ["tagY"], "cat3": "ignored_non_list"}), encoding="utf-8"
    )
    assert tm._extract_tags_from_json(nested_file) == ["tagX", "tagY"]

    # 6. JSON boolean / number (neither list nor dict)
    scalar_file = tmp_path / "scalar.json"
    scalar_file.write_text("12345", encoding="utf-8")
    assert tm._extract_tags_from_json(scalar_file) == []


def test_load_user_and_gemini_tags(tmp_path):
    tm = TagManager(config_dir=str(tmp_path))

    user_json = tmp_path / "custom_tags.json"
    user_json.write_text(json.dumps(["user_tracker", "my_group"]), encoding="utf-8")

    gemini_json = tmp_path / "gemini_tags.json"
    gemini_json.write_text(json.dumps(["ai_tag1", "ai_tag2"]), encoding="utf-8")

    assert tm.load_user_tags() == ["user_tracker", "my_group"]
    assert tm.load_gemini_tags() == ["ai_tag1", "ai_tag2"]

    # Deduplicated merged list and caching
    all_tags = tm.get_all_tags()
    assert "user_tracker" in all_tags
    assert "ai_tag1" in all_tags

    # Caching check
    cached = tm.get_all_tags()
    assert cached is all_tags

    tm.invalidate_cache()
    assert tm._cached_tags is None
    assert tm._master_regex is None


def test_master_regex_empty():
    tm = TagManager()
    with patch.object(tm, "get_all_tags", return_value=[]):
        rx = tm.get_master_regex()
        assert rx.search("Any text") is None


def test_master_regex_and_clean_text(tmp_path):
    core_file = tmp_path / "core.json"
    core_file.write_text(
        json.dumps({"categories": {"tags": ["1080p", "hdr10+", "hdr10", "bluray", "dts-hd", "x264"]}}), encoding="utf-8"
    )

    tm = TagManager(core_path=str(core_file), config_dir=str(tmp_path))
    rx = tm.get_master_regex()
    assert rx is tm.get_master_regex()  # Cache hit

    # Test clean_text with empty/None
    assert tm.clean_text("") == ""
    assert tm.clean_text(None) is None

    # Test clean_text
    sample = "Inception.2010.1080p.hdr10+.BluRay.x264.DTS-HD.mkv"
    cleaned = tm.clean_text(sample)
    assert "1080p" not in cleaned
    assert "hdr10+" not in cleaned
    assert "BluRay" not in cleaned
    assert "x264" not in cleaned
    assert "DTS-HD" not in cleaned

    # Verify no partial-word matching (boundary assertion)
    assert tm.clean_text("Application.mkv") == "Application.mkv"


def test_validate_tag():
    tm = TagManager()

    # Empty / non-string
    assert tm.validate_tag("")[0] is False
    assert tm.validate_tag(None)[0] is False
    assert tm.validate_tag(123)[0] is False

    # Short
    assert tm.validate_tag("ab")[0] is False
    assert "too short" in tm.validate_tag("ab")[1]

    # Stopwords (English and French)
    assert tm.validate_tag("the")[0] is False
    assert "protected" in tm.validate_tag("the")[1]
    assert tm.validate_tag("WAR")[0] is False
    assert tm.validate_tag("les")[0] is False
    assert tm.validate_tag("film")[0] is False

    # Numeric
    assert tm.validate_tag("12345")[0] is False
    assert "purely numeric" in tm.validate_tag("12345")[1]

    # Invalid chars
    assert tm.validate_tag("tag@bad!")[0] is False
    assert "invalid characters" in tm.validate_tag("tag@bad!")[1]

    # Valid tags
    ok, val = tm.validate_tag("  framestor  ")
    assert ok is True
    assert val == "framestor"

    ok, val = tm.validate_tag("ddp5.1")
    assert ok is True
    assert val == "ddp5.1"

    ok, val = tm.validate_tag("repack-team")
    assert ok is True
    assert val == "repack-team"


def test_add_gemini_and_user_tags(tmp_path):
    core_file = tmp_path / "core.json"
    core_file.write_text(json.dumps({"categories": {"base": ["existing_core"]}}), encoding="utf-8")

    tm = TagManager(core_path=str(core_file), config_dir=str(tmp_path))

    # Empty input
    assert tm.add_gemini_tags([]) == []
    assert tm.add_gemini_tags(None) == []

    # Filter out stopwords, short tags, and existing tags
    missing = ["the", "ok", "existing_core", "valid_tag_one", "valid_tag_two"]
    added = tm.add_gemini_tags(missing)
    assert added == ["valid_tag_one", "valid_tag_two"]

    # Verify file content
    gemini_file = tmp_path / "gemini_tags.json"
    assert gemini_file.is_file()
    content = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert content["tags"] == ["valid_tag_one", "valid_tag_two"]

    # Re-adding same tags -> duplicates ignored
    added_again = tm.add_gemini_tags(["valid_tag_one"])
    assert added_again == []

    # Add user tags
    user_added = tm.add_user_tags(["custom_release_group"])
    assert user_added == ["custom_release_group"]
    user_file = tmp_path / "custom_tags.json"
    assert user_file.is_file()
    u_content = json.loads(user_file.read_text(encoding="utf-8"))
    assert u_content["tags"] == ["custom_release_group"]


def test_legacy_data_module(tmp_path):
    assert len(legacy_data.TAGS) > 50
    assert len(legacy_data.TLDS) > 50
    assert len(legacy_data.RESOLUTION_PATTERNS) > 0
    assert len(legacy_data.QUALITY_PATTERNS) > 0

    # Test _load_core_data when file missing
    with patch("data.data.TAGS_JSON_FILE", tmp_path / "non_existent.json"):
        tags, tlds, res, qual = legacy_data._load_core_data()
        assert tags == []
        assert tlds == []
