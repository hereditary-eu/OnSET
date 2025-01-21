# %%
import numpy as np

# %%
import sys
import os

sys.path.insert(0, os.path.abspath("../.."))
sys.path.append(os.path.abspath("../../backend"))
sys.path.append(os.path.abspath(""))

import networkx as nx
from typing import TypeVar
from sqlalchemy.orm import aliased
from sqlalchemy.sql import text
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from backend.model import (
    Session,
)

from backend.ontology import OntologyManager, OntologyConfig, Graph
from backend.explorative_support import TopicModelling, select
from backend.llm_query import (
    Entity,
    Relation,
    EntitiesRelations,
    EnrichedEntity,
    EnrichedRelation,
    EnrichedEntitiesRelations,
    SubjectLink,
    SubjectInDB,
    SubjectLinkDB,
)
from tqdm import tqdm
import pandas as pd

store = SPARQLStore(
    "http://localhost:7012/",
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
)
graph = Graph(store=store)

config = OntologyConfig()

ontology_manager = OntologyManager(config, graph)
topic_man = TopicModelling(ontology_manager)

# %%
top_k = 100
seed = 42

# %%

SL = TypeVar("SL")


class EnrichedDBEntity(Entity, arbitrary_types_allowed=True):
    subject: SubjectInDB


class EnrichedDBRelation(Relation, arbitrary_types_allowed=True):
    link: SubjectLinkDB


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


def choose_graph(max_nodes=4, top_k=top_k, seed=seed, max_tries=5):
    rs = np.random.RandomState(seed)
    with Session(topic_man.engine) as session:
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
                choice_downgraded.to_id = downgraded_extend.subject_id
                choice_downgraded.to_subject = downgraded_extend
            else:
                choice_downgraded.from_id = downgraded_extend.subject_id
                choice_downgraded.from_subject = downgraded_extend
            if extending_to:
                current_links.append(
                    EnrichedDBRelation(
                        entity=choice.from_subject.label,
                        relation=choice.label,
                        target=choice_downgraded.to_subject.label,
                        link=choice_downgraded,
                    )
                )
            else:
                current_links.append(
                    EnrichedDBRelation(
                        entity=choice_downgraded.from_subject.label,
                        relation=choice.label,
                        target=choice.to_subject.label,
                        link=choice_downgraded,
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
                    subject=ontology_manager.enrich_subject(entity.subject.subject_id),
                    **entity.model_dump(exclude=["subject"]),
                )
                for entity in current_nodes.values()
            ],
            relations=[
                EnrichedRelation(
                    link=SubjectLink.from_db(relation.link, ontology_manager),
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

if __name__ == "__main__":
# %%
    llama_model = topic_man.llama_model

    # %%
    messages = [
        {
            "role": "system",
            "content": """"You are a helpful assistant turning relational knowledge into natural language.""",
        },
        {
            "role": "user",
            "content": EntitiesRelations(
                entities=[
                    Entity(
                        identifier="person 1",
                        type="person",
                    ),
                    Entity(
                        identifier="place 1",
                        type="place",
                    ),
                    Entity(
                        identifier="company 1",
                        type="person",
                    ),
                ],
                relations=[
                    Relation(
                        entity="company 1",
                        relation="employs",
                        target="person 1",
                    ),
                    Relation(
                        entity="person 1",
                        relation="residence",
                        target="place 1",
                    ),
                ],
            ).model_dump_json(),
        },
        {
            "role": "assistant",
            "content": "a person is employed by a company and the same person resides in a place",
        },
    ]


    # %%
    n_examples = 300
    n_nodes = [3, 5, 10]
    resulting_examples = []
    progress = tqdm(total=n_examples * len(n_nodes))
    for n_node in n_nodes:
        for i in range(n_examples):
            try:
                erl = choose_graph(seed=i, max_nodes=n_node)
                reduced_erl = reduce_erl(erl)
                response = llama_model.create_chat_completion(
                    # grammar=self.grammar_erl,
                    messages=messages
                    + [
                        {
                            "role": "user",
                            "content": reduced_erl.model_dump_json(),
                        }
                    ],
                    max_tokens=4096,
                    temperature=0.7,  # get wild :)
                )
                templated_query = erl_to_templated_query(erl)
                progress.update(1)
                resulting_examples.append(
                    {
                        "erl": erl.model_dump_json(),
                        "response": response["choices"][0]["message"]["content"],
                        "generator": "llama",
                        "n_nodes": n_node,
                        "seed": i,
                    }
                )
                resulting_examples.append(
                    {
                        "erl": erl.model_dump_json(),
                        "response": templated_query,
                        "generator": "templated",
                        "n_nodes": n_node,
                        "seed": i,
                    }
                )
            except Exception as e:
                print(e)
                continue
            resulting_examples_df = pd.DataFrame(resulting_examples)
            resulting_examples_df.to_csv("llama_examples.csv")

    # %%


    # %% [markdown]
    #
