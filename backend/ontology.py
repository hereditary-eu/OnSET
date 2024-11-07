from pydantic import BaseModel, Field
from rdflib import Graph, URIRef, Literal
from .model import Subject
import pandas as pd
from rdflib.plugins.sparql import prepareQuery


class Prefix(BaseModel):
    ttl_prefix: str = Field(
        "bto", title="Prefix", description="Prefix to be used in the ontology"
    )
    uri: str = Field(
        "https://w3id.org/brainteaser/ontology/schema/",
        title="URI",
        description="URI to be used in the ontology",
    )


class OntologyConfig(BaseModel):
    ttl_prefixes: list[Prefix] = Field(
        [Prefix()],
        title="Prefixes",
        description="List of prefixes to be used in the ontology",
    )
    parent_class_query: str = Field(
        f"""PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?cls
            WHERE {{
                    ?cls rdf:type owl:Class.
                    MINUS {{ ?cls rdfs:subClassOf ?sbcl}}.
            }}
                """,
        title="Parent Class Query",
        description="Query to get the parent classes",
    )
    sub_class_query: str = Field(
        f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?scls
                WHERE {{
                     ?scls rdf:type owl:Class.
                     ?scls rdfs:subClassOf ?cls.
                }}
                """,
        title="Sub Class Query",
        description="Query to get the sub classes",
    )


class OntologyManager:
    def __init__(self, config: OntologyConfig, brainteaser_graph: Graph):
        self.config = config
        self.onto = brainteaser_graph  # TODO enable dynamic loading

    def q_to_df(self, q: str):
        results = list(self.onto.query(q))
        # for r in results:
        #     for t in r:
        #         if isinstance(t, URIRef):
        #             print(t.n3(onto.namespace_manager))
        #         else:
        #             print(t)
        return pd.DataFrame(results).applymap(
            lambda x: x.n3(self.onto.namespace_manager) if hasattr(x, "n3") else x
        )

    def df_to_labels(self, df: pd.DataFrame):
        labeled_df = df.copy()
        for i, row in df.iterrows():
            for j, col in row.items():
                data = list(
                    self.onto.query(
                        f"SELECT ?label WHERE {{ {col} rdfs:label ?label }}"
                    )
                )
                labeled_df.at[i, j] = data[0][0] if data else col
        return labeled_df

    def get_root_classes(self) -> list[Subject]:
        classes = self.q_to_df(self.config.parent_class_query)
        classes_list = classes[0].tolist()
        onto_classes: list[Subject] = self.enrich_subjects(classes_list)
        return onto_classes

    def get_class(self, cls: str) -> list[Subject]:
        query = prepareQuery(
            queryString=self.config.sub_class_query,
            initNs={
                prefix.ttl_prefix: prefix.uri for prefix in self.config.ttl_prefixes
            },
        )
        classes = list(
            self.onto.query(
                self.config.sub_class_query.replace("?cls", cls),
                initBindings={"cls": self.onto.namespace_manager.absolutize(cls)},
            )
        )
        onto_classes: list[Subject] = self.enrich_subjects([cls[0] for cls in classes])
        return onto_classes

    def get_named_individuals(self, cls: str) -> list[Subject]:
        query = f"""
                    PREFIX owl: <http://www.w3.org/2002/07/owl#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    SELECT ?ind
                    WHERE {{
                         ?ind rdf:type owl:NamedIndividual.
                         ?ind rdf:type {cls}.
                    }}
                    """
        individuals = list(
            self.brainteaser_graph.query(
                query,
                # initBindings={"cls": self.brainteaser_graph.namespace_manager.absolutize(cls)},
            )
        )
        onto_classes: list[Subject] = self.enrich_subjects(
            [ind[0] for ind in individuals], subject_type="individual"
        )
        return onto_classes

    def label_for(self, subject: str):
        try:
            return list(
                self.onto.query(
                    f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?label WHERE {{ {subject} rdfs:label ?label }}
                """
                )
            )[0][0].value
        except Exception as e:
            print(e)
            return subject

    def to_readable(self, cls: str | Literal | URIRef):
        if isinstance(cls, Literal):
            return cls.value
        elif isinstance(cls, URIRef) or hasattr(cls, "n3"):
            return cls.n3(self.onto.namespace_manager)
        else:
            return cls

    def outgoing_edges_for(self, cls: str):
        try:
            outgoing_edges = list(
                self.onto.query(
                    f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?edge ?obj WHERE {{ {cls} ?edge ?obj. }}"""
                )
            )
            outgoing_edges_dict = {}
            for edge, obj in outgoing_edges:
                edge_n3 = self.to_readable(edge)
                if edge_n3 not in outgoing_edges_dict:
                    outgoing_edges_dict[edge_n3] = []
                outgoing_edges_dict[edge_n3].append(self.to_readable(obj))

            return outgoing_edges_dict
        except Exception as e:
            print(e)
            return {}

    def refcount(self, cls):
        try:
            refcount = list(
                self.onto.query(
                    f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT (COUNT(?s) as ?count) WHERE {{ ?s ?p {cls}. }}"""
                )
            )
            return refcount[0][0].value
        except Exception as e:
            print(e)
            return 0

    def enrich_subjects(
        self, classes: list[str], subject_type="class"
    ) -> list[Subject]:
        onto_classes: list[Subject] = []
        for col in classes:
            col_ref = col.n3(self.onto.namespace_manager) if hasattr(col, "n3") else col

            outgoing_edges = self.outgoing_edges_for(col_ref)
            # refs = self.refcount(col_ref)
            onto_classes.append(
                Subject(
                    subject_id=col_ref,
                    label=outgoing_edges.get("rdfs:label", [col_ref])[0],
                    spos=outgoing_edges,
                    subject_type=subject_type,
                    # refcount=refs,
                )
            )
        return onto_classes

    def load_full_graph(self) -> list[Subject]:
        roots = self.get_root_classes()

        def enrich_descendants(cls: Subject):
            print("enriching", cls.subject_id)
            try:
                subclasses = self.get_class(cls.subject_id)
                cls.descendants["subClass"] = subclasses
                for subcls in subclasses:
                    enrich_descendants(subcls)
            except Exception as e:
                print(e)
            try:
                named_ind = self.get_named_individuals(cls.subject_id)
                cls.descendants["namedIndividual"] = named_ind
                for ind in named_ind:
                    enrich_descendants(ind)
            except Exception as e:
                print(e)

        for root in roots:
            enrich_descendants(root)
        self.roots_cache = roots
        return roots

    def get_full_classes(self) -> list[Subject]:
        if hasattr(self, "roots_cache"):
            return self.roots_cache
        return self.roots_cache
