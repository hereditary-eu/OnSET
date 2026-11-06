"""Entity disambiguation of the builder's build (builder/disambiguate.py): normalization,
Levenshtein merging, the TF-IDF candidates and the LLM judge (faked), and the session's
settings (persisted, a change rebuilds the KG), all without a model."""

import json
import threading
import time

import pytest
from rdflib import RDFS, SKOS, Graph

from builder.disambiguate import Disambiguator, NgramIndex, answer_probability, judge_prompt, normalize
from builder.ontology import Ontology, OntoClass, OntoLink, extraction_triples
from builder.session import Builder
from eval_config import BuilderConfig, DisambiguationSettings, TextSetConfig

ONTO = Ontology(
    prefix="http://ex.org/o/",
    classes=[OntoClass(id="Person"), OntoClass(id="Company", label="Company", description="a business")],
    links=[OntoLink(id="worksFor", source="Person", target="Company")],
)


class FakeJudge:
    """P(same) 0.9 for the given (unordered, normalized) name pairs, 0.3 otherwise; records its calls."""

    def __init__(self, *same: tuple[str, str], fail: bool = False):
        self.same_pairs = {frozenset(map(normalize, p)) for p in same}
        self.calls: list[tuple[str, str]] = []
        self.fail = fail
        self._lock = threading.Lock()

    def p_same(self, cls, a, a_context, b, b_context) -> float:
        with self._lock:
            self.calls.append((a, b))
        if self.fail:
            raise RuntimeError("judge down")
        return 0.9 if frozenset((normalize(a), normalize(b))) in self.same_pairs else 0.3


def dis(mode: str, judge: FakeJudge | None = None, cache=None, **settings) -> Disambiguator:
    return Disambiguator(ONTO, DisambiguationSettings(mode=mode, **settings), (lambda: judge) if judge else None, cache)


def test_normalize():
    assert normalize("Enron  Corp.") == normalize("enron corp") == normalize(" ENRON\tCORP ") == "enron corp"
    assert normalize("AT&T") == "at t" and normalize("Müller") == "müller"
    assert normalize("...") == ""


def test_off_keeps_slug_instances():
    d = dis("off")
    assert d.resolver("text") is None
    assert d.resolve("Company", "Enron Corp") == (ONTO.instance("Company", "Enron Corp"), "Enron Corp")


def test_normalized_merge():
    d = dis("normalized")
    iri, label = d.resolve("Company", "Enron Corp")
    assert d.resolve("Company", "enron corp.") == (iri, "Enron Corp")
    assert d.resolve("Company", "ENRON  CORP") == (iri, "Enron Corp")
    # repeated aliases count once, other names and other classes stay apart
    d.resolve("Company", "enron corp.")
    assert d.merged == 2 and [m.alias for m in d.merges] == ["enron corp.", "ENRON  CORP"]
    assert {m.method for m in d.merges} == {"normalized"}
    assert d.resolve("Company", "Enron Corporation")[0] != iri
    assert d.resolve("Person", "enron corp")[0] == ONTO.instance("Person", "enron corp")
    # names with the same slug but different normalized names get IRIs of their own
    a, _ = d.resolve("Person", "Müller")
    b, _ = d.resolve("Person", "Möller")
    assert a != b and str(b).endswith("-2")


def test_levenshtein_merge():
    d = dis("levenshtein", max_distance=2, max_ratio=0.2)
    iri, _ = d.resolve("Company", "Enron Corp")
    assert d.resolve("Company", "Enron Corps") == (iri, "Enron Corp")
    assert d.merges[-1].method == "levenshtein"
    # within 2 edits but 1 of 3 characters: too far relative to the name
    bob, _ = d.resolve("Person", "Bob")
    assert d.resolve("Person", "Rob")[0] != bob
    # aliases are matched too (normalized: "enron corpss" is 1 edit from "enron corps")
    assert d.resolve("Company", "Enron Corpss")[0] == iri
    assert d.resolve("Company", "Enron Corporation")[0] != iri
    strict = dis("levenshtein", max_distance=0)
    first, _ = strict.resolve("Company", "Enron Corp")
    assert strict.resolve("Company", "Enron Corps")[0] != first


