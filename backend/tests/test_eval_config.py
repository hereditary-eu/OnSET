"""eval_config.py: config file loading, env interpolation and resolution."""

import json

import pytest
from pydantic import ValidationError

import eval_config
from eval_config import (
    AgentConfig,
    EvalConfig,
    OnsetConfigFile,
    ProgressiveConfig,
    SelectionDistribution,
    _interpolate_env,
    load_config_file,
)


def write_config(tmp_path, raw, name="config.json"):
    path = tmp_path / name
    path.write_text(json.dumps(raw))
    return path


def test_interpolate_env(monkeypatch):
    monkeypatch.setenv("ONSET_TEST_HOST", "db")
    monkeypatch.delenv("ONSET_TEST_UNSET", raising=False)
    raw = {
        "a": "postgres://${ONSET_TEST_HOST}:5434/${ONSET_TEST_UNSET:-onset}",
        "b": ["${ONSET_TEST_HOST:-x}", 1, None],
        "c": {"d": "${ONSET_TEST_UNSET:-}"},
        "e": "$NOT_INTERPOLATED and ${lower_case_ok:-y}",
    }
    assert _interpolate_env(raw) == {
        "a": "postgres://db:5434/onset",
        "b": ["db", 1, None],
        "c": {"d": ""},
        "e": "$NOT_INTERPOLATED and y",
    }


def test_interpolate_env_missing_variable(monkeypatch):
    monkeypatch.delenv("ONSET_TEST_UNSET", raising=False)
    with pytest.raises(KeyError, match="ONSET_TEST_UNSET"):
        _interpolate_env("${ONSET_TEST_UNSET}")


def test_resolution_order(tmp_path):
    config = load_config_file(
        write_config(
            tmp_path,
            {
                "default": "kg",
                "defaults": {
                    "model_id": "default/model",
                    "conn_str": "pg://default",
                    "name": "Default",
                },
                "configs": {
                    "kg": {
                        "name": "KG",
                        "conn_str": "pg://kg",
                        "variants": [
                            {"name": "KG variant", "model_id": "variant/model"},
                            {"name": "KG other"},
                        ],
                    },
                    "plain": {},
                },
            },
        )
    )
    variant, other, base = config.resolve("kg")
    # defaults <- config <- variant
    assert (variant.name, variant.model_id, variant.conn_str) == (
        "KG variant",
        "variant/model",
        "pg://kg",
    )
    assert (other.name, other.model_id) == ("KG other", "default/model")
    assert (base.name, base.model_id, base.conn_str) == (
        "KG",
        "default/model",
        "pg://kg",
    )
    assert config.base("kg") == base
    # only defaults (and the EvalConfig defaults)
    plain = config.base("plain")
    assert (plain.name, plain.sparql_endpoint) == ("Default", "http://localhost:7012")
    assert config.keys() == ["kg", "plain"]


def test_load_is_cached_per_path(tmp_path):
    path = write_config(tmp_path, {"default": "a", "configs": {"a": {}}})
    assert load_config_file(path) is load_config_file(path)


def test_env_path(tmp_path, monkeypatch):
    path = write_config(
        tmp_path, {"default": "a", "configs": {"a": {"name": "From env"}}}, "env.json"
    )
    monkeypatch.setenv(eval_config.CONFIG_PATH_ENV, str(path))
    # the path-less call is cached as well
    load_config_file.cache_clear()
    try:
        assert load_config_file().base("a").name == "From env"
    finally:
        load_config_file.cache_clear()


@pytest.mark.parametrize(
    "raw",
    [
        {"default": "missing", "configs": {"a": {}}},
        {"default": "a", "configs": {}},
        {"configs": {"a": {}}},
    ],
)
def test_invalid_config_files(raw):
    with pytest.raises(ValidationError):
        OnsetConfigFile(**raw)


def test_eval_config_fields():
    config = EvalConfig(
        ontology_extension=["@prefix a: <urn:a#> .", "a:x a a:Y ."],
        selection_distribution="uniform",
        multimodal_config={"encoding_model": "clip"},
    )
    assert config.ontology_extension == "@prefix a: <urn:a#> .\na:x a a:Y ."
    assert config.selection_distribution == SelectionDistribution.UNIFORM
    assert config.multimodal_config.encoding_model == "clip"
    assert config.multimodal_config.image_properties == ["dbo:thumbnail"]
    assert EvalConfig().multimodal_config is None


def test_agent_config_defaults():
    agent = EvalConfig().agent
    assert agent == AgentConfig()
    assert (agent.base_url, agent.api_key, agent.model) == (
        "http://localhost:8998/v1",
        "none",
        None,
    )
    assert (agent.stream, agent.max_steps, agent.retrieve_k, agent.temperature) == (
        True,
        12,
        5,
        None,
    )
    # an empty (interpolated) model id means "first served model"
    assert AgentConfig(model="").model is None
    assert AgentConfig(model="m").model == "m"


