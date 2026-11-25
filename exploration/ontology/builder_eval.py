"""Headless runs of the ontology builder agent and the scoring of a session (agent run or a
user's saved session) on an evaluation dataset (datasets.py).

A run is the builder's own machinery without the API: a ``Builder`` (its corpus replaced by
the dataset's evaluation documents), a ``BuilderSession`` saved below the run's directory and
a ``BuilderAgent`` driven by scripted user turns; between turns the progressive build runs
(the agent sees a partial or complete KG, as a user would).
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef

from builder.agent import BuilderAgent
from builder.corpus import Corpus
from builder.ontology import PROV, Ontology
from builder.session import Builder, BuilderSession
from datasets import Dataset, llms4ol_gold_lists
from onto_eval import (
    Mentions, Schema, mentions_from_graph, schema_from_ontology, score_mentions, score_schema, text2onto_metrics,
)

REFINE_PROMPT = (
    "The extraction has now read the documents. Inspect what it extracted (get_kg_stats, queries) and refine "
    "the ontology: fix or remove classes, fields and links that stay empty or are filled wrongly, and add what "
    "the documents talk about but the ontology misses."
)
BLIND_PROMPT = "Build an ontology for this document collection."

# classes whose instances are LLMs4OL terms (named individuals), the others' are types
TERM_CLASS = re.compile(r"\b(term|individual|instance|named entity|entity name)\b")


@dataclass
class RunConfig:
    dataset: Dataset
    run_id: str
    out_dir: Path
    # "guided": the dataset's task description, "blind": only "build an ontology"
    prompt: str = "guided"
    # refinement turns after the first
    refine_turns: int = 1
    # documents of the evaluated KG (None: all of the dataset's)
    max_documents: int | None = None
    seed: int = 0
    # seconds to wait for a build between turns / before scoring
    turn_build_timeout: float = 300
    final_build_timeout: float = 1800
    agent_overrides: dict = field(default_factory=dict)
    extract_instances: int | None = None
    # extraction model (GGUF repo on the Hugging Face Hub), None: the builder's
    extract_model: str | None = None
    store: str = "memory"


def wait_for_build(session: BuilderSession, timeout: float, poll: float = 2.0) -> bool:
    """Waits until the session's build is done (True) or ``timeout`` passes; touching the
    session keeps its build from pausing as idle."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not session.state().status.running:
            return True
        time.sleep(poll)
    return not session.state().status.running


_EXTRACTORS: dict = {}


def make_builder(cfg: RunConfig) -> Builder:
    config = cfg.dataset.builder_config()
    # rdflib's memory store: the KGs here are small, and the agent's SPARQL crashed Tentris'
    # native query (a segfault ends the whole run)
    update = {"save_dir": str(cfg.out_dir / "sessions"), "store": cfg.store}
    if cfg.extract_instances:
        update["extract_instances"] = cfg.extract_instances
    if cfg.extract_model:
        update["extract_model_id"] = cfg.extract_model
    if cfg.agent_overrides:
        update["agent"] = config.agent.model_copy(update=cfg.agent_overrides)
    config = config.model_copy(update=update)
    builder = Builder(cfg.dataset.builder, config)
    # one extraction model pool per model configuration for the whole process (a builder per
    # run would load a new pool every run and run out of GPU memory)
    key = (config.extract_model_id, config.extract_model_quant, config.extract_n_ctx, config.extract_instances)
    if key not in _EXTRACTORS:
        _EXTRACTORS[key] = builder.extractor
    builder.extractor = _EXTRACTORS[key]
    if cfg.dataset.documents is not None:
        builder.corpus = Corpus(cfg.dataset.documents(config, cfg.max_documents, cfg.seed))
    elif cfg.max_documents:
        builder.corpus = Corpus(builder.corpus.documents[: cfg.max_documents])
    return builder


def run_turn(agent: BuilderAgent, content: str, log: list) -> dict:
    """One scripted user turn; returns its tool call / step statistics."""
    log.append({"type": "user_message", "content": content})
    stats = Counter()
    start = time.monotonic()
    for message in agent.run_turn(content):
        kind = getattr(message, "type", "")
        if kind == "tool_call" and message.status != "running":
            stats["tool_calls"] += 1
            stats[f"tool_{message.name}"] += 1
            stats["tool_errors"] += message.status == "error"
            log.append(message.model_dump(mode="json", exclude={"changes", "details"}))
        elif kind in ("assistant_message", "thinking") and message.final and message.content:
            log.append({"type": kind, "content": message.content})
        elif kind in ("error", "done"):
            log.append(message.model_dump(mode="json"))
            if kind == "done":
                stats[f"done_{message.reason}"] += 1
    stats["seconds"] = time.monotonic() - start
    return dict(stats)


