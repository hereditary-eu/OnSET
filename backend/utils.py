from llama_cpp.llama import Llama
from langchain_community.llms import LlamaCpp
import fnmatch
import json
from typing import Any, List, Optional, Union, Literal
import os
from pathlib import Path
import regex as re
import json_repair


def llama_cpp_langchain_from_pretrained(
    repo_id: str,
    filename: Optional[str],
    additional_files: Optional[List] = None,
    local_dir: Optional[Union[str, os.PathLike[str]]] = None,
    local_dir_use_symlinks: Union[bool, Literal["auto"]] = "auto",
    cache_dir: Optional[Union[str, os.PathLike[str]]] = None,
    **kwargs: Any,
) -> "Llama":
    """Create a Llama model from a pretrained model name or path.
    This method requires the huggingface-hub package.
    You can install it with `pip install huggingface-hub`.

    Args:
        repo_id: The model repo id.
        filename: A filename or glob pattern to match the model file in the repo.
        additional_files: A list of filenames or glob patterns to match additional model files in the repo.
        local_dir: The local directory to save the model to.
        local_dir_use_symlinks: Whether to use symlinks when downloading the model.
        **kwargs: Additional keyword arguments to pass to the Llama constructor.

    Returns:
        A Llama model."""
    try:
        from huggingface_hub import hf_hub_download, HfFileSystem
        from huggingface_hub.utils import validate_repo_id
    except ImportError:
        raise ImportError(
            "Llama.from_pretrained requires the huggingface-hub package. "
            "You can install it with `pip install huggingface-hub`."
        )

    validate_repo_id(repo_id)

    hffs = HfFileSystem()

    files = [
        file["name"] if isinstance(file, dict) else file
        for file in hffs.ls(repo_id, recursive=True)
    ]

    # split each file into repo_id, subfolder, filename
    file_list: List[str] = []
    for file in files:
        rel_path = Path(file).relative_to(repo_id)
        file_list.append(str(rel_path))

    # find the only/first shard file:
    matching_files = [file for file in file_list if fnmatch.fnmatch(file, filename)]  # type: ignore

    if len(matching_files) == 0:
        raise ValueError(
            f"No file found in {repo_id} that match {filename}\n\n"
            f"Available Files:\n{json.dumps(file_list)}"
        )

    if len(matching_files) > 1:
        raise ValueError(
            f"Multiple files found in {repo_id} matching {filename}\n\n"
            f"Available Files:\n{json.dumps(files)}"
        )

    (matching_file,) = matching_files

    subfolder = str(Path(matching_file).parent)
    filename = Path(matching_file).name

    # download the file
    hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        subfolder=subfolder,
        local_dir=local_dir,
        local_dir_use_symlinks=local_dir_use_symlinks,
        cache_dir=cache_dir,
    )

    if additional_files:
        for additonal_file_name in additional_files:
            # find the additional shard file:
            matching_additional_files = [
                file for file in file_list if fnmatch.fnmatch(file, additonal_file_name)
            ]

            if len(matching_additional_files) == 0:
                raise ValueError(
                    f"No file found in {repo_id} that match {additonal_file_name}\n\n"
                    f"Available Files:\n{json.dumps(file_list)}"
                )

            if len(matching_additional_files) > 1:
                raise ValueError(
                    f"Multiple files found in {repo_id} matching {additonal_file_name}\n\n"
                    f"Available Files:\n{json.dumps(files)}"
                )

            (matching_additional_file,) = matching_additional_files

            # download the additional file
            hf_hub_download(
                repo_id=repo_id,
                filename=matching_additional_file,
                subfolder=subfolder,
                local_dir=local_dir,
                local_dir_use_symlinks=local_dir_use_symlinks,
                cache_dir=cache_dir,
            )

    if local_dir is None:
        model_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            subfolder=subfolder,
            local_dir=local_dir,
            local_dir_use_symlinks=local_dir_use_symlinks,
            cache_dir=cache_dir,
            local_files_only=True,
        )
    else:
        model_path = os.path.join(local_dir, filename)
    return LlamaCpp(model_path=model_path, **kwargs)


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


def fix_json(json_str: str, item_keys: list[str] = []) -> str:
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
