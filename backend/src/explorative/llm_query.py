from llama_cpp.llama import Llama

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session
from pydantic import BaseModel, create_model
from enum import Enum
import datetime
from fastapi import BackgroundTasks
import numpy as np
import tqdm

from utils import chat_content, escape_sparql_var, few_shot_messages, fix_json, grammar_for

from explorative.explorative_support import GuidanceManager, read_only_session
from explorative.exp_model import (
    FuzzyQuery,
    RETURN_TYPE,
    RELATION_TYPE,
    SubjectLinkDB,
    SubjectInDB,
    SampledGraphDB,
    GraphLinkDB,
    GraphEntityDB,
    BasePostgres,
)
from model import Subject, SubjectLink
from redis_cache import RedisCache
from explorative.llm_query_gen import choose_graph, reduce_erl

# The ERL models are re-exported here, the evaluation scripts import them from this module
from assistant.assistant_model import (
    Entity,
    EntitiesRelations,
    Constraint,
    Relation,
    EnrichedEntitiesRelations,
    EnrichedEntity,
    EnrichedRelation,
    EnrichedConstraint,
    Candidates,
    CandidateEntity,
    CandidateRelation,
    CandidateConstraint,
    QueryProgress,
)
from initiator import Initationatable

# System prompt describes information given to all conversations
ERL_PROMPT_SYSTEM = """
Return all the entity relations within the prompt in the form of JSON output. The output should be a list of all entities and their constraints, as well as the relations between them. Make sure to include all entities and targets in the list of entities
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
            # constraints=[
            #     Constraint(property="birth_date", value="1990", modifier="greater_than")
            # ],
        ),
        Entity(identifier="work 1", type="work", constraints=[]),
        Entity(identifier="place 1", type="place", constraints=[]),
    ],
)
# Example prompt demonstrating the output we are looking for
ERL_PROMPT_EXAMPLE = (
    "the birth place of an author of a work",
    ERL_SAMPLE.model_dump_json(),
)

ERL_PROMPT_QUERY_GEN = """You are a helpful assistant turning relational knowledge into natural language."""

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
    # constraints=[
    #     CandidateConstraint(
    #         property="birth date",
    #         value="1990",
    #         modifier="greater_than",
    #         score=0.9,
    #         type="sko:DateTime",
    #         entity="person 1",
    #     ),
    #     CandidateConstraint(
    #         property="death year",
    #         value="180cm",
    #         modifier="greater_than",
    #         score=0.8,
    #         type="sko:DateTime",
    #         entity="person 1",
    #     ),
    # ],
)

RAG_PROMPT_SYSTEM = """
Return all the entity relations within the prompt in the form of JSON output. The output should be a list of all entitie, as well as the relations between them. Make sure to include all entities and targets in the list of entities. Constraints should only be included in the list of entities they are associated with.
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
            # constraints=[
            #     Constraint(
            #         property="birth date",
            #         value="1.1.1990",
            #         modifier="greater_than",
            #     )
            # ],
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


