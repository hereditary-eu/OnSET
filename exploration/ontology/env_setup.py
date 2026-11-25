"""Import first (scripts and notebooks): makes backend/src and this folder importable and
loads the agent LLM settings (AGENT_LLM_BASE_URL / _API_KEY / _MODEL) from ``.env`` here,
else from ../querying/.env (variables already set win)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
for path in (HERE.parents[1] / "backend/src", HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
for env in (HERE / ".env", HERE.parent / "querying/.env"):
    if env.exists():
        load_dotenv(env, override=False)
        break
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
