from llama_cpp.llama import Llama, LlamaGrammar
from explorative_support import TopicModelling
from explorative_model import (
    FuzzyQuery,
    RETURN_TYPE,
    RELATION_TYPE,
    SubjectLink,
    SubjectLinkDB,
    SubjectInDB,
)
from model import Subject
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, create_model
from enum import Enum
import datetime
from fastapi import BackgroundTasks

# has to be installed from fork until merged!
from llama_cpp_agent.gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import (
    generate_gbnf_grammar_from_pydantic_models,
)
from redis_cache import RedisCache


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


# System prompt describes information given to all conversations
ERL_PROMPT_SYSTEM = """
Return all the entity relations and constraint within the prompt in the form of JSON output. The output should be a list of all entities and their constraints, as well as the relations between them. Make sure to include all entities and targets in the list of entities. Constraints should only be included in the list of entities they are associated with.
"""
ERL_SAMPLE = EntitiesRelations(
    relations=[
        Relation(entity="person 1", relation="author", target="work 1"),
        Relation(entity="person 1", relation="birth place", target="place 1"),
    ],
    entities=[
        Entity(
            identifier="person 1",
            type="person",
            constraints=[
                Constraint(property="birth_date", value="1990", modifier="greater_than")
            ],
        ),
        Entity(identifier="work 1", type="work", constraints=[]),
        Entity(identifier="place 1", type="place", constraints=[]),
    ],
)
# Example prompt demonstrating the output we are looking for
ERL_PROMPT_EXAMPLE = (
    "the birth place of an author of a work where the author is born after 1990",
    ERL_SAMPLE.model_dump_json(),
)

RAG_PROMPT_EXAMPLE_CANDIDATES = Candidates(
    relations=[
        CandidateRelation(
            entity="person 1", relation="author", target="work 1", score=0.9
        )
    ],
    entities=[
        CandidateEntity(identifier="person 1", type="person", score=0.9),
        CandidateEntity(identifier="composer 1", type="composer", score=0.7),
        CandidateEntity(identifier="work 1", type="work", score=0.9),
        CandidateEntity(identifier="song 1", type="song", score=0.6),
    ],
    constraints=[
        CandidateConstraint(
            property="birth date",
            value="1990",
            modifier="greater_than",
            score=0.9,
            type="sko:DateTime",
            entity="person 1",
        ),
        CandidateConstraint(
            property="death year",
            value="180cm",
            modifier="greater_than",
            score=0.8,
            type="sko:DateTime",
            entity="person 1",
        ),
    ],
)

RAG_PROMPT_SYSTEM = """
Return all the entity relations and constraint within the prompt in the form of JSON output. The output should be a list of all entities and their constraints, as well as the relations between them. Make sure to include all entities and targets in the list of entities. Constraints should only be included in the list of entities they are associated with.
"""

RAG_PROMPT_EXPECTED_OUTPUT = EntitiesRelations(
    relations=[
        Relation(entity="person 1", relation="author", target="work 1"),
        Relation(entity="person 1", relation="birth place", target="place 1"),
    ],
    entities=[
        Entity(
            identifier="person 1",
            type="person",
            constraints=[
                Constraint(
                    property="birth date",
                    value="1.1.1990",
                    modifier="greater_than",
                )
            ],
        ),
        Entity(identifier="work 1", type="work", constraints=[]),
        Entity(identifier="place 1", type="place", constraints=[]),
    ],
)
RAG_PROMPT_EXAMPLE = (
    ERL_PROMPT_EXAMPLE[0],
    RAG_PROMPT_EXAMPLE_CANDIDATES.model_dump_json(),
    ERL_SAMPLE.model_dump_json(),
)


