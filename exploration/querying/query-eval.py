# %%
import sys
import os
import traceback

sys.path.insert(0, os.path.abspath("../../"))
sys.path.append(os.path.abspath("../../backend/src"))

from rdflib.plugins.stores.sparqlstore import SPARQLStore

from backend.src.ontology import OntologyManager, OntologyConfig, Graph
from backend.src.explorative.explorative_support import GuidanceManager
from backend.src.explorative.llm_query import (
    EnrichedEntitiesRelations,
    EntitiesRelations,
    LLMQuery,
    QueryProgress,
)
import pandas as pd

from backend.src.eval_config import ALL_CONFIG_MAP, EvalConfig
from eval_common import (
    base_arg_parser,
    load_examples,
    run_evals,
    score_erl,
    wait_for_endpoint,
)

# %%
configs = ALL_CONFIG_MAP
parser = base_arg_parser(configs.keys())
parser.add_argument("--zero_shot", action="store_true")
args = parser.parse_args()


setup: EvalConfig = configs[args.dataset][args.cfg_idx]
setup_base = configs[args.dataset][-1]
print("Started with args", args)
print("Setup for", setup)

wait_for_endpoint(setup.sparql_endpoint)
store = SPARQLStore(
    setup.sparql_endpoint,
    method="POST_FORM",
    params={"infer": False, "sameAs": False},
)
graph = Graph(store=store)

# same prefixes/extension as the API: the stored schema ids use them (e.g. dbo:)
config = OntologyConfig.from_eval_config(setup)

ontology_manager = OntologyManager(config, graph)
topic_man = GuidanceManager(
    ontology_manager,
    llm_model_id=setup.model_id,
    ctx_size=6000,
    conn_str=setup.conn_str,
    llm_quant_model=setup.model_quant,
)

# %%
generated_queries = load_examples(
    setup_base.name, EnrichedEntitiesRelations.model_validate_json
)


# %%
def run_eval(query: pd.Series, llm_query: LLMQuery):
    target_erl: EnrichedEntitiesRelations = query["erl_loaded"]
    progress = QueryProgress(id="0", max_steps=1, start_time="0")
    error = None
    try:
        llm_query.run_query(query=query["response"], progress=progress, enable_cache=False)
    except Exception as e:
        # score the stages that finished, so one failing stage does not drop the query
        traceback.print_exc()
        error = repr(e)
    steps = progress.relations_steps  # raw, candidates, constrained, aligned
    eval_erls: dict[str, EntitiesRelations | EnrichedEntitiesRelations | None] = {
        "raw": steps[0] if len(steps) > 0 else None,
        "constrained": steps[2] if len(steps) > 2 else None,
        "aligned": progress.enriched_relations,
    }
    results = []
    for key, erl in eval_erls.items():
        if erl is None:
            continue
        try:
            scores = score_erl(target_erl, erl, normalize=ontology_manager.to_prefix)
        except Exception as e:
            traceback.print_exc()
            scores = {"score_error": repr(e)}
        results.append(
            {
                **scores,
                "error": error,
                "model": setup.model_id,
                "cfg_name": setup_base.name,
                "zeroshot": args.zero_shot,
                "stage": key,
            }
        )
    if not results and error is not None:
        raise RuntimeError(error)
    return results


if __name__ == "__main__":
    print("Running evals with setup", setup)
    zero_shot = args.zero_shot
    print(
        f"zero_shot={zero_shot}, n_samples={args.n_samples}, llm_model_id={setup.model_id}"
    )
    query_man = LLMQuery(topic_man, zero_shot=zero_shot, max_tokens=4096)
    output_file = f"results/eval_results_{setup_base.name}_{'zeroshot' if zero_shot else 'oneshot'}_{topic_man.llm_model_id.replace('/', '-')}.csv"
    run_evals(
        generated_queries.iloc[: args.n_samples],
        lambda q: run_eval(q, query_man),
        outfile=output_file,
    )
