from pydantic import BaseModel, Field
from rdflib import Graph, URIRef, Literal
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from model import Subject
import pandas as pd
from rdflib.plugins.sparql import prepareQuery
import numpy as np
from tqdm import tqdm
import traceback

from sqlalchemy import ForeignKey, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


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
        f"""SELECT ?cls
            WHERE {{
                    ?cls rdf:type owl:Class.
                    MINUS {{ ?cls rdfs:subClassOf ?sbcl}}.
            }}
                """,
        title="Parent Class Query",
        description="Query to get the parent classes",
    )
    sub_class_query: str = Field(
        f"""SELECT ?scls
                WHERE {{
                     ?scls rdf:type owl:Class.
                     ?scls rdfs:subClassOf ?cls.
                }}
                """,
        title="Sub Class Query",
        description="Query to get the sub classes",
    )
    property_types: list[str] = Field(["ObjectProperty", "DatatypeProperty"])
    language: str = Field(
        "en", title="Language", description="Language of the ontology"
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
        # return pd.DataFrame(results).map(
        #     lambda x: x.n3(self.onto.namespace_manager) if hasattr(x, "n3") else x
        # )
        return pd.DataFrame(results)

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

    def get_root_classes(self, load_properties=False) -> list[Subject]:
        classes = self.q_to_df(self.config.parent_class_query)
        if classes.empty:
            # if no parent classes, return all classes belonging to owl:Thing
            classes = self.q_to_df(
                f"""
                SELECT ?cls
                WHERE {{
                    ?cls rdf:type owl:Class.
        			?cls rdfs:subClassOf owl:Thing.   
                }}
                """
            )
        classes_list = classes[0].tolist()
        onto_classes: list[Subject] = [
            self.enrich_subject(cls, load_properties=load_properties)
            for cls in classes_list
        ]
        return onto_classes

    def get_classes(self, cls: str, load_properties=False) -> list[Subject]:
        query = prepareQuery(
            queryString=self.config.sub_class_query,
            initNs={
                prefix.ttl_prefix: prefix.uri for prefix in self.config.ttl_prefixes
            },
        )
        classes = list(
            self.onto.query(
                self.config.sub_class_query.replace("?cls", cls),
            )
        )
        onto_classes: list[Subject] = [
            self.enrich_subject(cls[0], load_properties=load_properties)
            for cls in classes
        ]
        return onto_classes

    def get_named_individuals(self, cls: str) -> list[Subject]:
        query = f"""SELECT ?ind
                    WHERE {{
                         ?ind rdf:type owl:NamedIndividual.
                         ?ind rdf:type {cls}.
                    }}
                    """
        individuals = list(
            self.onto.query(
                query,
                # initBindings={"cls": cls},
            )
        )
        onto_classes: list[Subject] = [
            self.enrich_subject(ind[0], subject_type="individual")
            for ind in individuals
        ]

        return onto_classes

    def label_for(self, subject: str):
        try:
            return list(
                self.onto.query(
                    f"""SELECT ?label WHERE {{ {subject} rdfs:label ?label }}
                """
                )
            )[0][0].value
        except Exception as e:
            print(traceback.format_exc())
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
                SELECT ?edge ?obj WHERE {{ {cls} ?edge ?obj. }}"""
                )
            )
            outgoing_edges_dict: dict[str, list[str] | dict[str, str]] = {}
            for edge, obj in outgoing_edges:
                edge_n3 = self.to_readable(edge)
                if edge_n3 not in outgoing_edges_dict:
                    outgoing_edges_dict[edge_n3] = []
                if isinstance(obj, Literal) and hasattr(obj, "language"):
                    if obj.language == self.config.language or obj.language is None:
                        outgoing_edges_dict[edge_n3].append(obj.value)
                else:
                    outgoing_edges_dict[edge_n3].append(self.to_readable(obj))

            return outgoing_edges_dict
        except Exception as e:
            print(traceback.format_exc())
            return {}

    def refcount(self, cls):
        try:
            refcount = list(
                self.onto.query(
                    f"""
                SELECT (COUNT(?s) as ?count) WHERE {{ ?s ?p {cls}. }}"""
                )
            )
            return refcount[0][0].value
        except Exception as e:
            print(traceback.format_exc())
            return 0

    def properties_for(
        self, cls: str, property_type: str = "ObjectProperty"
    ) -> list[Subject]:
        try:
            properties = list(
                self.onto.query(
                    f"""
                SELECT ?prop WHERE {{ 
                ?prop rdf:type owl:{property_type}.
                ?prop rdfs:domain {cls}.
                }}"""
                )
            )
            props_mapped: list[Subject] = [
                self.enrich_subject(prop[0], subject_type="individual")
                for prop in properties
            ]

            return props_mapped
        except Exception as e:
            print(traceback.format_exc())
            return {}

    def enrich_subject(self, cls: str, subject_type="class", load_properties=False):

        col_ref = cls.n3(self.onto.namespace_manager) if hasattr(cls, "n3") else cls

        outgoing_edges = self.outgoing_edges_for(col_ref)
        subject = Subject(
            subject_id=col_ref,
            label=outgoing_edges.get("rdfs:label", [col_ref])[0],
            spos=outgoing_edges,
            subject_type=subject_type,
            # refcount=refs,
        )
        if load_properties:
            subject.properties = {
                prop_type: self.properties_for(col_ref, property_type=prop_type)
                for prop_type in self.config.property_types
            }
        return subject
        # refs = self.refcount(col_ref)

    def load_full_graph(self, depth=10) -> list[Subject]:
        roots = self.get_root_classes(load_properties=True)[1:]

        def enrich_descendants(cls: Subject, d=depth):
            # print("enriching", cls.subject_id)
            cls.total_descendants = 1  # self
            if d <= 0:
                return []
            try:
                subclasses = self.get_classes(cls.subject_id, load_properties=True)
                cls.descendants["subClass"] = [
                    enrich_descendants(subcls, d=d - 1) for subcls in subclasses
                ]
            except Exception as e:
                print(traceback.format_exc())
            try:
                named_ind = self.get_named_individuals(cls.subject_id)
                cls.descendants["namedIndividual"] = [
                    enrich_descendants(ni, d=d - 1) for ni in named_ind
                ]
            except Exception as e:
                print(traceback.format_exc())

            return cls

        roots = [enrich_descendants(cls) for cls in tqdm(roots)]
        self.roots_cache = roots
        return roots

    def get_full_classes(self) -> list[Subject]:
        if hasattr(self, "roots_cache"):
            return self.roots_cache
        graph = self.load_full_graph()
        return graph
