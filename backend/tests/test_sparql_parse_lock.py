"""rdflib's SPARQL parser races on the first concurrent use of a grammar element and then stays
broken (``Param.postParse2() missing 1 required positional argument: 'tokenList'``), see
src/sparql_parse_lock.py. The race needs a cold grammar, so each attempt runs in a fresh
interpreter; without the lock nearly every attempt breaks."""

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

RACE = """
import sys, threading
sys.path.insert(0, {src!r})
if {locked}:
    import sparql_parse_lock  # noqa: F401
from rdflib import Graph

g = Graph()
queries = [
    "PREFIX c: <http://e/> SELECT ?s (COUNT(?o) AS ?n) WHERE {{ ?s c:p/c:q* ?o . "
    "OPTIONAL {{ ?o c:r ?x }} FILTER(REGEX(STR(?x), 'a')) BIND(1 AS ?b) VALUES ?v {{ 1 2 }} }} GROUP BY ?s",
    "PREFIX c: <http://e/> SELECT DISTINCT ?s WHERE {{ {{ ?s c:p ?o }} UNION {{ ?s c:q ?o }} "
    "MINUS {{ ?s c:z ?o }} FILTER(?o > 3 && LANG(?o) = 'en') }} ORDER BY DESC(?s) LIMIT 5",
]
barrier = threading.Barrier(4)

def run(i):
    barrier.wait()
    try:
        g.query(queries[i % 2])
    except Exception:
        pass

threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
for q in queries:  # the parser must still work afterwards
    g.query(q)
g.update("PREFIX c: <http://e/> INSERT DATA {{ c:a c:p c:b }}")
"""


def run_race(locked: bool) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", RACE.format(src=str(SRC), locked=locked)],
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("attempt", range(6))
def test_concurrent_cold_parses_leave_the_parser_working(attempt):
    result = run_race(locked=True)
    assert result.returncode == 0, result.stderr[-2000:]


def test_install_is_idempotent():
    import rdflib.plugins.sparql.parser as parser
    import rdflib.plugins.sparql.processor as processor

    import sparql_parse_lock

    before = parser.parseQuery
    sparql_parse_lock.install()
    assert parser.parseQuery is before
    assert processor.parseQuery is parser.parseQuery
    assert processor.parseUpdate is parser.parseUpdate
