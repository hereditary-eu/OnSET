from typing import Any

import json_repair
import regex as re
from llama_cpp import LlamaGrammar
from pydantic import BaseModel

# has to be installed from fork until merged!
from llama_cpp_agent.gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import (
    generate_gbnf_grammar_from_pydantic_models,
)


def grammar_for(model: type[BaseModel], root_name: str) -> LlamaGrammar:
    """GBNF grammar restricting llama.cpp output to the JSON of ``model``."""
    return LlamaGrammar.from_string(
        generate_gbnf_grammar_from_pydantic_models(
            [model], root_name, add_inner_thoughts=False
        )
    )


def chat_content(llm: Any, messages: list[dict], **kwargs) -> str:
    """Run a llama.cpp chat completion and return the message content."""
    response = llm.create_chat_completion(messages=messages, **kwargs)
    return response["choices"][0]["message"]["content"]


def few_shot_messages(
    system: str, query: str, example: tuple[str, str] | None = None
) -> list[dict]:
    """System prompt, an optional (user, assistant) example and the user query."""
    messages = [{"role": "system", "content": system}]
    if example is not None:
        messages.extend(
            [
                {"role": "user", "content": example[0]},
                {"role": "assistant", "content": example[1]},
            ]
        )
    messages.append({"role": "user", "content": query})
    return messages


def to_readable(s: str):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s).replace("_", " ").lower()


def to_readable_camelcase(txt: str, split_chars=["_", "-", "/", ":", "."]):
    if txt is None:
        return ""
    txt = re.sub(r"([a-z])([A-Z])", r"\1 \2", txt)
    txt = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", txt)
    txt = re.sub(r"([a-z])([0-9])", r"\1 \2", txt)
    txt = re.sub(r"([0-9])([a-z])", r"\1 \2", txt)
    for split_char in split_chars:
        txt = " ".join(txt.split(split_char))
    return txt


def escape_sparql_var(
    var: str,
    replace_chars=[
        "<",
        ">",
        "(",
        ")",
        "{",
        "}",
        "[",
        "]",
        "|",
        "?",
        "*",
        "+",
        ".",
        "^",
        "$",
        "\\",
        "/",
        "!",
        '"',
        "'",
        "`",
        "~",
        "@",
        "#",
        "%",
        "&",
        "=",
        ";",
        ":",
        ",",
        " ",
    ],
) -> str:
    for char in replace_chars:
        var = var.replace(char, "_")
    return var


def wrap_iri(s: str) -> str:
    if s.startswith("http://") or s.startswith("https://") or ":" not in s:
        return f"<{s}>"
    return s


def fix_json(json_str: str, item_keys: list[str] = []) -> dict:
    resp = json_repair.repair_json(json_str, logging=True)
    log = []
    fixed_response = ""
    if isinstance(resp, tuple):
        fixed_response = resp[0]
        log = resp[1]
    else:
        fixed_response = resp
    if len(log) > 0:
        print(f"Error in JSON: {json_str}")
        print(log)
        print("removing last element")
        for key in item_keys:
            if key in fixed_response and isinstance(fixed_response[key], list):
                fixed_response[key] = fixed_response[key][:-1]
        fixed_response["relations"] = fixed_response["relations"][:-1]
    # resp_str = json.dumps(fixed_response)
    return fixed_response
