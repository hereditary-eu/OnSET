from __future__ import annotations
from sentence_transformers import SentenceTransformer
import torch
from langchain_core.language_models import LLM
from langchain_core.prompts import ChatPromptTemplate
from bertopic import BERTopic
from bertopic.representation import LangChain
from hashlib import sha256
import regex as re
from sqlalchemy import text, inspect, create_engine, select, delete
from sqlalchemy.orm import Session
from tqdm import tqdm
import pandas as pd

from model import Subject
from ontology import OntologyManager
from utils import llama_cpp_langchain_from_pretrained

from explorative_model import (
    BasePostgres,
    TopicDB,
    SubjectLinkDB,
    SubjectLink,
    SubjectInDB,
    FuzzyQueryResult,
    FuzzyQuery,
    N_EMBEDDINGS,
    RETURN_TYPE,
    RELATION_TYPE,
    FUZZY_QUERY_ORDER,
    FuzzyQueryResults,
    Topic,
)

# System prompt describes information given to all conversations
TOPIC_LLAMA3_PROMPT_SYSTEM = """

You are a helpful, respectful and honest assistant for labeling topics. You should provide a short label for a topic based on the information provided about the topic. The topic is described by a set of documents and keywords. The label should be a short phrase that captures the essence of the topic. The label should be concise and informative, and should not contain any information that is not directly related to the topic.
"""

# Example prompt demonstrating the output we are looking for
TOPIC_LLAMA3_PROMPT_EXAMPLE = (
    """
I have a topic that contains the following documents:
- Traditional diets in most cultures were primarily plant-based with a little meat on top, but with the rise of industrial style meat production and factory farming, meat has become a staple food.
- Meat, but especially beef, is the word food in terms of emissions.
- Eating meat doesn't make you a bad person, not eating meat doesn't make you a good one.

The topic is described by the following keywords: 'meat, beef, eat, eating, emissions, steak, food, health, processed, chicken'.

Based on the information about the topic above, please create a short label of this topic. Make sure you to only return the label and nothing more.
""",
    """
Environmental impacts of eating meat
""",
)

# Our main prompt with documents ([DOCUMENTS]) and keywords ([KEYWORDS]) tags
TOPIC_LLAMA3_PROMPT_MAIN = """
I have a topic that contains the following documents:
[DOCUMENTS]

The topic is described by the following keywords: '[KEYWORDS]'.

Based on the information about the topic above, please create a short label of this topic. Make sure you to only return the label and nothing more.
"""


def to_readable(s: str):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s).replace("_", " ").lower()


