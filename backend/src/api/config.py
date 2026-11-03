import os
import threading
from collections import OrderedDict
from functools import cached_property
from typing import Annotated

from fastapi import Depends, HTTPException, WebSocketException, status
from starlette.requests import HTTPConnection

from agent.llm import AgentLLM
from agent.session import AgentSession, AgentSessionStore
from assistant.iterative_assistant import IterativeAssistant
from assistant.assistant_model import Operations
from assistant.progressive import ProgressiveResult, ProgressiveSampler
from datasetmatcher import DatasetManager
from eval_config import CONFIG_FILE, EvalConfig, MultimodalConfig
from explorative.explorative_support import GuidanceManager
from explorative.llm_query import LLMQuery
from initiator import InitatorManager
from ontology import Graph, OntologyConfig, OntologyManager
from redis_cache import RedisCache

from rdflib.plugins.stores.sparqlstore import SPARQLStore

base_path = "../../data"

# Name of the URL path parameter selecting the configuration, e.g. /{config_id}/classes/roots
CONFIG_PATH_PARAM = "config_id"


class ManMan:
    def __init__(self, config_id: str, eval_cfg: EvalConfig):
        self.config_id = config_id
        self.db_config = eval_cfg
        print(f"Using DB config '{config_id}':", eval_cfg)

        self.base_path = base_path

        self.ontology_manager: OntologyManager
        self.dataset_manager: DatasetManager
        self.guidance_man: GuidanceManager
        self.llm_query: LLMQuery
        self.initatior: InitatorManager

        self.start_systems()

    def start_systems(self):
        db_config = self.db_config
        self.store = SPARQLStore(
            db_config.sparql_endpoint,
            method="POST_FORM",
            params={"infer": False, "sameAs": False},
            timeout=300,
        )
        self.graph = Graph(store=self.store)

        self.config = OntologyConfig()
        self.config.multimodal_config = (
            db_config.multimodal_config
            if db_config.multimodal_config
            else MultimodalConfig()
        )
        self.config.ontology_extension = db_config.ontology_extension
        self.config.save_named_individuals = db_config.save_named_individuals
        if db_config.additional_namespaces:
            self.config.additional_namespaces.update(db_config.additional_namespaces)
        self.ontology_manager = OntologyManager(self.config, self.graph)
        # initialised lazily by GET /classes/outlinks
        self.dataset_manager = DatasetManager(self.ontology_manager)

        self.guidance_man = GuidanceManager(
            self.ontology_manager,
            conn_str=db_config.conn_str,
            llm_model_id=db_config.model_id,
            llm_quant_model=db_config.model_quant,
            device=db_config.device,
        )

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

    # --- agent chat (api/router/agent.py), created on first use ---

    @cached_property
    def agent_llm(self) -> AgentLLM:
        return AgentLLM(self.db_config.agent)

    def build_agent_session(self, session_id: str) -> AgentSession:
        return AgentSession(
            session_id,
            llm=self.agent_llm,
            ontology_manager=self.ontology_manager,
            guidance=self.guidance_man,
            config=self.db_config.agent,
        )

    @cached_property
    def agent_sessions(self) -> AgentSessionStore:
        return AgentSessionStore(
            lambda session_id: self.build_agent_session(session_id),
        )


    # --- progressive discovery (api/router/progressive.py), created on first use ---

    @cached_property
    def progressive(self) -> ProgressiveSampler:
        # schema lookups from the stored schema (Postgres), counts from the endpoint
        return ProgressiveSampler(
            self.ontology_manager,
            schema=self.guidance_man.schema_index,
            config=self.db_config.progressive,
        )

    @cached_property
    def progressive_cache(self) -> RedisCache[ProgressiveResult]:
        return RedisCache(redis_url=self.db_config.redis_cache_url, model=ProgressiveResult)


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


def get_manman(connection: HTTPConnection) -> ManMan:
    """Resolve the ManMan of the configuration addressed in the URL path.

    Works for HTTP requests and WebSockets alike (both are HTTPConnections).
    """
    config_id = connection.path_params.get(CONFIG_PATH_PARAM)
    if config_id is None or config_id not in REGISTRY:
        reason = f"Unknown configuration '{config_id}'"
        if connection.scope["type"] == "websocket":
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION, reason=reason
            )
        raise HTTPException(status_code=404, detail=reason)
    return REGISTRY.get(config_id)


ManManDep = Annotated[ManMan, Depends(get_manman)]
