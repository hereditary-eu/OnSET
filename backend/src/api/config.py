import os
import threading
from collections import OrderedDict
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from assistant.iterative_assistant import IterativeAssistant
from assistant.model import Operations
from datasetmatcher import DatasetManager
from eval_config import CONFIG_FILE, EvalConfig, MultimodalConfig
from explorative.explorative_support import GuidanceManager
from explorative.llm_query import LLMQuery
from initiator import InitatorManager
from ontology import Graph, OntologyConfig, OntologyManager
from redis_cache import RedisCache

from rdflib.plugins.stores.sparqlstore import SPARQLStore

base_path = "../../data"
onto_path = f"{base_path}/hero-ontology/hereditary_clinical.ttl"

# Name of the URL path parameter selecting the configuration, e.g. /{config_id}/classes/roots
CONFIG_PATH_PARAM = "config_id"


class ManMan:
    def __init__(self, config_id: str, db_config: EvalConfig):
        self.config_id = config_id
        self.db_config = db_config
        print(f"Using DB config '{config_id}':", db_config)

        self.base_path = base_path
        self.onto_path = onto_path
        self.start_systems()

    def start_systems(self):
        db_config = self.db_config
        self.store = SPARQLStore(
            db_config.sparql_endpoint,
            method="POST_FORM",
            params={"infer": False, "sameAs": False},
            timeout=300,
        )
        # store = SPARQLStore(
        #     "http://examode.dei.unipd.it:7200/repositories/TUGraz_test",
        #     method="POST_FORM",
        #     params={"infer": False, "sameAs": False},
        #     headers={
        #         "Authorization": "GDB eyJ1c2VybmFtZSI6ImJlbmVkaWt0LmthbnR6IiwiYXV0aGVudGljYXRlZEF0IjoxNzMzODMxOTk3NTIzfQ==.QqebiiJt752/OThRujrJyNg0XXKrrteU7MhNPUCoSBI="
        #     },
        # )
        self.graph = Graph(store=self.store)

        self.config = OntologyConfig()
        self.config.multimodal_config = (
            db_config.multimodal_config
            if db_config.multimodal_config
            else MultimodalConfig()
        )
        self.config.ontology_extension = db_config.ontology_extension
        self.ontology_manager = OntologyManager(self.config, self.graph)
        self.dataset_manager = DatasetManager(self.ontology_manager)
        # dataset_manager.initialise(glob_path="data/datasets/ALS/**/*.csv")

        # ontology_manager.load_full_graph()

        self.guidance_man = GuidanceManager(
            self.ontology_manager,
            conn_str=db_config.conn_str,
            llm_model_id=db_config.model_id,
        )
        # topic_man.initialize_topics(force=False)

        self.llm_query = LLMQuery(
            topic=self.guidance_man, redis_url=db_config.redis_cache_url
        )

        self.initatior = InitatorManager()
        self.initatior.register(self.guidance_man)
        self.initatior.register(self.llm_query)

        self.iterative_assistant = IterativeAssistant(guidance=self.guidance_man)

        self.assistant_cache = RedisCache(
            redis_url=db_config.redis_cache_url,
            model=Operations,
        )


class ManManRegistry:
    """Lazily creates one ManMan per configuration and keeps the most recently used ones.

    Each ManMan may hold its own embedding/LLM models, so at most ``max_loaded``
    of them are kept alive (``ONSET_MAX_LOADED_CONFIGS``, 0 = unlimited).
    """

    def __init__(self, max_loaded: int = 0):
        self.max_loaded = max_loaded
        self._loaded: OrderedDict[str, ManMan] = OrderedDict()
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def __contains__(self, config_id: str) -> bool:
        return config_id in CONFIG_FILE.configs

    def get(self, config_id: str) -> ManMan:
        if config_id not in self:
            raise KeyError(config_id)
        with self._lock:
            if config_id in self._loaded:
                self._loaded.move_to_end(config_id)
                return self._loaded[config_id]
            key_lock = self._key_locks.setdefault(config_id, threading.Lock())
        # Construct outside the global lock so other configurations stay responsive
        with key_lock:
            with self._lock:
                if config_id in self._loaded:
                    return self._loaded[config_id]
            manman = ManMan(config_id, CONFIG_FILE.base(config_id))
            with self._lock:
                self._loaded[config_id] = manman
                while self.max_loaded > 0 and len(self._loaded) > self.max_loaded:
                    evicted, _ = self._loaded.popitem(last=False)
                    print(f"Unloading config '{evicted}'")
            return manman


REGISTRY = ManManRegistry(max_loaded=int(os.getenv("ONSET_MAX_LOADED_CONFIGS", "0")))


def get_manman(request: Request) -> ManMan:
    """Resolve the ManMan of the configuration addressed in the URL path."""
    config_id = request.path_params.get(CONFIG_PATH_PARAM)
    if config_id is None or config_id not in REGISTRY:
        raise HTTPException(
            status_code=404, detail=f"Unknown configuration '{config_id}'"
        )
    return REGISTRY.get(config_id)


ManManDep = Annotated[ManMan, Depends(get_manman)]
