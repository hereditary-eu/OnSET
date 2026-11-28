# %%
import os
import sys
import dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
dotenv.load_dotenv(env_path)
print("Loaded environment variables from", env_path)
sys.path.insert(0, os.path.abspath("../../"))
sys.path.append(os.path.abspath("../../backend/src"))
sys.path.append(os.path.abspath("backend/src"))

# %%
import pandas as pd

from backend.src.api import ManMan
from backend.src.eval_config import ALL_CONFIG_MAP, get_config
from backend.src.explorative.llm_query import (
    EnrichedEntitiesRelations,
    EnrichedEntity,
    EnrichedRelation,
)
from backend.src.agent.graph_tools import QueryGraph
from eval_common import base_arg_parser, load_examples, run_evals, score_erl

# %%
args = base_arg_parser(ALL_CONFIG_MAP.keys()).parse_args()

setup = get_config(args.dataset, args.cfg_idx)
generated_queries = load_examples(
    setup.name, EnrichedEntitiesRelations.model_validate_json
)
setup.agent.max_steps = generated_queries["n_nodes"].max() * 2
# the evaluation compares subjects and links only, so the agent gets no constraint tools
setup.agent.constraint_tools = False
man_man = ManMan(
    config_id=args.dataset,
    eval_cfg=setup,
)
print("Running agent against", setup.agent.base_url)


def graph_to_erl(graph: QueryGraph) -> EnrichedEntitiesRelations:
    entities = []
    for subject in graph.subjects:
        print(f"Processing subject {subject.id} with URI {subject.uri}")
        subject_full = subject.get_full(man_man, load_properties=False)
        entities.append(
            EnrichedEntity(
                subject=subject_full,
                identifier=subject.id,
                constraints=[],
                type=subject.uri,
            )
        )
    links = []
    for relation in graph.links:
        print(
            f"Processing relation {relation.uri} from {relation.from_subject_id} to {relation.to_subject_id}"
        )
        relation_full = relation.get_full(man_man)
        links.append(
            EnrichedRelation(
                link=relation_full,
                relation=relation.uri,
                entity=relation.from_subject_id,
                target=relation.to_subject_id,
            )
        )
    return EnrichedEntitiesRelations(
        entities=entities,
        relations=links,
    )


# %%
def run_eval(query: pd.Series):
    target_erl: EnrichedEntitiesRelations = query["erl_loaded"]
    query_string: str = query["response"]
    session = man_man.build_agent_session(f"test_{query_string}")
    print(
        f"Running query {query_string} with {len(target_erl.entities)} nodes and {len(target_erl.relations)} edges"
    )
    for resp in session.run_turn(
        content=query_string,
    ):
        if hasattr(resp, "delta") and resp.delta:
            print(resp.delta, end="")
    print(f"Query {query_string} completed")
    # convert the graph to the erl format and compare with the expected erl
    erl_result = graph_to_erl(session.graph)
    return [
        {
            **score_erl(
                target_erl, erl_result, normalize=man_man.ontology_manager.to_prefix
            ),
            "model": setup.model_id,
            "cfg_name": setup.name,
            "stage": "agent",
        }
    ]


if __name__ == "__main__":
    print("Running evals with setup", setup)
    output_file = f"results/eval_results_{setup.name}_agent_{setup.agent.model.replace('/', '_')}.csv"
    run_evals(generated_queries.iloc[: args.n_samples], run_eval, outfile=output_file)
