from fastapi import (
    APIRouter,
    Query,
)

from api.config import ManManDep
from model import Instance, Property, Subject
from ontology import InstanceQuery
from utils import wrap_iri


instances_router = APIRouter(prefix="/instances")


@instances_router.get("")
def get_named_instance(manman: ManManDep, cls: str = Query()) -> list[Subject]:
    return manman.ontology_manager.get_named_individuals(cls)


@instances_router.get("/search")
def get_named_instance_search(manman: ManManDep, query: InstanceQuery = Query()) -> list[Instance]:
    return manman.ontology_manager.get_instances(query)


@instances_router.get("/properties")
def get_named_instance_properties(manman: ManManDep, instance_id: str = Query()) -> dict[str, Property]:
    instance_id = wrap_iri(instance_id)
    return manman.ontology_manager.outgoing_edges_for(instance_id)
