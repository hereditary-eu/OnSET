"""OpenAPI schemas compared to committed snapshots (tests/snapshots/).

The frontend client (frontend/src/api/client.ts) is generated from the
configuration-scoped schema, so any change here needs `npm run generate-client`.
After an intended change, refresh the snapshots with
``ONSET_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_openapi.py``.
"""

import json
import os
import sys

import pytest

from conftest import TESTS_DIR

SNAPSHOTS = TESTS_DIR / "snapshots"


def dump(schema: dict) -> str:
    return json.dumps(schema, indent=1, sort_keys=True) + "\n"


@pytest.mark.parametrize(
    "snapshot, attribute",
    [("openapi_app.json", "app"), ("openapi_config_app.json", "config_app")],
)
def test_openapi_snapshot(app, snapshot, attribute):
    # api/__init__.py star-imports app.py, so the module is only in sys.modules
    schema = getattr(sys.modules["api.app"], attribute).openapi()
    path = SNAPSHOTS / snapshot
    if os.getenv("ONSET_UPDATE_SNAPSHOTS"):
        path.write_text(dump(schema))
    assert json.loads(path.read_text()) == schema, (
        f"{attribute} OpenAPI schema changed, see {__name__} for how to update {snapshot}"
    )


def test_agent_websocket_not_in_schema():
    # WebSocket routes are not part of OpenAPI, the protocol is in agent/protocol.py
    schema = json.loads((SNAPSHOTS / "openapi_config_app.json").read_text())
    assert not any("agent" in path for path in schema["paths"])
