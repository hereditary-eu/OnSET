from pydantic import BaseModel, Field
from enum import Enum


class SelectionDistribution(str, Enum):
    INSTANCES = "instances"
    UNIFORM = "uniform"


class EvalConfig(BaseModel):
    model_id: str = Field(
        "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
    )  # NousResearch/Hermes-3-Llama-3.1-8B-GGUF or NousResearch/Hermes-3-Llama-3.2-3B-GGUF
    conn_str: str = "postgresql+psycopg://postgres:postgres@localhost:5434/onset"  # postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot for secondary
    sparql_endpoint: str = Field("http://localhost:7012")
    name: str = "DBpedia"  # DBpedia or OMA
    selection_distribution: SelectionDistribution = SelectionDistribution.INSTANCES


DBPEDIA_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        name="DBpedia small",
    ),
]
OMA_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA small",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]

UNIPROT_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7014",
        name="UniProt",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7014",
        name="UniProt small",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]

BTO_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-bto",
        sparql_endpoint="http://localhost:7015",
        name="BTO",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-bto",
        sparql_endpoint="http://localhost:7015",
        name="BTO small",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]
DNB_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-dnb",
        sparql_endpoint="http://localhost:7035",
        name="DNB",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-dnb",
        sparql_endpoint="http://localhost:7035",
        name="DNB small",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]