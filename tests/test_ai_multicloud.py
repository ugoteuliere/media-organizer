import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd

from src import api, ui, utils
from src.config import ConfigManager, config
from src.api import ParsedMediaItem, BatchMediaResponse


# ==============================================================================
# 1. Probability Scorer Tests
# ==============================================================================


def test_compute_tmdb_match_probability():
    # Exact match with matching year
    prob = utils.compute_tmdb_match_probability("Inception", "2010", "Inception", "2010")
    assert prob == 1.0

    # Title with punctuation and case difference
    prob = utils.compute_tmdb_match_probability("Spider-Man: No Way Home", "2021", "Spider Man No Way Home", "2021")
    assert prob >= 0.95

    # Completely different movie
    prob = utils.compute_tmdb_match_probability("Interstellar", "2014", "The Intern", "2015")
    assert prob < 0.50

    # Year off by 1 year (e.g. film festival release vs theatrical)
    prob_1yr = utils.compute_tmdb_match_probability("Avatar", "2009", "Avatar", "2010")
    assert prob_1yr == 0.95

    # Year off by 2 years
    prob_2yr = utils.compute_tmdb_match_probability("Avatar", "2009", "Avatar", "2011")
    assert prob_2yr == 0.85

    # Year off by 5 years
    prob_5yr = utils.compute_tmdb_match_probability("Avatar", "2009", "Avatar", "2014")
    assert prob_5yr < 0.85

    # Missing parsed_name or tmdb_title or unknown
    assert utils.compute_tmdb_match_probability("", "2020", "Movie", "2020") == 0.0
    assert utils.compute_tmdb_match_probability(None, "2020", "Movie", "2020") == 0.0
    assert utils.compute_tmdb_match_probability("Movie", "2020", None, "2020") == 0.0
    assert utils.compute_tmdb_match_probability("Movie", "2020", "unknown", "2020") == 0.0
    assert utils.compute_tmdb_match_probability("   ", "2020", "   ", "2020") == 0.0

    # Missing parsed year or tmdb year
    prob_no_ty = utils.compute_tmdb_match_probability("Gladiator", "2000", "Gladiator", None)
    assert prob_no_ty >= 0.85
    prob_no_py = utils.compute_tmdb_match_probability("Gladiator", None, "Gladiator", "2000")
    assert prob_no_py >= 0.90
    prob_neither = utils.compute_tmdb_match_probability("Gladiator", None, "Gladiator", None)
    assert prob_neither >= 0.90

    # Invalid non-numeric years
    prob_invalid = utils.compute_tmdb_match_probability("Gladiator", "bad_year", "Gladiator", "bad_tmdb_year")
    assert prob_invalid >= 0.85

    # Empty token set
    prob_punct = utils.compute_tmdb_match_probability("---", "2020", "---", "2020")
    assert prob_punct == 0.0


# ==============================================================================
# 2. Schema and Provider Caller Tests
# ==============================================================================


def test_is_quota_or_rate_limit_error():
    assert api.is_quota_or_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert api.is_quota_or_rate_limit_error(Exception("Rate limit reached for model")) is True
    assert api.is_quota_or_rate_limit_error(Exception("RESOURCE_EXHAUSTED: quota exceeded")) is True
    assert api.is_quota_or_rate_limit_error(Exception("insufficient_quota")) is True
    assert api.is_quota_or_rate_limit_error(Exception("all tokens consumed for today")) is True
    assert api.is_quota_or_rate_limit_error(Exception("This model is unavailable for free.")) is True
    assert api.is_quota_or_rate_limit_error(Exception("Rate limit exceeded: free-models-per-day")) is True
    assert api.is_quota_or_rate_limit_error(Exception("Connection timed out")) is False


