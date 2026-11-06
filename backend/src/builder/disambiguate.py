"""Entity disambiguation of the progressive build: merges extracted instances of a class
that name the same entity ("Enron Corp", "enron corp.", "Enron Corporation").

A ``Disambiguator`` belongs to one build (a session's generation, so a settings change
rebuilds from scratch). ``resolver(text)`` gives ``extraction_triples`` the canonical
instance of every name extracted from a document, following the chain of
``DisambiguationSettings.mode``:

1. ``normalized``: names equal after ``normalize`` (case folding, punctuation and
   whitespace) are one instance,
2. ``levenshtein``: a name within ``max_distance`` edits (and at most ``max_ratio`` of
   the longer name) of a known name of the class is merged into it (rapidfuzz),
3. ``llm_judge``: otherwise the ``judge_candidates`` closest known names of the class by
   char n-gram TF-IDF (cosine at least ``judge_min_similarity``) are put to a small LLM
   (``LlamaJudge``, LFM2.5-350M by default) asking "same entity?"; its answer is
   constrained to yes/no by reading the probability of the yes and no tokens, and a
   name is merged if P(yes) is at least ``judge_threshold``. The probabilities are
   cached per (class, name, name), so a threshold change reuses them.

The first name of an entity is its ``rdfs:label`` (and its IRI slug), every other name
merged into it a ``skos:altLabel``. Extraction threads resolve names concurrently: the
index is guarded by a lock, the judge runs outside it (its model pool serialises the
calls) and a name that another thread added in the meantime wins.
"""

import logging
import math
import re
import threading
import unicodedata
from collections import Counter, OrderedDict, defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal as TLiteral, Protocol

from pydantic import BaseModel
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein
from rdflib import URIRef

from builder.extract import ModelPool
from builder.ontology import OntoClass, Ontology
from eval_config import BuilderConfig, DisambiguationSettings

logger = logging.getLogger(__name__)

MODES = ("off", "normalized", "levenshtein", "llm_judge")
RECENT_MERGES = 100
JUDGMENT_CACHE = 50_000
CONTEXT_CHARS = 160

# (class id, name) -> (IRI, canonical label) of the instance the name refers to
Resolver = Callable[[str, str], tuple[URIRef, str]]


