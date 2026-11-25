"""Ontology builder extensions for LLMs4OL-style text sets: jsonl / llms4ol corpora, class
hierarchy, enum fields, few-shot extraction examples, annotated examples and KG statistics."""

import json
import queue

import pytest
from rdflib import RDFS

from builder.agent import BuilderAgent, BuilderTools
from builder.corpus import Corpus, JSONLSet, LLMs4OLSet, load_documents
from builder.extract import LlamaExtractor, extraction_messages
from builder.ontology import (
    ExtractionExample, Ontology, OntoClass, OntoField, extraction_schema, ontology_from_graph, ontology_graph,
    validate_example,
)
from builder.session import Builder
from eval_config import BuilderConfig, OnsetConfigFile, TextSetConfig

DOCS = [
    {"id": "942_0", "title": "Drumlin Fields: A Type of Hill Range", "text": "A drumlin field is a hill range shaped by glaciers."},
    {"id": "17_3", "title": "Exagram", "text": "The exagram is a prefixed unit of mass. Drumlin fields are not units."},
]
GOLD = {
    "942_0": {"types": ["drumlin field", "hill range"]},
    "17_3": {"types": ["prefixed unit"], "terms": [{"term": "exagram", "types": ["prefixed unit"]}]},
}


def write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n\n")


class TypeExtractor:
    """Every "drumlin field" / "hill range" mentioned, as a Type."""

    def extract(self, onto, text):
        names = [n for n in ("drumlin field", "hill range", "prefixed unit") if n in text.lower()]
        return {"Type": [{"name": n} for n in names]} if onto.get_class("Type") else {}


@pytest.fixture
def builder(tmp_path):
    for split in ("train", "test"):
        (tmp_path / split).mkdir()
        write_jsonl(tmp_path / split / "documents.jsonl", DOCS)
    (tmp_path / "train" / "gold.json").write_text(json.dumps(GOLD))
    config = BuilderConfig(
        name="LLMs4OL", save_dir=str(tmp_path / "saves"),
        text_set=TextSetConfig(format="llms4ol", path=str(tmp_path / "test")),
        examples=TextSetConfig(format="llms4ol", path=str(tmp_path / "train")),
    )
    b = Builder("llms4ol", config)
    b.extractor = TypeExtractor()
    return b


def wait_built(session, timeout=5):
    import time

    end = time.time() + timeout
    while session.status.running and time.time() < end:
        time.sleep(0.01)
    assert not session.status.running


# --- corpus ---


def test_jsonl_ids_and_line_numbers(tmp_path):
    write_jsonl(tmp_path / "a.jsonl", DOCS)
    docs = load_documents(TextSetConfig(format="jsonl", path=str(tmp_path / "a.jsonl"), id_field="id"))
    assert [(d.id, d.title) for d in docs] == [("942_0", DOCS[0]["title"]), ("17_3", "Exagram")]
    # without id_field: line numbers, prefixed with the file below a directory
    docs = load_documents(TextSetConfig(format="jsonl", path=str(tmp_path)))
    assert [d.id for d in docs] == ["a.jsonl#0", "a.jsonl#1"]


def test_dotted_fields(tmp_path):
    records = [{"meta": {"id": 7, "title": "T"}, "body": {"abstract": "A.", "full": "F."}}]
    (tmp_path / "r.json").write_text(json.dumps(records))
    config = TextSetConfig(format="json", path=str(tmp_path / "r.json"), id_field="meta.id",
                           title_field="meta.title", text_fields=["body.abstract", "body.missing", "body.full"])
    [doc] = load_documents(config)
    assert (doc.id, doc.title, doc.text) == ("7", "T", "A.\n\nF.")


def test_corpus_classes_by_format(tmp_path):
    write_jsonl(tmp_path / "documents.jsonl", DOCS)
    jsonl = Corpus.load(TextSetConfig(format="jsonl", path=str(tmp_path / "documents.jsonl"), id_field="id"))
    assert type(jsonl) is JSONLSet and jsonl.annotation("942_0") is None and not jsonl.annotated
    # a split without gold.json (the test split)
    split = Corpus.load(TextSetConfig(format="llms4ol", path=str(tmp_path)))
    assert type(split) is LLMs4OLSet and not split.annotated
    (tmp_path / "gold.json").write_text(json.dumps(GOLD))
    for path in (tmp_path, tmp_path / "documents.jsonl"):
        split = Corpus.load(TextSetConfig(format="llms4ol", path=str(path)))
        assert [d.id for d in split.documents] == ["942_0", "17_3"]
        assert split.annotation("17_3") == GOLD["17_3"] and split.annotated


