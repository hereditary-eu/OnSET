"""Aggregate query-generation eval results into the paper's tables and figures.

Groups only by dataset, model and system (raw / aligned / agent).
Run from anywhere: `uv run --project backend python exploration/querying/result_parse.py`.
"""

import glob
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import tikzplotlib

os.chdir(Path(__file__).parent)

MODEL_MAP = {
    "NousResearch Hermes 3 Llama 3.2 3B": "Hermes 3 3B",
    "NousResearch Hermes 3 Llama 3.1 8B": "Hermes 3 8B",
    "NousResearch Hermes 3 Llama 3.1 70B": "Hermes 3 70B",
    "bartowski Mistral Small Instruct": "Mistral Small 24B",
    "bartowski Qwen2.5 Coder 32B": "Qwen2.5 Coder 32B",
    "bartowski Qwen2.5 32B Instruct": "Qwen2.5 Instruct 32B",
    "Qwen3.8 27B Q4": "Qwen3.8 27B",
    "unsloth Qwen3.8 27B GGUF": "Qwen3.8 27B",
    "LiquidAI LFM3 1.7B": "LFM3 1.7B",
}
MODELS = ["LFM3 1.7B", "Qwen3.8 27B"]  # plot/table order
DATASETS = ["DBpedia", "UniProt", "BTO"]
SYSTEMS = ["raw", "aligned", "agent"]
# Paul Tol "bright": colour-blind safe, distinct in greyscale too.
SYSTEM_COLORS = {"raw": "#BBBBBB", "aligned": "#4477AA", "agent": "#EE6677"}
METRICS = ["f1_score", "f1_score_rel", "normed_ged"]
LABELS = {
    "f1_score": "$F_{1,node}$",
    "f1_score_rel": "$F_{1,rel.}$",
    "normed_ged": "$GED_{s}$",
    "dataset": "Dataset",
    "model": "Version \\& Size",
    "system": "System",
    "stat": "Statistic",
    "generator": "Query Origin",
}