def normalize(name: str) -> str:
    """``"Enron  Corp."`` -> ``"enron corp"``."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = re.sub(r"[\W_]+", " ", text)
    return " ".join(text.split())


def context(text: str, name: str, chars: int = CONTEXT_CHARS) -> str:
    at = text.lower().find(name.lower())
    if at < 0:
        return ""
    start = max(0, at - (chars - len(name)) // 2)
    return " ".join(text[start:start + max(chars, len(name))].split())


class NgramIndex:
    """Incremental char n-gram TF-IDF (char_wb 2-4, sublinear tf, smooth idf, L2), scoring
    only names that share one of the query's rarest n-grams."""

    def __init__(self, ngram_range=(2, 4), max_candidates: int = 2000):
        self.ngram_range = ngram_range
        self.max_candidates = max_candidates
        self.df: Counter = Counter()
        self.postings: dict[str, set[str]] = defaultdict(set)
        self.grams: dict[str, Counter] = {}

    def _grams(self, text: str) -> Counter:
        padded = f" {text} "
        lo, hi = self.ngram_range
        return Counter(padded[i:i + n] for n in range(lo, hi + 1) for i in range(len(padded) - n + 1))

    def __len__(self):
        return len(self.grams)

    def add(self, name: str):
        if name in self.grams:
            return
        grams = self.grams[name] = self._grams(name)
        for g in grams:
            self.df[g] += 1
            self.postings[g].add(name)

    def _vector(self, grams: Counter, n: int) -> dict[str, float]:
        vec = {g: (1 + math.log(tf)) * (math.log((1 + n) / (1 + self.df[g])) + 1) for g, tf in grams.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {g: w / norm for g, w in vec.items()}

    def search(self, name: str, k: int = 1, min_similarity: float = 0.0) -> list[tuple[str, float]]:
        n = len(self.grams)
        if not n:
            return []
        query = self._vector(self._grams(name), n)
        candidates: set[str] = set()
        for g in sorted((g for g in query if self.df[g]), key=lambda g: self.df[g]):
            candidates |= self.postings[g]
            if len(candidates) >= self.max_candidates:
                break
        candidates.discard(name)
        scored = []
        for other in candidates:
            vec = self._vector(self.grams[other], n)
            sim = sum(w * vec.get(g, 0.0) for g, w in query.items())
            if sim >= min_similarity:
                scored.append((other, sim))
        scored.sort(key=lambda s: (-s[1], s[0]))
        return scored[:k]


class Judge(Protocol):
    def p_same(self, cls: OntoClass, a: str, a_context: str, b: str, b_context: str) -> float:
        """The probability that names ``a`` and ``b`` (mentioned in these contexts) are one instance of ``cls``."""
        ...


JUDGE_SYSTEM = "You check whether two names refer to the same real-world entity. Answer with yes or no."
# answer tokens the judge's probability is read from (each must be one token of the model)
YES_TOKENS = ("yes", "Yes", " yes", " Yes")
NO_TOKENS = ("no", "No", " no", " No")


def judge_prompt(cls: OntoClass, a: str, a_context: str, b: str, b_context: str) -> str:
    """The question, as plain as it gets: with LFM2.5-350M, few-shot examples or longer
    instructions made it answer yes to everything."""
    kind = cls.label or cls.id
    lines = [f'{kind} A: "{a}"']
    if a_context:
        lines.append(f'(mentioned in: "...{a_context}...")')
    lines.append(f'{kind} B: "{b}"')
    if b_context:
        lines.append(f'(mentioned in: "...{b_context}...")')
    lines.append(f"Are A and B the same {kind.lower()}? Answer yes or no.")
    return "\n".join(lines)


def answer_probability(logits, yes_ids: list[int], no_ids: list[int]) -> float:
    """P(yes) of an answer constrained to the yes and no tokens, from the first token's logits."""
    import numpy as np

    logits = np.asarray(logits, dtype=np.float64)
    yes, no = logits[yes_ids], logits[no_ids]
    top = max(yes.max(), no.max())
    p_yes, p_no = np.exp(yes - top).sum(), np.exp(no - top).sum()
    return float(p_yes / (p_yes + p_no))


class LlamaJudge:
    """The judge model (``judge_model_id``, LiquidAI's LFM2.5-350M by default) in a pool of
    ``judge_instances`` (one: a model behind a lock), loaded on the first judgment.

    The answer is restricted to yes/no by reading the first token's logits (a logits
    processor, so one forward pass) and normalising over the yes and no tokens: the
    greedy answer of the small model leans to yes, its P(yes) separates far better."""

    def __init__(self, config: BuilderConfig):
        self.pool = ModelPool(config.judge_model_id, config.judge_model_quant, config.judge_n_ctx, config.judge_instances)
        self._ids: tuple[list[int], list[int]] | None = None

    def _answer_ids(self, llm) -> tuple[list[int], list[int]]:
        if self._ids is None:
            def ids(words):
                tokens = [llm.tokenize(w.encode(), add_bos=False, special=False) for w in words]
                return sorted({t[0] for t in tokens if len(t) == 1})

            self._ids = ids(YES_TOKENS), ids(NO_TOKENS)
        return self._ids

    def p_same(self, cls, a, a_context, b, b_context) -> float:
        from llama_cpp import LogitsProcessorList

        first: list = []

        def capture(input_ids, scores):
            if not first:
                first.append(scores.copy())
            return scores

        with self.pool.instance() as llm:
            yes_ids, no_ids = self._answer_ids(llm)
            llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": judge_prompt(cls, a, a_context, b, b_context)},
                ],
                temperature=0.0, max_tokens=1, logits_processor=LogitsProcessorList([capture]),
            )
        return answer_probability(first[0], yes_ids, no_ids)


class Merge(BaseModel):
    class_id: str
    alias: str
    canonical: str
    iri: str
    method: TLiteral["normalized", "levenshtein", "llm_judge"]


@dataclass
class _Entity:
    iri: URIRef
    label: str
    context: str = ""


@dataclass
class _ClassIndex:
    keys: dict[str, _Entity] = field(default_factory=dict)
    names: list[str] = field(default_factory=list)
    iris: set[URIRef] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    tfidf: NgramIndex = field(default_factory=NgramIndex)


