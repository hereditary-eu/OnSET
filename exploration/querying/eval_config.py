from pydantic import BaseModel, Field


class EvalConfig(BaseModel):
    model_id: str = Field(
        "NousResearch/Hermes-3-Llama-3.1-8B-GGUF"
    )  # NousResearch/Hermes-3-Llama-3.1-8B-GGUF or NousResearch/Hermes-3-Llama-3.2-3B-GGUF
    conn_str: str = "postgresql+psycopg://postgres:postgres@localhost:5434/onset"  # postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot for secondary
    sparql_endpoint: str = Field("http://localhost:7012")
    name: str = "DBpedia"  # DBpedia or OMA


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
    ),
    EvalConfig(
        model_id="NousResearch/Hermes-3-Llama-3.2-3B-GGUF",
        conn_str="postgresql+psycopg://postgres:postgres@localhost:5434/onset-uniprot",
        sparql_endpoint="http://localhost:7013",
        name="OMA small",
    ),
]
