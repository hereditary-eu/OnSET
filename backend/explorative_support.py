from __future__ import annotations
from model import *
from ontology import *
import regex as re
from bertopic import BERTopic
from bertopic.representation import MaximalMarginalRelevance, LlamaCPP
from llama_cpp import Llama
from hashlib import sha256
from explorative_model import *
from sqlalchemy import text, inspect, create_engine, select
import torch as t
import numpy as np

# System prompt describes information given to all conversations
TOPIC_LLAMA3_PROMPT_SYSTEM = """
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a helpful, respectful and honest assistant for labeling topics. You should provide a short label for a topic based on the information provided about the topic. The topic is described by a set of documents and keywords. The label should be a short phrase that captures the essence of the topic. The label should be concise and informative, and should not contain any information that is not directly related to the topic.
"""

# Example prompt demonstrating the output we are looking for
TOPIC_LLAMA3_PROMPT_EXAMPLE = """<|eot_id|><|start_header_id|>user<|end_header_id|>
I have a topic that contains the following documents:
- Traditional diets in most cultures were primarily plant-based with a little meat on top, but with the rise of industrial style meat production and factory farming, meat has become a staple food.
- Meat, but especially beef, is the word food in terms of emissions.
- Eating meat doesn't make you a bad person, not eating meat doesn't make you a good one.

The topic is described by the following keywords: 'meat, beef, eat, eating, emissions, steak, food, health, processed, chicken'.

Based on the information about the topic above, please create a short label of this topic. Make sure you to only return the label and nothing more.

<|eot_id|><|start_header_id|>assistant<|end_header_id|>
Environmental impacts of eating meat<|eot_id|>
"""