class TopicModelling:
    def __init__(
        self,
        oman: OntologyManager,
        device=None,
        conn_str: str = "postgresql+psycopg://postgres:postgres@localhost:5434/onset",
        llm_model_id: str = "NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
        langchain_model: LLM = None,
        ctx_size=10000,
    ) -> None:
        self.oman = oman
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device
        # This model supports two prompts: "s2p_query" and "s2s_query" for sentence-to-passage and sentence-to-sentence tasks, respectively.
        # They are defined in `config_sentence_transformers.json`
        self.query_prompt_name = "s2p_query"
        self.llm_model_id = llm_model_id
        self.langchain_model = langchain_model
        self.ctx_size = ctx_size
        self.engine = create_engine(conn_str)
        identifier_results = self.oman.onto.query(
            "SELECT ?s  ?p ?o WHERE {?s ?o ?p.} LIMIT 25"
        )
        if len(identifier_results) == 1:
            raise ValueError(
                "Ontology is empty or SPARQL endpoint is not reachable",
                identifier_results,
            )
        self.identifier = sha256(
            ".".join([str(e) for e in identifier_results]).encode()
        ).hexdigest()
        self.__lama_model = None
        self.__embedding_model = None

    @property
    def llama_model(self) -> LLM:
        if self.__lama_model is not None:
            return self.__lama_model
        print("Loading LLM model", self.llm_model_id, self.langchain_model)
        if self.llm_model_id is None and self.langchain_model is None:
            raise ValueError("No LLM model id specified")

        if self.langchain_model is not None:
            self.__lama_model = self.langchain_model
        elif self.llm_model_id is not None:
            self.__lama_model = llama_cpp_langchain_from_pretrained(
                repo_id=self.llm_model_id,
                filename="*.Q8_0.gguf",
                n_batch=2048,
                n_ubatch=512,
                n_ctx=self.ctx_size,
                n_gpu_layers=-1,
                n_threads=6,
                embedding=False,
            )
        return self.__lama_model

    @property
    def embedding_model(self):
        if self.__embedding_model is not None:
            return self.__embedding_model
        self.__embedding_model = SentenceTransformer(
            "dunzhang/stella_en_400M_v5",
            trust_remote_code=True,
            config_kwargs={
                "use_memory_efficient_attention": False,
                "unpad_inputs": False,
            },
            revision="eb1ce34a33908596b61c83a88903b5f5f30beaa9",  # problematic merge, wrong dimensionality
        ).to(self.device)
        # self.embedding_model = SentenceTransformer(
        #     "paraphrase-MiniLM-L6-v2",
        # ).to(device)
        return self.__embedding_model

    def initialize_topics(self, force: bool = False, delete_tables: bool = False):
        init_topics = False
        with Session(self.engine) as session:
            insp = inspect(self.engine)
            if not insp.has_table("topics", schema="public") or not insp.has_table(
                "subjects", schema="public"
            ):
                init_topics = True
            else:
                init_topics = (
                    session.execute(
                        select(TopicDB.topic_id).where(
                            TopicDB.onto_hash == self.identifier
                        )
                    ).first()
                    is None
                )
        if init_topics or force:
            print("Initializing topics")
            with Session(self.engine) as session:
                session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.commit()
            if delete_tables:
                BasePostgres.metadata.drop_all(self.engine)

            BasePostgres.metadata.create_all(self.engine)
            with Session(self.engine) as session:
                session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                session.execute(
                    delete(TopicDB).where(TopicDB.onto_hash == self.identifier)
                )
                session.execute(
                    delete(SubjectInDB).where(SubjectInDB.onto_hash == self.identifier)
                )
                session.execute(
                    delete(SubjectLinkDB).where(
                        SubjectLinkDB.onto_hash == self.identifier
                    )
                )
                session.commit()

            # embed first, then model to make sure subjects are available for topics
            self.embed_relations()
            self.model_topics()

    def __get_named_individuals_desc(self, c: Subject) -> dict[str, str]:
        nis = self.oman.get_named_individuals(c.subject_id)
        return {ne.subject_id: f"{ne.label} is a {c.label}" for ne in nis}

    def __get_properties_desc(self, c: Subject) -> dict[str, str]:
        prop_docs = {}
        for pt, p in c.properties.items():
            for prop in p:
                prop_doc = f"{c.label} \n"
                if prop.label.startswith("<"):
                    continue
                if pt == "DatatypeProperty":
                    prop_doc += f"{c.label} is defined by {to_readable(prop.label)}. "
                else:
                    prop_doc += f"{c.label} {to_readable(prop.label)} "
                if "rdfs:range" in prop.spos:
                    range = self.oman.enrich_subject(
                        prop.spos["rdfs:range"].first_value()
                    )
                    if range.label.startswith("<"):
                        continue
                    prop_doc += f" of type {range.label}. "
                if "rdfs:subPropertyOf" in prop.spos:
                    subprop = self.oman.enrich_subject(
                        prop.spos["rdfs:subPropertyOf"].first_value()
                    )
                    if subprop.label.startswith("<"):
                        continue
                    prop_doc += f" is subproperty of {subprop.label}. "
                prop_docs[prop.subject_id] = prop_doc
        return prop_docs

    def __get_subclass_desc(self, c: Subject) -> list[str]:
        cls_doc = f"{c.label}"
        if "rdfs:subClassOf" in c.spos:
            subcls = self.oman.enrich_subject(c.spos["rdfs:subClassOf"].first_value())
            if subcls.label.startswith("<"):
                return []
            cls_doc += f" is subclass of  {subcls.label}\n"
        return [cls_doc]

    def build_docs(self):
        classes = self.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        classes_enriched = [
            self.oman.enrich_subject(c, load_properties=True)
            for c in tqdm(classes, desc="Enriching classes")
        ]

        documents: list[dict[str, str]] = []
        for c in classes_enriched[1:]:
            if c.label.startswith("<"):
                print("ignoring", c.label)
                continue
            documents.extend(
                [
                    {
                        "subject_id": c.subject_id,
                        "named_individual_id": ne_id,
                        "doc": ne_doc,
                        "type": "named_individual",
                    }
                    for ne_id, ne_doc in self.__get_named_individuals_desc(c).items()
                ]
            )
            documents.extend(
                {
                    "subject_id": c.subject_id,
                    "property_id": prop_id,
                    "doc": prop_doc,
                    "type": "property",
                }
                for prop_id, prop_doc in self.__get_properties_desc(c).items()
            )
            documents.extend(
                {
                    "subject_id": c.subject_id,
                    "doc": subcls_doc,
                    "type": "subclass",
                }
                for subcls_doc in self.__get_subclass_desc(c)
            )
        return pd.DataFrame(documents)

    def model_topics(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", TOPIC_LLAMA3_PROMPT_SYSTEM),
                ("human", TOPIC_LLAMA3_PROMPT_EXAMPLE[0]),
                ("ai", TOPIC_LLAMA3_PROMPT_EXAMPLE[1]),
            ]
        )
        prompted_model = prompt | self.llama_model
        representation_llama = LangChain(
            prompted_model, TOPIC_LLAMA3_PROMPT_MAIN, diversity=0.3
        )
        docs = self.build_docs()
        # Create an instance of the Llama class and load the model

        # Create the provider by passing the Llama class instance to the LlamaCppPythonProvider class

        topic_model_llm = BERTopic(
            embedding_model=self.embedding_model,
            verbose=True,
            representation_model=representation_llama,
        )
        topic_model_llm.fit(docs["doc"])
        hierarchical_topics = topic_model_llm.hierarchical_topics(docs["doc"])
        topics = topic_model_llm.get_topic_info()
        # Save the model
        # topic_model_llm.save(f"model_{self.identifier}.pkl")
        with Session(self.engine) as session:
            # https://stackoverflow.com/a/48057795
            # defer for *current* transaction!
            session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            session.execute(delete(TopicDB).where(TopicDB.onto_hash == self.identifier))
            topic_map: dict[int, TopicDB] = {}
            for i, topic in topics.iterrows():
                topic_id = topic["Topic"]
                topic_label = topic_model_llm.get_topic(topic["Topic"])[0][0]
                repr_docs = "\n".join(topic["Representative_Docs"])

                topic_embedding = self.embedding_model.encode(
                    f"{topic_label}\n\n{repr_docs}"
                )
                topic_db = TopicDB(
                    topic_id=topic_id,
                    topic=topic_label,
                    doc_string=repr_docs,
                    embedding=topic_embedding,
                )
                # elif doc["type"] == "property":
                #     link=session.execute(
                #         select(SubjectLinkDB).where(SubjectLinkDB.property_id == doc["property_id"])
                #     ).first()
                #     if link is not None:
                #         topic_db.subjects.append(link)
                topic_map[topic_id] = topic_db

            doc_info = topic_model_llm.get_document_info(docs["doc"], docs)
            for i, doc in doc_info.iterrows():
                topic_id = doc["Topic"]
                if doc["type"] == "subclass":
                    subject = session.execute(
                        select(SubjectInDB).where(
                            SubjectInDB.subject_id == doc["subject_id"]
                        )
                    ).first()
                    if subject is not None and topic_id in topic_map:
                        subject[0].topic_id = topic_id
                elif doc["type"] == "property":
                    link = session.execute(
                        select(SubjectLinkDB).where(
                            SubjectLinkDB.property_id == doc["property_id"]
                        )
                    ).first()
                    if link is not None and topic_id in topic_map:
                        link[0].topic_id = topic_id
            for i, topic in hierarchical_topics.iterrows():
                parent_name: str = topic["Parent_Name"]
                parent_name = parent_name.strip("_")
                id = int(topic["Parent_ID"])
                topic_db = TopicDB(topic_id=id, topic=parent_name)
                topic_map[id] = topic_db
            for i, topic in hierarchical_topics.iterrows():
                sub_topics = [
                    topic_map[int(topic[st])]
                    for st in ["Child_Left_ID", "Child_Right_ID"]
                ]
                for sub_topic in sub_topics:
                    topic_map[int(sub_topic.topic_id)].parent_topic_id = int(
                        topic["Parent_ID"]
                    )

            for topic in topic_map.values():
                topic.onto_hash = self.identifier
                # if topic.embedding is None:
                #     topic.embedding = self.embedding_model.encode(topic.topic)
                topic.onto_hash = self.identifier
                session.add(topic)
            session.commit()

            # Aggregate embeddings
            # --> seems to be a bit too average-y -> parent topics are now combined
            root_topics = session.execute(
                select(TopicDB).where(
                    TopicDB.onto_hash == self.identifier,
                    TopicDB.parent_topic_id == None,
                )
            ).fetchall()

            def get_and_set_aggregated_embedding(topic: TopicDB) -> list[str]:
                if len(topic.sub_topics) == 0:
                    return [topic.topic + "\n" + topic.doc_string]
                sub_topics = [
                    topic_str
                    for sub_topic in topic.sub_topics
                    for topic_str in get_and_set_aggregated_embedding(sub_topic)
                ]
                topic_description = "\n".join(sub_topics)
                aggregated_embedding = self.embedding_model.encode(
                    f"{topic.topic}\n\n{topic_description}"
                )
                topic.embedding = aggregated_embedding
                session.add(topic)
                return [topic.topic] + sub_topics

            [
                get_and_set_aggregated_embedding(root_topic[0])
                for root_topic in root_topics
            ]
            session.commit()

    def get_topic_tree(self) -> list[Topic]:
        with Session(self.engine) as session:
            root_topic = session.execute(
                select(TopicDB).where(
                    TopicDB.parent_topic_id == None,
                    TopicDB.onto_hash == self.identifier,
                    TopicDB.topic_id != -1,
                )
            ).first()

            def topic_tree(topic: TopicDB):
                return Topic(
                    topic_id=topic.topic_id,
                    topic=topic.topic,
                    count=topic.count,
                    parent_topic_id=topic.parent_topic_id,
                    # embedding=topic.embedding,
                    sub_topics=[
                        topic_tree(sub_topic) for sub_topic in topic.sub_topics
                    ],
                    subjects_ids=[s.subject_id for s in topic.subjects],
                    property_ids=[l.property_id for l in topic.links],
                )

            return topic_tree(root_topic[0])

    def embed_relations(self):
        all_classes = self.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        all_classes = {
            c: self.oman.enrich_subject(c, load_properties=True)
            for c in tqdm(all_classes, desc="Enriching classes")
        }

        with Session(self.engine) as session:
            session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            session.execute(text("SET session_replication_role = replica"))
            cls_descs: dict[str, str] = {}
            for cls in tqdm(all_classes.values(), desc="Embedding classes"):
                comment = (
                    cls.spos["rdfs:comment"].first_value()
                    if "rdfs:comment" in cls.spos
                    else ""
                )
                subcls = (
                    cls.spos["rdfs:subClassOf"].first_value()
                    if "rdfs:subClassOf" in cls.spos
                    else ""
                )
                subcls_desc = ""
                if len(subcls) > 0:
                    parent_cls = all_classes.get(
                        subcls, self.oman.enrich_subject(subcls)
                    )
                    subcls_desc = (
                        ""
                        if len(subcls) == 0
                        else f"A {cls.label} is a {parent_cls.label}."
                    )
                properties_desc = "\n".join(self.__get_properties_desc(cls))
                desc_short = f"""A {cls.label} is a {cls.subject_type}. {subcls_desc} {comment}
                    """
                desc = f"""{desc_short}
                    {properties_desc}
                    """
                cls_descs[cls.subject_id] = desc_short
                embedding = self.embedding_model.encode(desc_short)
                session.add(
                    SubjectInDB(
                        subject_id=cls.subject_id,
                        embedding=embedding,
                        comment=comment if len(comment) > 0 else None,
                        label=cls.label,
                        onto_hash=self.identifier,
                        parent_id=subcls if len(subcls) > 0 else None,
                        subject_type=cls.subject_type,
                        instance_count=cls.instance_count,
                    )
                )
            session.commit()
            for cls in tqdm(all_classes.values(), desc="Embedding relations"):
                for prop in cls.properties.keys():
                    for p in cls.properties[prop]:
                        prop_range = (
                            p.spos["rdfs:range"].first_value()
                            if "rdfs:range" in p.spos
                            else ""
                        )
                        prop_range_desc = (
                            f"A {cls.label} is defined by {to_readable(p.label)}."
                        )
                        if len(prop_range) > 0:
                            prop_range_cls = all_classes.get(
                                prop_range, self.oman.enrich_subject(prop_range)
                            )
                            if prop == "ObjectProperty":
                                prop_range_desc = f"A {cls.label} is {to_readable(p.label)} of {to_readable(prop_range_cls.label)}."
                            else:
                                prop_range_desc = f"A {cls.label} has {to_readable(p.label)} of type {to_readable(prop_range_cls.label)}."
                            # print(prop_range_desc)
                        superprop = (
                            p.spos["rdfs:subPropertyOf"].first_value()
                            if "rdfs:subPropertyOf" in p.spos
                            else ""
                        )
                        superprop_desc = ""
                        if len(superprop) > 0:
                            superprop_cls = self.oman.enrich_subject(superprop)
                            if not superprop_cls.label.startswith("<"):
                                superprop_desc = f"{to_readable(p.label)} is a subproperty of {to_readable(superprop_cls.label)}."

                        prop_desc = f"{prop_range_desc} {superprop_desc}"
                        prop_embedding = self.embedding_model.encode(prop_desc)
                        to_id = (
                            p.spos["rdfs:range"].first_value()
                            if "rdfs:range" in p.spos
                            else None
                        )
                        to_proptype = None
                        if to_id is not None:
                            class_exists = session.execute(
                                select(SubjectInDB)
                                .where(SubjectInDB.subject_id == to_id)
                                .limit(1)
                            ).first()
                            if class_exists is None:
                                to_proptype = to_id
                                to_id = None
                                # print(f"Class {to_id} does not exist, skipping")
                        session.add(
                            SubjectLinkDB(
                                from_id=cls.subject_id,
                                to_id=to_id,
                                to_proptype=to_proptype,
                                property_id=p.subject_id,
                                link_type=prop,
                                onto_hash=self.identifier,
                                embedding=prop_embedding,
                                label=p.label,
                                instance_count=self.oman.property_count(p.subject_id),
                            )
                        )
            session.commit()

    def search_free(
        self,
        query: str,
        limit=25,
    ):
        query_embedding = self.embedding_model.encode(query)
        with Session(self.engine) as session:
            subjects = session.execute(
                select(SubjectInDB)
                .where(SubjectInDB.onto_hash == self.identifier)
                .order_by(SubjectInDB.embedding.cosine_distance(query_embedding))
                .limit(limit)
            ).all()
            subjects_enriched = [
                self.oman.enrich_subject(s[0].subject_id) for s in subjects
            ]
            links = session.execute(
                select(SubjectLinkDB)
                .where(SubjectLinkDB.onto_hash == self.identifier)
                .order_by(SubjectLinkDB.embedding.cosine_distance(query_embedding))
                .limit(limit)
            ).all()
            links_enriched = [SubjectLink.from_db(l[0], self.oman) for l in links]
            return FuzzyQueryResults(
                links=links_enriched,
                subjects=subjects_enriched,
            )

    def search_links(
        self, querystring: str = None, from_id: str = None, to_id: str = None
    ):
        with Session(self.engine) as session:
            query = select(SubjectLinkDB).where(
                SubjectLinkDB.onto_hash == self.identifier
            )
            if from_id is not None:
                query = query.where(SubjectLinkDB.from_id == from_id)
            if to_id is not None:
                query = query.where(SubjectLinkDB.to_id == to_id)
            if querystring is not None:
                query_embedding = self.embedding_model.encode(querystring)
                query = query.order_by(
                    SubjectLinkDB.embedding.cosine_distance(query_embedding)
                )
            links = session.execute(query.limit(25)).all()
            links_enriched = [SubjectLink.from_db(l[0], self.oman) for l in links]
            return links_enriched

    def search_fuzzy(self, query: FuzzyQuery):
        with Session(self.engine) as session:
            query_embedding = None
            if query.q is not None and len(query.q) > 0:
                query_embedding = self.embedding_model.encode(
                    query.q, prompt_name=self.query_prompt_name
                )
            if query.topic_ids is not None and len(query.topic_ids) > 0:
                topics = session.execute(
                    select(TopicDB)
                    .where(TopicDB.onto_hash == self.identifier)
                    .where(TopicDB.topic_id.in_(query.topic_ids))
                ).all()
                topic_embeddings = torch.tensor(
                    [topic[0].embedding for topic in topics]
                )
                topic_embedding = torch.mean(topic_embeddings, axis=0)
                if query_embedding is not None:
                    query_embedding = (
                        1 - query.mix_topic_factor
                    ) * query_embedding + query.mix_topic_factor * topic_embedding
                else:
                    query_embedding = topic_embedding

            if query.q is None and (
                query.topic_ids is None or len(query.topic_ids) == 0
            ):
                query_embedding = (
                    torch.ones(N_EMBEDDINGS) / N_EMBEDDINGS
                )  # default to uniform

            results: list[FuzzyQueryResult] = []
            if query.type == RETURN_TYPE.SUBJECT or query.type == RETURN_TYPE.BOTH:
                order_by = (
                    SubjectInDB.embedding.cosine_distance(query_embedding)
                    if query.order == FUZZY_QUERY_ORDER.SCORE
                    else SubjectInDB.instance_count
                )
                subjects = session.execute(
                    select(
                        SubjectInDB,
                        SubjectInDB.embedding.cosine_distance(query_embedding).label(
                            "distance"
                        ),
                    )
                    .where(SubjectInDB.onto_hash == self.identifier)
                    .order_by(order_by)
                    .offset(query.skip)
                    .limit(query.limit)
                ).all()
                subjects_enriched = [
                    (self.oman.enrich_subject(s[0].subject_id), s.distance)
                    for s in subjects
                ]
                for s in subjects_enriched:
                    results.append(FuzzyQueryResult(subject=s[0], score=s[1]))
            if query.type == RETURN_TYPE.LINK or query.type == RETURN_TYPE.BOTH:
                order_by = (
                    SubjectLinkDB.embedding.cosine_distance(query_embedding)
                    if query.order == FUZZY_QUERY_ORDER.SCORE
                    else SubjectLinkDB.instance_count
                )
                query_link = select(
                    SubjectLinkDB,
                    SubjectLinkDB.embedding.cosine_distance(query_embedding).label(
                        "distance"
                    ),
                ).where(SubjectLinkDB.onto_hash == self.identifier)
                if query.from_id is not None:
                    if isinstance(query.from_id, str):
                        query.from_id = [query.from_id]
                    from_parents = [
                        self.oman.get_parents(from_id) + [from_id]
                        for from_id in query.from_id
                    ]
                    from_parents = [
                        item for sublist in from_parents for item in sublist
                    ]
                    query_link = query_link.where(
                        SubjectLinkDB.from_id.in_(from_parents)
                    )
                if query.to_id is not None:
                    to_parents = self.oman.get_parents(query.to_id) + [query.to_id]
                    query_link = query_link.where(SubjectLinkDB.to_id.in_(to_parents))
                if query.relation_type == RELATION_TYPE.INSTANCE:
                    query_link = query_link.where(
                        SubjectLinkDB.to_id != None,
                    )
                elif query.relation_type == RELATION_TYPE.PROPERTY:
                    query_link = query_link.where(
                        SubjectLinkDB.to_id == None,
                        SubjectLinkDB.to_proptype
                        != None,  # constraint to known proptypes
                    )
                query_link = query_link.order_by(order_by)
                links = session.execute(
                    query_link.offset(query.skip).limit(query.limit)
                ).all()

                links_enriched = [
                    (SubjectLink.from_db(l[0], self.oman), l.distance) for l in links
                ]

                for l in links_enriched:
                    results.append(
                        FuzzyQueryResult(
                            link=l[0], score=l[1] if l[1] is not None else 0.0
                        )
                    )

            results = sorted(results, key=lambda x: x.score, reverse=False)
            return FuzzyQueryResults(results=results)