class Disambiguator:
    def __init__(self, onto: Ontology, settings: DisambiguationSettings,
                 judge: Callable[[], Judge] | None = None, cache: "OrderedDict | None" = None):
        self.onto = onto
        self.settings = settings
        self._level = MODES.index(settings.mode)
        self._judge = judge
        self._cache = cache if cache is not None else OrderedDict()
        self._classes: dict[str, _ClassIndex] = defaultdict(_ClassIndex)
        self._lock = threading.Lock()
        self.merged = 0
        self.judged = 0
        self.merges: deque[Merge] = deque(maxlen=RECENT_MERGES)

    @property
    def active(self) -> bool:
        return self._level > 0

    def resolver(self, text: str = "") -> Resolver | None:
        if not self.active:
            return None
        return lambda class_id, name: self.resolve(class_id, name, text)

    def register(self, class_id: str, label: str, iri: URIRef, aliases=()):
        key = normalize(label)
        if not self.active or not key:
            return
        with self._lock:
            index = self._classes[class_id]
            entity = index.keys.get(key) or _Entity(iri, label)
            index.iris.add(iri)
            for name in (label, *aliases):
                index.seen.add(name)
                self._add_key(index, normalize(name), entity)

    def _add_key(self, index, key, entity):
        if key and key not in index.keys:
            index.keys[key] = entity
            index.names.append(key)
            if self._level >= MODES.index("llm_judge"):
                index.tfidf.add(key)

    def _new_entity(self, index, class_id, name, text) -> _Entity:
        iri = self.onto.instance(class_id, name)
        n = 2
        while iri in index.iris:
            iri, n = URIRef(f"{self.onto.instance(class_id, name)}-{n}"), n + 1
        index.iris.add(iri)
        return _Entity(iri, name, context(text, name))

    def _close(self, index, key) -> _Entity | None:
        s = self.settings
        for other, distance, _ in process.extract(
            key, index.names, scorer=Levenshtein.distance, score_cutoff=s.max_distance, limit=5,
        ):
            if distance <= s.max_ratio * max(len(key), len(other)):
                return index.keys[other]
        return None

    def _same(self, class_id, name, key, text, other: _Entity) -> bool:
        """Whether the judge's P(same) of ``name`` and ``other`` reaches the threshold; the
        probability is cached per (class, names), from the contexts of its first judgment."""
        cache_key = (class_id, *sorted((key, normalize(other.label))))
        with self._lock:
            p = self._cache.get(cache_key)
            if p is not None:
                self._cache.move_to_end(cache_key)
        if p is None:
            cls = self.onto.get_class(class_id) or OntoClass(id=class_id)
            try:
                p = float(self._judge().p_same(cls, name, context(text, name), other.label, other.context))
            except Exception:
                # not cached: asked again on the next mention
                logger.warning("Disambiguation judge failed on %r / %r", name, other.label, exc_info=True)
                return False
            with self._lock:
                self.judged += 1
                self._cache[cache_key] = p
                while len(self._cache) > JUDGMENT_CACHE:
                    self._cache.popitem(last=False)
        return p >= self.settings.judge_threshold

    def resolve(self, class_id: str, name: str, text: str = "") -> tuple[URIRef, str]:
        key = normalize(name)
        if not self.active or not key:
            return self.onto.instance(class_id, name), name
        method = None
        candidates: list[_Entity] = []
        with self._lock:
            index = self._classes[class_id]
            entity = index.keys.get(key)
            if entity is not None:
                method = "normalized"
            elif self._level >= MODES.index("levenshtein") and (entity := self._close(index, key)) is not None:
                method = "levenshtein"
            elif self._level >= MODES.index("llm_judge") and self._judge is not None:
                for other, _ in index.tfidf.search(key, k=4 * self.settings.judge_candidates,
                                                   min_similarity=self.settings.judge_min_similarity):
                    if index.keys[other] not in candidates:
                        candidates.append(index.keys[other])
                candidates = candidates[: self.settings.judge_candidates]
        if entity is None:
            entity = next((c for c in candidates if self._same(class_id, name, key, text, c)), None)
            method = "llm_judge" if entity is not None else None
        with self._lock:
            index = self._classes[class_id]
            if (raced := index.keys.get(key)) is not None:
                entity, method = raced, "normalized"
            elif entity is None:
                entity = self._new_entity(index, class_id, name, text)
            self._add_key(index, key, entity)
            if name not in index.seen:
                index.seen.add(name)
                if name != entity.label:
                    self.merged += 1
                    self.merges.append(Merge(class_id=class_id, alias=name, canonical=entity.label,
                                             iri=str(entity.iri), method=method))
        return entity.iri, entity.label
