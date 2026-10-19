"""Configuration loading for OnSET.

All configurations live in a single JSON file (``backend/config.json`` by
default, overridable through the ``ONSET_CONFIG`` environment variable)::

    {
      "default": "dbpedia",
      "defaults": { ...fields shared by every configuration... },
      "configs": {
        "dbpedia": {
          "name": "DBpedia",
          ...fields overriding the defaults...,
          "variants": [ { "name": "DBpedia Mistral", "model_id": "..." } ]
        }
      }
    }

Every configuration resolves to a list of ``EvalConfig`` objects: one per
variant (defaults <- config <- variant) followed by the base configuration
itself, so ``ALL_CONFIG_MAP[key][-1]`` is always the base configuration that
the API serves. String values may reference environment variables as
``${VAR}`` or ``${VAR:-fallback}``.
"""

import json
import os
import re
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SelectionDistribution(str, Enum):
    INSTANCES = "instances"
    UNIFORM = "uniform"


class MultimodalConfig(BaseModel):
    encoding_model: str = "clip-ViT-B-32"
    image_vector_properties: list[str] = ["dbo:thumbnail_embedding"]
    image_properties: list[str] = ["dbo:thumbnail"]
    image_types: list[str] = ["<http://dbpedia.org/ontology/Image>"]


class EvalConfig(BaseModel):
    model_id: str = Field(
        "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
    )  # NousResearch/Hermes-3-Llama-3.1-8B-GGUF or NousResearch/Hermes-3-Llama-3.2-3B-GGUF
    conn_str: str = "postgresql+psycopg://postgres:postgres@localhost:5434/onset"
    sparql_endpoint: str = Field("http://localhost:7012")
    name: str = "DBpedia"
    description: str = ""
    selection_distribution: SelectionDistribution = SelectionDistribution.INSTANCES
    model_quant: str = "*.Q8_0.gguf"
    redis_cache_url: str = "redis://localhost:6379/1"
    ontology_extension: str = ""
    multimodal_config: MultimodalConfig | None = None

    @field_validator("ontology_extension", mode="before")
    @classmethod
    def _join_lines(cls, value: Any) -> Any:
        # Allow multi-line turtle snippets to be written as a list of lines in JSON
        if isinstance(value, list):
            return "\n".join(value)
        return value


CONFIG_PATH_ENV = "ONSET_CONFIG"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate_env(value: Any) -> Any:
    if isinstance(value, str):

        def replace(match: re.Match) -> str:
            name, fallback = match.group(1), match.group(2)
            resolved = os.getenv(name, fallback)
            if resolved is None:
                raise KeyError(
                    f"Environment variable '{name}' referenced in config is not set"
                )
            return resolved

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    return value


class OnsetConfigFile(BaseModel):
    default: str
    defaults: dict[str, Any] = {}
    configs: dict[str, dict[str, Any]]

    @field_validator("configs")
    @classmethod
    def _non_empty(cls, value: dict) -> dict:
        if not value:
            raise ValueError("At least one configuration has to be defined")
        return value

    def model_post_init(self, __context: Any) -> None:
        if self.default not in self.configs:
            raise ValueError(
                f"Default configuration '{self.default}' is not one of {list(self.configs)}"
            )

    def keys(self) -> list[str]:
        return list(self.configs.keys())

    def resolve(self, key: str) -> list[EvalConfig]:
        """All configurations for ``key``: its variants followed by the base config."""
        raw = self.configs[key]
        base = {**self.defaults, **{k: v for k, v in raw.items() if k != "variants"}}
        variants = [EvalConfig(**{**base, **v}) for v in raw.get("variants", [])]
        return variants + [EvalConfig(**base)]

    def base(self, key: str) -> EvalConfig:
        return self.resolve(key)[-1]


@lru_cache
def load_config_file(path: str | os.PathLike | None = None) -> OnsetConfigFile:
    path = Path(path or os.getenv(CONFIG_PATH_ENV) or DEFAULT_CONFIG_PATH)
    with open(path) as f:
        raw = json.load(f)
    return OnsetConfigFile(**_interpolate_env(raw))


def get_configs(key: str) -> list[EvalConfig]:
    return CONFIG_FILE.resolve(key)


def get_config(key: str | None = None, idx: int = -1) -> EvalConfig:
    return CONFIG_FILE.resolve(key or CONFIG_FILE.default)[idx]


CONFIG_FILE = load_config_file()
ALL_CONFIG_MAP: dict[str, list[EvalConfig]] = {
    key: CONFIG_FILE.resolve(key) for key in CONFIG_FILE.keys()
}
