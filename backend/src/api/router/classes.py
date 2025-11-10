from fastapi import (
    APIRouter,
    Query,
    Body,
    BackgroundTasks,
)


from api.config import DEFAULT_MANMAN
from model import GeneralizationQuery, Instance, Property, SparseOutLinks, Subject, SubjectLink
from ontology import InstanceQuery
from explorative.exp_model import (
    SubjectLinkDB,
    FuzzyQuery,
    FuzzyQueryResults,
)
from explorative.llm_query import QueryProgress, EnrichedEntitiesRelations
from assistant.model import QueryGraph, Operations
from sqlalchemy.orm import Session


manman = DEFAULT_MANMAN

classes_router = APIRouter(prefix="/classes")


@classes_router.get("/outlinks")
def get_outlinks(subject_id: str = Query()) -> SparseOutLinks:
    if not hasattr(manman.dataset_manager, "engine"):
        manman.dataset_manager.initialise(
            glob_path=f"{manman.base_path}/datasets/ALS/**/*.csv"
        )
    return manman.dataset_manager.target_outlinks(subject_id)


@classes_router.get("/subjects")
def get_subject(
    subject_id: str = Query(),
) -> Subject | None:
    return manman.ontology_manager.enrich_subject(subject_id)


@classes_router.get("/links")
def get_link(
    link_id: str = Query(),
) -> SubjectLink | None:
    with Session(manman.guidance_man.engine) as session:
        link = (
            session.query(SubjectLinkDB)
            .filter(SubjectLinkDB.property_id == link_id)
            .first()
        )
        if link is None:
            return None
        return link.from_db(oman=manman.ontology_manager)


@classes_router.post("/search")
def search_classes(
    q: FuzzyQuery = Body(FuzzyQuery()),
) -> FuzzyQueryResults:
    return manman.guidance_man.search_fuzzy(q)


@classes_router.get("/relations")
def get_relations(
    q: str | None = Query(None),
    from_id: str | None = Query(None),
    to_id: str | None = Query(None),
) -> list[SubjectLink]:
    return manman.guidance_man.search_links(q, from_id, to_id)


@classes_router.get("/search/llm")
def get_llm_results(
    background_tasks: BackgroundTasks,
    q: str = Query("working field of person"),
) -> QueryProgress:
    return manman.llm_query.start_query(q, background_tasks)


@classes_router.get("/search/llm/running")
def get_llm_results_running(
    query_id: str = Query(),
) -> QueryProgress | None:
    return manman.llm_query.query_progress(query_id)


@classes_router.get("/search/llm/examples")
def get_llm_examples() -> list[EnrichedEntitiesRelations]:
    return manman.llm_query.get_examples()


@classes_router.post("/search/assistant")
def get_assistant_results(
    q: str = Query("working field of person"),
    graph: QueryGraph = Body(...),
) -> Operations:
    key = f"{q}_{graph.model_dump_json()}"
    cache = manman.assistant_cache[key]
    if cache:
        return cache
    else:
        operations = manman.iterative_assistant.run_query(q, graph)
        manman.assistant_cache[key] = operations
        return operations


@classes_router.get("/full")
def get_full_classes() -> list[Subject]:
    roots = manman.ontology_manager.get_full_classes()
    return roots


@classes_router.get("/roots")
def get_root_classes() -> list[Subject]:
    return manman.ontology_manager.get_root_classes()


@classes_router.get("/subclasses")
def get_class(cls: str = Query()) -> list[Subject]:
    return manman.ontology_manager.get_subclasses(cls)


@classes_router.post("/subclasses/search")
def get_class_search(q: FuzzyQuery = Body(FuzzyQuery())) -> FuzzyQueryResults:
    return manman.guidance_man.search_subclasses(q)


@classes_router.post("/parents/most_generic")
def get_most_generics(
    q: GeneralizationQuery = Body(GeneralizationQuery()),
) -> Subject:
    return manman.ontology_manager.get_most_generic_classes(q)


@classes_router.get("/instances")
def get_named_instance(cls: str = Query()) -> list[Subject]:
    return manman.ontology_manager.get_named_individuals(cls)


@classes_router.get("/instances/search")
def get_named_instance_search(query: InstanceQuery = Query()) -> list[Instance]:
    return manman.ontology_manager.get_instances(query)


@classes_router.get("/instances/properties")
def get_named_instance_properties(instance_id: str = Query()) -> dict[str, Property]:
    return manman.ontology_manager.outgoing_edges_for(instance_id)
