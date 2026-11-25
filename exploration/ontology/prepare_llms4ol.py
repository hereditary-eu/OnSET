"""Builds the LLMs4OL 2025 Task A (Text2Onto) text sets of the ontology builder:
``data/text-sets/llms4ol-2025/<domain>/{train,test,blind}`` from the challenge checkout.

The official test documents have no released gold, so the official *train* documents are
split (by document, seed 25 as the organisers' splitter, ``--test_fraction``) into ``train``
(given to the builder agent as annotated examples) and ``test`` (extracted and scored);
``blind`` holds the official test documents (predictions in the submission format only).

Every split directory holds the challenge's files, restricted to its documents:
- ``documents.jsonl``: ``{"id", "title", "text"}`` per line,
- ``types.txt`` / ``types2docs.json``: the classes of its documents (the challenge's
  ``terms2docs.json`` is in fact this type -> documents map, kept under its true name),
- ``terms.txt`` / ``terms2types.json``: the individuals (A1) and their types; the challenge
  gives no term -> document map, so terms are assigned to the documents whose text contains
  them (case-insensitive, as participants did) in ``terms2docs.json``; terms found in no
  document stay in ``train`` only,
- ``gold.json``: ``{doc_id: {"types": [...], "terms": [{"term", "types"}]}}``, the per-document
  annotation the builder's ``get_training_examples`` tool shows.
"""

import argparse
import json
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

ROOT = Path(__file__).resolve().parents[2]
CHALLENGE = ROOT / "LLMs4OL-Challenge/2025/TaskA-Text2Onto"
OUT = ROOT / "data/text-sets/llms4ol-2025"
DOMAINS = ("ecology", "engineering", "scholarly")


def read_jsonl(path: Path) -> list[dict]:
    """Records of a JSONL file, also when a line holds several concatenated objects
    (line 234 of the ecology test file) or is blank."""
    decoder, records = json.JSONDecoder(), []
    for line in path.read_text().splitlines():
        line = line.strip()
        while line:
            record, end = decoder.raw_decode(line)
            records.append(record)
            line = line[end:].strip()
    return records


def write_jsonl(path: Path, records: list[dict]):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


def write_lines(path: Path, items) -> None:
    path.write_text("".join(f"{x}\n" for x in items))


# terms that are also common words ("are", the unit) would be found in every document; the
# stop words of the builder's text search (builder/corpus.py, scikit-learn's English list)
STOP_WORDS = ENGLISH_STOP_WORDS


def contains(text: str, term: str) -> bool:
    if term.lower() in STOP_WORDS:
        return False
    return re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", text) is not None


def write_split(out: Path, docs: list[dict], types2docs: dict, terms2types: dict, term_docs: dict):
    out.mkdir(parents=True, exist_ok=True)
    ids = {d["id"] for d in docs}
    t2d = {t: sorted(set(v) & ids) for t, v in types2docs.items() if set(v) & ids}
    term2d = {t: sorted(set(v) & ids) for t, v in term_docs.items() if set(v) & ids}
    terms = sorted(term2d)
    write_jsonl(out / "documents.jsonl", docs)
    write_lines(out / "types.txt", sorted(t2d))
    write_lines(out / "terms.txt", terms)
    (out / "types2docs.json").write_text(json.dumps(t2d, indent=1, ensure_ascii=False))
    (out / "terms2docs.json").write_text(json.dumps(term2d, indent=1, ensure_ascii=False))
    (out / "terms2types.json").write_text(json.dumps(
        [{"term": t, "types": terms2types[t]} for t in terms], indent=1, ensure_ascii=False))
    gold = defaultdict(lambda: {"types": [], "terms": []})
    for t, ds in t2d.items():
        for d in ds:
            gold[d]["types"].append(t)
    for t, ds in term2d.items():
        for d in ds:
            gold[d]["terms"].append({"term": t, "types": terms2types[t]})
    (out / "gold.json").write_text(json.dumps({d["id"]: gold[d["id"]] for d in docs}, indent=1, ensure_ascii=False))
    return {"docs": len(docs), "types": len(t2d), "terms": len(terms)}


def prepare(domain: str, test_fraction: float, seed: int) -> dict:
    src, out = CHALLENGE / domain, OUT / domain
    docs = read_jsonl(src / "train/documents.jsonl")
    types2docs = json.loads((src / "train/terms2docs.json").read_text())
    terms2types = {x["term"]: x["types"] for x in json.loads((src / "train/terms2types.json").read_text())}
    texts = {d["id"]: f"{d['title']}\n{d['text']}".lower() for d in docs}
    term_docs = {t: [i for i, text in texts.items() if contains(text, t)] for t in terms2types}
    ids = sorted(texts)
    random.Random(seed).shuffle(ids)
    test_ids = set(ids[: max(1, round(len(ids) * test_fraction))])
    stats = {
        "test": write_split(out / "test", [d for d in docs if d["id"] in test_ids], types2docs, terms2types, term_docs),
    }
    # terms found in no document are only in train (they cannot be extracted from a test text)
    train_terms = {t: (v or ["__none__"]) for t, v in term_docs.items()}
    train_docs = [d for d in docs if d["id"] not in test_ids]
    stats["train"] = write_split(out / "train", train_docs, types2docs, terms2types,
                                 {t: [i for i in v if i not in test_ids] or (["__none__"] if v == ["__none__"] else [])
                                  for t, v in train_terms.items()})
    # the unfound terms: listed in the train terms.txt like the challenge does
    unfound = sorted(t for t, v in term_docs.items() if not v)
    if unfound:
        terms = sorted(set((out / "train/terms.txt").read_text().split("\n")) - {""} | set(unfound))
        write_lines(out / "train/terms.txt", terms)
        (out / "train/terms2types.json").write_text(json.dumps(
            [{"term": t, "types": terms2types[t]} for t in terms], indent=1, ensure_ascii=False))
    blind = read_jsonl(next((src / "test").glob("*.jsonl")))
    (out / "blind").mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "blind/documents.jsonl", blind)
    stats["blind"] = {"docs": len(blind)}
    stats["unfound_terms"] = len(unfound)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--domains", nargs="+", default=list(DOMAINS))
    parser.add_argument("--test_fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=25)
    args = parser.parse_args()
    for domain in args.domains:
        if (OUT / domain).exists():
            shutil.rmtree(OUT / domain)
        print(domain, json.dumps(prepare(domain, args.test_fraction, args.seed)))
    shutil.copy(CHALLENGE.parent / "README.md", OUT / "CHALLENGE_README.md")
    (OUT / "README.md").write_text(
        "# LLMs4OL 2025 Task A (Text2Onto)\n\nGenerated by `exploration/ontology/prepare_llms4ol.py` from "
        "`LLMs4OL-Challenge/2025/TaskA-Text2Onto` (see its docstring for the split and file meanings).\n"
        "`train`/`test`: split of the official train documents (with gold), `blind`: the official test "
        "documents (no gold released).\n")
