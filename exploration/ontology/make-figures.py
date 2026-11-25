"""Tables (LaTeX) and figures (PDF + tikzplotlib .tex) of the ontology builder evaluation.

    ./py.sh make-figures.py [--sessions sessions_builder-saves]

Reads ``results/ontology_eval_<dataset>_<tag>.csv`` (agent runs, ontology-eval-agent.py),
``results/sessions_<name>.csv`` (user sessions, compare-sessions.py) and
``results/reference_<dataset>.csv`` (the true ontologies, reference-baseline.py) and writes
``tables/*.tex`` and ``figures/*.{pdf,tex}``:

- ``tables/agent_vs_users.tex``: median and best of the main metrics per dataset, agent
  runs against user sessions,
- ``tables/schema_<tag>.tex``: schema metrics per dataset and strictness level (mean ± sd),
- ``tables/kg_gutbrainie.tex``: instance metrics on the GutBrainIE gold,
- ``tables/llms4ol.tex``: Text2Onto P/R/F1 per domain, with the challenge's best systems
  (official test set, so only indicative: ours is a held-out part of the train documents),
- ``tables/kg_yield.tex``: instances per document and documents covered (agent, users, reference),
- ``tables/aids.tex``: the extraction-aid ablation (extraction-aids.py),
- ``figures/schema_levels``, ``figures/agent_vs_users``, ``figures/kg_gutbrainie``,
  ``figures/llms4ol``, ``figures/aids`` and ``figures/ablation`` (if several tags exist).
"""

import env_setup  # noqa: F401

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

HERE = Path(__file__).resolve().parent
RESULTS, TABLES, FIGURES = HERE / "results", HERE / "tables", HERE / "figures"

DATASET_NAMES = {"enron": "Enron", "gutbrainie": "GutBrainIE", "llms4ol-ecology": "LLMs4OL Ecology",
                 "llms4ol-engineering": "LLMs4OL Engineering", "llms4ol-scholarly": "LLMs4OL Scholarly"}
LEVEL_NAMES = {"exact": "exact", "fuzzy": "fuzzy", "sem": "semantic"}
METRIC_NAMES = {
    "schema_sem_f1": r"$F_{1,schema}$", "class_sem_f1": r"$F_{1,class}$", "class_sem_cov_r": r"$R_{cov,class}$",
    "rel_label_sem_f1": r"$F_{1,rel.\,name}$", "rel_triple_sem_f1": r"$F_{1,rel.}$", "field_sem_f1": r"$F_{1,field}$",
    "kg_ent_typed_len_f1": r"$F_{1,ent.}$", "kg_rel_typed_len_f1": r"$F_{1,rel.\,inst.}$",
    "a1_terms_f1": r"$F_{1,A1\,terms}$", "a2_types_f1": r"$F_{1,A2\,types}$",
}
MAIN = list(METRIC_NAMES)
# LLMs4OL 2025 Task A, best F1 per subtask on the official test set (overview paper, Table 3)
CHALLENGE_BEST = {
    ("scholarly", "a1_terms_f1"): ("LABKAG", 0.7000), ("engineering", "a1_terms_f1"): ("LABKAG", 0.6661),
    ("ecology", "a2_types_f1"): ("SBU-NLP", 0.6602), ("scholarly", "a2_types_f1"): ("LABKAG", 0.8308),
    ("engineering", "a2_types_f1"): ("ELLMO", 0.6750),
}


