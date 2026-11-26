try:
    from cuml.manifold.umap import UMAP
    from cuml import TSNE
except ImportError:
    print("Cuml not found, using CPU-based libraries.")
    cuml = None
    from sklearn.manifold import TSNE
    from umap import UMAP

from explorative.data_tensor import DataTensor
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
        return self.fit_transform_from_queries([(query, target_properties)])

    def fit_transform_from_queries(self, queries: list[tuple[str, list[str]]]):
        """
        Reduces the tensors of the target properties of the results of several queries in
        one fit, so that their coordinates are comparable (e.g. the previous and the current
        query of a difference view). Each row's target tensors are concatenated; rows missing
        one get no coordinates. The records carry `query_index`, the index of their query.
        """
        frames = []
        rows: list[tuple[int, int]] = []
        vectors: list[np.ndarray] = []
        for query_index, (query, target_properties) in enumerate(queries):
            data = self.oman.q_to_df_values(query)
            if len(data) == 0:
                continue
            for prop in target_properties:
                if prop not in data.columns:
                    raise ValueError(f"Property '{prop}' not found in query results.")
            for row_index, record in enumerate(data[target_properties].itertuples(index=False)):
                if any(not isinstance(value, str) for value in record):
                    continue
                vectors.append(
                    np.concatenate(
                        [
                            np.asarray(DataTensor.from_literal(value).data, dtype=np.float32).ravel()
                            for value in record
                        ]
                    )
                )
                rows.append((query_index, row_index))
            data["query_index"] = query_index
            data["dim_reduced"] = None
            frames.append((query_index, data))
        if len(frames) == 0:
            return []
        if len({len(v) for v in vectors}) > 1:
            raise ValueError("The tensors of the queries have different sizes.")
        if len(vectors) > 0:
            reduced_embedding = self.fit_transform(np.vstack(vectors)).tolist()
            by_query = dict(frames)
            for (query_index, row_index), coords in zip(rows, reduced_embedding):
                by_query[query_index].at[row_index, "dim_reduced"] = coords
        return [record for _, data in frames for record in data.to_dict(orient="records")]