def run_agent(cfg: RunConfig) -> tuple[BuilderSession, dict]:
    """Runs the agent on the dataset and waits for the final build; returns the session and
    the run's statistics (also written to ``<out_dir>/runs/<run_id>.json`` with the chat)."""
    builder = make_builder(cfg)
    # a fresh session: a crashed earlier attempt of this run left its state behind, kept aside
    state = builder.state_file(cfg.run_id)
    for path in state.parent.glob(f"{cfg.run_id}.*"):
        if ".crashed" not in path.name:
            path.rename(path.with_name(path.name.replace(cfg.run_id, f"{cfg.run_id}.crashed{int(time.time())}", 1)))
    session = builder.session(cfg.run_id)
    agent = BuilderAgent(builder.agent_llm, session)
    first = BLIND_PROMPT if cfg.prompt == "blind" else f"{BLIND_PROMPT} {cfg.dataset.task}"
    log: list = []
    stats: dict = {"turns": []}
    start = time.monotonic()
    for i, content in enumerate([first] + [REFINE_PROMPT] * cfg.refine_turns):
        if i:
            stats.setdefault("build_complete_before_turn", []).append(wait_for_build(session, cfg.turn_build_timeout))
        stats["turns"].append(run_turn(agent, content, log))
    stats["agent_seconds"] = time.monotonic() - start
    stats["build_complete"] = wait_for_build(session, cfg.final_build_timeout)
    stats["seconds"] = time.monotonic() - start
    stats["status"] = session.state().status.model_dump()
    stats["documents"] = len(builder.corpus.documents)
    out = cfg.out_dir / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{cfg.run_id}.json").write_text(json.dumps(
        {"stats": stats, "ontology": session.ontology.model_dump(), "chat": log}, indent=1, default=str))
    (out / f"{cfg.run_id}.ttl").write_text(session.export("all"))
    return session, stats


# --- scoring ---


def text2onto_lists(graph: Graph, onto: Ontology) -> dict[str, list[str]]:
    """The LLMs4OL lists of a KG: ``terms`` are the names of instances of term classes
    (``TERM_CLASS`` on the class id/label; every instance if there is none), ``types`` the
    names of all other instances; each list deduplicated (case-insensitive) and ordered by
    the number of documents a name was extracted from (the challenge matches greedily)."""
    term_classes = {onto.term(c.id) for c in onto.classes
                    if TERM_CLASS.search(f"{c.id} {c.label}".lower().replace("_", " "))}
    classes = {onto.term(c.id) for c in onto.classes}
    counts = {"terms": Counter(), "types": Counter()}
    for s, _, cls in graph.triples((None, RDF.type, None)):
        if cls not in classes or not isinstance(s, URIRef):
            continue
        docs = max(1, len(list(graph.objects(s, URIRef("http://www.w3.org/ns/prov#wasDerivedFrom")))))
        kind = "terms" if cls in term_classes or not term_classes else "types"
        for name in graph.objects(s, RDFS.label):
            counts[kind][str(name).strip()] += docs
        if not term_classes:
            for name in graph.objects(s, RDFS.label):
                counts["types"][str(name).strip()] += docs
    out = {}
    for kind, c in counts.items():
        seen, ordered = set(), []
        for name, _ in c.most_common():
            if name.lower() not in seen:
                seen.add(name.lower())
                ordered.append(name)
        out[kind] = ordered
    return out


