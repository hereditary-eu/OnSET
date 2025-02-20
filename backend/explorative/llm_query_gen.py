import numpy as np

# %%
import sys
import os

sys.path.insert(0, os.path.abspath("../.."))
sys.path.append(os.path.abspath("../../backend"))
sys.path.append(os.path.abspath(""))

import networkx as nx

from langchain_core.prompts import ChatPromptTemplate
from typing import TypeVar
from sqlalchemy.orm import aliased
from sqlalchemy.sql import text
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from model import Session, Subject
from pydantic import BaseModel, Field, create_model

from ontology import OntologyManager, OntologyConfig, Graph
from explorative.explorative_support import GuidanceManager, select
from explorative.explorative_model import (
    SubjectLink,
    SubjectInDB,
    SubjectLinkDB,
)
from tqdm import tqdm
import pandas as pd

SL = TypeVar("SL")

top_k = 100
seed = 42



class Constraint(BaseModel):
    property: str
    value: str | None
    modifier: str | None


class Entity(BaseModel):
    identifier: str
    type: str
    constraints: list[Constraint] = Field([])


class Relation(BaseModel):
    entity: str
    relation: str
    target: str


class EntitiesRelations(BaseModel):
    relations: list[Relation]
    entities: list[Entity]
    message: str = Field("Found Relations and Entities")


class CandidateRelation(Relation):
    score: float
    link: SubjectLink | None = Field(None)


class CandidateConstraint(Constraint):
    score: float
    type: str
    property: str
    entity: str
    link: SubjectLink | None = Field(None)


class CandidateEntity(Entity):
    score: float
    type: str
    subject: Subject | None = Field(None)


class Candidates(EntitiesRelations):
    relations: list[CandidateRelation]
    entities: list[CandidateEntity]
    constraints: list[CandidateConstraint]


class EnrichedConstraint(Constraint):
    constraint: SubjectLink | None


class EnrichedEntity(Entity):
    subject: Subject
    constraints: list[EnrichedConstraint] = Field([])


class EnrichedRelation(Relation):
    link: SubjectLink | None


class EnrichedEntitiesRelations(EntitiesRelations):
    relations: list[EnrichedRelation] = Field([])
    entities: list[EnrichedEntity] = Field([])


class QueryProgress(BaseModel):
    id: str
    start_time: str
    progress: int = Field(0)
    max_steps: int
    message: str = Field("")
    relations_steps: list[
        EntitiesRelations | Candidates | EnrichedEntitiesRelations
    ] = Field([])
    enriched_relations: EnrichedEntitiesRelations | None = None


class EnrichedDBEntity(Entity, arbitrary_types_allowed=True):
    subject: SubjectInDB | Subject | None


class EnrichedDBRelation(Relation, arbitrary_types_allowed=True):
    link: SubjectLinkDB | SubjectLink | None


def safe_prob(probs: np.array):
    if np.sum(probs) == 0:
        return np.ones(len(probs)) / len(probs)
    else:
        return probs / probs.sum()


def choose_entity(links: list[SL], rs: np.random.RandomState) -> SL:
    probs = np.array([link.instance_count for link in links])
    probs = safe_prob(probs)
    indices = np.arange(len(links))
    choice = rs.choice(indices, p=probs)
    return links[choice]


def random_downgrade(cls: SubjectInDB, rs: np.random.RandomState) -> SubjectInDB:
    def get_subclasses(subcls: SubjectInDB):
        subclasses = [subcls.sub_classes] + [
            get_subclasses(sub) for sub in subcls.sub_classes
        ]
        return [sub for sublist in subclasses for sub in sublist]

    # print(f"downgrading {cls.label}", [sc.label for sc in cls.sub_classes])
    subclasses = [cls] + get_subclasses(cls)
    probs = np.array([float(sc.instance_count) for sc in subclasses])
    probs = safe_prob(probs)
    # print(f"{cls.label} probs", probs)
    choice = rs.choice(np.arange(len(subclasses)), p=probs)
    return subclasses[choice]