def test_example_paths_resolved_against_config_dir(tmp_path):
    builders = {"b": {"name": "B", "text_set": {"format": "llms4ol", "path": "test"},
                      "examples": {"format": "llms4ol", "path": "train", "gold": "gold.json"}}}
    config = OnsetConfigFile(default="x", configs={"x": {}}, builders=builders, base_dir=str(tmp_path))
    b = config.builder("b")
    assert b.examples.path == str(tmp_path / "train")
    assert b.examples.gold == str(tmp_path / "gold.json")
    assert config.builder("b").examples.gold == str(tmp_path / "gold.json")  # not resolved twice


# --- ontology ---


def onto() -> Ontology:
    return Ontology(
        prefix="http://ex.org/o/",
        classes=[
            OntoClass(id="Landform"),
            OntoClass(id="Hill", parents=["Landform"],
                      fields=[OntoField(name="kind", type="enum", values=["drumlin", "esker"], description="shape")]),
        ],
    )


def test_enum_field_schema_and_template():
    schema = extraction_schema(onto())
    assert schema["properties"]["Hill"]["items"]["properties"]["kind"] == {"type": "string", "enum": ["drumlin", "esker"]}
    system = extraction_messages(onto(), "text")[0]["content"]
    assert "one of: drumlin, esker" in system


def test_parents_and_enum_roundtrip():
    g = ontology_graph(onto())
    assert (onto().term("Hill"), RDFS.subClassOf, onto().term("Landform")) in g
    back, instances = ontology_from_graph(g)
    assert len(instances) == 0
    hill = back.get_class("Hill")
    assert hill.parents == ["Landform"]
    assert hill.fields[0].type == "enum" and hill.fields[0].values == ["drumlin", "esker"]


def test_remove_class_drops_parent():
    o = onto()
    o.remove_class("Landform")
    assert o.get_class("Hill").parents == []


def test_examples_in_schema_key_and_messages():
    o = onto()
    key = o.schema_key()
    o.examples.append(ExtractionExample(text="An esker.", output={"Hill": [{"name": "esker", "kind": "esker"}]}))
    assert o.schema_key() != key
    messages = extraction_messages(o, "the document")
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert json.loads(messages[2]["content"]) == {"Landform": [], "Hill": [{"name": "esker", "kind": "esker"}]}
    assert messages[-1]["content"] == "the document"


def test_validate_example():
    assert validate_example(onto(), {"Hill": [{"name": "x"}]}) == {"Landform": [], "Hill": [{"name": "x"}]}
    for bad in ({"Mountain": []}, {"Hill": [{"name": "x", "height": 1}]}, {"Hill": [{"kind": "esker"}]},
                {"Hill": [{"name": "x", "kind": "volcano"}]}):
        with pytest.raises(ValueError):
            validate_example(onto(), bad)


class CapturingLlama:
    def __init__(self):
        self.messages = None

    def create_chat_completion(self, messages, **kwargs):
        self.messages = messages
        return {"choices": [{"message": {"content": '{"Hill": []}'}}], "usage": {}}


def test_llama_extractor_sends_examples(builder):
    extractor = LlamaExtractor(builder.config)
    fake = CapturingLlama()
    extractor.pool._free = queue.Queue()
    extractor.pool._free.put(fake)
    o = onto()
    o.examples = [ExtractionExample(text="x" * 3000, output={"Hill": []})] * 4
    assert extractor.extract(o, "doc") == {"Hill": []}
    assert len(fake.messages) == 1 + 2 * 3 + 1
    assert len(fake.messages[1]["content"]) == 1500


# --- agent tools ---


