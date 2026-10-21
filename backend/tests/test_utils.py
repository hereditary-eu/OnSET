"""utils.py: grammar/chat helpers and string utilities."""

import json

import pytest
from llama_cpp import LlamaGrammar
from pydantic import BaseModel

from assistant.assistant_model import EntitiesRelations
from utils import (
    chat_content,
    escape_sparql_var,
    few_shot_messages,
    fix_json,
    grammar_for,
    to_readable,
    to_readable_camelcase,
    wrap_iri,
)


class Answer(BaseModel):
    name: str
    count: int


def test_grammar_for():
    grammar = grammar_for(Answer, "Answer")
    assert isinstance(grammar, LlamaGrammar)
    # the root rule is the model, its fields are rules of the grammar
    assert "root" in grammar._grammar and "Answer" in grammar._grammar
    assert "count" in grammar._grammar
    # the ERL grammar of explorative.llm_query builds as well
    assert isinstance(grammar_for(EntitiesRelations, "EntitiesRelations"), LlamaGrammar)


def test_chat_content():
    class Llama:
        def create_chat_completion(self, messages, **kwargs):
            self.args = (messages, kwargs)
            return {"choices": [{"message": {"content": json.dumps({"name": "x", "count": 1})}}]}

    llm = Llama()
    content = chat_content(llm, [{"role": "user", "content": "hi"}], max_tokens=5)
    assert Answer.model_validate_json(content) == Answer(name="x", count=1)
    assert llm.args == ([{"role": "user", "content": "hi"}], {"max_tokens": 5})


def test_few_shot_messages():
    assert few_shot_messages("sys", "q") == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
    ]
    assert few_shot_messages("sys", "q", ("ex_q", "ex_a")) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "ex_q"},
        {"role": "assistant", "content": "ex_a"},
        {"role": "user", "content": "q"},
    ]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("http://dbpedia.org/ontology/Ship", "<http://dbpedia.org/ontology/Ship>"),
        ("https://w3id.org/x", "<https://w3id.org/x>"),
        ("<http://dbpedia.org/ontology/Ship>", "<http://dbpedia.org/ontology/Ship>"),
        ("dbo:Ship", "dbo:Ship"),
    ],
)
def test_wrap_iri(value, expected):
    assert wrap_iri(value) == expected


def test_readable():
    assert to_readable("birthPlace_of") == "birth place of"
    assert to_readable_camelcase("dbo:birthPlace2nd") == "dbo birth Place 2 nd"
    assert to_readable_camelcase("HTMLParser") == "HTML Parser"
    assert to_readable_camelcase(None) == ""


def test_escape_sparql_var():
    assert escape_sparql_var("<http://x.org/a b>") == "_http___x_org_a_b_"
    assert escape_sparql_var("plain_name") == "plain_name"


def test_fix_json_valid_is_unchanged():
    assert fix_json('{"relations": [1, 2], "entities": []}', ["entities", "relations"]) == {
        "relations": [1, 2],
        "entities": [],
    }


def test_fix_json_drops_truncated_item():
    fixed = fix_json('{"relations": [1, 2, {"x": ', item_keys=[])
    assert fixed == {"relations": [1, 2]}


@pytest.mark.xfail(
    strict=True,
    reason="utils.fix_json trims 'relations' twice when it is in item_keys (as in explorative.llm_query)",
)
def test_fix_json_trims_relations_once():
    fixed = fix_json('{"relations": [1, 2, {"x": ', item_keys=["relations"])
    assert fixed == {"relations": [1, 2]}


@pytest.mark.xfail(strict=True, raises=KeyError, reason="utils.fix_json assumes a 'relations' key")
def test_fix_json_without_relations():
    assert fix_json('{"entities": [1, 2, {"x": ', item_keys=["entities"]) == {"entities": [1, 2]}