class LLMQuery:
    def __init__(
        self, topic: TopicModelling, zero_shot=False, temperature=0.3, max_tokens=2048
    ):
        self.max_tokens = max_tokens
        self.zero_shot = zero_shot
        self.temperature = temperature
        self.topic_man = topic
        self.gbnf_erl = generate_gbnf_grammar_from_pydantic_models(
            [EntitiesRelations], "EntitiesRelations", add_inner_thoughts=False
        )
        self.grammar_erl = LlamaGrammar.from_string(self.gbnf_erl)

        self.gbnf_candidates = generate_gbnf_grammar_from_pydantic_models(
            [Candidates], "Candidates", add_inner_thoughts=False
        )
        self.grammar_candidates = LlamaGrammar.from_string(self.gbnf_candidates)
        self.query_id_counter = 0
        self.cache = RedisCache[QueryProgress](model=QueryProgress)

    def run_query(self, progress: QueryProgress, query: str):
        progress.progress = 1
        progress.message = "Querying entities and relations"
        self.cache[progress.id] = progress

        erl = self.query_erl(query)
        progress.progress = 2
        progress.message = "Fetching possible candidates"
        erl.message = "Found entities and relations"
        progress.relations_steps.append(erl)
        self.cache[progress.id] = progress

        candidates = self.candidates_for_erl(erl)
        progress.progress = 3
        progress.message = "Querying candidates"
        candidates.message = "Found similar candidates"
        progress.relations_steps.append(candidates)
        self.cache[progress.id] = progress

        constrained_erl = self.query_constrained(query, candidates)
        progress.progress = 4
        progress.message = "Enriching results"
        constrained_erl.message = "Constraints applied"
        progress.relations_steps.append(constrained_erl)
        self.cache[progress.id] = progress

        enriched_erl = self.enrich_entities_relations(constrained_erl)
        progress.progress = 5
        progress.message = "Query completed"
        enriched_erl.message = "Aligned results"
        progress.enriched_relations = enriched_erl
        progress.relations_steps.append(enriched_erl)
        self.cache[progress.id] = progress

    def start_query(self, query: str, background_tasks: BackgroundTasks):
        query_id = self.query_id_counter = self.query_id_counter + 1
        start_time = datetime.datetime.now().isoformat()
        query_key = f"query:{query_id}:{start_time}"
        progress = QueryProgress(
            max_steps=5,
            id=query_key,
            start_time=start_time,
            relations_steps=[],
        )
        self.cache[query_key] = progress
        background_tasks.add_task(self.run_query, progress, query)
        return progress

    def query_progress(self, query_id: str) -> QueryProgress:
        return self.cache[query_id]

    @property
    def model(self) -> Llama:
        return self.topic_man.llama_model

    def query_erl(self, query: str) -> EntitiesRelations:
        messages = [
            {"role": "system", "content": ERL_PROMPT_SYSTEM},
        ]
        if not self.zero_shot:
            messages.extend(
                [
                    {"role": "user", "content": ERL_PROMPT_EXAMPLE[0]},
                    {"role": "assistant", "content": ERL_PROMPT_EXAMPLE[1]},
                ]
            )
        messages.append({"role": "user", "content": query})
        response = self.model.create_chat_completion(
            grammar=self.grammar_erl,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        return EntitiesRelations.model_validate_json(response_msg)

    def query_constrained(
        self, query: str, candidates: Candidates
    ) -> EntitiesRelations:
        ConstrainedEntitiesRelations = self.build_constrained_classes(candidates)
        grammar_constrained = LlamaGrammar.from_string(
            generate_gbnf_grammar_from_pydantic_models(
                [ConstrainedEntitiesRelations],
                "ConstrainedEntitiesRelations",
                add_inner_thoughts=False,
            )
        )
        messages = [
            {"role": "system", "content": RAG_PROMPT_SYSTEM},
        ]
        if not self.zero_shot:
            messages.extend(
                [
                    {"role": "user", "content": RAG_PROMPT_EXAMPLE[0]},
                    {"role": "assistant", "content": RAG_PROMPT_EXAMPLE[2]},
                ]
            )
        messages.append({"role": "user", "content": query})
        response = self.model.create_chat_completion(
            grammar=grammar_constrained,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        return ConstrainedEntitiesRelations.model_validate_json(response_msg)

    def candidates_for_erl(
        self, erl: EntitiesRelations, candidate_limit=3
    ) -> Candidates:
        example_limit = 3
        relation_candidates: list[CandidateRelation] = []
        constraint_candidates: list[CandidateConstraint] = []
        entity_candidates: list[CandidateEntity] = []
        for relation in erl.relations:
            top_results = self.topic_man.search_fuzzy(
                query=FuzzyQuery(
                    q=f"A {relation.entity} is {relation.relation} of {relation.target}",
                    limit=example_limit,
                    type=RETURN_TYPE.LINK,
                    relation_type=RELATION_TYPE.INSTANCE,
                )
            )
            relation_candidates.extend(
                [
                    CandidateRelation(
                        entity=res.link.from_subject.label,
                        relation=res.link.label,
                        target=res.link.to_subject.label,
                        score=res.score,
                        link=res.link,
                    )
                    for res in top_results.results
                ]
            )

        for entity in erl.entities:
            top_results = self.topic_man.search_fuzzy(
                query=FuzzyQuery(
                    q=f"A {entity.type}",
                    limit=example_limit,
                    type=RETURN_TYPE.SUBJECT,
                    relation_type=RELATION_TYPE.INSTANCE,
                )
            )
            candidates = [
                CandidateEntity(
                    type=res.subject.label,
                    score=res.score,
                    identifier=res.subject.label,
                    subject=res.subject,
                )
                for res in top_results.results
            ]
            candidate_ids = [c.subject.subject_id for c in candidates]
            entity_candidates.extend(candidates)
            for constraint in entity.constraints:
                top_results = self.topic_man.search_fuzzy(
                    query=FuzzyQuery(
                        q=f"The {constraint.property} of is {constraint.modifier} {constraint.value}",
                        limit=example_limit,
                        from_id=candidate_ids,
                        type=RETURN_TYPE.LINK,
                        relation_type=RELATION_TYPE.PROPERTY,
                    )
                )
                constraint_candidates.extend(
                    [
                        CandidateConstraint(
                            property=res.link.label,
                            value=None,
                            modifier=None,
                            score=res.score,
                            type=res.link.to_proptype,
                            entity=res.link.from_subject.subject_id,
                            link=res.link,
                        )
                        for res in top_results.results
                    ]
                )
        candidates = Candidates(
            relations=relation_candidates,
            entities=entity_candidates,
            constraints=constraint_candidates,
        )
        return candidates

    def build_constrained_classes(self, candidates: Candidates) -> BaseModel:
        constrained_classes = []
        ALLOWED_ENTITY_TYPES = Enum(
            "ALLOWED_ENTITY_TYPES",
            {e.type: e.type for e in candidates.entities},
        )
        ALLOWED_CONSTRAINT_TYPES = Enum(
            "ALLOWED_CONSTRAINT_TYPES",
            {c.property: c.property for c in candidates.constraints},
        )
        ALLOWED_RELATION_TYPES = Enum(
            "ALLOWED_RELATION_TYPES",
            {r.relation: r.relation for r in candidates.relations},
        )

        ConstrainedRelation = create_model(
            "ConstrainedRelation",
            # (BaseModel,),
            **{
                "entity": (str, ...),
                "relation": (ALLOWED_RELATION_TYPES, ...),
                "target": (str, ...),
            },
        )
        ConstrainedConstraint = create_model(
            "ConstrainedConstraint",
            # (BaseModel,),
            **{
                "property": (ALLOWED_CONSTRAINT_TYPES, ...),
                "value": (str, ...),
                "modifier": (str, ...),
            },
        )
        ConstrainedEntity = create_model(
            "ConstrainedEntity",
            # (BaseModel,),
            **{
                "type": (ALLOWED_ENTITY_TYPES, ...),
                "identifier": (str, ...),
                "constraints": (list[ConstrainedConstraint], []),
            },
        )
        ConstrainedEntitiesRelations = create_model(
            "ConstrainedEntitiesRelations",
            # (BaseModel,),
            **{
                "relations": (list[ConstrainedRelation], []),
                "entities": (list[ConstrainedEntity], []),
                "message": (str, "Constrained Entities and Relations"),
            },
        )

        return ConstrainedEntitiesRelations

    def enrich_entities_relations(
        self, erl: EntitiesRelations
    ) -> EnrichedEntitiesRelations:
        with Session(self.topic_man.engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            session.autoflush = False

            def enrich_relation(relation: Relation) -> EnrichedRelation:
                link_db = session.execute(
                    select(SubjectLinkDB)
                    .where(
                        SubjectLinkDB.label == relation.relation,
                    )
                    .limit(1)
                ).first()
                return EnrichedRelation(
                    link=SubjectLink.from_db(link_db[0], self.topic_man.oman),
                    **relation.model_dump(),
                )

            def enrich_constraint(constraint: Constraint) -> EnrichedConstraint:
                link_db = session.execute(
                    select(SubjectLinkDB)
                    .where(
                        SubjectLinkDB.label == constraint.property,
                    )
                    .limit(1)
                ).first()
                return EnrichedConstraint(
                    constraint=SubjectLink.from_db(link_db[0], self.topic_man.oman),
                    **constraint.model_dump(),
                )

            def enrich_entity(entity: Entity) -> EnrichedEntity:
                subject_db = session.execute(
                    select(SubjectInDB)
                    .where(
                        SubjectInDB.label == entity.type,
                    )
                    .limit(1)
                ).first()
                return EnrichedEntity(
                    subject=self.topic_man.oman.enrich_subject(
                        subject_db[0].subject_id
                    ),
                    constraints=[enrich_constraint(c) for c in entity.constraints],
                    **entity.model_dump(exclude=["constraints"]),
                )

            erl_enriched = EnrichedEntitiesRelations(
                relations=[enrich_relation(r) for r in erl.relations],
                entities=[enrich_entity(e) for e in erl.entities],
            )
            # swap links if the schema is the other way around - does not constrain llm
            # TODO: how could we constrain LLM?
            for relation in erl_enriched.relations:
                from_entity = next(
                    (
                        e
                        for e in erl_enriched.entities
                        if e.identifier == relation.entity
                    ),
                    None,
                )
                to_entity = next(
                    (
                        e
                        for e in erl_enriched.entities
                        if e.identifier == relation.target
                    ),
                    None,
                )
                if from_entity and to_entity:
                    if from_entity.subject.is_of_type(
                        relation.link.to_id
                    ) and to_entity.subject.is_of_type(relation.link.from_id):
                        relation.entity, relation.target = (
                            relation.target,
                            relation.entity,
                        )

            return erl_enriched
