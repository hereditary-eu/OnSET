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
    return " ".join(text[start : start + max(chars, len(name))].split())


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
        return Counter(
            padded[i : i + n]
            for n in range(lo, hi + 1)
            for i in range(len(padded) - n + 1)
        )

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
        vec = {
            g: (1 + math.log(tf)) * (math.log((1 + n) / (1 + self.df[g])) + 1)
            for g, tf in grams.items()
        }
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {g: w / norm for g, w in vec.items()}

    def search(
        self, name: str, k: int = 1, min_similarity: float = 0.0
    ) -> list[tuple[str, float]]:
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
    def p_same(
        self, cls: OntoClass, a: str, a_context: str, b: str, b_context: str
    ) -> float:
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
        self.pool = ModelPool(
            config.judge_model_id,
            config.judge_model_quant,
            config.judge_n_ctx,
            config.judge_instances,
        )
        self._ids: tuple[list[int], list[int]] | None = None

    def _answer_ids(self, llm) -> tuple[list[int], list[int]]:
        if self._ids is None:

            def ids(words):
                tokens = [
                    llm.tokenize(w.encode(), add_bos=False, special=False)
                    for w in words
                ]
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
                    {
                        "role": "user",
                        "content": judge_prompt(cls, a, a_context, b, b_context),
                    },
                ],
                temperature=0.0,
                max_tokens=1,
                logits_processor=LogitsProcessorList([capture]),
            )
        return answer_probability(first[0], yes_ids, no_ids)


MergeMethod = TLiteral["normalized", "levenshtein", "llm_judge"]


class Merge(BaseModel):
    class_id: str
    alias: str
    canonical: str
    iri: str
    method: MergeMethod


@dataclass
class _Entity:
    """One instance of a class: its IRI, canonical label and the text around its first
    mention (shown to the judge)."""

    iri: URIRef
    label: str
    context: str = ""


@dataclass
class _Match:
    entity: _Entity
    method: MergeMethod


@dataclass
class _ClassIndex:
    """What is known about the instances of one class."""

    # normalized name -> the entity it refers to (several names may share one entity)
    entity_by_key: dict[str, _Entity] = field(default_factory=dict)
    # the normalized names in insertion order, searched for Levenshtein matches
    keys: list[str] = field(default_factory=list)
    # IRIs in use, so a new entity whose slug collides with another gets a suffix
    iris: set[URIRef] = field(default_factory=set)
    # names as extracted that were already resolved, so each merge is recorded once
    seen_names: set[str] = field(default_factory=set)
    # char n-gram TF-IDF over the normalized names, for the judge's candidates
    tfidf: NgramIndex = field(default_factory=NgramIndex)


