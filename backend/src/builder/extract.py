"""Grammar-constrained extraction of ontology instances from one document.

The model (by default LiquidAI's LFM2-350M-Extract, run by llama.cpp) gets the
ontology as a JSON schema in its system prompt and its output is constrained to
that schema (llama.cpp turns ``response_format.schema`` into a grammar), so
every answer parses and only uses the ontology's classes, fields and links.
"""

import json
import threading
from typing import Protocol

from builder.ontology import Ontology, extraction_schema
from eval_config import BuilderConfig

SYSTEM_PROMPT = """Return data as a JSON object with the following schema:
{template}
Extract every matching entity mentioned in the text, using its name as written in the text. Missing data should be omitted."""


class Extractor(Protocol):
    def extract(self, onto: Ontology, text: str) -> dict: ...


def template(onto: Ontology) -> dict:
    """The ontology as an example output whose values describe what to fill in
    (the schema format LFM2-Extract is trained on)."""
    out = {}
    for cls in onto.classes:
        item = {"name": f"name of the {cls.label or cls.id}" + (f" ({cls.description})" if cls.description else "")}
        for f in cls.fields:
            item[f.name] = f"{f.type}" + (f": {f.description}" if f.description else f": {f.name}")
        for link in onto.links:
            if link.source == cls.id:
                item[link.id] = [f"name of a {link.target} it {link.label or link.id}" + (f" ({link.description})" if link.description else "")]
        out[cls.id] = [item]
    return out


class LlamaExtractor:
    """llama.cpp model, loaded on first use and shared by all sessions of a builder."""

    def __init__(self, config: BuilderConfig):
        self.config = config
        self._llm = None
        # llama.cpp contexts are not thread safe
        self._lock = threading.Lock()

    def _model(self):
        if self._llm is None:
            from llama_cpp import Llama

            self._llm = Llama.from_pretrained(
                self.config.extract_model_id,
                filename=self.config.extract_model_quant,
                n_ctx=self.config.extract_n_ctx,
                n_gpu_layers=-1,
                verbose=False,
            )
        return self._llm

    def extract(self, onto: Ontology, text: str) -> dict:
        schema = extraction_schema(onto)
        with self._lock:
            response = self._model().create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.format(
                        template=json.dumps(template(onto), indent=1))},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object", "schema": schema},
                temperature=0.0,
                max_tokens=1024,
            )
        content = response["choices"][0]["message"]["content"] or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # cut off by max_tokens
            from json_repair import repair_json

            return repair_json(content, return_objects=True) or {}
