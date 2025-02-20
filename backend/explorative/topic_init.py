from bertopic import BERTopic
from bertopic.representation import LangChain, LlamaCPP


from sqlalchemy import text, inspect, create_engine, select, delete
from sqlalchemy.orm import Session
from model import Subject
from tqdm import tqdm
import regex as re
import pandas as pd

from eval_config import EvalConfig
from explorative.exp_model import TopicDB, SubjectLinkDB, SubjectInDB, BasePostgres
from explorative.explorative_support import GuidanceManager

from initiator import Initationatable, InitatorManager

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


class TopicInitator:
    def __init__(self, guidance_man: GuidanceManager):
        self.guidance_man = guidance_man

    def model_topics(self):
        representation_llama = LlamaCPP(
            self.guidance_man.llama_model, TOPIC_LLAMA3_PROMPT, diversity=0.3
        )
        docs = self.guidance_man.build_docs()
        # Create an instance of the Llama class and load the model

        # Create the provider by passing the Llama class instance to the LlamaCppPythonProvider class

        topic_model_llm = BERTopic(
            embedding_model=self.guidance_man.embedding_model,
            verbose=True,
            representation_model=representation_llama,
        )
        topic_model_llm.fit(docs["doc"])
        hierarchical_topics = topic_model_llm.hierarchical_topics(docs["doc"])
        topics = topic_model_llm.get_topic_info()
        # Save the model
        # topic_model_llm.save(f"model_{self.guidance_man.identifier}.pkl")
        with Session(self.guidance_man.engine) as session:
            # https://stackoverflow.com/a/48057795
            # defer for *current* transaction!
            session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            session.execute(delete(TopicDB).where(TopicDB.onto_hash == self.guidance_man.identifier))
            topic_map: dict[int, TopicDB] = {}
            for i, topic in topics.iterrows():
                topic_id = topic["Topic"]
                topic_label = topic_model_llm.get_topic(topic["Topic"])[0][0]
                repr_docs = "\n".join(topic["Representative_Docs"])

                topic_embedding = self.guidance_man.embedding_model.encode(
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
                topic.onto_hash = self.guidance_man.identifier
                # if topic.embedding is None:
                #     topic.embedding = self.guidance_man.embedding_model.encode(topic.topic)
                topic.onto_hash = self.guidance_man.identifier
                session.add(topic)
            session.commit()

            # Aggregate embeddings
            # --> seems to be a bit too average-y -> parent topics are now combined
            root_topics = session.execute(
                select(TopicDB).where(
                    TopicDB.onto_hash == self.guidance_man.identifier,
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
                aggregated_embedding = self.guidance_man.embedding_model.encode(
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

    def embed_relations(self):
        all_classes = self.guidance_man.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        all_classes = {
            c: self.guidance_man.oman.enrich_subject(c, load_properties=True)
            for c in tqdm(all_classes, desc="Enriching classes")
        }

        with Session(self.guidance_man.engine) as session:
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
                        subcls, self.guidance_man.oman.enrich_subject(subcls)
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
                embedding = self.guidance_man.embedding_model.encode(desc_short)
                session.add(
                    SubjectInDB(
                        subject_id=cls.subject_id,
                        embedding=embedding,
                        comment=comment if len(comment) > 0 else None,
                        label=cls.label,
                        onto_hash=self.guidance_man.identifier,
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
                                prop_range, self.guidance_man.oman.enrich_subject(prop_range)
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
                            superprop_cls = self.guidance_man.oman.enrich_subject(superprop)
                            if not superprop_cls.label.startswith("<"):
                                superprop_desc = f"{to_readable(p.label)} is a subproperty of {to_readable(superprop_cls.label)}."

                        prop_desc = f"{prop_range_desc} {superprop_desc}"
                        prop_embedding = self.guidance_man.embedding_model.encode(prop_desc)
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
                                onto_hash=self.guidance_man.identifier,
                                embedding=prop_embedding,
                                label=p.label,
                                instance_count=self.guidance_man.oman.property_count(p.subject_id),
                            )
                        )
            session.commit()

    def initate(
        self, reset=True, config: EvalConfig = None, force=True, *args, **kwargs
    ):
        init_topics = False
        delete_tables = reset
        with Session(self.guidance_man.engine) as session:
            insp = inspect(self.guidance_man.engine)
            if not insp.has_table("topics", schema="public") or not insp.has_table(
                "subjects", schema="public"
            ):
                init_topics = True
            else:
                init_topics = (
                    session.execute(
                        select(TopicDB.topic_id).where(
                            TopicDB.onto_hash == self.guidance_man.identifier
                        )
                    ).first()
                    is None
                )
        if init_topics or force:
            print("Initializing topics")
            with Session(self.guidance_man.engine) as session:
                session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                session.commit()
            if delete_tables:
                BasePostgres.metadata.drop_all(self.guidance_man.engine)

            BasePostgres.metadata.create_all(self.guidance_man.engine)
            with Session(self.guidance_man.engine) as session:
                session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
                session.execute(
                    delete(TopicDB).where(TopicDB.onto_hash == self.guidance_man.identifier)
                )
                session.execute(
                    delete(SubjectInDB).where(SubjectInDB.onto_hash == self.guidance_man.identifier)
                )
                session.execute(
                    delete(SubjectLinkDB).where(
                        SubjectLinkDB.onto_hash == self.guidance_man.identifier
                    )
                )
                session.commit()

            # embed first, then model to make sure subjects are available for topics
            self.embed_relations()
            self.model_topics()

    def __get_named_individuals_desc(self, c: Subject) -> dict[str, str]:
        nis = self.guidance_man.oman.get_named_individuals(c.subject_id)
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
                    range = self.guidance_man.oman.enrich_subject(
                        prop.spos["rdfs:range"].first_value()
                    )
                    if range.label.startswith("<"):
                        continue
                    prop_doc += f" of type {range.label}. "
                if "rdfs:subPropertyOf" in prop.spos:
                    subprop = self.guidance_man.oman.enrich_subject(
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
            subcls = self.guidance_man.oman.enrich_subject(c.spos["rdfs:subClassOf"].first_value())
            if subcls.label.startswith("<"):
                return []
            cls_doc += f" is subclass of  {subcls.label}\n"
        return [cls_doc]

    def build_docs(self):
        classes = self.guidance_man.oman.q_to_df(
            """
SELECT ?s
WHERE {
    ?s rdf:type owl:Class.
}
"""
        )[0].to_list()
        classes_enriched = [
            self.guidance_man.oman.enrich_subject(c, load_properties=True)
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
