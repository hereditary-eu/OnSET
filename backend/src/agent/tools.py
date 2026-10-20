"""Declaring LLM tools as methods.

A ``ToolCollection`` subclass exposes its methods decorated with ``@tool`` as
function tools. The JSON schema of each tool is derived from the method's
signature (type annotations) and its Google-style docstring::

    class Editor(ToolCollection):
        @tool()
        def add_subject(self, uri: str) -> AssistantSubject:
            \"\"\"Add a class as a new subject to the query graph.

            Args:
                uri: URI of the class, as returned by search_classes.
            \"\"\"

    Editor().definitions()             # Responses API tool definitions
    Editor().call("add_subject", '{"uri": "dbo:Ship"}')

Tools signal failures the model should react to by raising ``ToolError``; any
other exception is reported to the model as well, but logged as a bug.
"""

import enum
import inspect
import json
import re
import traceback
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel

_TOOL_ATTR = "__agent_tool__"

_PRIMITIVES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
}


class ToolError(Exception):
    """An expected tool failure whose message is shown to the model."""


def json_schema_for(annotation: Any) -> dict:
    """JSON schema of a parameter annotation (primitives, Literal, Enum, list, X | None)."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is Literal:
        return {"type": _PRIMITIVES.get(type(args[0]), "string"), "enum": list(args)}
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        schema = json_schema_for(members[0]) if len(members) == 1 else {"type": "string"}
        if len(members) < len(args):
            # nullable: strict tool schemas require every parameter, optional ones accept null
            schema = {**schema, "type": [schema["type"], "null"]}
        return schema
    if origin in (list, tuple, set) or annotation in (list, tuple, set):
        items = json_schema_for(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": items}
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {"type": "string", "enum": [m.value for m in annotation]}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.model_json_schema()
    return {"type": _PRIMITIVES.get(annotation, "string")}


_SECTION = re.compile(r"^\s*(Args|Arguments|Parameters|Returns|Raises|Example|Examples):\s*$")
_ARG_LINE = re.compile(r"^\s*(\*{0,2}\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$")


def parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Split a Google-style docstring into (description, {argument: description}).

    The description keeps every section but ``Args`` (e.g. ``Returns`` and
    examples help the model to use the tool).
    """
    lines = inspect.cleandoc(doc or "").splitlines()
    description: list[str] = []
    arguments: dict[str, str] = {}
    section = None
    current = None
    for line in lines:
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
            current = None
            if section not in ("Args", "Arguments", "Parameters"):
                description.append(line)
            continue
        if section in ("Args", "Arguments", "Parameters"):
            arg = _ARG_LINE.match(line)
            if arg and (len(line) - len(line.lstrip())) <= 4:
                current = arg.group(1).lstrip("*")
                arguments[current] = arg.group(3).strip()
            elif current is not None and line.strip():
                arguments[current] += " " + line.strip()
            continue
        description.append(line)
    return "\n".join(description).strip(), arguments


@dataclass
class ToolSpec:
    """A function tool exposed to the model."""

    name: str
    description: str
    func: Callable
    parameters: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    strict: bool = True

    @classmethod
    def from_method(cls, func: Callable, strict: bool = True) -> "ToolSpec":
        description, arg_docs = parse_docstring(func.__doc__)
        hints = typing.get_type_hints(func)
        parameters: dict[str, dict] = {}
        required: list[str] = []
        for name, param in inspect.signature(func).parameters.items():
            if name == "self" or param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            schema = json_schema_for(hints.get(name, param.annotation))
            if name in arg_docs:
                schema["description"] = arg_docs[name]
            if param.default is not inspect.Parameter.empty and param.default is not None:
                schema["default"] = (
                    param.default.value
                    if isinstance(param.default, enum.Enum)
                    else param.default
                )
            parameters[name] = schema
            # strict mode: every parameter is required, optional ones are nullable
            if strict or param.default is inspect.Parameter.empty:
                required.append(name)
        return cls(
            name=func.__name__,
            description=description,
            func=func,
            parameters=parameters,
            required=required,
            strict=strict,
        )

    def definition(self) -> dict:
        """Tool definition of the OpenAI Responses API."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
                "additionalProperties": False,
            },
            "strict": self.strict,
        }


def tool(strict: bool = True):
    """Expose a public method of a ``ToolCollection`` as a function tool."""

    def wrap(func: Callable) -> Callable:
        assert not func.__name__.startswith("_"), "Only public methods can be tools"
        setattr(func, _TOOL_ATTR, ToolSpec.from_method(func, strict=strict))
        return func

    return wrap


def to_jsonable(obj: Any) -> Any:
    """Tool results as plain JSON values (pydantic models are dumped)."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", exclude_none=True)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, enum.Enum):
        return obj.value
    return obj


@dataclass
class ToolResult:
    name: str
    arguments: dict
    output: Any = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def for_model(self) -> str:
        """The function_call_output handed back to the model."""
        payload = {"error": self.error} if self.error else self.output
        return json.dumps(payload, indent=1, default=str)


class ToolCollection:
    """Base class collecting the ``@tool`` methods of a class and its bases."""

    _tools_: dict[str, ToolSpec] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        tools: dict[str, ToolSpec] = {}
        for base in reversed(cls.__mro__[1:]):
            tools.update(getattr(base, "_tools_", {}))
        for member in vars(cls).values():
            spec = getattr(member, _TOOL_ATTR, None)
            if spec is not None:
                tools[spec.name] = spec
        cls._tools_ = tools

    def tool_names(self) -> list[str]:
        return list(self._tools_)

    def definitions(self) -> list[dict]:
        return [spec.definition() for spec in self._tools_.values()]

    def call(self, name: str, arguments: str | dict | None) -> ToolResult:
        """Run tool ``name`` with the model's (JSON) arguments, never raises."""
        try:
            args = json.loads(arguments or "{}") if isinstance(arguments, str) else dict(arguments or {})
        except json.JSONDecodeError as e:
            return ToolResult(name, {}, error=f"Arguments are not valid JSON: {e}")
        if not isinstance(args, dict):
            return ToolResult(name, {}, error="Arguments must be a JSON object.")
        spec = self._tools_.get(name)
        if spec is None:
            return ToolResult(
                name, args, error=f"Tool {name} not found, available: {self.tool_names()}"
            )
        unknown = set(args) - set(spec.parameters)
        if unknown:
            return ToolResult(name, args, error=f"Unknown arguments {sorted(unknown)} for {name}.")
        try:
            return ToolResult(name, args, output=to_jsonable(spec.func(self, **args)))
        except ToolError as e:
            return ToolResult(name, args, error=str(e))
        except Exception as e:
            traceback.print_exc()
            return ToolResult(name, args, error=f"Tool {name} raised {type(e).__name__}: {e}")