def test_tools(builder):
    session = builder.session("s1")
    tools = BuilderTools(session)

    def ok(tool, /, **args):
        result = tools.call(tool, args)
        assert result.ok, result.error
        return result.output

    ok("add_class", name="Type", description="a generic concept")
    ok("add_class", name="Landform", description="a landform")
    ok("set_superclasses", class_id="Type", parent_ids=["Landform"])
    assert not tools.call("set_superclasses", {"class_id": "Landform", "parent_ids": ["Type"]}).ok
    assert not tools.call("add_field", {"class_id": "Type", "name": "kind", "type": "enum", "description": ""}).ok
    field = ok("add_field", class_id="Type", name="kind", type="enum", description="", values=["a", "b", "a"])
    assert field["values"] == ["a", "b"]
    assert not tools.call("add_extraction_example", {"text": "t", "output_json": '{"Nope": []}'}).ok
    ok("add_extraction_example", text="A hill range.", output_json='{"Type": [{"name": "hill range"}]}')
    shown = ok("get_ontology")
    assert shown["examples"][0]["output"]["Type"] == [{"name": "hill range"}]
    assert shown["classes"][0]["parents"] == ["Landform"]
    ok("remove_extraction_example", index=0)
    assert session.ontology.examples == []

    wait_built(session)
    stats = ok("get_kg_stats", top=5)
    assert stats["classes"]["Type"]["instances"] == 3
    assert stats["classes"]["Type"]["top"]["drumlin field"] == 2
    assert stats["classes"]["Landform"] == {"instances": 0, "with_subclasses": 3, "top": {}}
    assert "2/2 documents" in stats["build"]

    ok("remove_class", class_id="Landform")
    assert session.ontology.get_class("Type").parents == []


def test_annotated_examples_gated_by_config(builder):
    session = builder.session("s1")
    tools = BuilderTools(session)
    assert "get_annotated_examples" in tools.tool_names()
    by_query = tools.call("get_annotated_examples", {"n": 1, "query": "exagram unit"}).output
    assert by_query == [{"id": "17_3", "title": "Exagram", "text": DOCS[1]["text"], "annotation": GOLD["17_3"]}]
    sample = tools.call("get_annotated_examples", {"n": 9}).output
    assert sorted(d["id"] for d in sample) == ["17_3", "942_0"]
    assert "get_annotated_examples" in BuilderAgent(None, session).system_prompt

    # no examples configured, or examples without annotations (a test split)
    for examples in (None, builder.config.text_set):
        plain = Builder("plain", builder.config.model_copy(update={"examples": examples}))
        plain.extractor = TypeExtractor()
        tools = BuilderTools(plain.session("s2"))
        assert "get_annotated_examples" not in tools.tool_names()
        assert all(d["name"] != "get_annotated_examples" for d in tools.definitions())
        assert not tools.call("get_annotated_examples", {"n": 1}).ok
        assert "get_annotated_examples" not in BuilderAgent(None, plain.session("s2")).system_prompt


def test_grounded_names():
    from builder.ontology import Ontology, OntoClass, extraction_triples, grounded

    assert grounded("drumlin field", "Drumlin fields are hills.")
    assert grounded("Enron Corp.", "at enron corp, we")
    assert not grounded("noun frame", "Tenses: present, past and future.")
    assert not grounded("past", "the pasta")
    onto = Ontology(classes=[OntoClass(id="Type", description="e.g. tense or case")])
    data = {"Type": [{"name": "tense"}, {"name": "case"}, {"name": "noun frame"}]}
    names = lambda triples: sorted(str(o) for _, p, o in triples if str(p).endswith("label"))
    # grounded: real mentions stay even if a description names them, copies from the prompt go
    assert names(extraction_triples(onto, data, text="The tense of a verb.")) == ["tense"]
    # without the text: names in the descriptions are dropped (the previous behaviour)
    assert names(extraction_triples(onto, data)) == ["noun frame"]


def test_chunks_and_merge():
    from builder.corpus import chunks
    from builder.extract import merge_extractions

    text = "One short sentence. Another one here! A third sentence follows? Last."
    pieces = chunks(text, 40)
    assert " ".join(pieces) == text and all(len(p) <= 40 for p in pieces) and len(pieces) > 1
    assert chunks("x" * 300, 100) == ["x" * 300]
    assert merge_extractions([{"A": [{"name": "a"}]}, {"A": [{"name": "b"}], "B": []}, {}]) == {
        "A": [{"name": "a"}, {"name": "b"}], "B": []}


class ChunkCounter(TypeExtractor):
    def __init__(self):
        self.calls = 0

    def extract(self, onto, text):
        self.calls += 1
        return super().extract(onto, text)