def load() -> pd.DataFrame:
    dfs = []
    for f in glob.glob("results_agents/*.csv"):
        df = pd.read_csv(f, index_col=0)
        name = re.findall(r"eval_results_\w+_(.+)\.csv", f)[0].replace("_", " ").replace("-", " ")
        df["model"] = next((v for k, v in MODEL_MAP.items() if name.startswith(k)), name)
        dfs.append(df)
    df = pd.concat(dfs, ignore_index=True)
    df["dataset"] = df["cfg_name"].str.strip()
    df = df.rename(columns={"stage": "system"})
    df = df[df["model"].isin(MODELS) & df["dataset"].isin(DATASETS) & df["system"].isin(SYSTEMS)]
    return df.dropna(subset=METRICS)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Q1/median/Q3/mean per (dataset, model, system), stat as last index level."""
    g = df.groupby(["dataset", "model", "system"])[METRICS]
    q = g.quantile([0.25, 0.5, 0.75]).rename(index={0.25: "Q1", 0.5: "median", 0.75: "Q3"})
    m = g.mean().assign(stat="mean").set_index("stat", append=True)
    out = pd.concat([q.rename_axis(m.index.names), m]).reset_index()
    order = {"dataset": DATASETS, "model": MODELS, "system": SYSTEMS, "stat": ["Q1", "median", "Q3", "mean"]}
    out = out.sort_values(list(order), key=lambda c: c.map({v: i for i, v in enumerate(order[c.name])}))
    return out.set_index(list(order))


def write_tex(df: pd.DataFrame, path: str, caption: str, label: str):
    df = df.rename(columns=LABELS).rename_axis([LABELS.get(n, n) for n in df.index.names])
    Path(path).write_text(df.to_latex(float_format="%.2f", caption=caption, label=label))


def tables(df: pd.DataFrame):
    summary = summarize(df)
    for dataset in DATASETS:
        write_tex(summary.xs(dataset), f"tables/compare_model_{dataset}.tex",
                  f"Comparison of models for {dataset}", f"tab:compare_model_{dataset}")
    merged = summary.unstack("dataset").swaplevel(axis=1).reindex(summary.droplevel("dataset").index.unique())
    merged = merged.reindex(columns=pd.MultiIndex.from_product([DATASETS, METRICS])).dropna(how="all")
    merged.columns = [f"{d} {LABELS[m]}" for d, m in merged.columns]
    write_tex(merged, "tables/compare_model_merged.tex",
              f"Comparison of models for {', '.join(DATASETS)}", "tab:compare_model_merged")

    # Query origin comparison (smallest model, DBpedia).
    qg = df[df["model"].eq("LFM3 1.7B") & df["dataset"].eq("DBpedia") & df["system"].ne("agent")]
    write_tex(qg.groupby(["generator", "system"])[["f1_score", "normed_ged"]].mean().add_prefix("Mean "),
              "tables/compare_gen_query.tex",
              "Comparison of query generation methods for LFM3 1.7B on DBpedia with one shot prompts.",
              "tab:compare_gen_query")
    aligned = qg[qg["system"] == "aligned"]
    human = aligned.loc[aligned["generator"] == "human", "f1_score"]
    for origin in ["llama", "templated"]:
        t = stats.ttest_ind(aligned.loc[aligned["generator"] == origin, "f1_score"], human, equal_var=False)
        print(f"Welch t-test {origin} vs human (aligned F1): t={t.statistic:.3f}, p={t.pvalue:.3f}")


def figures(df: pd.DataFrame):
    plt.rcParams.update({"figure.facecolor": "white", "axes.facecolor": "white", "font.size": 9})
    g = df.groupby(["dataset", "model", "system"])[METRICS]
    mean, sem = g.mean(), g.sem().fillna(0)
    width = 0.26
    for dataset in DATASETS:
        for metric in METRICS:
            fig, ax = plt.subplots(figsize=(3.4, 2.0))
            for xi, model in enumerate(MODELS):
                present = [s for s in SYSTEMS if (dataset, model, s) in mean.index]
                for j, system in enumerate(present):
                    key = (dataset, model, system)
                    ax.bar(
                        xi + (j - (len(present) - 1) / 2) * width,
                        mean.loc[key, metric],
                        width * 0.9,
                        yerr=1.96 * sem.loc[key, metric],
                        color=SYSTEM_COLORS[system],
                        ecolor="#333333",
                        capsize=2,
                        label=system,
                    )
            ax.set_xticks(range(len(MODELS)), MODELS)
            ax.set_ylabel(f"Mean {LABELS[metric]}")
            ax.set_ylim(0, 1)
            ax.set_yticks(np.linspace(0, 1, 5))
            ax.grid(axis="y", color="#DDDDDD", linewidth=0.5)
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            # dedupe legend entries (raw/aligned appear once per model)
            handles = dict(zip(*reversed(ax.get_legend_handles_labels())))

            def save(suffix: str):
                tikzplotlib.save(
                    f"figures/compare_{dataset}_{metric}{suffix}.tex",
                    axis_width="\\linewidth",
                    axis_height="0.55\\linewidth",
                    extra_axis_parameters=[
                        "legend style={font=\\footnotesize, draw=none, fill=none, at={(0.5,1.02)}, anchor=south}",
                        "ybar legend",
                    ],
                )

            save("")
            ax.legend(handles.values(), handles.keys(), ncols=3, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0))
            save("_legend")
            if preview := os.environ.get("PREVIEW_DIR"):
                fig.tight_layout()
                fig.savefig(f"{preview}/compare_{dataset}_{metric}.png", dpi=150)
            plt.close(fig)


if __name__ == "__main__":
    df = load()
    print(df.groupby(["dataset", "model", "system"]).size().to_string())
    tables(df)
    figures(df)