def test_tfidf_candidates():
    index = NgramIndex()
    # with many "... corporation"s, the common suffix weighs less than the distinctive "enron"
    others = [f"{n} corporation" for n in ("acme", "umbrella", "initech", "stark", "wayne", "tyrell")]
    for name in ("enron corp", "globex", "enron energy services", *others):
        index.add(name)
    index.add("globex")  # adding twice is a no-op
    assert len(index) == 9
    hits = index.search("enron corporation", k=2)
    assert [h[0] for h in hits][0] == "enron corp" and hits[0][1] > hits[1][1] > 0
    assert index.search("enron corp", k=5)[0][0] != "enron corp"  # the name itself is no candidate
    assert index.search("hooli", k=3, min_similarity=0.4) == []
    assert NgramIndex().search("x") == []


def test_llm_judge_merges_and_caches():
    judge = FakeJudge(("Enron Corporation", "Enron Corp"))
    d = dis("llm_judge", judge, judge_min_similarity=0.3)
    iri, _ = d.resolve("Company", "Enron Corp", "Mail from Enron Corp about the merger.")
    d.resolve("Company", "Globex")
    # not within the edit limits: the closest name by TF-IDF is judged
    assert d.resolve("Company", "Enron Corporation", "Enron Corporation said") == (iri, "Enron Corp")
    assert judge.calls == [("Enron Corporation", "Enron Corp")]
    assert d.merges[-1].method == "llm_judge" and d.judged == 1
    # the alias is known now, dissimilar names are not judged
    d.resolve("Company", "enron corporation")
    d.resolve("Company", "Initech")
    assert len(judge.calls) == 1
    # a "no" keeps them apart
    d.resolve("Company", "Enron Energy")
    assert judge.calls[-1][0] == "Enron Energy" and d.resolve("Company", "Enron Energy")[0] != iri
    # judgments are cached per (class, names) across disambiguators sharing the cache
    calls = len(judge.calls)
    again = dis("llm_judge", judge, cache=d._cache, judge_min_similarity=0.3)
    again.resolve("Company", "Enron Corp")
    assert again.resolve("Company", "Enron Corporation")[0] == iri
    assert len(judge.calls) == calls
    # the cache keeps probabilities: a stricter threshold reuses them and merges nothing
    strict = dis("llm_judge", judge, cache=d._cache, judge_min_similarity=0.3, judge_threshold=0.95)
    first, _ = strict.resolve("Company", "Enron Corp")
    assert strict.resolve("Company", "Enron Corporation")[0] != first
    assert len(judge.calls) == calls


def test_llm_judge_failure_is_no_merge():
    judge = FakeJudge(fail=True)
    d = dis("llm_judge", judge, judge_min_similarity=0.3)
    iri, _ = d.resolve("Company", "Enron Corp")
    assert d.resolve("Company", "Enron Corporation")[0] != iri
    assert not d._cache and d.judged == 0


def test_judge_prompt_and_answer_probability():
    prompt = judge_prompt(ONTO.classes[1], "Enron Corporation", "said Enron Corporation", "Enron Corp", "")
    assert '"Enron Corporation"' in prompt and '"Enron Corp"' in prompt and "same company?" in prompt
    assert prompt.count("mentioned in") == 1 and "said Enron Corporation" in prompt
    # P(yes) over the yes and no tokens only: other tokens don't count
    logits = [0.0, 2.0, 1.0, 2.0, 50.0]
    assert answer_probability(logits, [1, 2], [3]) == pytest.approx((1 + 1 / 2.718281828) / (2 + 1 / 2.718281828))
    assert answer_probability(logits, [1], [3]) == pytest.approx(0.5)


def test_concurrent_resolve_gives_one_instance():
    d = dis("normalized")
    results = []

    def run(name):
        results.append(d.resolve("Company", name))

    threads = [threading.Thread(target=run, args=(n,)) for n in ["Enron Corp", "enron corp", "ENRON CORP."] * 10]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({iri for iri, _ in results}) == 1 and d.merged == 2


def test_extraction_triples_alt_labels():
    d = dis("normalized")
    data = {"Person": [{"name": "Alice", "worksFor": ["Enron Corp", "enron corp."]}]}
    g = Graph()
    for t in extraction_triples(ONTO, data, resolve=d.resolver("")):
        g.add(t)
    enron = ONTO.instance("Company", "Enron Corp")
    assert {str(o) for o in g.objects(enron, RDFS.label)} == {"Enron Corp"}
    # trailing punctuation is cut by clean_name already
    assert {str(o) for o in g.objects(enron, SKOS.altLabel)} == {"enron corp"}
    assert set(g.objects(ONTO.instance("Person", "Alice"), ONTO.term("worksFor"))) == {enron}


# --- the session ---

