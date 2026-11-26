"""POST /{config_id}/search/dim-reduce: tensors of several queries reduced in one fit."""

import json

import numpy as np
import pandas as pd
import pytest

from explorative.dim_reduction import DimensionalityReducer


def tensor(*values: float) -> str:
    return json.dumps({"data": list(values), "type": "float32", "shape": [len(values)]})


RESULTS = {
    "current": pd.DataFrame(
        {"s": ["a", "b", "c"], "emb": [tensor(1, 2), tensor(3, 4), None]}, dtype=object
    ),
    "previous": pd.DataFrame({"s": ["d"], "vec": [tensor(5, 6)]}, dtype=object),
    "wide": pd.DataFrame({"s": ["e"], "vec": [tensor(1, 2, 3)]}, dtype=object),
}


@pytest.fixture
def fits(monkeypatch, fake_manman):
    monkeypatch.setattr(fake_manman.ontology_manager, "q_to_df_values", lambda q: RESULTS[q].copy())
    fitted = []

    def fit_transform(self, X):
        fitted.append(X)
        return np.asarray(X)[:, :2] * 10

    monkeypatch.setattr(DimensionalityReducer, "fit_transform", fit_transform)
    return fitted


def test_single_query(client, fits):
    resp = client.post(
        "/dbpedia/search/dim-reduce", json={"query": "current", "target_properties": ["emb"]}
    )
    assert resp.status_code == 200, resp.text
    records = resp.json()
    assert [r["dim_reduced"] for r in records] == [[10, 20], [30, 40], None]
    assert all(r["query_index"] == 0 and "emb" not in r for r in records)


def test_compare_queries_share_one_fit(client, fits):
    resp = client.post(
        "/dbpedia/search/dim-reduce",
        json={
            "query": "current",
            "target_properties": ["emb"],
            "compare": [{"query": "previous", "target_properties": ["vec"]}],
        },
    )
    assert resp.status_code == 200, resp.text
    records = resp.json()
    assert len(fits) == 1 and fits[0].shape == (3, 2)
    assert [(r["s"], r["query_index"], r["dim_reduced"]) for r in records] == [
        ("a", 0, [10, 20]),
        ("b", 0, [30, 40]),
        ("c", 0, None),
        ("d", 1, [50, 60]),
    ]
    assert all("emb" not in r and "vec" not in r for r in records)


def test_compare_queries_of_different_sizes(client, fits):
    with pytest.raises(ValueError, match="different sizes"):
        client.post(
            "/dbpedia/search/dim-reduce",
            json={
                "query": "current",
                "target_properties": ["emb"],
                "compare": [{"query": "wide", "target_properties": ["vec"]}],
            },
        )
