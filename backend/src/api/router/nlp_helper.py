import enum
from typing import Any
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel
from sklearn.base import BaseEstimator
from sklearn.decomposition import PCA
from sklearn.metrics import pairwise_distances
from sklearn.manifold import MDS, TSNE, smacof
import numpy as np

from api.config import DEFAULT_MANMAN

manman = DEFAULT_MANMAN

nlp_router = APIRouter(prefix="/nlp")


@nlp_router.get("/embeddings")
def nlp_embeddings(query: str = Query(...)) -> dict[str, Any]:
    data = manman.guidance_man.embedding_model.encode([query]).squeeze().tolist()
    return {"embedding": data}


class ManifoldAlg(str, enum.Enum):
    TSNE = "TSNE"
    MDS = "MDS"
    SMACOF = "smacof"


class ManifoldRequest(BaseModel):
    embeddings: list[list[float]]
    n_out: int = 2
    alg: ManifoldAlg = ManifoldAlg.TSNE
    metric: str = "cosine"


class ClosestRequest(BaseModel):
    embedding: list[float] | None
    query: str | None
    all_embeddings: list[list[float]]
    n_closest: int = 5


class ClosestResponse(BaseModel):
    index: int
    distance: float


@nlp_router.post("/embeddings/closest")
def nlp_embeddings_closest(request: ClosestRequest) -> list[ClosestResponse]:
    if request.query is not None:
        embedding = (
            manman.guidance_man.embedding_model.encode([request.query])
            .squeeze()
            .tolist()
        )
    elif request.embedding is not None:
        embedding = request.embedding

    if embedding is None:
        raise ValueError("Either 'query' or 'embedding' must be provided.")
    embedding = np.array(embedding)
    all_embeddings = np.array(request.all_embeddings)

    distances = pairwise_distances(all_embeddings, embedding.reshape(1, -1), metric="cosine").squeeze()
    closest_indices = np.argsort(distances)[: request.n_closest]
    closest = [
        ClosestResponse(index=int(idx), distance=float(distances[idx]))
        for idx in closest_indices
    ]
    return closest


class SMACOF(BaseEstimator):
    def __init__(
        self, n_components=2, n_init=1, dissimilarity="precomputed", random_state=None
    ):
        self.n_components = n_components
        self.n_init = n_init
        self.dissimilarity = dissimilarity
        self.random_state = random_state

    def fit_transform(self, X, y=None):
        n_lin = np.linspace(-np.pi, np.pi)
        init_pos = np.zeros((X.shape[0], self.n_components))
        if self.n_components == 2:
            init_pos = np.dstack((np.cos(n_lin), np.sin(n_lin)))[0]
        else:
            for i in range(X.shape[0]):
                rs = np.random.RandomState(seed=i)
                init_pos[i, :] = rs.rand(self.n_components)
        return smacof(
            X,
            n_components=self.n_components,
            n_init=self.n_init,
            random_state=self.random_state,
        )[0]


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
        D = 1 - D
        reducer = PCA(n_components=n_out)
    elif alg == "MDS":
        D = D
        reducer = MDS(
            n_components=n_out, n_init=1, dissimilarity="precomputed", random_state=42
        )
    elif alg == "smacof":
        D = D
        reducer = SMACOF(
            n_components=n_out, n_init=1, dissimilarity="precomputed", random_state=42
        )
    else:
        raise ValueError(f"Unknown algorithm: {alg}")

    reduced = reducer.fit_transform(
        D if alg == "MDS" or alg == "TSNE" or alg == "smacof" else embeddings
    )
    return reduced.tolist()
