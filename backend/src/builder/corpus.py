"""The text documents of an ontology builder and a snippet search over them.

Documents are loaded once per builder (``Corpus.load``). The search ranks the
sentences of all documents by TF-IDF cosine similarity to the query and returns
only the best sentences (with their document), so the agent and the user see
the relevant snippet instead of whole documents.
"""

import email
import email.policy
import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer

from eval_config import TextSetConfig

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n\s*\n")


@dataclass
class Document:
    id: str
    title: str
    text: str


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


def load_documents(config: TextSetConfig) -> list[Document]:
    root = Path(config.path)
    limit = config.max_documents
    if config.format == "json":
        records = json.loads(root.read_text())
        items = records.items() if isinstance(records, dict) else enumerate(records)
        docs = []
        for key, record in items:
            text = "\n\n".join(
                str(record[f]) for f in config.text_fields if record.get(f)
            )
            docs.append(Document(str(key), str(record.get(config.title_field, key)), text))
            if limit and len(docs) >= limit:
                break
        return docs
    docs = []
    for path in sorted(p for p in root.glob(config.glob) if p.is_file()):
        title, text = _read_mail(path)
        docs.append(Document(str(path.relative_to(root)), title, text))
        if limit and len(docs) >= limit:
            break
    return docs


class Corpus:
    def __init__(self, documents: list[Document]):
        self.documents = documents
        self.by_id = {d.id: d for d in documents}

    @classmethod
    def load(cls, config: TextSetConfig) -> "Corpus":
        return cls(load_documents(config))

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
