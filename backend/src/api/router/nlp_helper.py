from typing import Any
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel
from sklearn.decomposition import PCA
from sklearn.metrics import pairwise_distances
from sklearn.manifold import MDS, TSNE
import numpy as np

from api.config import DEFAULT_MANMAN

manman = DEFAULT_MANMAN

nlp_router = APIRouter(prefix="/nlp")


@nlp_router.get("/embeddings")
def nlp_embeddings(query: str = Query(...)) -> dict[str, Any]:
    data = manman.guidance_man.embedding_model.encode([query]).squeeze().tolist()
    return {"embedding": data}


class ManifoldRequest(BaseModel):
    embeddings: list[list[float]]
    n_out: int = 2
    alg: str = "TSNE"
    metric: str = "cosine"


@nlp_router.post("/embeddings/manifold")
def nlp_embeddings_manifold(request: ManifoldRequest = Body(...)) -> list[list[float]]:
    embeddings = request.embeddings
    n_out = request.n_out
    alg = request.alg
    embeddings = np.array(embeddings)

    D = pairwise_distances(embeddings, metric=request.metric)
    if alg == "TSNE":
        reducer = TSNE(
            n_components=n_out,
            perplexity=np.min([50, embeddings.shape[0] - 1]),
            metric="precomputed",
            init="random",
        )
    elif alg == "PCA":
        reducer = PCA(n_components=n_out)
    elif alg == "MDS":
        D = 1 - D
        reducer = MDS(n_components=n_out, dissimilarity="precomputed", random_state=42)
    else:
        raise ValueError(f"Unknown algorithm: {alg}")

    reduced = reducer.fit_transform(D if alg == "MDS" or alg == "TSNE" else embeddings)
    return reduced.tolist()