# Our main prompt with documents ([DOCUMENTS]) and keywords ([KEYWORDS]) tags
TOPIC_LLAMA3_PROMPT_MAIN = """
<|eot_id|><|start_header_id|>user<|end_header_id|>
I have a topic that contains the following documents:
[DOCUMENTS]

The topic is described by the following keywords: '[KEYWORDS]'.

Based on the information about the topic above, please create a short label of this topic. Make sure you to only return the label and nothing more.
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

TOPIC_LLAMA3_PROMPT = (
    TOPIC_LLAMA3_PROMPT_SYSTEM + TOPIC_LLAMA3_PROMPT_EXAMPLE + TOPIC_LLAMA3_PROMPT_MAIN
)


def to_readable(s: str):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s).replace("_", " ").lower()


from sentence_transformers import SentenceTransformer
import torch
from sentence_transformers import SentenceTransformer


class TopicModelling:
    def __init__(
        self,
        oman: OntologyManager,
        device=None,
        conn_str: str = "postgresql+psycopg://postgres:postgres@localhost:5434/onset",
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
        self.embedding_model = SentenceTransformer(
            "dunzhang/stella_en_400M_v5",
            trust_remote_code=True,
            config_kwargs={
                "use_memory_efficient_attention": False,
                "unpad_inputs": False,
            },
        ).to(device)
        # self.embedding_model = SentenceTransformer(
        #     "paraphrase-MiniLM-L6-v2",
        # ).to(device)
        self.llama_model = Llama.from_pretrained(
            repo_id="NousResearch/Hermes-3-Llama-3.1-8B-GGUF",
            filename="*.Q8_0.gguf",
            n_batch=1024,
            n_ctx=10000,
            n_gpu_layers=-1,
        )
        self.engine = create_engine(conn_str)
        self.identifier = sha256(
            ".".join(
                [
                    str(e)
                    for e in self.oman.onto.query(
                        "SELECT ?s  ?p ?o WHERE {?s ?o ?p.} LIMIT 25"
                    )
                ]
            ).encode()
        ).hexdigest()

    def __get_named_individuals_desc(self, c: Subject) -> list[str]:
        nis = self.oman.get_named_individuals(c.subject_id)
        return [f"{ne.label} is a {c.label}" for ne in nis]

    def __get_properties_desc(self, c: Subject) -> list[str]:
        prop_docs = []
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
                    range = self.oman.enrich_subject(prop.spos["rdfs:range"][0])
                    if range.label.startswith("<"):
                        continue
                    prop_doc += f" of type {range.label}. "
                if "rdfs:subPropertyOf" in prop.spos:
                    subprop = self.oman.enrich_subject(
                        prop.spos["rdfs:subPropertyOf"][0]
                    )
                    if subprop.label.startswith("<"):
                        continue
                    prop_doc += f" is subproperty of {subprop.label}. "
                prop_docs.append(prop_doc)
        return prop_docs

    def __get_subclass_desc(self, c: Subject) -> list[str]:
        cls_doc = f"{c.label}"
        if "rdfs:subClassOf" in c.spos:
            subcls = self.oman.enrich_subject(c.spos["rdfs:subClassOf"][0])
            if subcls.label.startswith("<"):
                return []
            cls_doc += f" is subclass of  {subcls.label}\n"
        return [cls_doc]

    def __build_docs(self) -> list[str]:
        classes = self.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        classes_enriched = [
            self.oman.enrich_subject(c, load_properties=True) for c in classes
        ]

        documents = []
        for c in classes_enriched[1:]:
            if c.label.startswith("<"):
                print("ignoring", c.label)
                continue
            documents.extend(
                self.__get_named_individuals_desc(c)
                + self.__get_properties_desc(c)
                + self.__get_subclass_desc(c)
            )
        return documents

    def __model_topics(self):

        docs = self.__build_docs()
        # Create an instance of the Llama class and load the model

        # Create the provider by passing the Llama class instance to the LlamaCppPythonProvider class
        representation_llama = LlamaCPP(
            self.llama_model, TOPIC_LLAMA3_PROMPT, diversity=0.3
        )
        topic_model_llm = BERTopic(
            embedding_model=self.embedding_model,
            verbose=True,
            representation_model=representation_llama,
        )
        topic_model_llm.fit(docs)
        hierarchical_topics = topic_model_llm.hierarchical_topics(docs)
        topics = topic_model_llm.get_topic_info()
        # Save the model
        # topic_model_llm.save(f"model_{self.identifier}.pkl")
        with Session(self.engine) as session:
            # https://stackoverflow.com/a/48057795
            # defer for *current* transaction!
            session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            topic_map: dict[int, TopicDB] = {}
            for i, topic in topics.iterrows():
                topic_label = topic_model_llm.get_topic(topic["Topic"])
                docs = "\n".join(topic["Representative_Docs"][0])

                topic_embedding = self.embedding_model.encode(
                    f"{topic_label}\n\n{docs}"
                )
                topic_db = TopicDB(
                    topic_id=i,
                    topic=topic_label,
                    # doc_str=docs,
                    embedding=topic_embedding,
                )
                topic_map[i] = topic_db
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
                session.add(topic)
            session.commit()

            # Aggregate embeddings
            root_topic = session.execute(
                select(TopicDB).where(
                    TopicDB.onto_hash == self.identifier,
                    TopicDB.parent_topic_id == None,
                )
            ).first()

            def get_and_set_aggregated_embedding(topic: TopicDB):
                if len(topic.sub_topics) == 0:
                    return topic.embedding
                sub_embeddings = [
                    get_and_set_aggregated_embedding(sub_topic)
                    for sub_topic in topic.sub_topics
                ]
                aggregated_embedding = np.mean(np.stack(sub_embeddings), axis=0)
                topic.embedding = aggregated_embedding
                return aggregated_embedding

            get_and_set_aggregated_embedding(root_topic[0])
            session.commit()

    def initialize_topics(self, force: bool = False):
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
            with Session(self.engine) as session:
                session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.commit()
            BasePostgres.metadata.drop_all(self.engine)
            BasePostgres.metadata.create_all(self.engine)
            self.__model_topics()
            self.__embed_relations()

    def get_topic_tree(self) -> list[Topic]:
        with Session(self.engine) as session:
            root_topic = session.execute(
                select(TopicDB).where(
                    TopicDB.parent_topic_id == None,
                    TopicDB.onto_hash == self.identifier,
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
                )

            return topic_tree(root_topic[0])

    def __embed_relations(self):

        all_classes = self.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        all_classes = {
            c: self.oman.enrich_subject(c, load_properties=True) for c in all_classes
        }

        with Session(self.engine) as session:

            session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            cls_descs: dict[str, str] = {}
            for cls in tqdm(all_classes.values(), desc="Embedding classes"):
                comment = cls.spos.get("rdfs:comment", [""])[0]
                subcls = cls.spos.get("rdfs:subClassOf", [""])[0]
                subcls_desc = ""
                if len(subcls) > 0:
                    parent_cls = all_classes.get(
                        subcls, self.oman.enrich_subject(subcls)
                    )
                    subcls_desc = (
                        ""
                        if len(subcls) == 0
                        else f"{cls.label} is a subclass of {parent_cls.label}."
                    )
                properties_desc = "\n".join(self.__get_properties_desc(cls))
                desc_short = f"""{cls.label} is a {cls.subject_type}. {subcls_desc} {comment}
                    """
                desc = f"""{desc_short}
                    {properties_desc}
                    """
                cls_descs[cls.subject_id] = desc_short
                embedding = self.embedding_model.encode(desc)

                session.add(
                    SubjectInDB(
                        subject_id=cls.subject_id,
                        embedding=embedding,
                        comment=comment if len(comment) > 0 else None,
                        label=cls.label,
                        onto_hash=self.identifier,
                        parent_id=subcls if len(subcls) > 0 else None,
                        subject_type=cls.subject_type,
                    )
                )
            session.commit()
            for cls in tqdm(all_classes.values(), desc="Embedding relations"):
                for prop in cls.properties.keys():
                    for p in cls.properties[prop]:
                        prop_range = p.spos.get("rdfs:range", [""])[0]
                        prop_range_desc = (
                            f"A {cls.label} is defined by {to_readable(p.label)}."
                        )
                        if len(prop_range) > 0:
                            prop_range_cls = all_classes.get(
                                prop_range, self.oman.enrich_subject(prop_range)
                            )
                            if prop =='ObjectProperty':
                                prop_range_desc = f"A {cls.label} is {to_readable(p.label)} of {to_readable(prop_range_cls.label)}."
                            else:
                                prop_range_desc = f"A {cls.label} has {to_readable(p.label)} of type {to_readable(prop_range_cls.label)}."
                            # print(prop_range_desc)
                        superprop = p.spos.get("rdfs:subPropertyOf", [""])[0]
                        superprop_desc = ""
                        if len(superprop) > 0:
                            superprop_cls = self.oman.enrich_subject(superprop)
                            superprop_desc = f"{to_readable(p.label)} is a subproperty of {to_readable(superprop_cls.label)}."

                        prop_desc = f"{prop_range_desc} {superprop_desc} {cls_descs[cls.subject_id]}"
                        prop_embedding = self.embedding_model.encode(prop_desc)
                        to_id = (
                            p.spos["rdfs:range"][0] if "rdfs:range" in p.spos else None
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
            if query.q is not None:
                query_embedding = self.embedding_model.encode(
                    query.q, prompt_name=self.query_prompt_name
                )
            if query.topic_ids is not None or len(query.topic_ids) > 0:
                topics = session.execute(
                    select(TopicDB)
                    .where(TopicDB.onto_hash == self.identifier)
                    .where(TopicDB.topic_id.in_(query.topic_ids))
                ).all()
                topic_embeddings = t.tensor([t[0].embedding for t in topics])
                topic_embedding = t.mean(topic_embeddings, axis=0)
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
                    t.ones(N_EMBEDDINGS) / N_EMBEDDINGS
                )  # default to uniform

            subjects = session.execute(
                select(
                    SubjectInDB,
                    SubjectInDB.embedding.cosine_distance(query_embedding).label(
                        "distance"
                    ),
                )
                .where(SubjectInDB.onto_hash == self.identifier)
                .order_by(SubjectInDB.embedding.cosine_distance(query_embedding))
                .limit(query.limit)
            ).all()
            subjects_enriched = [
                (self.oman.enrich_subject(s[0].subject_id), s.distance)
                for s in subjects
            ]

            query_link = select(
                SubjectLinkDB,
                SubjectLinkDB.embedding.cosine_distance(query_embedding).label(
                    "distance"
                ),
            ).where(SubjectLinkDB.onto_hash == self.identifier)
            if query.from_id is not None:
                query_link = query_link.where(SubjectLinkDB.from_id == query.from_id)
            if query.to_id is not None:
                query_link = query_link.where(SubjectLinkDB.to_id == query.to_id)
            if query.q is not None:
                query_link = query_link.order_by(
                    SubjectLinkDB.embedding.cosine_distance(query_embedding)
                )
            links = session.execute(query_link.limit(25)).all()

            links_enriched = [
                (SubjectLink.from_db(l[0], self.oman), l.distance) for l in links
            ]

            results: list[FuzzyQueryResult] = []
            for s in subjects_enriched:
                results.append(FuzzyQueryResult(subject=s[0], score=s[1]))
            for l in links_enriched:
                results.append(FuzzyQueryResult(link=l[0], score=l[1]))
            results = sorted(results, key=lambda x: x.score, reverse=True)
            return FuzzyQueryResults(results=results)