def test_check_extraction_and_chunking(builder):
    session = builder.session("check")
    tools = BuilderTools(session)
    assert tools.call("add_class", {"name": "Type", "description": "a concept"}).ok
    result = tools.call("check_extraction", {"n": 2})
    assert result.ok, result.error
    report = result.output
    # gold strings in the texts: drumlin field, hill range (942_0); prefixed unit, exagram (17_3)
    # "drumlin field" is also named in 17_3, whose gold lacks it
    assert report["precision"] == 0.75 and report["recall"] == 0.75
    missed = {d["id"]: d["missed"] for d in report["documents"]}
    assert missed["17_3"] == ["exagram"]
    counter = ChunkCounter()
    builder.extractor = counter
    assert tools.call("set_extraction_options", {"chunk_chars": 100}).ok
    assert session.ontology.chunk_chars == 100
    assert not tools.call("set_extraction_options", {"chunk_chars": 10}).ok
    counter.calls = 0
    session.extract_text(session.ontology, "A drumlin field is here. " * 10)
    assert counter.calls > 1


# --- annotation-driven extraction aids: retrieved examples, vocabulary ---


def test_annotation_values():
    from builder.ontology import annotation_values

    ann = {"types": ["prefixed unit", "unit"], "terms": [{"term": "exagram", "types": ["prefixed unit"]},
                                                         {"term": "kilogram", "types": ["base unit", 3]}]}
    assert annotation_values(ann, "types") == ["prefixed unit", "unit"]
    assert annotation_values(ann, "terms.term") == ["exagram", "kilogram"]
    assert annotation_values(ann, "terms.types") == ["prefixed unit", "base unit"]
    assert annotation_values(ann, "terms") == []  # objects, no strings
    assert annotation_values(ann, "nope.term") == []
    assert annotation_values([{"a": "x"}, {"a": ["y"]}], "a") == ["x", "y"]


def test_vocabulary_matches():
    from builder.ontology import Vocabulary

    vocab = Vocabulary([("d1", {"types": ["drumlin field", "the", "x", "hill range"]}),
                        ("d2", {"types": ["hill range"]}), ("d3", None)], "types")
    assert len(vocab) == 2  # stop word and one-character value left out
    text = "Hill ranges and drumlin fields. The x."
    assert vocab.matches(text) == ["hill range", "drumlin field"]
    # only d1 is annotated with "drumlin field": excluded with it, "hill range" also has d2
    assert vocab.matches(text, exclude_doc="d1") == ["hill range"]
    assert vocab.matches("the drumlin", exclude_doc=None) == []


def test_new_options_in_schema_key():
    o = onto()
    keys = {o.schema_key()}
    o.annotation_map["Hill"] = "types"
    keys.add(o.schema_key())
    o.retrieved_examples = 2
    keys.add(o.schema_key())
    o.vocabulary_classes = ["Hill"]
    keys.add(o.schema_key())
    assert len(keys) == 4
    o.remove_class("Hill")
    assert (o.annotation_map, o.vocabulary_classes, o.retrieved_examples) == ({}, [], 0)


class RecordingExtractor:
    """Records the extraction messages of every call, extracts nothing."""

    def __init__(self):
        self.calls = []

    def extract(self, onto, text):
        self.calls.append(extraction_messages(onto, text))
        return {}


def test_retrieved_examples(builder):
    session = builder.session("retrieve")
    recorder = RecordingExtractor()
    builder.extractor = recorder
    o = Ontology(classes=[OntoClass(id="Type")], annotation_map={"Type": "types"}, retrieved_examples=2,
                 examples=[ExtractionExample(text="static", output={"Type": []})])
    text = "Drumlin fields and prefixed units of mass."
    session.extract_text(o, text)
    messages = recorder.calls[-1]
    shots = [(messages[i]["content"], json.loads(messages[i + 1]["content"])) for i in range(1, len(messages) - 1, 2)]
    assert shots[-1] == ("static", {"Type": []})  # static examples after the retrieved ones
    retrieved = dict(shots[:-1])
    assert retrieved[DOCS[0]["text"]] == {"Type": [{"name": "drumlin field"}, {"name": "hill range"}]}
    # 17_3's first sentence has its "prefixed unit" (its "exagram" is no Type here)
    assert {"name": "prefixed unit"} in retrieved[next(t for t in retrieved if "exagram" in t)]["Type"]
    assert messages[-1]["content"] == text

    # the excluded document is never used
    session.extract_text(o, text, exclude_doc="942_0")
    assert all(DOCS[0]["text"] not in m["content"] for m in recorder.calls[-1][1:-1])
    # per chunk
    recorder.calls.clear()
    session.extract_text(o.model_copy(update={"chunk_chars": 100}), "A drumlin field is here. " * 10)
    assert len(recorder.calls) > 1 and all(len(m) > 4 for m in recorder.calls)
    # nothing retrieved without a mapping
    recorder.calls.clear()
    session.extract_text(o.model_copy(update={"annotation_map": {}}), text)
    assert len(recorder.calls[-1]) == 4


