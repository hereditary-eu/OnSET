try:
    from cuml.manifold.umap import UMAP
    from cuml import TSNE
except ImportError:
    print("Cuml not found, using CPU-based libraries.")
    cuml = None
    from sklearn.manifold import TSNE
    from umap import UMAP

from api.router.multimodal import DataTensorResp
from explorative.explorative_support import DataTensor
from ontology import OntologyManager
import numpy as np


class DimensionalityReducer:
    def __init__(
        self,
        oman: OntologyManager,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
    ):
        self.method = method
        self.n_neighbors = n_neighbors
        self.min_dist = min_dist
        self.oman = oman

        if method == "umap":
            self.reducer = UMAP(n_neighbors=n_neighbors, min_dist=min_dist)
        elif method == "tsne":
            self.reducer = TSNE()
        else:
            raise ValueError(f"Unsupported dimensionality reduction method: {method}")

    def fit_transform(self, X):
        return self.reducer.fit_transform(X)

    def fit_transform_from_query(self, query: str, target_properties: list[str]):
        data = self.oman.q_to_df_values(query)
        if len(data) == 0:
            return []
        combined_vectors = []
        for prop in target_properties:
            if prop not in data.columns:
                raise ValueError(f"Property '{prop}' not found in query results.")
            raw_dts = data[prop].tolist()
            dts = [DataTensor.from_literal(dt) for dt in raw_dts]
            vectors = [tensor.data for tensor in dts]
            combined_vectors.append(vectors)
        # Stack vectors to create a combined feature space
        vectors = np.vstack(combined_vectors)
        reduced_embedding = self.fit_transform(vectors)
        data["dim_reduced"] = [v for v in reduced_embedding.tolist()]
        return data.to_dict(orient="records")
