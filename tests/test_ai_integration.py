import os
import pytest
from src import api, config, ui
from src.config import ConfigManager


def get_live_key(provider_name: str) -> str:
    """Helper to retrieve key from module, config, or environment."""
    if provider_name == "groq":
        return getattr(api, "GROQ_API_KEY", None) or getattr(config.config, "GROQ_API_KEY", None) or os.environ.get("GROQ_API_KEY")
    elif provider_name == "openrouter":
        return getattr(api, "OPENROUTER_API_KEY", None) or getattr(config.config, "OPENROUTER_API_KEY", None) or os.environ.get("OPENROUTER_API_KEY")
    elif provider_name == "cloudflare_token":
        return getattr(api, "CLOUDFLARE_API_TOKEN", None) or getattr(config.config, "CLOUDFLARE_API_TOKEN", None) or os.environ.get("CLOUDFLARE_API_TOKEN")
    elif provider_name == "cloudflare_account":
        return getattr(api, "CLOUDFLARE_ACCOUNT_ID", None) or getattr(config.config, "CLOUDFLARE_ACCOUNT_ID", None) or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    elif provider_name == "gemini":
        return getattr(api, "GEMINI_API_KEY", None) or getattr(config.config, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")
    return None


def is_live_api_transient_error(e: Exception) -> bool:
    """Detects rate limits, quota exhaustion, network timeouts or server drops on live API endpoints."""
    err_str = str(e).lower()
    return (
        api.is_quota_or_rate_limit_error(e)
        or "timeout" in err_str
        or "timed out" in err_str
        or "connection" in err_str
        or "502" in err_str
        or "503" in err_str
        or "504" in err_str
    )


# ==============================================================================
# Live Cloud AI Integration Tests (with automatic bypass when limits are reached)
# ==============================================================================

def test_integration_groq_live():
    """Live integration test for Groq Cloud. Gracefully bypasses if key missing or limits reached."""
    key = get_live_key("groq")
    if not key:
        pytest.skip("Groq API key not configured; bypassing live test.")

    test_item = [{
        'File': 'Inception.2010.1080p.BluRay.x264.mkv',
        'Folder': 'Movies',
        'Path': '/movies/Inception.2010.1080p.BluRay.x264.mkv',
        'Clean': 'Inception',
        'Parse': 'Inception',
        'Media': 'movie'
    }]

    try:
        res = api.call_groq_batch(test_item)
        assert len(res.items) >= 1
        item = res.items[0]
        assert item.title is not None
        assert "inception" in item.title.lower()
        assert item.year == "2010"
        assert item.confidence_score >= 0.70
    except Exception as e:
        if is_live_api_transient_error(e):
            pytest.skip(f"Groq live limits or network error: {e}. Gracefully bypassed.")
        raise


def test_integration_openrouter_live():
    """Live integration test for OpenRouter :free models. Gracefully bypasses if key missing or limits reached."""
    key = get_live_key("openrouter")
    if not key:
        pytest.skip("OpenRouter API key not configured; bypassing live test.")

    test_item = [{
        'File': 'Inception.2010.1080p.BluRay.x264.mkv',
        'Folder': 'Movies',
        'Path': '/movies/Inception.2010.1080p.BluRay.x264.mkv',
        'Clean': 'Inception',
        'Parse': 'Inception',
        'Media': 'movie'
    }]

    try:
        res = api.call_openrouter_batch(test_item)
        assert len(res.items) >= 1
        item = res.items[0]
        assert item.title is not None
        assert "inception" in item.title.lower()
        assert item.confidence_score >= 0.60
    except Exception as e:
        if is_live_api_transient_error(e):
            pytest.skip(f"OpenRouter live limits or network error: {e}. Gracefully bypassed.")
        raise


def test_integration_cloudflare_live():
    """Live integration test for Cloudflare Workers AI. Gracefully bypasses if token/account missing or neuron quota reached."""
    token = get_live_key("cloudflare_token")
    acc_id = get_live_key("cloudflare_account")
    if not token or not acc_id:
        pytest.skip("Cloudflare API token or Account ID not configured; bypassing live test.")

    test_item = [{
        'File': 'Inception.2010.1080p.BluRay.x264.mkv',
        'Folder': 'Movies',
        'Path': '/movies/Inception.2010.1080p.BluRay.x264.mkv',
        'Clean': 'Inception',
        'Parse': 'Inception',
        'Media': 'movie'
    }]

    try:
        res = api.call_cloudflare_batch(test_item)
        assert len(res.items) >= 1
        item = res.items[0]
        assert item.title is not None
        assert "inception" in item.title.lower()
    except Exception as e:
        if is_live_api_transient_error(e):
            pytest.skip(f"Cloudflare daily neuron limit or network error: {e}. Gracefully bypassed.")
        raise


def test_integration_gemini_live():
    """Live integration test for Google Gemini. Gracefully bypasses if key missing or limits reached."""
    key = get_live_key("gemini")
    if not key:
        pytest.skip("Gemini API key not configured; bypassing live test.")

    test_item = [{
        'File': 'Inception.2010.1080p.BluRay.x264.mkv',
        'Folder': 'Movies',
        'Path': '/movies/Inception.2010.1080p.BluRay.x264.mkv',
        'Clean': 'Inception',
        'Parse': 'Inception',
        'Media': 'movie'
    }]

    try:
        res = api.call_gemini_batch(test_item)
        assert len(res.items) >= 1
        item = res.items[0]
        assert item.title is not None
        assert "inception" in item.title.lower()
        assert item.year == "2010"
    except Exception as e:
        if is_live_api_transient_error(e):
            pytest.skip(f"Gemini quota/rate limit or network error: {e}. Gracefully bypassed.")
        raise


def test_integration_orchestrator_live_failover_and_bypass():
    """Live integration test for orchestrator failover with bypass across all available live providers."""
    providers = api.get_available_providers()
    if not providers:
        pytest.skip("No cloud AI providers configured; bypassing live orchestrator test.")

    test_item = [{
        'File': 'Interstellar.2014.IMAX.1080p.mkv',
        'Folder': 'Movies',
        'Path': '/movies/Interstellar.2014.IMAX.1080p.mkv',
        'Clean': 'Interstellar',
        'Parse': 'Interstellar',
        'Media': 'movie'
    }]

    results = api.execute_ai_batch_with_failover(test_item)
    assert len(results) == 1
    success, title, year, lang, tags = results[0]
    if success:
        assert "interstellar" in str(title).lower()
        assert year == "2014"
