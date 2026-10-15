from dataclasses import dataclass
import io
from typing import Any
import requests

from fastapi import (
    APIRouter,
    Body,
)

from api.config import DEFAULT_MANMAN
from backend.src.explorative.data_tensor import DataTensorResp
from PIL import Image
from base64 import b64decode
import re
from fastapi.responses import Response

from explorative.dim_reduction import DimensionalityReducer


manman = DEFAULT_MANMAN
multimodal_router = APIRouter(prefix="/search")


@multimodal_router.post("/encode/text")
def encode_text(
    text: str = Body(...),
) -> DataTensorResp:
    return manman.guidance_man.encode(text=text).to_resp()


@multimodal_router.post("/encode/image")
def encode_image(image: str = Body(...)) -> DataTensorResp:
    # validate_image_file(image)
    # url encoded base 64 data
    image_data = re.match(r"^data:image/([^;]+);base64,(.*)$", image)
    if not image_data:
        raise ValueError("Invalid image data")
    print("Decoding image data of:", format(image_data.group(1)))
    image_content = b64decode(image_data.group(2))
    image_pil = Image.open(io.BytesIO(image_content))
    image_pil = image_pil.convert("RGB")
    return manman.guidance_man.encode(image=image_pil).to_resp()


@multimodal_router.post("/dim-reduce")
def dim_reduce(
    query: str = Body(...),
    target_properties: list[str] = Body(...),
    algorithm: str = Body("umap"),
    remove_vectors: bool = Body(True),
) -> list[dict[str, Any]]:
    dim_reducer = DimensionalityReducer(oman=manman.ontology_manager, method=algorithm)

    result = dim_reducer.fit_transform_from_query(
        query=query, target_properties=target_properties
    )
    if remove_vectors:
        for record in result:
            for prop in target_properties:
                if prop in record:
                    del record[prop]
    return result


@dataclass
class ImgCacheEntry:
    content: bytes
    media_type: str
    failed: bool = False


img_cache: dict[str, ImgCacheEntry] = {}


@multimodal_router.get("/wikimedia/proxy")
def wikimedia_proxy(url: str) -> Response:
    if url in img_cache:
        if img_cache[url].failed:
            raise ValueError("Failed to fetch Wikimedia page previously.")
        return Response(
            content=img_cache[url].content, media_type=img_cache[url].media_type
        )
    assert url.startswith("https://commons.wikimedia.org/wiki/")
    resp = requests.get(url, headers={"User-Agent": "OnSET/1.0"})
    if resp.status_code != 200:
        img_cache[url] = ImgCacheEntry(content=b"", media_type="", failed=True)
        raise ValueError(f"Failed to fetch Wikimedia page: {resp.status_code}")
    # Extract the image URL from the Wikimedia page
    assert resp.headers["Content-Type"].startswith("image/")
    img_cache[url] = ImgCacheEntry(
        content=resp.content, media_type=resp.headers["Content-Type"]
    )
    return Response(content=resp.content, media_type=resp.headers["Content-Type"])
