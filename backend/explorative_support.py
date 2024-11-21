from __future__ import annotations
from model import *
from ontology import *
import regex as re
from bertopic import BERTopic
from bertopic.representation import MaximalMarginalRelevance, LlamaCPP
from llama_cpp import Llama
from hashlib import sha256
from explorative_model import *
from sqlalchemy import text, inspect

# System prompt describes information given to all conversations
TOPIC_LLAMA3_PROMPT_SYSTEM = """
<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a helpful, respectful and honest assistant for labeling topics.
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
        self.embedding_model = SentenceTransformer("paraphrase-MiniLM-L6-v2").to(device)
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
                    for e in self.oman.onto.query("SELECT ?s  ?p ?o WHERE {?s ?o ?p.} LIMIT 25")
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
                    prop_doc += f"{c.label} is defined by {to_readable(prop.label)} "
                else:
                    prop_doc += f"{c.label} {to_readable(prop.label)} "
                if "rdfs:range" in prop.spos:
                    range = self.oman.enrich_subject(prop.spos["rdfs:range"][0])
                    if range.label.startswith("<"):
                        continue
                    prop_doc += f" of type {range.label}"
                if "rdfs:subPropertyOf" in prop.spos:
                    subprop = self.oman.enrich_subject(
                        prop.spos["rdfs:subPropertyOf"][0]
                    )
                    if subprop.label.startswith("<"):
                        continue
                    prop_doc += f" is subproperty of {subprop.label}"
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

        with Session(self.engine) as session:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            session.commit()
        BasePostgres.metadata.drop_all(self.engine)
        BasePostgres.metadata.create_all(self.engine)
        docs = self.__build_docs()
        # Create an instance of the Llama class and load the model

        # Create the provider by passing the Llama class instance to the LlamaCppPythonProvider class
        representation_llama = LlamaCPP(self.llama_model, TOPIC_LLAMA3_PROMPT, diversity=0.3)
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
                topic_db = TopicDB(topic_id=i, topic=topic["Representation"][0])
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
                topic.embedding = self.embedding_model.encode(topic.topic)
                session.add(topic)
            session.commit()

    def initialize_topics(self):
        init_topics = False
        with Session(self.engine) as session:
            insp = inspect(self.engine)
            if not insp.has_table("topics", schema="public"):
                init_topics = True
            else:
                init_topics = (
                    session.execute(
                        select(TopicDB).where(TopicDB.onto_hash == self.identifier)
                    ).first()
                    is None
                )
        if init_topics:
            self.__model_topics()

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
                    embedding=topic.embedding,
                    sub_topics=[
                        topic_tree(sub_topic) for sub_topic in topic.sub_topics
                    ],
                )

            return topic_tree(root_topic[0])
    
    
    