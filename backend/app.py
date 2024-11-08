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

config = OntologyConfig()

ontology_manager = OntologyManager(config, brainteaser_graph)
# ontology_manager.load_full_graph()

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
    roots = ontology_manager.get_full_classes()
    return roots


@app.get("/classes/roots")
def get_root_classes() -> list[Subject]:
    return ontology_manager.get_root_classes()


@app.get("/classes/subclasses")
def get_class(cls: str = Query()) -> list[Subject]:
    return ontology_manager.get_classes(cls)


@app.get("/classes/named-individuals")
def get_named_individuals(cls: str = Query()) -> list[Subject]:
    return ontology_manager.get_named_individuals(cls)
