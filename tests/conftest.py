import os
import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    # Store originals
    orig_mode = settings.MARKET_DATA_MODE
    orig_twelve = settings.TWELVE_DATA_API_KEY
    orig_gemini = settings.GEMINI_API_KEY
    orig_anthropic = settings.ANTHROPIC_API_KEY

    # Set safe test defaults
    settings.MARKET_DATA_MODE = "simulation"
    settings.TWELVE_DATA_API_KEY = None
    settings.GEMINI_API_KEY = None
    settings.ANTHROPIC_API_KEY = None

    yield

    # Restore originals
    settings.MARKET_DATA_MODE = orig_mode
    settings.TWELVE_DATA_API_KEY = orig_twelve
    settings.GEMINI_API_KEY = orig_gemini
    settings.ANTHROPIC_API_KEY = orig_anthropic