def test_call_gemini_batch_success_and_errors(monkeypatch):
    dummy_items = [
        {"File": "Test.mkv", "Folder": "dl", "Path": "/dl/Test.mkv", "Clean": "Test", "Parse": "Test", "Media": "movie"}
    ]

    # 1. Missing API key
    monkeypatch.setattr(api, "GEMINI_API_KEY", None)
    with patch.object(ConfigManager, "GEMINI_API_KEY", new_callable=PropertyMock, return_value=None):
        with pytest.raises(ValueError, match="Gemini API key is not configured"):
            api.call_gemini_batch(dummy_items)

    # 2. Success with BatchMediaResponse JSON format
    monkeypatch.setattr(api, "GEMINI_API_KEY", "dummy_gemini")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(
        {
            "items": [
                {
                    "file_id": 0,
                    "title": "Gemini Movie",
                    "year": "2023",
                    "original_language": "en",
                    "missing_tags": ["remux"],
                    "confidence_score": 0.95,
                }
            ]
        }
    )
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Gemini Movie"
        assert res.items[0].confidence_score == 0.95

    # 3. Success with raw list JSON format
    mock_resp.text = json.dumps(
        [
            {
                "file_id": 0,
                "title": "Gemini List Movie",
                "year": "2023",
                "original_language": "en",
                "missing_tags": [],
                "confidence_score": 0.90,
            }
        ]
    )
    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Gemini List Movie"

    # 4. Backward compatibility with single-item dict format
    mock_resp.text = json.dumps(
        {"success": 1, "name": "Legacy Movie", "year": "2021", "original_language": "fr", "missing_tags": ["1080p"]}
    )
    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Legacy Movie"

    # Single-item dict with success = 0
    mock_resp.text = json.dumps({"success": 0})
    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 0

    # Scalar JSON response (non-dict, non-list)
    mock_resp.text = json.dumps("just a string")
    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 0

    # 5. Invalid JSON
    mock_resp.text = "{invalid json"
    mock_client.models.generate_content.side_effect = None
    mock_client.models.generate_content.return_value = mock_resp
    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(ValueError, match="Failed to parse Gemini response as JSON"):
            api.call_gemini_batch(dummy_items)

    # 6. Model fallback on non-quota error and quota exception propagation
    valid_resp = MagicMock()
    valid_resp.text = json.dumps({"items": [{"file_id": 0, "title": "Fallback Movie", "confidence_score": 0.9}]})
    mock_client.models.generate_content.side_effect = [RuntimeError("Model not found"), valid_resp]
    with patch("google.genai.Client", return_value=mock_client):
        res = api.call_gemini_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Fallback Movie"

    # Quota error raises immediately
    mock_client.models.generate_content.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED")
    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
            api.call_gemini_batch(dummy_items)

    # All models fail with non-quota error
    mock_client.models.generate_content.side_effect = RuntimeError("Server down")
    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="Server down"):
            api.call_gemini_batch(dummy_items)


def test_call_groq_batch(monkeypatch):
    dummy_items = [
        {"File": "Groq.mkv", "Folder": "dl", "Path": "/dl/Groq.mkv", "Clean": "Groq", "Parse": "Groq", "Media": "movie"}
    ]

    # 1. Missing Groq API key
    monkeypatch.setattr(api, "GROQ_API_KEY", None)
    with patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value=None):
        with pytest.raises(ValueError, match="Groq API key is not configured"):
            api.call_groq_batch(dummy_items)

    # 2. Successful response
    monkeypatch.setattr(api, "GROQ_API_KEY", "gsk_test")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "file_id": 0,
                                    "title": "Groq Movie",
                                    "year": "2024",
                                    "original_language": "en",
                                    "missing_tags": ["hdr"],
                                    "confidence_score": 0.98,
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = api.call_groq_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Groq Movie"
        mock_post.assert_called_once()
        assert "api.groq.com" in mock_post.call_args[0][0]

    # 3. HTTP error (e.g. 429 quota error)
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Groq API error"):
            api.call_groq_batch(dummy_items)