DOCS = {
    "d1": {"title": "One", "text": "Alice works for Enron Corp"},
    "d2": {"title": "Two", "text": "Bob works for ENRON  corp"},
    "d3": {"title": "Three", "text": "Carol works for Enron Corporation"},
}


class VariantExtractor:
    def extract(self, onto, text):
        person, company = text.split(" works for ")
        return {"Person": [{"name": person, "worksFor": [company]}]}


@pytest.fixture
def builder(tmp_path):
    path = tmp_path / "docs.json"
    path.write_text(json.dumps(DOCS))
    config = BuilderConfig(
        name="Test", save_dir=str(tmp_path / "saves"),
        text_set=TextSetConfig(format="json", path=str(path), text_fields=["text"]),
        disambiguation=DisambiguationSettings(mode="off"),
    )
    b = Builder("test", config)
    b.extractor = VariantExtractor()
    b.judge = FakeJudge(("Enron Corporation", "Enron Corp"))
    return b


def wait_built(session, timeout=5):
    end = time.time() + timeout
    while session.status.running and time.time() < end:
        time.sleep(0.01)
    assert not session.status.running


def companies(session) -> dict[str, set[str]]:
    """Labels and alt labels of every company instance."""
    rows = session.run_query(
        "SELECT ?c ?l WHERE { ?c a onto:Company . { ?c rdfs:label ?l } UNION { ?c skos:altLabel ?l } }"
    ).rows
    out: dict[str, set[str]] = {}
    for c, l in rows:
        out.setdefault(c.value, set()).add(l.value)
    return out


def test_session_settings_rebuild_and_persist(builder, client, monkeypatch):
    import api.router.builder as router

    monkeypatch.setitem(router._builders, "test", builder)
    monkeypatch.setattr(router.CONFIG_FILE, "builders", {"test": {}})
    session = builder.session("s")
    session.set_ontology(ONTO)
    wait_built(session)
    # off: the slug merges the case variants, labelled with both names
    assert sorted(map(len, companies(session).values())) == [1, 2] and session.status.merged == 0
    url = "/onto-builder/test/sessions/s/disambiguation"
    assert client.get(url).json()["settings"]["mode"] == "off"

    version, graph = session.version, session.graph
    state = client.put(url, json={"mode": "llm_judge", "judge_min_similarity": 0.3}).json()
    assert state["settings"]["mode"] == "llm_judge" and state["settings"]["max_distance"] == 2
    # the change rebuilt the KG from scratch
    assert session.version == version + 1 and session.graph is not graph
    wait_built(session)
    assert list(companies(session).values()) == [{"Enron Corp", "ENRON  corp", "Enron Corporation"}]
    state = client.get(url).json()
    assert state["merged"] == 2 == session.status.merged and state["judged"] == 1
    assert {m["method"] for m in state["merges"]} == {"normalized", "llm_judge"}
    assert client.get("/onto-builder/test/sessions/s").json()["disambiguation"]["mode"] == "llm_judge"
    assert client.put(url, json={"mode": "bogus"}).status_code == 422

    # unchanged settings don't rebuild
    version, graph = session.version, session.graph
    client.put(url, json=state["settings"])
    assert session.version == version and session.graph is graph

    # saved with the session, restored after a restart (old saves get the builder default)
    saved = json.loads(builder.state_file("s").read_text())
    assert saved["disambiguation"]["mode"] == "llm_judge"
    restarted = Builder("test", builder.config)
    restarted.extractor = VariantExtractor()
    restarted.judge = FakeJudge(("Enron Corporation", "Enron Corp"))
    restored = restarted.session("s", create=False)
    assert restored.disambiguation == session.disambiguation
    wait_built(restored)
    assert len(companies(restored)) == 1


def test_imported_instances_are_merge_targets(builder):
    session = builder.session("src")
    session.set_ontology(ONTO)
    session.set_disambiguation(DisambiguationSettings(mode="normalized"))
    wait_built(session)
    ttl = session.export("all")
    other = builder.session("imp")
    other.set_disambiguation(DisambiguationSettings(mode="normalized"))
    other.import_ttl(ttl)
    wait_built(other)
    # the rebuilt mentions resolve to the imported instances (no "-2" duplicates)
    assert len(companies(other)) == 2
    assert not any(c.endswith("-2") for c in companies(other))
    # a build knows the imported instances and their aliases before extracting
    seeded = other._disambiguator(other.ontology)
    iri, label = seeded.resolve("Company", "enron CORP")
    assert str(iri) in companies(other) and label in companies(other)[str(iri)]