def score_session(dataset: Dataset, onto: Ontology | dict, graph: Graph | None = None,
                  ref: Schema | None = None, gold: Mentions | None = None,
                  documents: int | None = None) -> tuple[dict, dict]:
    """Metrics (flat dict) and details (alignments) of an ontology and, if given, its KG."""
    onto = onto if isinstance(onto, Ontology) else Ontology(**onto)
    pred = schema_from_ontology(onto)
    metrics, details = {"n_classes": len(onto.classes), "n_links": len(onto.links),
                        "n_fields": sum(len(c.fields) for c in onto.classes)}, {}
    class_map, link_map = {}, {}
    if ref is not None:
        score = score_schema(pred, ref)
        metrics |= score.metrics
        details["alignment"] = score.alignment
        class_map, link_map = score.class_map["sem"], score.link_map
    if graph is not None:
        metrics["kg_triples"] = len(graph)
        classes = {onto.term(c.id) for c in onto.classes}
        instances = {s for s, _, c in graph.triples((None, RDF.type, None)) if c in classes}
        docs = {d for s in instances for d in graph.objects(s, PROV.wasDerivedFrom)}
        metrics["kg_instances"] = len(instances)
        metrics["kg_docs_with_instances"] = len(docs)
        if documents:
            metrics["kg_doc_coverage"] = len(docs) / documents
            metrics["kg_instances_per_doc"] = len(instances) / documents
        if gold is not None:
            mentions = mentions_from_graph(graph, onto.prefix)
            if dataset.llms4ol:
                # types and terms are compared untyped (the agent's classes are its own)
                metrics |= {f"doc_{k}": v for k, v in score_mentions(mentions, gold, {}, {}).items()
                            if k.startswith(("ent_strict", "ent_len", "docs"))}
            else:
                metrics |= {f"kg_{k}": v for k, v in score_mentions(mentions, gold, class_map, link_map).items()}
        if dataset.llms4ol:
            lists = text2onto_lists(graph, onto)
            gold_lists = llms4ol_gold_lists(dataset.llms4ol)
            metrics |= text2onto_metrics(lists["terms"], gold_lists["terms"], "a1_terms")
            metrics |= text2onto_metrics(lists["types"], gold_lists["types"], "a2_types")
            details["lists"] = lists
    return metrics, details


# --- users' saved sessions ---

MAIN_METRICS = ["schema_sem_f1", "class_sem_f1", "rel_triple_sem_f1", "kg_ent_typed_len_f1", "kg_rel_typed_len_f1",
                "a1_terms_f1", "a2_types_f1"]


def default_sessions_dir() -> Path:
    """The backend's builder save_dir (config.json)."""
    from eval_config import CONFIG_FILE

    return Path(CONFIG_FILE.builder(next(iter(CONFIG_FILE.builders))).save_dir)


def score_saved_sessions(sessions_dir: Path | None = None, registry: dict | None = None, min_classes: int = 1,
                         with_kg: bool = False, max_documents: int | None = None, out_dir: Path | None = None):
    """One row of metrics per saved session (``<sessions_dir>/<builder>/<id>.json``) whose
    builder id names a dataset; ``with_kg`` rebuilds each session's KG on the dataset's
    evaluation documents (sessions saved below ``out_dir``) for the instance metrics."""
    import pandas as pd

    from datasets import DATASETS
    from onto_eval import load_session

    sessions_dir = Path(sessions_dir or default_sessions_dir())
    registry = registry or DATASETS
    out_dir = out_dir or Path(__file__).resolve().parent / "results" / f"sessions_{sessions_dir.name}"
    rows = []
    for builder_dir in sorted(p for p in sessions_dir.iterdir() if p.is_dir()):
        dataset = registry.get(builder_dir.name)
        if dataset is None:
            continue
        ref = dataset.reference_schema()
        gold = dataset.gold(ref) if dataset.gold else None
        for path in sorted(builder_dir.glob("*.json")):
            state = load_session(path)
            if state is None or len(state["ontology"].get("classes", [])) < min_classes:
                continue
            onto = Ontology(**state["ontology"])
            graph = None
            if with_kg:
                cfg = RunConfig(dataset, f"user-{path.stem}", out_dir, max_documents=max_documents)
                session = make_builder(cfg).session(cfg.run_id)
                session.set_ontology(onto)
                wait_for_build(session, cfg.final_build_timeout)
                graph = session.graph
                session.stop()
            metrics, _ = score_session(dataset, onto, graph, ref, gold,
                                       len(session.builder.corpus.documents) if with_kg else None)
            turns = sum(1 for e in (state.get("chat") or {}).get("log", []) if e.get("type") == "user_message")
            rows.append({"dataset": dataset.name, "run_id": path.stem, "source": "user", "user_turns": turns, **metrics})
    return pd.DataFrame(rows)


def aggregate(df, metrics=MAIN_METRICS):
    """Median and best (max) of each metric per dataset and source."""
    cols = [m for m in metrics if m in df]
    return df.groupby(["dataset", "source"])[cols].agg(["median", "max"]).rename(columns={"max": "best"}, level=1)