class LLMQuery(Initationatable):
    def __init__(
        self,
        topic: GuidanceManager,
        zero_shot=False,
        temperature=0.4,
        max_tokens=1024,  # 1024 is the default for llama.cpp,
        redis_url="redis://localhost:6379/0",
    ):
        self.max_tokens = max_tokens
        self.zero_shot = zero_shot
        self.temperature = temperature
        self.guidance_man = topic
        self.grammar_erl = grammar_for(EntitiesRelations, "EntitiesRelations")
        self.grammar_candidates = grammar_for(Candidates, "Candidates")
        self.query_id_counter = 0
        self.cache = RedisCache[QueryProgress](model=QueryProgress, redis_url=redis_url)

    def run_query(
        self, query: str, progress: QueryProgress | None = None, enable_cache=True
    ):
        if progress is None:
            progress = QueryProgress(
                max_steps=5,
                id="query:0",
                start_time=datetime.datetime.now().isoformat(),
                relations_steps=[],
            )

        def advance(step: int, message: str):
            progress.progress = step
            progress.message = message
            if enable_cache:
                self.cache[progress.id] = progress

        advance(1, "Querying entities and relations")

        erl = self.query_erl(query)
        erl.message = "Found entities and relations"
        progress.relations_steps.append(erl)
        advance(2, "Fetching possible candidates")

        candidates = self.candidates_for_erl(erl)
        candidates.message = "Found similar candidates"
        progress.relations_steps.append(candidates)
        advance(3, "Querying candidates")

        constrained_erl = self.query_constrained(query, candidates)
        constrained_erl.message = "Constraints applied"
        # store a plain copy, the dynamic Enum model neither serialises nor compares by string
        progress.relations_steps.append(
            EntitiesRelations.model_validate(constrained_erl.model_dump(mode="json"))
        )
        advance(4, "Enriching results")

        enriched_erl = self.enrich_entities_relations(constrained_erl, candidates)
        enriched_erl.message = "Aligned results"
        progress.enriched_relations = enriched_erl
        progress.relations_steps.append(enriched_erl)
        advance(5, "Query completed")
        return progress

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
        background_tasks.add_task(self.run_query, query, progress)
        return progress

    def query_progress(self, query_id: str) -> QueryProgress:
        return self.cache[query_id]

    @property
    def model(self) -> Llama:
        return self.guidance_man.llama_model

    def query_erl(self, query: str) -> EntitiesRelations:
        messages = few_shot_messages(
            ERL_PROMPT_SYSTEM,
            query,
            example=None if self.zero_shot else ERL_PROMPT_EXAMPLE,
        )
        response_msg = chat_content(
            self.model,
            messages,
            grammar=self.grammar_erl,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        fixed_response = fix_json(response_msg, item_keys=["entities", "relations"])
        return EntitiesRelations.model_validate(fixed_response)

    def query_constrained(self, query: str, candidates: Candidates) -> BaseModel:
        ConstrainedEntitiesRelations = self.build_constrained_classes(candidates)
        grammar_constrained = grammar_for(
            ConstrainedEntitiesRelations, "ConstrainedEntitiesRelations"
        )
        messages = few_shot_messages(
            RAG_PROMPT_SYSTEM,
            query,
            example=(
                None
                if self.zero_shot
                else (RAG_PROMPT_EXAMPLE[0], RAG_PROMPT_EXAMPLE[2])
            ),
        )
        response_msg = chat_content(
            self.model,
            messages,
            grammar=grammar_constrained,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        fixed_response = fix_json(response_msg, item_keys=["entities", "relations"])

        return ConstrainedEntitiesRelations.model_validate(fixed_response)

    def candidates_for_erl(
        self, erl: EntitiesRelations, candidate_limit=3
    ) -> Candidates:
        relation_candidates: list[CandidateRelation] = []
        constraint_candidates: list[CandidateConstraint] = []
        entity_candidates: list[CandidateEntity] = []
        for relation in erl.relations:
            top_results = self.guidance_man.search_fuzzy(
                query=FuzzyQuery(
                    q=f"A {relation.entity} is {relation.relation} of {relation.target}",
                    limit=candidate_limit,
                    type=RETURN_TYPE.LINK,
                    relation_type=RELATION_TYPE.INSTANCE,
                    include_thing=False,
                ),
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
            top_results = self.guidance_man.search_fuzzy(
                query=FuzzyQuery(
                    q=f"A {entity.type}",
                    limit=candidate_limit,
                    type=RETURN_TYPE.SUBJECT,
                    relation_type=RELATION_TYPE.INSTANCE,
                    include_thing=False,
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
            entity_candidates.extend(candidates)
            # candidate_ids = [c.subject.subject_id for c in candidates]
            # for constraint in entity.constraints:
            #     top_results = self.guidance_man.search_fuzzy(
            #         query=FuzzyQuery(
            #             q=f"The {constraint.property} of is {constraint.modifier} {constraint.value}",
            #             limit=candidate_limit,
            #             from_id=candidate_ids,
            #             type=RETURN_TYPE.LINK,
            #             relation_type=RELATION_TYPE.PROPERTY,
            #             include_thing=False,
            #         )
            #     )
            #     constraint_candidates.extend(
            #         [
            #             CandidateConstraint(
            #                 property=res.link.label,
            #                 value=None,
            #                 modifier=None,
            #                 score=res.score,
            #                 type=res.link.to_proptype,
            #                 entity=res.link.from_subject.subject_id,
            #                 link=res.link,
            #             )
            #             for res in top_results.results
            #         ]
            #     )
        candidates = Candidates(
            relations=relation_candidates,
            entities=entity_candidates,
            # constraints=constraint_candidates,
        )
        return candidates

    def build_constrained_classes(self, candidates: Candidates) -> BaseModel:
        # member name = ontology id, value = label (what the grammar lets the model pick)
        entity_types = {
            e.subject.subject_id: e.type
            for e in candidates.entities
            if e.subject is not None
        }
        ALLOWED_ENTITY_TYPES = (
            Enum("ALLOWED_ENTITY_TYPES", entity_types) if entity_types else str
        )

        # constrained_classes = []
        # ALLOWED_CONSTRAINT_TYPES = Enum(
        #     "ALLOWED_CONSTRAINT_TYPES",
        #     {c.link.property_id: c.property for c in candidates.constraints},
        # )
        # if len(candidates.constraints) == 0:
        #     ALLOWED_CONSTRAINT_TYPES = str

        relation_types = {
            r.link.property_id: r.relation
            for r in candidates.relations
            if r.link is not None
        }
        ALLOWED_RELATION_TYPES = (
            Enum("ALLOWED_RELATION_TYPES", relation_types) if relation_types else str
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
        # ConstrainedConstraint = create_model(
        #     "ConstrainedConstraint",
        #     # (BaseModel,),
        #     **{
        #         "property": (ALLOWED_CONSTRAINT_TYPES, ...),
        #         "value": (str, ...),
        #         "modifier": (str, ...),
        #     },
        # )
        ConstrainedEntity = create_model(
            "ConstrainedEntity",
            # (BaseModel,),
            **{
                "type": (ALLOWED_ENTITY_TYPES, ...),
                "identifier": (str, ...),
                # "constraints": (list[ConstrainedConstraint], []),
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
        self, erl: BaseModel, candidates: Candidates
    ) -> EnrichedEntitiesRelations:
        """Aligns the (constrained) ERL with the ontology.

        Constrained types are Enum members whose name is the candidate's subject/property id,
        so they resolve directly. Plain strings fall back to a label match against the
        candidates and then the database. Entities/relations that cannot be resolved are dropped.
        """
        subject_candidates = {
            c.subject.subject_id: c.subject
            for c in candidates.entities
            if c.subject is not None
        }
        link_candidates = {
            c.link.property_id: c.link
            for c in candidates.relations
            if c.link is not None
        }

        def match_label(value: str, items: dict, label_of) -> str | None:
            value = value.strip().casefold()
            return next(
                (
                    key
                    for key, item in items.items()
                    if (label_of(item) or "").strip().casefold() == value
                ),
                None,
            )

        with read_only_session(self.guidance_man.engine) as session:

            def resolve_subject_id(type_) -> str | None:
                if isinstance(type_, Enum):
                    if type_.name in subject_candidates:
                        return type_.name
                    type_ = type_.value
                if not isinstance(type_, str) or not type_:
                    return None
                if type_ in subject_candidates:
                    return type_
                found = match_label(type_, subject_candidates, lambda s: s.label)
                if found is not None:
                    return found
                row = session.execute(
                    select(SubjectInDB.subject_id)
                    .where(func.lower(SubjectInDB.label) == type_.strip().lower())
                    .limit(1)
                ).first()
                return row[0] if row else None

            def resolve_link(relation_) -> SubjectLink | None:
                if isinstance(relation_, Enum):
                    if relation_.name in link_candidates:
                        return link_candidates[relation_.name]
                    relation_ = relation_.value
                if not isinstance(relation_, str) or not relation_:
                    return None
                if relation_ in link_candidates:
                    return link_candidates[relation_]
                found = match_label(relation_, link_candidates, lambda l: l.label)
                if found is not None:
                    return link_candidates[found]
                row = session.execute(
                    select(SubjectLinkDB)
                    .where(
                        func.lower(SubjectLinkDB.label) == relation_.strip().lower()
                    )
                    .limit(1)
                ).first()
                return row[0].from_db(self.guidance_man.oman) if row else None

            def as_str(value) -> str:
                return value.value if isinstance(value, Enum) else str(value)

            entities: list[EnrichedEntity] = []
            for entity in erl.entities:
                subject_id = resolve_subject_id(entity.type)
                subject = (
                    self.guidance_man.oman.enrich_subject(subject_id)
                    if subject_id is not None
                    else None
                )
                if subject is None:
                    print(f"Dropping unresolved entity {entity.identifier}: {entity.type}")
                    continue
                entities.append(
                    EnrichedEntity(
                        identifier=entity.identifier,
                        type=as_str(entity.type),
                        subject=subject,
                    )
                )
            relations: list[EnrichedRelation] = []
            for relation in erl.relations:
                link = resolve_link(relation.relation)
                if link is None:
                    print(f"Dropping unresolved relation {relation.relation}")
                    continue
                relations.append(
                    EnrichedRelation(
                        link=link,
                        relation=as_str(relation.relation),
                        entity=relation.entity,
                        target=relation.target,
                    )
                )
            erl_enriched = EnrichedEntitiesRelations(
                relations=relations, entities=entities
            )

            def get_entity_by_id(identifier: str):
                return next(
                    (e for e in erl_enriched.entities if e.identifier == identifier),
                    None,
                )

            # swap links if the schema is the other way around - does not constrain llm
            for relation in erl_enriched.relations:
                from_entity = get_entity_by_id(relation.entity)
                to_entity = get_entity_by_id(relation.target)
                if (
                    from_entity is not None
                    and from_entity.subject.is_of_type(relation.link.to_id)
                ) or (
                    to_entity is not None
                    and to_entity.subject.is_of_type(relation.link.from_id)
                ):
                    print(
                        f"Swapping relation {relation.relation} from {relation.entity} to {relation.target}"
                    )
                    relation.entity, relation.target = relation.target, relation.entity
                # add missing entities from the relation's schema
                for identifier, subject_id in (
                    (relation.entity, relation.link.from_id),
                    (relation.target, relation.link.to_id),
                ):
                    if not subject_id or get_entity_by_id(identifier) is not None:
                        continue
                    subject = session.execute(
                        select(SubjectInDB)
                        .where(SubjectInDB.subject_id == subject_id)
                        .limit(1)
                    ).first()
                    if subject:
                        subject_parsed: Subject = subject[0].from_db(
                            self.guidance_man.oman
                        )
                        erl_enriched.entities.append(
                            EnrichedEntity(
                                identifier=identifier,
                                type=subject_parsed.label or subject_id,
                                subject=subject_parsed,
                            )
                        )
            # drop relations whose endpoints could not be resolved
            erl_enriched.relations = [
                r
                for r in erl_enriched.relations
                if get_entity_by_id(r.entity) is not None
                and get_entity_by_id(r.target) is not None
            ]
            # remove orphan entities that are not in any relation
            linked = {r.entity for r in erl_enriched.relations} | {
                r.target for r in erl_enriched.relations
            }
            if linked:
                erl_enriched.entities = [
                    e for e in erl_enriched.entities if e.identifier in linked
                ]
            return erl_enriched

    def initiate(self, force=False, n_queries=10, k_min=2, k_max=4, seed=42):
        do_init = False
        if force:
            do_init = True
        else:
            with Session(self.guidance_man.engine) as session:
                count = session.execute(
                    select(func.count(SampledGraphDB.graph_id)).where(
                        SampledGraphDB.onto_hash == self.guidance_man.identifier
                    )
                ).scalar()
                if count == 0:
                    do_init = True
        if not do_init:
            return None
        rs = np.random.RandomState(42)
        k_s = rs.randint(k_min, k_max, n_queries)
        queries: list[tuple[str, EnrichedEntitiesRelations]] = []
        for i, k in enumerate(tqdm.tqdm(k_s)):
            query_graph = choose_graph(
                k, guidance_man=self.guidance_man, seed=seed + i, top_k=10
            )
            query_graph_reduced = reduce_erl(query_graph)
            query_str = chat_content(
                self.guidance_man.llama_model,
                # grammar=self.grammar_erl,
                messages=[
                    {
                        "role": "system",
                        "content": ERL_PROMPT_QUERY_GEN,
                    },
                    {
                        "role": "user",
                        "content": ERL_PROMPT_EXAMPLE[1],
                    },
                    {
                        "role": "assistant",
                        "content": ERL_PROMPT_EXAMPLE[0],
                    },
                    {
                        "role": "user",
                        "content": query_graph_reduced.model_dump_json(),
                    },
                ],
                max_tokens=4096,
                temperature=0.3,  # get wild :)
            )
            queries.append((query_str, query_graph))

        BasePostgres.metadata.create_all(self.guidance_man.engine, checkfirst=True)
        with Session(self.guidance_man.engine) as session:
            # session.execute(text("SET TRANSACTION READ ONLY"))
            session.autoflush = True

            for query_str, query_graph in queries:
                sampled_graph = SampledGraphDB(
                    graph_name=f"k={len(query_graph.entities)}",
                    graph_query=query_str,
                    onto_hash=self.guidance_man.identifier,
                    instance_count=-1,
                )
                subject_ids = [e.subject.subject_id for e in query_graph.entities]

                entities: dict[str, GraphEntityDB] = {}

                for subject_id in subject_ids:
                    subject_link = session.execute(
                        select(SubjectInDB)
                        .where(SubjectInDB.subject_id == subject_id)
                        .limit(1)
                    ).first()
                    if subject_link:
                        entity = GraphEntityDB(
                            subject_id=subject_link[0].subject_id,
                        )
                        entity.graph = sampled_graph
                        entities[subject_id] = entity
                        session.add(entity)
                links: dict[int, SubjectLinkDB] = {}
                for rel in query_graph.relations:
                    link = GraphLinkDB(
                        subject_link_id=rel.link.link_id,
                    )
                    link.graph = sampled_graph
                    from_entity = entities[rel.link.from_id]
                    to_entity = entities[rel.link.to_id]

                    link.from_entity = from_entity
                    link.to_entity = to_entity
                    links[rel.link.link_id] = link
                    session.add(link)
                session.add(sampled_graph)
                session.commit()
        return queries

    def get_examples(self, n=10) -> list[EnrichedEntitiesRelations]:
        with Session(self.guidance_man.engine) as sess:
            graphs = (
                sess.query(SampledGraphDB)
                .filter(SampledGraphDB.onto_hash == self.guidance_man.identifier)
                .all()
            )
            examples = []
            for graph in graphs:
                query_graph = EnrichedEntitiesRelations(message=graph.graph_query)
                for entity in graph.graph_entities:
                    enriched_entity = EnrichedEntity(
                        identifier=f"{escape_sparql_var(entity.subject.subject_id)}_{entity.entity_id}",
                        constraints=[],
                        type=entity.subject.subject_id,
                        subject=self.guidance_man.oman.enrich_subject(
                            entity.subject.subject_id
                        ),
                    )
                    query_graph.entities.append(enriched_entity)
                for link in graph.graph_links:
                    enriched_relation = EnrichedRelation(
                        entity=f"{escape_sparql_var(link.from_entity.subject.subject_id)}_{link.from_entity.entity_id}",
                        relation=link.subject_link.property_id,
                        target=f"{escape_sparql_var(link.to_entity.subject.subject_id)}_{link.to_entity.entity_id}",
                        link=link.subject_link.from_db(self.guidance_man.oman),
                    )
                    query_graph.relations.append(enriched_relation)
                examples.append(query_graph)
            if len(examples) < n:
                print(
                    f"Not enough examples found in the database, found {len(examples)}, generating {n - len(examples)} more"
                )
                new_examples = self.initiate(force=True, n_queries=n - len(examples))
                if new_examples:
                    examples.extend([e[1] for e in new_examples])
            return examples
