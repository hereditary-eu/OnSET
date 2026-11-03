"""api/router/progressive.py: the streaming WebSocket of progressive discovery."""

import threading
import time

from assistant.progressive import ProgressiveRequest
from eval_config import ProgressiveConfig
from fakes import make_ontology, make_sampler

from test_progressive import FLEET_TTL, TREE_TTL, homeport_graph, ship, ship_graph
from assistant.assistant_model import QueryGraph

WS = "/dbpedia/progressive/ws"


def sample(ws, request_id, **request):
    ws.send_json({"type": "sample", "request_id": request_id, "request": request})


def collect(ws, request_id):
    """Events until the done (or error) of ``request_id``."""
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["request_id"] == request_id and event["type"] in ("done", "error"):
            return events


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def check_stream(events, request_id):
    """Start first, done last, every announced modification (and the base) counted once;
    the final modifications by id."""
    assert all(e["request_id"] == request_id for e in events)
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done" and "start" not in types[1:]
    announced = [m["id"] for m in events[0]["modifications"]]
    announced += [m["id"] for e in events if e["type"] == "modifications" for m in e["modifications"]]
    counted = [e["id"] for e in events if e["type"] == "count"]
    assert len(set(announced)) == len(announced)
    assert sorted(counted, key=str) == sorted(announced + [None], key=str)
    # a modification is counted after it was announced
    seen = set()
    for event in events:
        if event["type"] in ("start", "modifications"):
            seen |= {m["id"] for m in event["modifications"]}
        elif event["type"] == "count" and event["id"] is not None:
            assert event["id"] in seen
    counts = {e["id"]: e["count"] for e in events if e["type"] == "count"}
    return counts


def test_stream_order_and_counts(client, fake_manman):
    fake_manman.progressive = make_sampler(make_ontology(FLEET_TTL), config=ProgressiveConfig())
    body = {"graph": homeport_graph().model_dump(), "sample_size": 4, "seed": 1, "sample_constraints": True,
            "constraint_sample_size": 3, "depth": 2, "branching": 2}
    with client.websocket_connect(WS) as ws:
        sample(ws, "r1", **body)
        events = collect(ws, "r1")
    counts = check_stream(events, "r1")
    start, done = events[0], events[-1]
    assert start["cached"] is False and start["depth"] == 2 and start["seed"] == 1
    assert all(m["count"] is None for m in start["modifications"])
    # the same modifications and counts as the whole result
    expected = fake_manman.progressive.sample(ProgressiveRequest(**body))
    assert counts == {None: expected.base_count, **{m.id: m.count for m in expected.modifications}}
    assert {k: done[k] for k in ("depth", "expanded_ids", "failed_constraints", "budget_exhausted", "query_count")} == \
        expected.model_dump(include={"depth", "expanded_ids", "failed_constraints", "budget_exhausted", "query_count"})
    assert done["complete"] is True and done["cached"] is False
    # constraint modifications and a tree level became known while streaming
    batches = [e for e in events if e["type"] == "modifications"]
    assert any(e["parent_id"] is None and e["depth"] == 1 for e in batches)
    assert any(e["depth"] == 2 for e in batches) and [e for e in events if e["type"] == "level"]
    # the complete result is cached
    (key,) = fake_manman.progressive_cache.data
    assert key.startswith("dbpedia:progressive:")
    assert fake_manman.progressive_cache.data[key] == expected


def test_cache_replay(client, fake_manman):
    body = {"graph": ship_graph().model_dump(), "sample_size": 10, "seed": 3}
    with client.websocket_connect(WS) as ws:
        sample(ws, "a", **body)
        live = collect(ws, "a")
        check_stream(live, "a")
        fake_manman.progressive = None  # a cached request must not sample again
        sample(ws, "b", **body)
        replayed = collect(ws, "b")
    assert [e["type"] for e in replayed] == ["start", "done"]
    start, done = replayed
    assert start["cached"] and done["cached"] and done["complete"]
    counts = {e["id"]: e["count"] for e in live if e["type"] == "count"}
    assert start["base_count"] == counts[None] == 2
    assert {m["id"]: m["count"] for m in start["modifications"]} == {k: v for k, v in counts.items() if k is not None}
    # the POST endpoint shares the cache
    result = client.post("/dbpedia/progressive/sample", json=body).json()
    assert {m["id"]: m["count"] for m in result["modifications"]} == {m["id"]: m["count"] for m in start["modifications"]}