def test_progressive_config_defaults():
    progressive = EvalConfig().progressive
    assert progressive == ProgressiveConfig()
    assert (
        progressive.timeout,
        progressive.parallelism,
        progressive.server_timeout,
    ) == (10.0, 4, True)
    # every candidate is counted unless a sample size is configured
    assert (progressive.default_sample_size, progressive.count_limit) == (
        None,
        1_000_000,
    )
    assert (progressive.constraint_sample_size, progressive.categorical_samples) == (
        None,
        None,
    )
    assert (
        progressive.child_sample_size,
        progressive.child_constraint_sample_size,
    ) == (None, None)
    # an empty interpolated size (${VAR:-}) is None, a number samples that many
    assert (
        ProgressiveConfig(
            default_sample_size="", categorical_samples=" "
        ).default_sample_size
        is None
    )
    assert (
        ProgressiveConfig(
            default_sample_size="12", child_constraint_sample_size="0"
        ).default_sample_size
        == 12
    )
    with pytest.raises(ValidationError):
        ProgressiveConfig(default_sample_size=0)
    # interpolated values are strings
    parsed = ProgressiveConfig(timeout="2.5", parallelism="8", server_timeout="false")
    assert (parsed.timeout, parsed.parallelism, parsed.server_timeout) == (
        2.5,
        8,
        False,
    )
    with pytest.raises(ValidationError):
        ProgressiveConfig(parallelism=0)


def test_nested_objects_are_merged(tmp_path, monkeypatch):
    monkeypatch.setenv("ONSET_TEST_TIMEOUT", "3")
    config = load_config_file(
        write_config(
            tmp_path,
            {
                "default": "kg",
                "defaults": {
                    "progressive": {
                        "timeout": "${ONSET_TEST_TIMEOUT:-10}",
                        "child_sample_size": 64,
                    },
                    "agent": {"base_url": "http://default/v1", "max_steps": 3},
                },
                "configs": {
                    "kg": {
                        "progressive": {"child_sample_size": 32},
                        "variants": [
                            {"name": "KG variant", "progressive": {"count_limit": 5}}
                        ],
                    },
                    "plain": {},
                },
            },
        )
    )
    variant, base = config.resolve("kg")
    # defaults <- config <- variant, field by field
    assert (
        base.progressive.timeout,
        base.progressive.child_sample_size,
        base.progressive.count_limit,
    ) == (3, 32, 1_000_000)
    assert (
        variant.progressive.timeout,
        variant.progressive.child_sample_size,
        variant.progressive.count_limit,
    ) == (3, 32, 5)
    assert config.base("plain").progressive.child_sample_size == 64
    assert (base.agent.base_url, base.agent.max_steps) == ("http://default/v1", 3)


def test_test_config_file_is_loaded():
    # tests/conftest.py points ONSET_CONFIG at tests/data/config.json
    assert eval_config.CONFIG_FILE.keys() == ["dbpedia", "oma"]
    assert eval_config.CONFIG_FILE.default == "dbpedia"
    assert [c.name for c in eval_config.ALL_CONFIG_MAP["dbpedia"]] == [
        "DBpedia Variant",
        "DBpedia",
    ]
    assert eval_config.get_config().name == "DBpedia"
    assert eval_config.get_config("dbpedia", 0).model_id == "test/Variant-GGUF"
    assert (
        eval_config.get_configs("oma")[-1].selection_distribution
        == SelectionDistribution.UNIFORM
    )
    dbpedia = eval_config.get_config("dbpedia")
    assert dbpedia.sparql_endpoint == "http://sparql.invalid:7012"
    assert (
        dbpedia.agent.base_url == "http://llm.invalid/v1"
        and dbpedia.agent.model is None
    )
    assert "thumbnail_embedding" in dbpedia.ontology_extension
    # progressive: defaults (with an interpolated timeout) <- dbpedia
    assert (dbpedia.progressive.timeout, dbpedia.progressive.default_sample_size) == (
        5,
        32,
    )
    assert (
        dbpedia.progressive.child_sample_size == 4
        and eval_config.get_config("oma").progressive.child_sample_size == 8
    )


def test_repository_config_is_valid(monkeypatch):
    """backend/config.json resolves with only the fallbacks of its ${VAR:-...}."""
    for name in [
        "ONSET_DEFAULT_CONFIG",
        "ONSET_DB_HOST",
        "ONSET_SPARQL_HOST",
        "REDIS_CACHE_URL",
        "LLM_MODEL_ID",
        "LLM_MODEL_QUANT",
        "AGENT_LLM_BASE_URL",
        "AGENT_LLM_API_KEY",
        "AGENT_LLM_MODEL",
        *(
            f"ONSET_PROGRESSIVE_{name.upper()}"
            for name in ProgressiveConfig.model_fields
        ),
    ]:
        monkeypatch.delenv(name, raising=False)
    config = load_config_file(str(eval_config.DEFAULT_CONFIG_PATH))
    assert config.default in config.keys()
    for key in config.keys():
        resolved = config.resolve(key)
        assert resolved[-1].name
        assert all(isinstance(c, EvalConfig) for c in resolved)
        # the fallbacks are the model defaults, except the served sample cap
        assert resolved[-1].progressive == ProgressiveConfig()