def test_call_openrouter_batch(monkeypatch):
    dummy_items = [
        {"File": "OR.mkv", "Folder": "dl", "Path": "/dl/OR.mkv", "Clean": "OR", "Parse": "OR", "Media": "movie"}
    ]

    # 1. Missing OpenRouter API key
    monkeypatch.setattr(api, "OPENROUTER_API_KEY", None)
    with patch.object(ConfigManager, "OPENROUTER_API_KEY", new_callable=PropertyMock, return_value=None):
        with pytest.raises(ValueError, match="OpenRouter API key is not configured"):
            api.call_openrouter_batch(dummy_items)

    # 2. Successful response
    monkeypatch.setattr(api, "OPENROUTER_API_KEY", "sk-or-v1-test")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "items": [
                                {
                                    "file_id": 0,
                                    "title": "OpenRouter Movie",
                                    "year": "2023",
                                    "original_language": "en",
                                    "missing_tags": [],
                                    "confidence_score": 0.88,
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = api.call_openrouter_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "OpenRouter Movie"
        mock_post.assert_called_once()
        assert "openrouter.ai" in mock_post.call_args[0][0]

    # 3. HTTP error (e.g. 500 error)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="OpenRouter API error"):
            api.call_openrouter_batch(dummy_items)


def test_call_cloudflare_batch(monkeypatch):
    dummy_items = [
        {"File": "CF.mkv", "Folder": "dl", "Path": "/dl/CF.mkv", "Clean": "CF", "Parse": "CF", "Media": "movie"}
    ]

    # 1. Missing Token or Account ID
    monkeypatch.setattr(api, "CLOUDFLARE_API_TOKEN", None)
    monkeypatch.setattr(api, "CLOUDFLARE_ACCOUNT_ID", None)
    with patch.object(ConfigManager, "CLOUDFLARE_API_TOKEN", new_callable=PropertyMock, return_value=None):
        with pytest.raises(ValueError, match="Cloudflare API token or Account ID is not configured"):
            api.call_cloudflare_batch(dummy_items)

    monkeypatch.setattr(api, "CLOUDFLARE_API_TOKEN", "token123")
    monkeypatch.setattr(api, "CLOUDFLARE_ACCOUNT_ID", "acc123")

    # 2. Successful response with clean JSON
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "response": json.dumps(
                {
                    "items": [
                        {
                            "file_id": 0,
                            "title": "Cloudflare Movie",
                            "year": "2024",
                            "original_language": "en",
                            "missing_tags": [],
                            "confidence_score": 0.92,
                        }
                    ]
                }
            )
        },
        "success": True,
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = api.call_cloudflare_batch(dummy_items)
        assert len(res.items) == 1
        assert res.items[0].title == "Cloudflare Movie"
        assert "api.cloudflare.com" in mock_post.call_args[0][0]

    # 3. Successful response wrapped in markdown ```json
    mock_resp.json.return_value = {
        "result": {
            "response": "```json\n"
            + json.dumps(
                {
                    "items": [
                        {
                            "file_id": 0,
                            "title": "Markdown CF Movie",
                            "year": "2024",
                            "original_language": "en",
                            "missing_tags": [],
                            "confidence_score": 0.90,
                        }
                    ]
                }
            )
            + "\n```"
        },
        "success": True,
    }
    with patch("requests.post", return_value=mock_resp):
        res = api.call_cloudflare_batch(dummy_items)
        assert res.items[0].title == "Markdown CF Movie"

    # 4. Result dict directly containing json
    mock_resp.json.return_value = {
        "result": {
            "items": [
                {
                    "file_id": 0,
                    "title": "Dict CF Movie",
                    "year": "2024",
                    "original_language": "en",
                    "missing_tags": [],
                    "confidence_score": 0.90,
                }
            ]
        },
        "success": True,
    }
    with patch("requests.post", return_value=mock_resp):
        res = api.call_cloudflare_batch(dummy_items)
        assert res.items[0].title == "Dict CF Movie"

    # 4b. Result dict containing choices array (OpenAI-compatible format)
    mock_resp.json.return_value = {
        "result": {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "items": [
                                    {
                                        "file_id": 0,
                                        "title": "Choices CF Movie",
                                        "year": "2024",
                                        "original_language": "en",
                                        "missing_tags": [],
                                        "confidence_score": 0.95,
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        },
        "success": True,
    }
    with patch("requests.post", return_value=mock_resp):
        res = api.call_cloudflare_batch(dummy_items)
        assert res.items[0].title == "Choices CF Movie"

    # 5. HTTP error
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Cloudflare Workers AI error"):
            api.call_cloudflare_batch(dummy_items)


# ==============================================================================
# 3. Failover and Batch Orchestrator Tests
# ==============================================================================


def test_get_available_and_prioritized_providers(monkeypatch):
    monkeypatch.setattr(api, "GEMINI_API_KEY", "g_key")
    monkeypatch.setattr(api, "GROQ_API_KEY", "gr_key")
    monkeypatch.setattr(api, "OPENROUTER_API_KEY", "or_key")
    monkeypatch.setattr(api, "CLOUDFLARE_API_TOKEN", "cf_tok")
    monkeypatch.setattr(api, "CLOUDFLARE_ACCOUNT_ID", "cf_acc")

    available = api.get_available_providers()
    assert available == ["gemini", "groq", "openrouter", "cloudflare"]

    # When AI_PROVIDER is auto
    monkeypatch.setattr(config, "AI_PROVIDER", "auto")
    assert api.get_prioritized_providers() == ["gemini", "groq", "openrouter", "cloudflare"]

    # When AI_PROVIDER is groq
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")
    assert api.get_prioritized_providers() == ["groq", "gemini", "openrouter", "cloudflare"]

    # When AI_PROVIDER is openrouter
    monkeypatch.setattr(config, "AI_PROVIDER", "openrouter")
    assert api.get_prioritized_providers() == ["openrouter", "gemini", "groq", "cloudflare"]


def test_execute_ai_batch_with_failover_scenarios(monkeypatch):
    dummy_items = [
        {
            "File": "Movie1.mkv",
            "Folder": "dl",
            "Path": "/dl/Movie1.mkv",
            "Clean": "Movie1",
            "Parse": "Movie1",
            "Media": "movie",
        },
        {
            "File": "Movie2.mkv",
            "Folder": "dl",
            "Path": "/dl/Movie2.mkv",
            "Clean": "Movie2",
            "Parse": "Movie2",
            "Media": "movie",
        },
    ]

    # 1. Empty list
    assert api.execute_ai_batch_with_failover([]) == []

    # 2. No providers configured
    with patch("src.api.get_prioritized_providers", return_value=[]):
        res = api.execute_ai_batch_with_failover(dummy_items)
        assert len(res) == 2
        assert res[0][0] is False

    # 3. Single provider succeeds with confidence and missing tags learning
    mock_batch_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(
                file_id=0,
                title="Movie One",
                year="2021",
                original_language="en",
                missing_tags=["tagA"],
                confidence_score=0.95,
            ),
            ParsedMediaItem(
                file_id=1,
                title="Movie Two",
                year="2022",
                original_language="fr",
                missing_tags=["tagB"],
                confidence_score=0.85,
            ),
        ]
    )

    with (
        patch("src.api.get_prioritized_providers", return_value=["groq"]),
        patch("src.api.call_groq_batch", return_value=mock_batch_resp) as mock_groq,
        patch("src.ui.LEARN_ENABLED", True),
        patch("src.api.tag_manager.add_gemini_tags", return_value=["tagA"]) as mock_tags,
        patch("src.mail.send_tag_learned_email") as mock_mail,
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 2
        assert results[0] == [True, "Movie One", "2021", "en", ["tagA"]]
        assert results[1] == [True, "Movie Two", "2022", "fr", ["tagB"]]
        mock_groq.assert_called_once()
        mock_tags.assert_called()
        assert mock_mail.call_count == 2

    # 4. Failover scenario: Provider 1 (Gemini) hits 429 quota error -> Provider 2 (Groq) takes over!
    with (
        patch("src.api.get_prioritized_providers", return_value=["gemini", "groq"]),
        patch("src.api.call_gemini_batch", side_effect=RuntimeError("429 Resource exhausted")) as mock_gem,
        patch("src.api.call_groq_batch", return_value=mock_batch_resp) as mock_gr,
        patch("src.ui.LEARN_ENABLED", False),
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 2
        assert results[0][0] is True
        mock_gem.assert_called_once()
        mock_gr.assert_called_once()

    # 5. All providers fail
    with (
        patch("src.api.get_prioritized_providers", return_value=["gemini", "groq"]),
        patch("src.api.call_gemini_batch", side_effect=RuntimeError("Gemini down")),
        patch("src.api.call_groq_batch", side_effect=RuntimeError("Groq down")),
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 2
        assert results[0][0] is False
        assert results[1][0] is False

    # 6. Low confidence item is rejected
    low_conf_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(
                file_id=0,
                title="Uncertain Movie",
                year="2020",
                original_language="en",
                missing_tags=[],
                confidence_score=0.40,
            ),
        ]
    )
    with (
        patch("src.api.get_prioritized_providers", return_value=["groq"]),
        patch("src.api.call_groq_batch", return_value=low_conf_resp),
    ):
        results = api.execute_ai_batch_with_failover([dummy_items[0]])
        assert results[0][0] is False


def test_unit_groq_limit_bypassed_to_openrouter():
    """Unit test: When Groq returns a rate limit / 429 quota error, orchestrator bypasses Groq and uses OpenRouter."""
    dummy_items = [
        {"File": "Film.mkv", "Folder": "dl", "Path": "/dl/Film.mkv", "Clean": "Film", "Parse": "Film", "Media": "movie"}
    ]
    expected_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(
                file_id=0, title="Film OpenRouter", year="2022", original_language="en", confidence_score=0.95
            )
        ]
    )

    with (
        patch("src.api.get_prioritized_providers", return_value=["groq", "openrouter"]),
        patch("src.api.call_groq_batch", side_effect=RuntimeError("Groq 429: Too many requests. Rate limit exceeded.")),
        patch("src.api.call_openrouter_batch", return_value=expected_resp) as mock_or,
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 1
        assert results[0] == [True, "Film OpenRouter", "2022", "en", []]
        mock_or.assert_called_once()


def test_unit_openrouter_limit_bypassed_to_cloudflare():
    """Unit test: When OpenRouter returns quota exhausted error, orchestrator bypasses OpenRouter and uses Cloudflare."""
    dummy_items = [
        {"File": "Film.mkv", "Folder": "dl", "Path": "/dl/Film.mkv", "Clean": "Film", "Parse": "Film", "Media": "movie"}
    ]
    expected_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(
                file_id=0, title="Film Cloudflare", year="2023", original_language="fr", confidence_score=0.91
            )
        ]
    )

    with (
        patch("src.api.get_prioritized_providers", return_value=["openrouter", "cloudflare"]),
        patch(
            "src.api.call_openrouter_batch",
            side_effect=RuntimeError("OpenRouter error (status 429): Insufficient credits / rate limit"),
        ),
        patch("src.api.call_cloudflare_batch", return_value=expected_resp) as mock_cf,
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 1
        assert results[0] == [True, "Film Cloudflare", "2023", "fr", []]
        mock_cf.assert_called_once()


def test_unit_cloudflare_limit_bypassed_to_gemini():
    """Unit test: When Cloudflare returns daily neuron limit error, orchestrator bypasses Cloudflare and uses Gemini."""
    dummy_items = [
        {"File": "Film.mkv", "Folder": "dl", "Path": "/dl/Film.mkv", "Clean": "Film", "Parse": "Film", "Media": "movie"}
    ]
    expected_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(file_id=0, title="Film Gemini", year="2024", original_language="en", confidence_score=0.93)
        ]
    )

    with (
        patch("src.api.get_prioritized_providers", return_value=["cloudflare", "gemini"]),
        patch(
            "src.api.call_cloudflare_batch",
            side_effect=RuntimeError("Cloudflare Workers AI error (status 429): daily neuron quota exhausted"),
        ),
        patch("src.api.call_gemini_batch", return_value=expected_resp) as mock_gem,
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 1
        assert results[0] == [True, "Film Gemini", "2024", "en", []]
        mock_gem.assert_called_once()


def test_unit_gemini_limit_bypassed_to_groq():
    """Unit test: When Gemini returns ResourceExhausted 429 error, orchestrator bypasses Gemini and uses Groq."""
    dummy_items = [
        {"File": "Film.mkv", "Folder": "dl", "Path": "/dl/Film.mkv", "Clean": "Film", "Parse": "Film", "Media": "movie"}
    ]
    expected_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(file_id=0, title="Film Groq", year="2021", original_language="en", confidence_score=0.96)
        ]
    )

    with (
        patch("src.api.get_prioritized_providers", return_value=["gemini", "groq"]),
        patch("src.api.call_gemini_batch", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")),
        patch("src.api.call_groq_batch", return_value=expected_resp) as mock_gr,
    ):
        results = api.execute_ai_batch_with_failover(dummy_items)
        assert len(results) == 1
        assert results[0] == [True, "Film Groq", "2021", "en", []]
        mock_gr.assert_called_once()


def test_gemini_api_call_with_alternative_provider(monkeypatch):
    dummy_info = {
        "File": "Test.mkv",
        "Folder": "dl",
        "Path": "/dl/Test.mkv",
        "Clean": "Test",
        "Parse": "Test",
        "Media": "movie",
    }

    # Configure Groq as provider, Gemini key None
    monkeypatch.setattr(api, "GEMINI_API_KEY", None)
    monkeypatch.setattr(config, "AI_PROVIDER", "groq")

    with (
        patch("src.api.get_available_providers", return_value=["groq"]),
        patch(
            "src.api.execute_ai_batch_with_failover", return_value=[[True, "Groq Single", "2024", "en", []]]
        ) as mock_exec,
    ):
        res = api.gemini_api_call(dummy_info)
        assert res == [True, "Groq Single", "2024", "en", []]
        mock_exec.assert_called_once_with([dummy_info])

    # Empty result from fallback
    with (
        patch("src.api.get_available_providers", return_value=["groq"]),
        patch("src.api.execute_ai_batch_with_failover", return_value=[]),
    ):
        res = api.gemini_api_call(dummy_info)
        assert res == [False, None, None, None, None]


# ==============================================================================
# 4. ConfigManager Validation and Property Tests
# ==============================================================================


def test_config_cloud_ai_properties(tmp_path):
    ini_file = tmp_path / "cloud_config.ini"
    cm = ConfigManager(custom_path=str(ini_file))

    # Test Groq key
    assert cm.GROQ_API_KEY is None
    cm.GROQ_API_KEY = "gsk_12345"
    assert cm.GROQ_API_KEY == "gsk_12345"
    cm.GROQ_API_KEY = None
    assert cm.GROQ_API_KEY is None

    # Test OpenRouter key
    assert cm.OPENROUTER_API_KEY is None
    cm.OPENROUTER_API_KEY = "sk-or-12345"
    assert cm.OPENROUTER_API_KEY == "sk-or-12345"
    cm.OPENROUTER_API_KEY = None
    assert cm.OPENROUTER_API_KEY is None

    # Test Cloudflare Token & Account ID
    assert cm.CLOUDFLARE_API_TOKEN is None
    assert cm.CLOUDFLARE_ACCOUNT_ID is None
    cm.CLOUDFLARE_API_TOKEN = "cf_token_val"
    cm.CLOUDFLARE_ACCOUNT_ID = "cf_acc_val"
    assert cm.CLOUDFLARE_API_TOKEN == "cf_token_val"
    assert cm.CLOUDFLARE_ACCOUNT_ID == "cf_acc_val"
    cm.CLOUDFLARE_API_TOKEN = None
    cm.CLOUDFLARE_ACCOUNT_ID = None
    assert cm.CLOUDFLARE_API_TOKEN is None
    assert cm.CLOUDFLARE_ACCOUNT_ID is None

    # Test AI Provider
    assert cm.AI_PROVIDER == "auto"
    cm.AI_PROVIDER = "groq"
    assert cm.AI_PROVIDER == "groq"
    cm.AI_PROVIDER = "openrouter"
    assert cm.AI_PROVIDER == "openrouter"
    cm.AI_PROVIDER = "cloudflare"
    assert cm.AI_PROVIDER == "cloudflare"
    cm.AI_PROVIDER = "gemini"
    assert cm.AI_PROVIDER == "gemini"
    with pytest.raises(ValueError, match="AI provider must be one of"):
        cm.set("options.ai_provider", "invalid_llm")

    # Test Confidence Thresholds
    assert cm.TMDB_MIN_CONFIDENCE == 0.75
    assert cm.AI_MIN_CONFIDENCE == 0.70

    cm.TMDB_MIN_CONFIDENCE = 0.80
    assert cm.TMDB_MIN_CONFIDENCE == 0.80
    cm.AI_MIN_CONFIDENCE = 0.65
    assert cm.AI_MIN_CONFIDENCE == 0.65

    # Out of range / non-float
    with pytest.raises(ValueError, match="must be a float between 0.0 and 1.0"):
        cm.set("options.tmdb_min_confidence", "1.5")
    with pytest.raises(ValueError, match="must be a float between 0.0 and 1.0"):
        cm.set("options.ai_min_confidence", "-0.1")
    with pytest.raises(ValueError, match="must be a float between 0.0 and 1.0"):
        cm.set("options.tmdb_min_confidence", "not_a_number")

    # Fallback to defaults when value is invalid in parser
    with patch.object(cm, "get", return_value="invalid_str"):
        assert cm.TMDB_MIN_CONFIDENCE == 0.75
        assert cm.AI_MIN_CONFIDENCE == 0.70


# ==============================================================================
# 5. UI and CLI Integration Tests
# ==============================================================================


def test_ui_provider_flag_and_validation(monkeypatch):
    import sys

    # 1. Flag --provider sets config.AI_PROVIDER
    monkeypatch.setattr(sys, "argv", ["main.py", "--provider", "groq", "-a"])
    monkeypatch.setattr(ui, "GEMINI_API_KEY", None)
    with patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value="gsk_valid"):
        args = ui.parse_arguments()
        assert args.provider == "groq"
        assert config.AI_PROVIDER == "groq"

    # 2. Flag --provider requested but credentials not configured
    monkeypatch.setattr(sys, "argv", ["main.py", "--provider", "cloudflare", "-a"])
    with (
        patch.object(ConfigManager, "CLOUDFLARE_API_TOKEN", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value="gsk_valid"),
    ):
        with pytest.raises(SystemExit):
            ui.parse_arguments()


