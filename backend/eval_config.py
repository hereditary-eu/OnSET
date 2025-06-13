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
    model_quant: str = "*.Q8_0.gguf"


DBPEDIA_CONFIGS = [
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        name="DBpedia Mistral",
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        name="DBpedia large",
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
    ),
]
OMA_CONFIGS = [
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA Mistral",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA large",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]

UNIPROT_CONFIGS = [
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7014",
        name="UniProt Mistral",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7014",
        name="UniProt large",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7014",
        name="UniProt",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]

BTO_CONFIGS = [
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-bto",
        sparql_endpoint="http://localhost:7015",
        name="BTO  Mistral",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-bto",
        sparql_endpoint="http://localhost:7015",
        name="BTO large",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-bto",
        sparql_endpoint="http://localhost:7015",
        name="BTO",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]
DNB_CONFIGS = [
    
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-dnb",
        sparql_endpoint="http://localhost:7035",
        name="DNB Mistral",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-dnb",
        sparql_endpoint="http://localhost:7035",
        name="DNB large",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-dnb",
        sparql_endpoint="http://localhost:7035",
        name="DNB",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]
YAGO_CONFIGS = [
    EvalConfig(
        model_id="bartowski/Mistral-Small-Instruct-2409-GGUF",
        model_quant="*-Q6_K.gguf",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-yago",
        sparql_endpoint="http://localhost:9024",
        name="Yago Mistral",
        selection_distribution=SelectionDistribution.INSTANCES,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-yago",
        sparql_endpoint="http://localhost:9024",
        name="Yago 8B",
        selection_distribution=SelectionDistribution.INSTANCES,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-yago",
        sparql_endpoint="http://localhost:9024",
        name="Yago",
        selection_distribution=SelectionDistribution.INSTANCES,
    ),
    
]
GUTBRAINIE_CONFIGS = [
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-gutbrainie",
        sparql_endpoint="http://localhost:9101",
        name="GutBrainIE 8B",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-gutbrainie",
        sparql_endpoint="http://localhost:9101",
        name="GutBrainIE",
        selection_distribution=SelectionDistribution.UNIFORM,
    ),
]
ALL_CONFIGS = (
    DBPEDIA_CONFIGS
    + OMA_CONFIGS
    + UNIPROT_CONFIGS
    + BTO_CONFIGS
    + DNB_CONFIGS
    + YAGO_CONFIGS
)