def test_vocabulary_in_extraction_and_check(builder):
    session = builder.session("vocab")
    builder.extractor = RecordingExtractor()
    o = Ontology(classes=[OntoClass(id="Type"), OntoClass(id="Term")],
                 annotation_map={"Type": "types", "Term": "terms.term"}, vocabulary_classes=["Type", "Term"])
    data = session.extract_text(o, "An exagram, not a hill range. Hill ranges!")
    assert data == {"Type": [{"name": "hill range"}], "Term": [{"name": "exagram"}]}
    # values only the excluded document is annotated with are not added
    assert session.extract_text(o, "An exagram on a hill range.", exclude_doc="17_3") == {
        "Type": [{"name": "hill range"}], "Term": []}
    # check_extraction leaves the checked document out: each document's own values are unknown
    session.set_ontology(o)
    report = session.check_extraction(builder.examples.annotated_examples(2))
    extracted = {d["id"]: d["extracted"] for d in report["documents"]}
    # only the other document's values are known: 17_3 names 942_0's "drumlin field"
    assert extracted == {"942_0": [], "17_3": ["Type: drumlin field"]}


def test_annotation_tools(builder):
    session = builder.session("tools")
    builder.extractor = RecordingExtractor()
    tools = BuilderTools(session)
    assert tools.call("add_class", {"name": "Type", "description": "a concept"}).ok
    assert not tools.call("set_extraction_options", {"chunk_chars": None, "retrieved_examples": 2}).ok
    assert not tools.call("map_annotations", {"class_id": "Type", "path": "nope", "vocabulary": False}).ok
    assert not tools.call("map_annotations", {"class_id": "Nope", "path": "types", "vocabulary": False}).ok
    result = tools.call("map_annotations", {"class_id": "Type", "path": "types", "vocabulary": True})
    assert result.ok, result.error
    assert result.output["documents"] == 2 and result.output["distinct_values"] == 3
    assert session.ontology.annotation_map == {"Type": "types"} and session.ontology.vocabulary_classes == ["Type"]
    assert tools.call("set_extraction_options", {"chunk_chars": None, "retrieved_examples": 3}).ok
    assert not tools.call("set_extraction_options", {"chunk_chars": None, "retrieved_examples": 6}).ok
    # backwards compatible: retrieved_examples kept
    assert tools.call("set_extraction_options", {"chunk_chars": 200}).ok
    assert (session.ontology.chunk_chars, session.ontology.retrieved_examples) == (200, 3)
    shown = tools.call("get_ontology", {}).output
    assert shown["annotation_map"] == {"Type": "types"} and shown["retrieved_examples"] == 3
    assert "map_annotations" in BuilderAgent(None, session).system_prompt
    # remapping without vocabulary, then clearing
    assert tools.call("map_annotations", {"class_id": "Type", "path": "types", "vocabulary": False}).ok
    assert session.ontology.vocabulary_classes == []
    assert tools.call("map_annotations", {"class_id": "Type", "path": "", "vocabulary": False}).ok
    assert session.ontology.annotation_map == {} and session.ontology.retrieved_examples == 0


def test_check_extraction_per_class(builder):
    session = builder.session("perclass")
    tools = BuilderTools(session)
    assert tools.call("add_class", {"name": "Type", "description": "a concept"}).ok
    assert tools.call("map_annotations", {"class_id": "Type", "path": "types", "vocabulary": False}).ok
    report = tools.call("check_extraction", {"n": 2}).output
    # Type values in the texts: drumlin field, hill range (942_0), prefixed unit (17_3); extracted
    # also drumlin field in 17_3
    assert report["classes"]["Type"] == {"precision": 0.75, "recall": 1.0}