# ==============================================================================
# 6. End-to-End Batching and Probability Scorer in utils.py
# ==============================================================================


def test_get_corrected_media_filenames_ai_batching(monkeypatch):
    monkeypatch.setattr(ui, "AI_FALLBACK_ENABLED", True)
    monkeypatch.setattr(ui, "LEARN_ENABLED", False)

    # 3 files:
    # File 1: High confidence TMDB match -> No AI needed
    # File 2: Movie, low TMDB confidence -> AI fallback needed
    # File 3: TV show, low TMDB confidence -> AI fallback needed
    messy_df = pd.DataFrame(
        [
            {
                "File": "HighConf.2020.mkv",
                "Path": "/dl/HighConf.2020.mkv",
                "Media": "movie",
                "Parse": ["High Conf", "2020", None, None],
                "Clean": ["High Conf", "2020", None, None],
            },
            {
                "File": "Obfuscated.Movie.mkv",
                "Path": "/dl/Obfuscated.Movie.mkv",
                "Media": "movie",
                "Parse": ["Obfuscated", None, None, None],
                "Clean": ["Obfuscated", None, None, None],
            },
            {
                "File": "Obfuscated.Series.S01E01.mkv",
                "Path": "/dl/Obfuscated.Series.S01E01.mkv",
                "Media": "tv",
                "Parse": ["Obfuscated Series", None, 1, 1, None, None],
                "Clean": ["Obfuscated Series", None, None, None],
            },
        ]
    )
    clean_df = pd.DataFrame(columns=["Original", "Corrected", "Path", "Media", "Season", "Episode"])

    def fake_api_call(name, year, lang, media_type):
        if name == "High Conf":
            return [True, "High Conf", "2020", "en"]
        elif "Obfuscated" in name:
            # Low confidence match returned
            return [True, "Unrelated Name", "2000", "en"]
        return [False, None, None, None]

    ai_batch_returns = [[True, "Cleaned AI Movie", "2022", "en", []], [True, "Cleaned AI Show", None, "en", []]]

    with (
        patch("src.api.api_call", side_effect=fake_api_call),
        patch("src.api.execute_ai_batch_with_failover", return_value=ai_batch_returns) as mock_batch_ai,
    ):
        result_df = utils.get_corrected_media_filenames(messy_df, clean_df)
        assert len(result_df) == 3
        # Ensure batch AI was called exactly ONCE for the two obfuscated files
        mock_batch_ai.assert_called_once()
        assert len(mock_batch_ai.call_args[0][0]) == 2

        corrected_names = result_df["Corrected"].tolist()
        assert "High Conf (2020)" in corrected_names
        assert "Cleaned AI Movie (2022)" in corrected_names
        assert "Cleaned AI Show - S01E01" in corrected_names


