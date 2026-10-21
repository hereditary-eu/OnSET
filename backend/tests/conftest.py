"""Shared fixtures; the fakes themselves live in tests/fakes.py.

The configuration file is swapped for tests/data/config.json before any
backend module is imported, since eval_config loads it at import time.
"""

import os
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
os.environ["ONSET_CONFIG"] = str(TESTS_DIR / "data" / "config.json")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, str(TESTS_DIR))

import pytest
from fastapi.testclient import TestClient

from fakes import FakeManMan, make_ontology, StubGuidance


@pytest.fixture
def ontology():
    return make_ontology()


@pytest.fixture
def guidance(ontology):
    return StubGuidance(ontology)


@pytest.fixture
def app():
    from api.app import app

    return app


@pytest.fixture
def fake_manman():
    return FakeManMan()


@pytest.fixture
def client(app, fake_manman):
    """TestClient whose /{config_id} routes all use ``fake_manman``."""
    from api.app import config_app
    from api.config import get_manman

    config_app.dependency_overrides[get_manman] = lambda: fake_manman
    try:
        yield TestClient(app)
    finally:
        config_app.dependency_overrides.pop(get_manman, None)


@pytest.fixture
def raw_client(app):
    """TestClient with the real ManMan resolution (only unknown configs are safe)."""
    return TestClient(app)