def choose_graph(
    max_nodes=4, top_k=100, seed=42, max_tries=5, guidance_man: GuidanceManager = None
):
    rs = np.random.RandomState(seed)
    with Session(guidance_man.engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.autoflush = False

        def downgrade_link_subjects(link: SubjectLinkDB):
            from_downgrade = random_downgrade(link.from_subject, rs)
            to_downgrade = random_downgrade(link.to_subject, rs)
            link.from_id = from_downgrade.subject_id
            link.to_id = to_downgrade.subject_id
            link.from_subject = from_downgrade
            link.to_subject = to_downgrade
            return link

        from_subject_alias = aliased(SubjectInDB, name="from_subject")
        to_subject_alias = aliased(SubjectInDB, name="to_subject")
        best_links_db = session.execute(
            select(SubjectLinkDB)
            .filter(SubjectLinkDB.from_id != SubjectLinkDB.to_id)
            .filter(SubjectLinkDB.to_id != None)
            .order_by(SubjectLinkDB.instance_count.desc())
            .join(
                from_subject_alias,
                SubjectLinkDB.from_subject.of_type(from_subject_alias),
            )
            .join(to_subject_alias, SubjectLinkDB.to_subject.of_type(to_subject_alias))
            # .options(
            #     lazyload(SubjectLinkDB.from_subject.of_type(from_subject_alias)),
            #     lazyload(SubjectLinkDB.to_subject.of_type(to_subject_alias)),
            # )
            .limit(top_k)
        ).all()
        best_links: list[SubjectLinkDB] = [link[0] for link in best_links_db]
        choice = choose_entity(best_links, rs)
        choice_downgraded = downgrade_link_subjects(choice)

        current_links = [
            (
                EnrichedDBRelation(
                    entity=choice_downgraded.from_subject.label,
                    relation=choice.label,
                    target=choice_downgraded.to_subject.label,
                    link=choice_downgraded,
                )
            )
        ]
        current_nodes = {
            subject.label: EnrichedDBEntity(
                identifier=subject.label,
                type=subject.label,
                subject=subject,
            )
            for subject in [
                choice_downgraded.from_subject,
                choice_downgraded.to_subject,
            ]
        }
        retries = 0
        while len(current_nodes) < max_nodes:
            start_node = choose_entity(
                list([nd.subject for nd in current_nodes.values()]), rs
            )
            left_right = rs.choice([0, 1])
            extending_to = left_right == 0
            query = (
                select(SubjectLinkDB)
                .where(SubjectLinkDB.from_id != SubjectLinkDB.to_id)
                .where(SubjectLinkDB.to_id is not None)
                .join(
                    from_subject_alias,
                    SubjectLinkDB.from_subject.of_type(from_subject_alias),
                )
                .join(
                    to_subject_alias, SubjectLinkDB.to_subject.of_type(to_subject_alias)
                )
                .filter(
                    SubjectLinkDB.link_id.not_in(
                        [link.link.link_id for link in current_links]
                    )
                )
            )
            if extending_to:
                query = query.where(SubjectLinkDB.from_id == start_node.subject_id)
            else:
                query = query.where(SubjectLinkDB.to_id == start_node.subject_id)
            # print("Extending to", start_node.label, "extending_to", extending_to)
            new_links = session.execute(
                query.order_by(SubjectLinkDB.instance_count.desc()).limit(top_k)
            ).all()
            new_links: list[SubjectLinkDB] = [link[0] for link in new_links]
            if len(new_links) == 0:
                if retries >= max_tries:
                    break
                retries += 1
                continue
            choice = choose_entity(new_links, rs)

            extending_direction = (
                (choice.from_subject, choice.to_subject)
                if extending_to
                else (choice.to_subject, choice.from_subject)
            )

            downgraded_extend = random_downgrade(extending_direction[1], rs)
            # print(
            #     "Downgraded from",
            #     extending_direction[1].label,
            #     downgraded_extend.label,
            #     "on link",
            #     choice.label,
            # )
            if extending_to:
                choice.to_id = downgraded_extend.subject_id
                choice.to_subject = downgraded_extend
            else:
                choice.from_id = downgraded_extend.subject_id
                choice.from_subject = downgraded_extend
            current_links.append(
                EnrichedDBRelation(
                    entity=choice.from_subject.label,
                    relation=choice.label,
                    target=choice.to_subject.label,
                    link=choice,
                )
            )
            current_nodes.update(
                {
                    subject.label: EnrichedDBEntity(
                        identifier=subject.label,
                        type=subject.label,
                        subject=subject,
                    )
                    for subject in [extending_direction[0], downgraded_extend]
                }
            )
        enriched_erl = EnrichedEntitiesRelations(
            entities=[
                EnrichedEntity(
                    subject=guidance_man.oman.enrich_subject(entity.subject.subject_id),
                    **entity.model_dump(exclude=["subject"]),
                )
                for entity in current_nodes.values()
            ],
            relations=[
                EnrichedRelation(
                    link=SubjectLink.from_db(relation.link, guidance_man.oman),
                    **relation.model_dump(exclude=["link"]),
                )
                for relation in current_links
            ],
        )
        return enriched_erl


def erl_to_templated_query(erl: EnrichedEntitiesRelations):
    qs = []
    for rel in erl.relations:
        qs.append(f"a {rel.entity} has a {rel.relation} with {rel.target}")
    return ", and ".join(qs)


def reduce_erl(erl: EnrichedEntitiesRelations):
    reduced_erl = EntitiesRelations(entities=erl.entities, relations=erl.relations)
    return reduced_erl
