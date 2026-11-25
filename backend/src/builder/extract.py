"""Grammar-constrained extraction of ontology instances from one document.

The model (by default LiquidAI's LFM2-350M-Extract, run by llama.cpp) gets the
ontology as a JSON schema in its system prompt and its output is constrained to
that schema (llama.cpp turns ``response_format.schema`` into a grammar), so
every answer parses and only uses the ontology's classes, fields and links. The
grammar is checked lazily (builder/lazy_grammar.py), which makes extraction
several times faster with the same output. The ontology's extraction examples
(up to ``MAX_EXAMPLES``, after the examples retrieved for the text, see
``BuilderSession.extract_text``) precede the document as earlier user/assistant turns.
"""

import datetime
import json
import logging
import queue
import threading
from contextlib import contextmanager
from typing import Protocol

from builder.ontology import Ontology, example_output, extraction_schema
from eval_config import BuilderConfig

SYSTEM_PROMPT = """Return data as a JSON object with the following schema:
{template}
Extract every matching entity mentioned in the text, using its name as written in the text. Missing data should be omitted."""

# few-shot examples given to the extraction model, and the characters of each example's text
MAX_EXAMPLES = 3
MAX_EXAMPLE_CHARS = 1500

logger = logging.getLogger(__name__)
# llama-cpp-python silences a model's loading by pointing the process's stdout/stderr at
# /dev/null and back, which loses them for good when two threads load at once
_load_lock = threading.Lock()


class Extractor(Protocol):
    def extract(self, onto: Ontology, text: str) -> dict: ...


def template(onto: Ontology) -> dict:
    """The ontology as an example output whose values describe what to fill in
    (the schema format LFM2-Extract is trained on)."""
    out = {}
    for cls in onto.classes:
        item = {
            "name": f"name of the {cls.label or cls.id}"
            + (f" ({cls.description})" if cls.description else "")
        }
        for f in cls.fields:
            item[f.name] = f"{f.type}" + (
                f": {f.description}" if f.description else f": {f.name}"
            ) + (f" (one of: {', '.join(f.values)})" if f.type == "enum" and f.values else "")
        for link in onto.links:
            if link.source == cls.id:
                item[link.id] = [
                    f"name of a {link.target} it {link.label or link.id}"
                    + (f" ({link.description})" if link.description else "")
                ]
        out[cls.id] = [item]
    return out


def extraction_messages(onto: Ontology, text: str) -> list[dict]:
    """The chat of an extraction: the schema template, the ontology's examples as earlier
    turns (their outputs fitted to the current ontology) and the document. Up to ``MAX_EXAMPLES``
    plus ``retrieved_examples`` examples (the retrieved ones come first, ``BuilderSession.extract_text``)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(template=json.dumps(template(onto), indent=1))}]
    for example in onto.examples[:MAX_EXAMPLES + onto.retrieved_examples]:
        messages.append({"role": "user", "content": example.text[:MAX_EXAMPLE_CHARS]})
        messages.append({"role": "assistant", "content": json.dumps(example_output(onto, example.output))})
    messages.append({"role": "user", "content": text})
    return messages


class ModelPool:
    """``size`` llama.cpp models (GGUF ``model_id``/``quant`` from the Hugging Face Hub), each
    loaded on first use: ``instance()`` borrows a free one, waiting if all are busy (a llama.cpp
    context is not thread safe on its own). A pool of size 1 is a lock around one model."""

    def __init__(self, model_id: str, quant: str, n_ctx: int, size: int = 1):
        self.model_id, self.quant, self.n_ctx = model_id, quant, n_ctx
        # free instances, None for one not loaded yet
        self._free: queue.Queue = queue.Queue()
        for _ in range(size):
            self._free.put(None)

    def _load(self):
        from builder.lazy_grammar import LazyGrammarLlama

        with _load_lock:
            return LazyGrammarLlama.from_pretrained(
                self.model_id, filename=self.quant, n_ctx=self.n_ctx, n_gpu_layers=-1, verbose=False,
            )

    @contextmanager
    def instance(self):
        """Borrow a free instance (waiting for one if all are busy)."""
        llm = self._free.get()
        try:
            if llm is None:
                llm = self._load()
            yield llm
        finally:
            self._free.put(llm)


class LlamaExtractor:
    """A pool of ``config.extract_instances`` extraction models shared by all sessions of a
    builder: every extract() call borrows a free instance, so that many threads extract at once."""

    def __init__(self, config: BuilderConfig):
        self.config = config
        self.pool = ModelPool(
            config.extract_model_id, config.extract_model_quant, config.extract_n_ctx, config.extract_instances,
        )

    def extract(self, onto: Ontology, text: str) -> dict:
        schema = extraction_schema(onto)

        with self.pool.instance() as llm:
            start_time = datetime.datetime.now()
            response = llm.create_chat_completion(
                messages=extraction_messages(onto, text),
                response_format={"type": "json_object", "schema": schema},
                temperature=0.0,
                max_tokens=1024,
            )
            end_time = datetime.datetime.now() - start_time
            logger.debug("Extracted in %.2fs: %s", end_time.total_seconds(), response["usage"])
        content = response["choices"][0]["message"]["content"] or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # cut off by max_tokens
            from json_repair import repair_json

            return repair_json(content, return_objects=True) or {}


def merge_extractions(outputs: list[dict]) -> dict:
    """The outputs of several pieces of a document as one (each class' instances concatenated)."""
    merged: dict = {}
    for data in outputs:
        for class_id, items in (data or {}).items():
            if isinstance(items, list):
                merged.setdefault(class_id, []).extend(items)
    return merged
