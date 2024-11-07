from rdflib import Graph, URIRef, Literal
from rdflib.plugins.sparql import prepareQuery
import networkx as nx

from typing import Union
from fastapi import FastAPI, Query, File, UploadFile, Body, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Annotated

from dataclasses import dataclass, field

from psycopg.rows import dict_row
import psycopg
import requests as req

import os
from .model import *
from .ontology import *


base_path = "data"
onto_path = base_path + "/brainteaser-ontology/bto.ttl"


brainteaser_graph = Graph().parse(onto_path, format="turtle")
brainteaser_graph.bind("bto", "http://www.semanticweb.org/ontologies/2020/3/bto#")

ontology_manager = OntologyManager(OntologyConfig(), brainteaser_graph)


source_classes = ontology_manager.q_to_df(
    f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?cls
                WHERE {{
                     ?cls rdf:type owl:Class.
                     MINUS {{ ?cls rdfs:subClassOf ?sbcl}}.
                }}
                """
)


app = FastAPI(title="Ontology Provenance API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return "Welcome to the Ontology Provenance API"


config = OntologyConfig()


@app.post("/management/ontology")
def load_ontology(
    ontology: UploadFile,
):
    brainteaser_graph = Graph().parse(ontology.file, format="turtle")
    for prefix in config.ttl_prefixes:
        brainteaser_graph.bind(prefix.ttl_prefix, prefix.uri)
    return {"ontology": ontology.filename, "prefixes": config}



@app.get("/classes/full")
def get_full_classes() -> list[Subject]:
    roots = get_root_classes()

    def enrich_descendants(cls: Subject):
        print("enriching", cls.subject_id)
        try:
            subclasses = get_class(cls.subject_id)
            cls.descendants["subClass"] = subclasses
            for subcls in subclasses:
                enrich_descendants(subcls)
        except Exception as e:
            print(e)
        try:
            named_ind = get_named_individuals(cls.subject_id)
            cls.descendants["namedIndividual"] = named_ind
            for ind in named_ind:
                enrich_descendants(ind)
        except Exception as e:
            print(e)

    for root in roots:
        enrich_descendants(root)
    return roots


@app.get("/classes/roots")
def get_root_classes() -> list[Subject]:
    classes = q_to_df(config.parent_class_query)
    classes_list = classes[0].tolist()
    onto_classes: list[Subject] = enrich_subjects(classes_list)
    return onto_classes


@app.get("/classes/subclasses")
def get_class(cls: str = Query()) -> list[Subject]:
    query = prepareQuery(
        queryString="""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?scls
                WHERE {
                     ?scls rdf:type owl:Class.
                     ?scls rdfs:subClassOf ?cls.
                }
                """,
        initNs={prefix.ttl_prefix: prefix.uri for prefix in config.ttl_prefixes},
    )
    # print(cls, query.algebra, query._original_args, query.prologue)
    classes = list(
        brainteaser_graph.query(
            config.sub_class_query.replace("?cls", cls),
            initBindings={"cls": brainteaser_graph.namespace_manager.absolutize(cls)},
        )
    )
    onto_classes: list[Subject] = enrich_subjects([cls[0] for cls in classes])
    return onto_classes


@app.get("/classes/named-individuals")
def get_named_individuals(cls: str = Query()) -> list[Subject]:
    query = f"""
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                SELECT ?ind
                WHERE {{
                     ?ind rdf:type owl:NamedIndividual.
                     ?ind rdf:type {cls}.
                }}
                """
    # print(cls, query.algebra, query._original_args, query.prologue)
    individuals = list(
        brainteaser_graph.query(
            query,
            # initBindings={"cls": brainteaser_graph.namespace_manager.absolutize(cls)},
        )
    )
    onto_classes: list[Subject] = enrich_subjects(
        [ind[0] for ind in individuals], subject_type="individual"
    )
    return onto_classes
