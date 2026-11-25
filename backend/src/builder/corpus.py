"""The text documents of an ontology builder and a snippet search over them.

Documents are loaded once per builder (``Corpus.load``). The search ranks the
sentences of all documents by TF-IDF cosine similarity to the query and returns
only the best sentences (with their document), so the agent and the user see
the relevant snippet instead of whole documents.

``Corpus.load`` picks the corpus class by the text set's format: ``JSONLSet`` reads
one JSON record per line, ``LLMs4OLSet`` (an LLMs4OL Text2Onto split) also has the
gold annotation of each document (``annotation``), which the agent reads as examples
of what to extract (``annotated_examples``).
"""

import email
import email.policy
import json
import random
import re
from dataclasses import dataclass
from collections.abc import Iterator
from functools import cached_property
from itertools import islice
from pathlib import Path

from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer

from eval_config import TextSetConfig

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n\s*\n")



def chunks(text: str, max_chars: int) -> list[str]:
    """``text`` in pieces of whole sentences (the search's split) of at most ``max_chars``
    (a longer sentence is a piece of its own)."""
    out, current = [], ""
    for sentence in (s.strip() for s in _SENTENCE_END.split(text)):
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            out.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    return out + [current] if current else out

@dataclass
class Document:
    id: str
    title: str
    text: str
    # its file, relative to the text set's path (a JSON file's records share it)
    path: str = ""


class Snippet(BaseModel):
    doc_id: str
    title: str
    text: str
    score: float


def _read_mail(path: Path) -> tuple[str, str]:
    """Subject and plain text body of an e-mail file (any other file: name and content)."""
    raw = path.read_bytes()
    message = email.message_from_bytes(raw, policy=email.policy.default)
    if not message.get("Subject") and not message.get("From"):
        return path.name, raw.decode(errors="replace")
    body = message.get_body(preferencelist=("plain",))
    text = body.get_content() if body is not None else ""
    return str(message.get("Subject") or path.name), text


def field_value(record, path: str):
    """The value at a dotted ``path`` (``metadata.title``) of a JSON record, None if missing."""
    for key in path.split("."):
        if not isinstance(record, dict) or key not in record:
            return None
        record = record[key]
    return record


def _records(path: Path, config: TextSetConfig) -> Iterator[tuple]:
    """(key, record) of a JSON file: object keys, list indices or (jsonl) line numbers."""
    if config.format in ("jsonl", "llms4ol"):
        yield from JSONLSet.records(path)
        return
    records = json.loads(path.read_text())
    yield from records.items() if isinstance(records, dict) else enumerate(records)


def _json_documents(
    path: Path, config: TextSetConfig, id_prefix: str = "", rel: str = ""
) -> Iterator[Document]:
    for key, record in _records(path, config):
        values = (field_value(record, f) for f in config.text_fields)
        text = "\n\n".join(str(v) for v in values if v)
        title = field_value(record, config.title_field)
        doc_id = field_value(record, config.id_field) if config.id_field else None
        doc_id = str(doc_id) if doc_id not in (None, "") else f"{id_prefix}{key}"
        yield Document(doc_id, str(title if title is not None else key), text, rel or path.name)


def _iter_documents(config: TextSetConfig) -> Iterator[Document]:
    root = Path(config.path)
    records = config.format != "files"
    if config.format == "llms4ol" and root.is_dir():
        root = root / LLMs4OLSet.DOCUMENTS
    if records and root.is_file():
        yield from _json_documents(root, config)
        return
    pattern = config.glob or {"json": "**/*.json", "files": "**/*"}.get(config.format, "**/*.jsonl")
    for path in sorted(p for p in root.glob(pattern) if p.is_file()):
        rel = str(path.relative_to(root))
        if records:
            # ids are prefixed with the file so equal keys in different files stay apart
            yield from _json_documents(path, config, f"{rel}#", rel)
        else:
            title, text = _read_mail(path)
            yield Document(rel, title, text, rel)


def load_documents(config: TextSetConfig) -> list[Document]:
    return list(islice(_iter_documents(config), config.max_documents))