def blocking_sampler(fake_manman):
    """A sampler of one count at a time whose counts wait for the returned gate."""
    gate, calls = threading.Event(), []
    sampler = make_sampler(make_ontology(TREE_TTL), config=ProgressiveConfig(parallelism=1, timeout=10))
    run_count = sampler.run_count

    def count(query, timeout):
        calls.append(query)
        gate.wait(10)
        return run_count(query, timeout)

    sampler.run_count = count
    fake_manman.progressive = sampler
    return gate, calls


def test_new_request_cancels(client, fake_manman):
    gate, calls = blocking_sampler(fake_manman)
    body = {"graph": QueryGraph(subjects=[ship()]).model_dump(), "sample_size": 10}
    try:
        with client.websocket_connect(WS) as ws:
            sample(ws, "old", **body, seed=1)
            assert ws.receive_json()["type"] == "start"
            wait_for(lambda: len(calls) == 1)
            sample(ws, "new", **body, seed=2)
            gate.set()
            events = collect(ws, "new")
    finally:
        gate.set()
    # nothing of the old request after the new one started, the old one never finishes
    first_new = next(i for i, e in enumerate(events) if e["request_id"] == "new")
    assert all(e["request_id"] == "new" for e in events[first_new:])
    assert not [e for e in events if e["request_id"] == "old" and e["type"] == "done"]
    check_stream(events[first_new:], "new")
    # the old request's waiting counts were dropped: one ran, then the new request's 1 + 2
    assert len(calls) == 1 + 3
    # only the complete new result is cached
    assert len(fake_manman.progressive_cache.data) == 1


def test_cancel_message_and_disconnect(client, fake_manman):
    gate, calls = blocking_sampler(fake_manman)
    body = {"graph": QueryGraph(subjects=[ship()]).model_dump(), "sample_size": 10, "seed": 1}
    try:
        with client.websocket_connect(WS) as ws:
            sample(ws, "a", **body)
            assert ws.receive_json()["type"] == "start"
            wait_for(lambda: len(calls) == 1)
            ws.send_json({"type": "cancel"})
            gate.set()
            time.sleep(0.2)
            assert len(calls) == 1
            gate.clear()
            # the socket stays usable
            sample(ws, "b", **body)
            assert ws.receive_json()["request_id"] == "b"
            wait_for(lambda: len(calls) == 2)
        # disconnected while counting: the waiting counts are dropped
        gate.set()
        time.sleep(0.2)
        assert len(calls) == 2 and not fake_manman.progressive_cache.data
    finally:
        gate.set()


def test_errors(client):
    with client.websocket_connect(WS) as ws:
        sample(ws, "x", graph=ship_graph().model_dump(), count_subject="nope")
        error = ws.receive_json()
        assert error["type"] == "error" and error["request_id"] == "x" and "count_subject" in error["message"]
        sample(ws, "y", graph=ship_graph().model_dump(), depth=4)
        assert "max_depth" in ws.receive_json()["message"]
        ws.send_json({"type": "sample", "request_id": "z", "request": {"graph": {}, "sample_size": 0}})
        invalid = ws.receive_json()
        assert invalid["type"] == "error" and invalid["request_id"] is None
        # still serving
        sample(ws, "ok", graph=ship_graph().model_dump(), sample_size=10, seed=3)
        assert collect(ws, "ok")[-1]["type"] == "done"


def test_stream_details_carry_instance_counts(client, fake_manman):
    fake_manman.progressive = make_sampler(make_ontology(FLEET_TTL), config=ProgressiveConfig())
    body = {"graph": ship_graph().model_dump(), "sample_size": 4, "seed": 1, "depth": 2, "branching": 2}
    with client.websocket_connect(WS) as ws:
        sample(ws, "r1", **body)
        events = collect(ws, "r1")
    modifications = list(events[0]["modifications"])
    modifications += [m for e in events if e["type"] == "modifications" for m in e["modifications"]]
    # the same details (and counts) as the whole result, links of used properties counted
    expected = fake_manman.progressive.sample(ProgressiveRequest(**body))
    expected_details = {m.id: m.details.model_dump(mode="json") for m in expected.modifications}
    assert {m["id"]: m["details"] for m in modifications} == expected_details
    homeport = next(m for m in modifications if m["label"] == "ship → homeport → country")
    assert homeport["details"]["links"]["homeport_1"]["instance_count"] == 10
    assert homeport["details"]["subjects"]["country_1"]["instance_count"] == 3