def load_results(sessions: list[str] | None) -> pd.DataFrame:
    frames = []
    for csv in sorted(RESULTS.glob("ontology_eval_*.csv")):
        df = pd.read_csv(csv)
        if "error" in df:
            df = df[df["error"].isna()]
        df["tag"] = re.match(r"ontology_eval_(.+?)_(.+)\.csv", csv.name).group(2)
        frames.append(df)
    for csv in sorted(RESULTS.glob("reference_*.csv")):
        df = pd.read_csv(csv)
        # the whole-document extraction is the reference row of the comparisons
        df = df[df["chunk_chars"].isna()] if "chunk_chars" in df else df
        df["tag"], df["source"] = "reference", "reference"
        frames.append(df)
    for csv in sorted(RESULTS.glob("sessions_*.csv")):
        if sessions and csv.stem not in sessions:
            continue
        df = pd.read_csv(csv)
        df["tag"], df["source"] = csv.stem, "user"
        frames.append(df)
    if not frames:
        raise SystemExit(f"No results in {RESULTS}")
    df = pd.concat(frames, ignore_index=True)
    df["Dataset"] = df["dataset"].map(DATASET_NAMES).fillna(df["dataset"])
    return df


def save_fig(fig, name: str):
    FIGURES.mkdir(exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    try:
        import tikzplotlib

        tikzplotlib.save(FIGURES / f"{name}.tex", figure=fig, axis_width=r"\linewidth", axis_height=r".6\linewidth")
    except Exception as e:  # tikzplotlib lags behind matplotlib; the PDF is enough then
        print(f"tikzplotlib failed for {name}: {e}")
    plt.close(fig)


def save_table(df: pd.DataFrame, name: str, caption: str, **kwargs):
    TABLES.mkdir(exist_ok=True)
    (TABLES / f"{name}.tex").write_text(df.to_latex(
        caption=caption, label=f"tab:onto_{name}", float_format="%.2f", na_rep="--", escape=False,
        multirow=True, **kwargs))


def agent_vs_users(df: pd.DataFrame, agent_tag: str):
    """Median and best per dataset of the agent runs (of ``agent_tag``) and the user sessions."""
    sel = df[((df["source"] == "agent") & (df["tag"] == agent_tag)) | df["source"].isin(["user", "reference"])]
    cols = [m for m in MAIN if m in sel and sel[m].notna().any()]
    agg = sel.groupby(["Dataset", "source"])[cols].agg(["median", "max"])
    agg.columns = pd.MultiIndex.from_tuples([(METRIC_NAMES[m], "best" if a == "max" else a) for m, a in agg.columns])
    counts = sel.groupby(["Dataset", "source"]).size().rename("$n$")
    out = agg.join(counts.to_frame().set_axis(pd.MultiIndex.from_tuples([("$n$", "")]), axis=1))
    out.index = out.index.set_names(["Dataset", "Source"])
    save_table(out, "agent_vs_users", "Agent runs, user sessions and the true (reference) ontology extracted by the "
               "same extractor: median and best per dataset.")
    long = sel.melt(id_vars=["Dataset", "source"], value_vars=[c for c in ["schema_sem_f1", "class_sem_f1",
                                                                          "rel_triple_sem_f1"] if c in sel],
                    var_name="metric", value_name="F1")
    if len(long.dropna()):
        long["metric"] = long["metric"].map(METRIC_NAMES)
        g = sns.catplot(long, x="Dataset", y="F1", hue="source", col="metric", kind="box", height=3, aspect=1.2)
        g.set_xticklabels(rotation=30, ha="right")
        save_fig(g.figure, "agent_vs_users")


def schema_levels(df: pd.DataFrame, tag: str):
    agent = df[(df["source"] == "agent") & (df["tag"] == tag)]
    rows = []
    for _, r in agent.iterrows():
        for level in LEVEL_NAMES:
            for kind, name in (("class", "Classes"), ("rel_label", "Relation names"), ("rel_triple", "Relations"),
                               ("field", "Fields")):
                if f"{kind}_{level}_f1" in r and pd.notna(r[f"{kind}_{level}_f1"]):
                    rows.append({"Dataset": r["Dataset"], "Level": LEVEL_NAMES[level], "Element": name,
                                 "P": r[f"{kind}_{level}_p"], "R": r[f"{kind}_{level}_r"], "F1": r[f"{kind}_{level}_f1"]})
    if not rows:
        return
    long = pd.DataFrame(rows)
    table = long.groupby(["Dataset", "Element", "Level"])[["P", "R", "F1"]].agg(
        lambda s: f"{s.mean():.2f} $\\pm$ {s.std():.2f}" if len(s) > 1 else f"{s.mean():.2f}").unstack("Level")
    save_table(table, f"schema_{tag}", f"Schema alignment of the agent's ontologies ({tag}), mean $\\pm$ sd over runs.")
    g = sns.catplot(long, x="Element", y="F1", hue="Level", col="Dataset", kind="bar", height=3, aspect=1,
                    errorbar="sd", col_wrap=3)
    g.set_xticklabels(rotation=30, ha="right")
    save_fig(g.figure, f"schema_levels_{tag}")


def kg_gutbrainie(df: pd.DataFrame, tag: str):
    sel = df[(df["dataset"] == "gutbrainie") & (((df["source"] == "agent") & (df["tag"] == tag))
                                                | df["source"].isin(["user", "reference"]))]
    rows = []
    for _, r in sel.iterrows():
        for kind, name in (("ent", "Entities"), ("ent_typed", "Typed entities"), ("rel_pair", "Entity pairs"),
                           ("rel_typed", "Typed relations")):
            for match in ("strict", "len"):
                col = f"kg_{kind}_{match}"
                if f"{col}_f1" in r and pd.notna(r[f"{col}_f1"]):
                    rows.append({"Source": r["source"], "Element": name, "Names": "lenient" if match == "len" else match,
                                 "P": r[f"{col}_p"], "R": r[f"{col}_r"], "F1": r[f"{col}_f1"]})
    if not rows:
        return
    long = pd.DataFrame(rows)
    table = long.groupby(["Source", "Element", "Names"])[["P", "R", "F1"]].median().unstack("Names")
    save_table(table, "kg_gutbrainie", "Extracted instances against the GutBrainIE dev annotations (median over runs/sessions).")
    g = sns.catplot(long, x="Element", y="F1", hue="Names", col="Source", kind="bar", height=3, aspect=1.2, errorbar="sd")
    g.set_xticklabels(rotation=30, ha="right")
    save_fig(g.figure, "kg_gutbrainie")


def llms4ol(df: pd.DataFrame, tag: str):
    sel = df[(df["dataset"].str.startswith("llms4ol")) & (df["source"] == "agent") & (df["tag"] == tag)]
    if sel.empty:
        return
    rows = []
    for _, r in sel.iterrows():
        domain = r["dataset"].split("-", 1)[1]
        for task, prefix in (("A1 terms", "a1_terms"), ("A2 types", "a2_types")):
            if f"{prefix}_f1" in r and pd.notna(r[f"{prefix}_f1"]):
                rows.append({"Domain": domain, "Task": task, "P": r[f"{prefix}_p"], "R": r[f"{prefix}_r"],
                             "F1": r[f"{prefix}_f1"], "best": CHALLENGE_BEST.get((domain, f"{prefix}_f1"), (None, None))[1]})
    long = pd.DataFrame(rows)
    table = long.groupby(["Domain", "Task"]).agg(P=("P", "median"), R=("R", "median"), F1=("F1", "median"),
                                                 F1_best=("F1", "max"), challenge=("best", "first"))
    table.columns = ["$P$", "$R$", "$F_1$", "$F_1$ best run", "$F_1$ challenge best$^*$"]
    save_table(table, "llms4ol", "LLMs4OL 2025 Text2Onto on the held-out split (median over runs). $^*$Best "
               "challenge system on the official test set, for orientation only.")
    fig, ax = plt.subplots(figsize=(5, 3))
    long["Subtask"] = long["Domain"] + "\n" + long["Task"]
    sns.barplot(long, x="Subtask", y="F1", errorbar="sd", ax=ax, color="tab:blue", label="OnSET agent")
    best = long.groupby("Subtask")["best"].first().dropna()
    order = [t.get_text() for t in ax.get_xticklabels()]
    ax.scatter([order.index(s) for s in best.index], best.values, marker="*", color="tab:red", s=80,
               label="challenge best", zorder=3)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", labelsize=7)
    save_fig(fig, "llms4ol")


def kg_yield(df: pd.DataFrame, tag: str):
    """KG yield per dataset and source (the only instance-level view for Enron, which has no gold)."""
    sel = df[((df["source"] == "agent") & (df["tag"] == tag)) | df["source"].isin(["user", "reference"])]
    cols = {"kg_instances_per_doc": "instances/doc", "kg_doc_coverage": "docs covered", "kg_instances": "instances",
            "n_classes": "classes", "n_links": "links", "n_fields": "fields"}
    cols = {k: v for k, v in cols.items() if k in sel and sel[k].notna().any()}
    if "kg_instances" not in cols:
        return
    table = sel[sel["kg_instances"].notna()].groupby(["Dataset", "source"])[list(cols)].median().rename(columns=cols)
    save_table(table, "kg_yield", "KG yield: median per dataset and source (reference: the true ontology).")


def aids():
    """The extraction-aid ablation (extraction-aids.py): Text2Onto F1 per domain and variant."""
    frames = [pd.read_csv(p) for p in sorted(RESULTS.glob("aids_*.csv"))]
    if not frames:
        return
    df = pd.concat(frames, ignore_index=True)
    df["Domain"] = df["dataset"].str.replace("llms4ol-", "")
    cols = {"a1_terms_f1": r"$F_{1,A1\,terms}$", "a2_types_f1": r"$F_{1,A2\,types}$", "doc_ent_strict_f1": r"$F_{1,doc}$"}
    table = df.set_index(["Domain", "variant"])[[c for c in cols if c in df]].rename(columns=cols)
    save_table(table, "aids", "Extraction aids with a fixed Type/Term ontology (no agent): retrieved examples "
               "and vocabulary matching from the annotated train split.")
    long = df.melt(id_vars=["Domain", "variant"], value_vars=[c for c in ("a1_terms_f1", "a2_types_f1") if c in df],
                   var_name="metric", value_name="F1").dropna()
    long["metric"] = long["metric"].map(cols)
    g = sns.catplot(long, x="variant", y="F1", hue="Domain", col="metric", kind="bar", height=3, aspect=1.3)
    g.set_xticklabels(rotation=30, ha="right")
    save_fig(g.figure, "aids")


def ablation(df: pd.DataFrame):
    agent = df[df["source"] == "agent"]
    if agent["tag"].nunique() < 2:
        return
    cols = [m for m in ["schema_sem_f1", "kg_ent_typed_len_f1", "a2_types_f1", "a1_terms_f1"] if m in agent]
    table = agent.groupby(["Dataset", "tag"])[cols].median().rename(columns=METRIC_NAMES)
    save_table(table, "ablation", "Prompt (guided/blind) and refinement turns: median per dataset.")
    long = agent.melt(id_vars=["Dataset", "tag"], value_vars=cols, var_name="metric", value_name="F1").dropna()
    long["metric"] = long["metric"].map(METRIC_NAMES)
    g = sns.catplot(long, x="Dataset", y="F1", hue="tag", col="metric", kind="bar", height=3, aspect=1.2, errorbar="sd")
    g.set_xticklabels(rotation=30, ha="right")
    save_fig(g.figure, "ablation")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tag", default="guided_r1", help="agent configuration of the main tables")
    parser.add_argument("--sessions", nargs="*", default=None, help="sessions_<name> result files (default: all)")
    args = parser.parse_args()
    sns.set_theme(style="whitegrid", font_scale=0.8)
    df = load_results(args.sessions)
    agent_vs_users(df, args.tag)
    schema_levels(df, args.tag)
    kg_gutbrainie(df, args.tag)
    llms4ol(df, args.tag)
    ablation(df)
    kg_yield(df, args.tag)
    aids()
    print("Tables:", sorted(p.name for p in TABLES.glob("*.tex")))
    print("Figures:", sorted(p.name for p in FIGURES.glob("*.pdf")))


if __name__ == "__main__":
    main()