def test_failover_through_openrouter_and_cloudflare():
    dummy_items = [
        {"File": "Test.mkv", "Folder": "dl", "Path": "/dl/Test.mkv", "Clean": "Test", "Parse": "Test", "Media": "movie"}
    ]
    mock_resp = BatchMediaResponse(
        items=[
            ParsedMediaItem(file_id=999, title="CF Title", year="2024", original_language="en", confidence_score=0.99)
        ]
    )

    # 1. OpenRouter provider in execute_ai_batch_with_failover
    with (
        patch("src.api.get_prioritized_providers", return_value=["openrouter"]),
        patch("src.api.call_openrouter_batch", return_value=mock_resp) as mock_or,
    ):
        res = api.execute_ai_batch_with_failover(dummy_items)
        assert res[0][1] == "CF Title"
        mock_or.assert_called_once()

    # 2. Cloudflare provider in execute_ai_batch_with_failover, also testing sequential indexing fallback (file_id 999 != 0)
    with (
        patch("src.api.get_prioritized_providers", return_value=["cloudflare"]),
        patch("src.api.call_cloudflare_batch", return_value=mock_resp) as mock_cf,
    ):
        res = api.execute_ai_batch_with_failover(dummy_items)
        assert res[0][1] == "CF Title"
        mock_cf.assert_called_once()