class Disambiguator:
    def __init__(
        self,
        onto: Ontology,
        settings: DisambiguationSettings,
        judge: Callable[[], Judge] | None = None,
        cache: "OrderedDict | None" = None,
    ):
        self.onto = onto
        self.settings = settings
        self._level = MODES.index(settings.mode)
        self._judge = judge
        # (class id, name, name) -> P(same), shared between the builds of a session
        self._cache = cache if cache is not None else OrderedDict()
        self._classes: dict[str, _ClassIndex] = defaultdict(_ClassIndex)
        self._lock = threading.Lock()
        self.merged = 0
        self.judged = 0
        self.merges: deque[Merge] = deque(maxlen=RECENT_MERGES)

    @property
    def active(self) -> bool:
        return self._level > 0

    def _uses(self, mode: str) -> bool:
        """Whether ``mode`` is part of the configured chain of modes."""
        return self._level >= MODES.index(mode)

    def resolver(self, text: str = "") -> Resolver | None:
        if not self.active:
            return None
        return lambda class_id, name: self.resolve(class_id, name, text)

    def register(self, class_id: str, label: str, iri: URIRef, aliases=()):
        """Adds an existing instance (e.g. from the previous build) with its label and aliases."""
        key = normalize(label)
        if not self.active or not key:
            return
        with self._lock:
            index = self._classes[class_id]
            entity = index.entity_by_key.get(key) or _Entity(iri, label)
            index.iris.add(iri)
            for name in (label, *aliases):
                index.seen_names.add(name)
                self._add_key(index, normalize(name), entity)

    # -- resolving ---------------------------------------------------------------------

    def resolve(self, class_id: str, name: str, text: str = "") -> tuple[URIRef, str]:
        """The (IRI, canonical label) of the instance of ``class_id`` that ``name``
        (extracted from ``text``) refers to, a new instance if it matches none."""
        key = normalize(name)
        if not self.active or not key:
            return self.onto.instance(class_id, name), name

        # 1. the cheap matches, and the judge's candidates if there is none
        with self._lock:
            index = self._classes[class_id]
            match = self._match_known(index, key)
            candidates = self._judge_candidates(index, key) if match is None else []

        # 2. the judge is slow, so it runs without the lock
        if match is None:
            match = self._match_by_judge(class_id, name, key, text, candidates)

        # 3. record the name under its entity (or a new one)
        with self._lock:
            entity = self._commit(
                self._classes[class_id], class_id, name, key, text, match
            )
        return entity.iri, entity.label

    def _match_known(self, index: _ClassIndex, key: str) -> _Match | None:
        """The entity of a known name equal to ``key`` or, in levenshtein mode and up, close to it."""
        if (entity := index.entity_by_key.get(key)) is not None:
            return _Match(entity, "normalized")
        if (
            self._uses("levenshtein")
            and (entity := self._levenshtein_match(index, key)) is not None
        ):
            return _Match(entity, "levenshtein")
        return None

    def _levenshtein_match(self, index: _ClassIndex, key: str) -> _Entity | None:
        """The entity of the closest known name within ``max_distance`` edits that also
        differs in at most ``max_ratio`` of the longer name's characters."""
        s = self.settings
        closest = process.extract(
            key,
            index.keys,
            scorer=Levenshtein.distance,
            score_cutoff=s.max_distance,
            limit=5,
        )
        for other, distance, _ in closest:
            if distance <= s.max_ratio * max(len(key), len(other)):
                return index.entity_by_key[other]
        return None

    def _judge_candidates(self, index: _ClassIndex, key: str) -> list[_Entity]:
        """Up to ``judge_candidates`` distinct entities whose names are the most similar to
        ``key``, empty below the llm_judge mode. Several names may refer to one entity, so
        more names than entities are searched."""
        if not self._uses("llm_judge") or self._judge is None:
            return []
        s = self.settings
        similar = index.tfidf.search(
            key, k=4 * s.judge_candidates, min_similarity=s.judge_min_similarity
        )
        candidates: list[_Entity] = []
        for similar_key, _ in similar:
            entity = index.entity_by_key[similar_key]
            if entity not in candidates:
                candidates.append(entity)
        return candidates[: s.judge_candidates]

    def _match_by_judge(
        self, class_id, name, key, text, candidates: list[_Entity]
    ) -> _Match | None:
        """The first candidate (the most similar first) that the judge finds to be ``name``."""
        for candidate in candidates:
            if self._judged_same(class_id, name, key, text, candidate):
                return _Match(candidate, "llm_judge")
        return None

    def _judged_same(self, class_id, name, key, text, other: _Entity) -> bool:
        """Whether the judge's P(same) of ``name`` and ``other`` reaches the threshold; the
        probability is cached per (class, names), from the contexts of its first judgment."""
        pair = (class_id, *sorted((key, normalize(other.label))))
        p = self._cached_judgment(pair)
        if p is None:
            p = self._ask_judge(class_id, name, text, other)
            if p is None:
                # not cached: asked again on the next mention
                return False
            self._cache_judgment(pair, p)
        return p >= self.settings.judge_threshold

    def _ask_judge(self, class_id, name, text, other: _Entity) -> float | None:
        cls = self.onto.get_class(class_id) or OntoClass(id=class_id)
        try:
            return float(
                self._judge().p_same(
                    cls, name, context(text, name), other.label, other.context
                )
            )
        except Exception:
            logger.warning(
                "Disambiguation judge failed on %r / %r",
                name,
                other.label,
                exc_info=True,
            )
            return None

    def _cached_judgment(self, pair) -> float | None:
        with self._lock:
            p = self._cache.get(pair)
            if p is not None:
                self._cache.move_to_end(pair)
            return p

    def _cache_judgment(self, pair, p: float):
        with self._lock:
            self.judged += 1
            self._cache[pair] = p
            while len(self._cache) > JUDGMENT_CACHE:
                self._cache.popitem(last=False)

    def _commit(
        self, index: _ClassIndex, class_id, name, key, text, match: _Match | None
    ) -> _Entity:
        """Adds ``key`` to the index under the matched entity (a new one without a match)
        and records a merge if ``name`` is not the entity's label. Called with the lock held."""
        if (raced := index.entity_by_key.get(key)) is not None:
            # another thread added this name while the judge ran: its entity wins
            match = _Match(raced, "normalized")
        entity = (
            match.entity
            if match is not None
            else self._new_entity(index, class_id, name, text)
        )
        self._add_key(index, key, entity)

        if name in index.seen_names:
            return entity
        index.seen_names.add(name)
        if name != entity.label:
            # a new entity is labelled with ``name``, so ``match`` is set here
            self.merged += 1
            self.merges.append(
                Merge(
                    class_id=class_id,
                    alias=name,
                    canonical=entity.label,
                    iri=str(entity.iri),
                    method=match.method,
                )
            )
        return entity

    def _add_key(self, index: _ClassIndex, key: str, entity: _Entity):
        if key and key not in index.entity_by_key:
            index.entity_by_key[key] = entity
            index.keys.append(key)
            if self._uses("llm_judge"):
                index.tfidf.add(key)

    def _new_entity(self, index: _ClassIndex, class_id, name, text) -> _Entity:
        """A new entity labelled ``name``, its IRI suffixed with -2, -3, ... if taken."""
        base = self.onto.instance(class_id, name)
        iri, n = base, 2
        while iri in index.iris:
            iri, n = URIRef(f"{base}-{n}"), n + 1
        index.iris.add(iri)
        return _Entity(iri, name, context(text, name))
