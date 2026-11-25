"""The evaluation datasets of the ontology builder: which builder (``builders`` in
backend/config.json) to run, the documents the KG is built from for scoring, the reference
ontology and the gold annotations.

- ``enron``: schema only (no instance gold), a random sample of the sent mails,
- ``gutbrainie``: schema against the challenge's labels, instances against the dev set's
  entity and mention-level relation annotations (``--gutbrainie_split gold`` for train gold),
- ``llms4ol-<domain>``: Text2Onto term/type lists of the held-out ``test`` split
  (prepare_llms4ol.py), the ``train`` split being the builder's annotated examples.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from builder.corpus import Corpus, Document
from eval_config import CONFIG_FILE, BuilderConfig
from onto_eval import Mentions, Schema, load_reference
from builder.disambiguate import normalize

ROOT = Path(__file__).resolve().parents[2]
TEXT_SETS = ROOT / "data/text-sets"
LLMS4OL = TEXT_SETS / "llms4ol-2025"
LLMS4OL_DOMAINS = ("ecology", "engineering", "scholarly")


@dataclass
class Dataset:
    name: str
    builder: str
    # what the scripted user asks for (the "guided" prompt; the "blind" one omits it)
    task: str
    reference: str | None = None
    # documents the evaluated KG is built from (None: the builder's own corpus)
    documents: Callable[[BuilderConfig, int | None, int], list[Document]] | None = None
    # per-document gold mentions in reference class/link ids
    gold: Callable[[Schema | None], Mentions] | None = None
    # LLMs4OL: domain of the Text2Onto lists
    llms4ol: str | None = None
    extra: dict = field(default_factory=dict)

    def builder_config(self) -> BuilderConfig:
        return CONFIG_FILE.builder(self.builder)

    def reference_schema(self) -> Schema | None:
        return load_reference(self.reference) if self.reference else None


def _sample(docs: list[Document], n: int | None, seed: int) -> list[Document]:
    if n is None or n >= len(docs):
        return docs
    return random.Random(seed).sample(docs, n)


def _builder_docs(config: BuilderConfig, n: int | None, seed: int) -> list[Document]:
    """A random sample of the builder's corpus (the builder loads in path order, so its
    own ``max_documents`` would only see the first mailboxes)."""
    return _sample(Corpus.load(config.text_set).documents, n, seed)


# --- GutBrainIE ---

GUTBRAINIE = TEXT_SETS / "gutbrainie"
GUTBRAINIE_SPLITS = {
    "dev": ("Articles/json_format/articles_dev.json", "Annotations/Dev/json_format/dev.json"),
    "gold": ("Articles/json_format/articles_train_gold.json", "Annotations/Train/gold_quality/json_format/train_gold.json"),
}


def _gutbrainie_docs(split: str):
    def load(config: BuilderConfig, n: int | None, seed: int) -> list[Document]:
        text_set = config.text_set.model_copy(update={"path": str(GUTBRAINIE / GUTBRAINIE_SPLITS[split][0]), "glob": None})
        return _sample(Corpus.load(text_set).documents, n, seed)
    return load


def _gutbrainie_gold(split: str):
    def load(ref: Schema | None) -> Mentions:
        """Entities (span, class) and mention-level relations (subject, predicate, object) per
        PMID, labels and predicates mapped to the reference's class/link ids by their label."""
        classes = {c.label.lower(): c.id for c in ref.classes} if ref else {}
        links = {l.label.lower(): l.id for l in ref.links} if ref else {}
        data = json.loads((GUTBRAINIE / GUTBRAINIE_SPLITS[split][1]).read_text())
        gold = Mentions()
        for pmid, article in data.items():
            for e in article.get("entities", []):
                gold.entities[pmid].add((normalize(e["text_span"]), classes.get(e["label"].lower(), e["label"])))
            for r in article.get("mention_level_relations", []):
                gold.relations[pmid].add((normalize(r["subject_text_span"]), links.get(r["predicate"].lower(), r["predicate"]),
                                          normalize(r["object_text_span"])))
        return gold
    return load


# --- LLMs4OL ---


def llms4ol_split(domain: str, split: str) -> Path:
    return LLMS4OL / domain / split


def llms4ol_gold_lists(domain: str, split: str = "test") -> dict[str, list[str]]:
    """The Text2Onto gold lists of a split: ``terms`` (A1) and ``types`` (A2)."""
    d = llms4ol_split(domain, split)
    return {k: [x for x in (d / f"{k}.txt").read_text().split("\n") if x] for k in ("terms", "types")}


def _llms4ol_gold(domain: str):
    def load(ref: Schema | None) -> Mentions:
        """Per-document types and terms as untyped mentions (class "type"/"term")."""
        gold = Mentions()
        for doc, ann in json.loads((llms4ol_split(domain, "test") / "gold.json").read_text()).items():
            gold.entities[doc].update((normalize(t), "type") for t in ann["types"])
            gold.entities[doc].update((normalize(t["term"]), "term") for t in ann["terms"])
        return gold
    return load


TASKS = {
    "enron": "The documents are e-mails sent by employees of Enron. Model the people, organisations, "
             "business activities and communication that the e-mails talk about, so the KG supports "
             "questions about who works with whom, on what, and when.",
    "gutbrainie": "The documents are PubMed abstracts on the gut-brain axis. Model the biomedical entities "
                  "they mention (e.g. microbes, chemicals, diseases, anatomy, interventions, techniques) and the "
                  "relations between them that the abstracts state, as a curator annotating them would.",
    "llms4ol": "This is the LLMs4OL Text2Onto task for the {domain} domain: from every document extract the "
               "ontological types (general concepts/classes the text mentions, as lowercase noun phrases written "
               "as in the text) and the terms (named individuals) together with their types. Look at the "
               "annotated examples first to see what counts as a type and a term, and design the ontology "
               "(and extraction examples) so the extraction model reproduces that annotation.",
}


def datasets(gutbrainie_split: str = "dev") -> dict[str, Dataset]:
    out = {
        "enron": Dataset("enron", "enron", TASKS["enron"], reference="enron", documents=_builder_docs),
        "gutbrainie": Dataset("gutbrainie", "gutbrainie", TASKS["gutbrainie"], reference="gutbrainie",
                              documents=_gutbrainie_docs(gutbrainie_split), gold=_gutbrainie_gold(gutbrainie_split)),
    }
    for domain in LLMS4OL_DOMAINS:
        out[f"llms4ol-{domain}"] = Dataset(
            f"llms4ol-{domain}", f"llms4ol-{domain}", TASKS["llms4ol"].format(domain=domain),
            gold=_llms4ol_gold(domain), llms4ol=domain,
        )
    return out


DATASETS = datasets()