def test_ui_openrouter_and_cloudflare_keys(monkeypatch):
    import sys

    monkeypatch.setattr(ui, "GEMINI_API_KEY", None)

    # 1. OpenRouter key allows -a without Gemini
    monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
    with (
        patch.object(ConfigManager, "GEMINI_API_KEY", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "OPENROUTER_API_KEY", new_callable=PropertyMock, return_value="sk-or-valid"),
    ):
        ui.parse_arguments()
        assert ui.AI_FALLBACK_ENABLED is True

    # 2. Cloudflare credentials allow -i without Gemini
    with (
        patch.object(ConfigManager, "GEMINI_API_KEY", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "OPENROUTER_API_KEY", new_callable=PropertyMock, return_value=None),
        patch.object(ConfigManager, "CLOUDFLARE_API_TOKEN", new_callable=PropertyMock, return_value="token"),
        patch.object(ConfigManager, "CLOUDFLARE_ACCOUNT_ID", new_callable=PropertyMock, return_value="acc_id"),
    ):
        ui.parse_arguments()
        assert ui.AI_FALLBACK_ENABLED is True


def test_utils_low_confidence_fallbacks(monkeypatch):
    monkeypatch.setattr(ui, "AI_FALLBACK_ENABLED", True)
    monkeypatch.setattr(utils, "RESOLUTION", False)
    monkeypatch.setattr(utils, "QUALITY", False)

    fake_movie = {
        "File": "Uncertain.Movie.2020.mkv",
        "Path": "/dl/Uncertain.Movie.2020.mkv",
        "Media": "movie",
        "Parse": ["Uncertain Movie", "2020", None, None],
        "Clean": ["Uncertain Clean", "2020", None, None],
    }

    # Movie: Parse is low confidence, Clean is high confidence
    with patch("src.api.api_call") as mock_api:
        mock_api.side_effect = [
            [True, "Totally Unrelated", "2000", "en"],  # Parse TMDB -> low confidence
            [True, "Uncertain Clean", "2020", "en"],  # Clean TMDB -> high confidence
        ]
        res = utils.correct_movie_filename(fake_movie)
        assert res == "Uncertain Clean (2020)"

    # Movie: Parse and Clean both low confidence, AI fails -> fallback to best initial match
    with (
        patch("src.api.api_call") as mock_api,
        patch("src.api.gemini_api_call", return_value=[False, None, None, None, []]),
    ):
        mock_api.side_effect = [
            [True, "Initial Best Match", "2020", "en"],  # Parse
            [True, "Clean Mismatch", "1990", "en"],  # Clean -> low confidence
        ]
        res = utils.correct_movie_filename(fake_movie)
        assert res == "Initial Best Match (2020)"

    fake_tv = {
        "File": "Uncertain.Show.S01E01.mkv",
        "Path": "/dl/Uncertain.Show.S01E01.mkv",
        "Media": "tv",
        "Parse": ["Uncertain Show", None, 1, 1, None, None],
        "Clean": ["Uncertain Clean Show", None, None, None],
    }

    # TV: Parse is low confidence, Clean is high confidence
    with patch("src.api.api_call") as mock_api:
        mock_api.side_effect = [
            [True, "Random Show", None, "en"],  # Parse TMDB -> low confidence
            [True, "Uncertain Clean Show", None, "en"],  # Clean TMDB -> high confidence
        ]
        res, s, e = utils.correct_tv_show_filename(fake_tv)
        assert res == "Uncertain Clean Show - S01E01"

    # TV: Parse and Clean both low confidence, AI fails -> fallback to best initial match
    with (
        patch("src.api.api_call") as mock_api,
        patch("src.api.gemini_api_call", return_value=[False, None, None, None, []]),
    ):
        mock_api.side_effect = [
            [True, "Initial TV Match", None, "en"],  # Parse
            [True, "Clean TV Mismatch", None, "en"],  # Clean -> low confidence
        ]
        res, s, e = utils.correct_tv_show_filename(fake_tv)
        assert res == "Initial TV Match - S01E01"

    # get_corrected_media_filenames with unknown media type
    unknown_df = pd.DataFrame(
        [{"File": "ignored.txt", "Path": "/dl/ignored.txt", "Media": "unknown", "Parse": None, "Clean": None}]
    )
    clean_df = pd.DataFrame(columns=["Original", "Corrected", "Path", "Media", "Season", "Episode"])
    with patch("src.ui.print_log"):
        res_df = utils.get_corrected_media_filenames(unknown_df, clean_df)
        assert res_df.empty
