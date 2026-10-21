"""agent/tools.py: tool schemas from signatures/docstrings and ToolCollection.call."""

import enum
import json
from typing import Literal

import pytest
from pydantic import BaseModel

from agent.tools import (
    ToolCollection,
    ToolError,
    ToolResult,
    json_schema_for,
    parse_docstring,
    to_jsonable,
    tool,
)


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Point(BaseModel):
    x: int
    y: int | None = None


class Tools(ToolCollection):
    @tool()
    def f(self, a: str, side: str | None = None, k: int = 3):
        """Do f.

        Args:
            a: the a.
                continued.
            side: optional side.

        Returns:
            something
        """
        return {"a": a, "side": side, "k": k}

    @tool()
    def colored(self, color: Color = Color.RED) -> Point:
        """Return a point."""
        return Point(x=1)

    @tool()
    def fail(self, reason: str):
        """Always fails.

        Args:
            reason: shown to the model.
        """
        raise ToolError(reason)

    @tool()
    def crash(self):
        """A bug."""
        raise ZeroDivisionError("boom")

    @tool(strict=False)
    def loose(self, a: int, b: int = 2):
        """Non-strict."""
        return a + b

    def helper(self):
        return "not a tool"


class MoreTools(Tools):
    @tool()
    def extra(self) -> list[Color]:
        """Inherits the tools of Tools."""
        return [Color.BLUE]


@pytest.mark.parametrize(
    "annotation, schema",
    [
        (str, {"type": "string"}),
        (int, {"type": "integer"}),
        (float, {"type": "number"}),
        (bool, {"type": "boolean"}),
        (dict, {"type": "object"}),
        (list[int], {"type": "array", "items": {"type": "integer"}}),
        (list, {"type": "array", "items": {"type": "string"}}),
        (Literal["source", "target"], {"type": "string", "enum": ["source", "target"]}),
        (Literal[1, 2], {"type": "integer", "enum": [1, 2]}),
        (Color, {"type": "string", "enum": ["red", "blue"]}),
        (int | None, {"type": ["integer", "null"]}),
        (int | str, {"type": "string"}),
    ],
)
def test_json_schema_for(annotation, schema):
    assert json_schema_for(annotation) == schema


def test_json_schema_for_pydantic_model():
    assert json_schema_for(Point) == Point.model_json_schema()


def test_parse_docstring_keeps_all_but_args():
    description, args = parse_docstring(Tools.f.__doc__)
    assert args == {"a": "the a. continued.", "side": "optional side."}
    assert description.startswith("Do f.")
    assert "Returns:" in description and "something" in description
    assert "Args" not in description
    assert parse_docstring(None) == ("", {})


def test_definition_strict():
    definition = {d["name"]: d for d in Tools().definitions()}["f"]
    parameters = definition["parameters"]
    assert definition["type"] == "function" and definition["strict"] is True
    # strict: every parameter is required, optional ones are nullable
    assert parameters["required"] == ["a", "side", "k"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["side"]["type"] == ["string", "null"]
    assert parameters["properties"]["a"]["description"] == "the a. continued."
    assert parameters["properties"]["k"]["default"] == 3
    # None defaults are not repeated
    assert "default" not in parameters["properties"]["side"]


def test_definition_enum_default_and_non_strict():
    definitions = {d["name"]: d for d in Tools().definitions()}
    assert definitions["colored"]["parameters"]["properties"]["color"]["default"] == "red"
    loose = definitions["loose"]
    assert loose["strict"] is False
    assert loose["parameters"]["required"] == ["a"]


def test_collection_only_exposes_tools_and_inherits():
    assert Tools().tool_names() == ["f", "colored", "fail", "crash", "loose"]
    assert MoreTools().tool_names() == Tools().tool_names() + ["extra"]
    assert MoreTools().call("extra", "{}").output == ["blue"]


def test_private_methods_cannot_be_tools():
    with pytest.raises(AssertionError):

        class Bad(ToolCollection):
            @tool()
            def _hidden(self):
                """No."""


def test_call_success():
    result = Tools().call("f", '{"a": "x", "side": null, "k": 1}')
    assert result.ok and result.output == {"a": "x", "side": None, "k": 1}
    assert result.arguments == {"a": "x", "side": None, "k": 1}
    # dict arguments and empty arguments work too
    assert Tools().call("loose", {"a": 1}).output == 3
    assert Tools().call("colored", None).output == {"x": 1}


@pytest.mark.parametrize(
    "name, arguments, error",
    [
        ("f", "{not json", "not valid JSON"),
        ("f", "[1, 2]", "must be a JSON object"),
        ("nope", "{}", "Tool nope not found"),
        ("f", '{"b": 1}', "Unknown arguments ['b']"),
        ("f", "{}", "TypeError"),
        ("fail", '{"reason": "no such class"}', "no such class"),
        ("crash", "{}", "ZeroDivisionError: boom"),
    ],
)
def test_call_never_raises(name, arguments, error):
    result = Tools().call(name, arguments)
    assert not result.ok
    assert error in result.error


def test_tool_error_is_not_reported_as_crash():
    result = Tools().call("fail", {"reason": "expected"})
    assert result.error == "expected"


def test_tool_result_for_model():
    assert json.loads(ToolResult("f", {}, output={"a": 1}).for_model()) == {"a": 1}
    assert json.loads(ToolResult("f", {}, error="bad").for_model()) == {"error": "bad"}


def test_to_jsonable():
    value = {"p": Point(x=1), "c": Color.BLUE, "l": (Point(x=2, y=3),), "n": 4}
    assert to_jsonable(value) == {"p": {"x": 1}, "c": "blue", "l": [{"x": 2, "y": 3}], "n": 4}