class Corpus:
    def __init__(self, documents: list[Document]):
        self.documents = documents
        self.by_id = {d.id: d for d in documents}

    @classmethod
    def load(cls, config: TextSetConfig) -> "Corpus":
        """The documents of a text set, as the corpus class of its format."""
        corpus_class = {"jsonl": JSONLSet, "llms4ol": LLMs4OLSet}.get(config.format, Corpus)
        return corpus_class.from_config(config)

    @classmethod
    def from_config(cls, config: TextSetConfig) -> "Corpus":
        return cls(load_documents(config))

    def annotation(self, doc_id: str) -> dict | None:
        """The gold annotation of a document (what should be extracted from it), None if none."""
        return None

    @property
    def annotated(self) -> bool:
        """Whether any document has an annotation."""
        return any(self.annotation(d.id) is not None for d in self.documents)

    def annotated_examples(self, n: int, query: str | None = None, max_chars: int = 1500) -> list[dict]:
        """``n`` annotated documents with their annotation: those most relevant to ``query``
        (``search``), without one a fixed sample."""
        if query:
            ids = dict.fromkeys(s.doc_id for s in self.search(query, 8 * n))
            docs = [self.by_id[i] for i in ids if self.annotation(i) is not None]
        else:
            docs = [d for d in self.documents if self.annotation(d.id) is not None]
            docs = random.Random(0).sample(docs, min(n, len(docs)))
        return [
            {"id": d.id, "title": d.title, "text": d.text[:max_chars], "annotation": self.annotation(d.id)}
            for d in docs[:n]
        ]

    @cached_property
    def _index(self):
        # (document index, sentence) of every non-trivial sentence
        sentences = [
            (i, s.strip())
            for i, doc in enumerate(self.documents)
            for s in _SENTENCE_END.split(doc.text)
            if len(s.strip()) > 20
        ]
        vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True)
        matrix = vectorizer.fit_transform(s for _, s in sentences) if sentences else None
        return sentences, vectorizer, matrix

    def search(self, query: str, k: int = 8) -> list[Snippet]:
        """The ``k`` sentences most similar to ``query``, at most two per document."""
        sentences, vectorizer, matrix = self._index
        if matrix is None:
            return []
        scores = (matrix @ vectorizer.transform([query]).T).toarray().ravel()
        results: list[Snippet] = []
        per_doc: dict[int, int] = {}
        for i in scores.argsort()[::-1]:
            if scores[i] <= 0 or len(results) >= k:
                break
            doc_index, sentence = sentences[i]
            if per_doc.get(doc_index, 0) >= 2:
                continue
            per_doc[doc_index] = per_doc.get(doc_index, 0) + 1
            doc = self.documents[doc_index]
            results.append(
                Snippet(doc_id=doc.id, title=doc.title, text=sentence[:400], score=float(scores[i]))
            )
        return results


class JSONLSet(Corpus):
    """Documents of JSON records, one per line."""

    @staticmethod
    def records(path: Path) -> Iterator[tuple]:
        """(line number, record) of the non-empty lines of a JSONL file."""
        with path.open() as f:
            for number, line in enumerate(f):
                if line.strip():
                    yield number, json.loads(line)


class LLMs4OLSet(JSONLSet):
    """A split of the LLMs4OL Text2Onto task: ``documents.jsonl`` (``{"id", "title", "text"}``)
    and the gold annotation of its documents, ``gold.json`` ``{doc_id: {"types": [...],
    "terms": [{"term": ..., "types": [...]}]}}`` (any JSON value per document is kept as is).

    ``path`` is the split's directory or its documents file (the gold file then lies next to it);
    ``gold`` names another gold file."""

    DOCUMENTS = "documents.jsonl"
    GOLD = "gold.json"

    def __init__(self, documents: list[Document], gold: dict):
        super().__init__(documents)
        self.gold = gold

    @classmethod
    def from_config(cls, config: TextSetConfig) -> "LLMs4OLSet":
        root = Path(config.path)
        gold = Path(config.gold or (root if root.is_dir() else root.parent) / cls.GOLD)
        documents = load_documents(config.model_copy(update={"id_field": config.id_field or "id"}))
        # a split without gold (e.g. the test split) has no annotations; a configured gold file must exist
        return cls(documents, json.loads(gold.read_text()) if config.gold or gold.is_file() else {})

    def annotation(self, doc_id: str) -> dict | None:
        return self.gold.get(doc_id)
