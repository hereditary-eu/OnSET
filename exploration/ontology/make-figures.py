"""Tables (LaTeX) and figures (PDF + tikzplotlib .tex) of the ontology builder evaluation.

    ./py.sh make-figures.py [--tag guided_r1] [--sessions sessions_builder-saves]

Reads ``results/ontology_eval_<dataset>_<tag>.csv`` (agent runs, ontology-eval-agent.py),
``results/sessions_<name>.csv`` (user sessions, compare-sessions.py),
``results/reference_<dataset>.csv`` (the true ontologies, reference-baseline.py) and
``results/aids_<dataset>.csv`` (extraction-aids.py).

Results are split by what they measure:
- **ontology**: the schema the agent designed against the reference: classes, relations (link
  types with their domain/range) and fields. For LLMs4OL, the extracted *types* (A2) are
  ontology classes.
- **KG**: the instances extracted with that schema: named entities (GutBrainIE mentions,
  LLMs4OL *terms*, A1) and relation instances.

Naming throughout: *class* for an ontology class (LLMs4OL type), *named entity* for an
extracted instance (LLMs4OL term), *relation* for a link type (ontology) or link instance (KG).

Writes:
- ``tables/overview.tex``: median and best per dataset and source (agent, users, reference),
- ``tables/ontology_<tag>.tex``: ontology alignment per strictness level (mean ± sd),
- ``tables/kg_gutbrainie.tex``, ``tables/kg_yield.tex``, ``tables/llms4ol.tex`` (with the
  challenge's best systems on the official test set, for orientation only), ``tables/aids.tex``,
  ``tables/ablation.tex``,
- ``figures/ontology``, ``figures/ontology_levels``, ``figures/kg_gutbrainie``,
  ``figures/llms4ol``, ``figures/aids``, ``figures/ablation``.
Bars are means over runs/sessions with ± one standard deviation, dots the single runs; every
score axis spans [0, 1].
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

DATASET_NAMES = {"enron": "Enron", "gutbrainie": "GutBrainIE", "llms4ol-ecology": "Ecology",
                 "llms4ol-engineering": "Engineering", "llms4ol-scholarly": "Scholarly"}
SOURCE_NAMES = {"agent": "Agent", "user": "Users", "reference": "True ontology"}
SOURCE_ORDER = list(SOURCE_NAMES.values())
PALETTE = dict(zip(SOURCE_ORDER, sns.color_palette("colorblind", 3)))
LEVEL_NAMES = {"exact": "Exact", "fuzzy": "Fuzzy", "sem": "Semantic"}
F1 = r"$F_1$ score"

# ontology-level metrics (semantic matching)
ONTOLOGY = {"class_sem_f1": "Classes", "rel_triple_sem_f1": "Relations", "field_sem_f1": "Fields"}
# KG-level metrics against the GutBrainIE gold (lenient names)
KG = {"kg_ent_len_f1": "Named entities", "kg_ent_typed_len_f1": "Named entities + class",
      "kg_rel_pair_len_f1": "Related pairs", "kg_rel_typed_len_f1": "Relations"}
# LLMs4OL Text2Onto: A2 types are classes (ontology), A1 terms named entities (KG)
TEXT2ONTO = {"a2_types": ("Ontology", "Classes (A2 types)"), "a1_terms": ("KG", "Named entities (A1 terms)")}
OVERVIEW = {"schema_sem_f1": r"$F_{1}$ ontology", "class_sem_f1": r"$F_{1}$ classes",
            "rel_triple_sem_f1": r"$F_{1}$ relations", "kg_ent_typed_len_f1": r"$F_{1}$ named entities",
            "kg_rel_typed_len_f1": r"$F_{1}$ relation inst.", "a2_types_f1": r"$F_{1}$ classes (A2)",
            "a1_terms_f1": r"$F_{1}$ named entities (A1)"}
# LLMs4OL 2025 Task A, best F1 per subtask on the official test set (overview paper, Table 3)
CHALLENGE_BEST = {
    ("Scholarly", "a1_terms"): ("LABKAG", 0.7000), ("Engineering", "a1_terms"): ("LABKAG", 0.6661),
    ("Ecology", "a2_types"): ("SBU-NLP", 0.6602), ("Scholarly", "a2_types"): ("LABKAG", 0.8308),
    ("Engineering", "a2_types"): ("ELLMO", 0.6750),
}
BAR = dict(errorbar="sd", capsize=0.15, err_kws={"linewidth": 1}, edgecolor="none")


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
        # the whole-document extraction is the true ontology's row
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
    df = pd.concat(frames, ignore_index=True).copy()
    df["Dataset"] = df["dataset"].map(DATASET_NAMES).fillna(df["dataset"])
    df["Source"] = df["source"].map(SOURCE_NAMES)
    return df


def main_rows(df: pd.DataFrame, tag: str) -> pd.DataFrame:
    """The agent runs of ``tag``, the user sessions and the true ontology."""
    return df[((df["source"] == "agent") & (df["tag"] == tag)) | df["source"].isin(["user", "reference"])]


def save_fig(fig, name: str):
    FIGURES.mkdir(exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    # PNG for REPORT.md (PDFs are not tracked)
    fig.savefig(FIGURES / f"{name}.png", bbox_inches="tight", dpi=150)
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


def score_axes(g, xlabel: str = ""):
    """[0, 1] score axes with an F1 label, readable x labels."""
    for ax in g.axes.flat:
        ax.set_ylim(0, 1)
        ax.set_xlabel(xlabel)
        ax.tick_params(axis="x", rotation=20)
    g.set_ylabels(F1)
    return g


def bars(long: pd.DataFrame, x: str, hue: str, col: str | None = None, palette=None, order=None,
         hue_order=None, col_wrap=None, height=2.8, aspect=1.1):
    """Mean bars ± sd with the single values as dots (both in the same x/hue order, so the dots
    sit on their bars also where a panel lacks a hue)."""
    order = order or list(dict.fromkeys(long[x]))
    hue_order = hue_order or list(dict.fromkeys(long[hue]))
    g = sns.catplot(long, x=x, y="F1", hue=hue, col=col, kind="bar", palette=palette, order=order,
                    hue_order=hue_order, col_wrap=col_wrap, height=height, aspect=aspect, **BAR)
    for ax in g.axes.flat:
        title = ax.get_title().split(" = ")[-1]
        data = long[long[col] == title] if col else long
        sns.stripplot(data, x=x, y="F1", hue=hue, order=order, hue_order=hue_order, dodge=True, ax=ax,
                      palette=["black"] * long[hue].nunique(), size=2.5, alpha=0.6, legend=False, jitter=0.1)
        ax.set_title(title)
        # categories without any value (e.g. no gold) are marked instead of looking like a zero
        labels = [t.get_text() for t in ax.get_xticklabels()]
        for i, label in enumerate(labels):
            if data[data[x] == label]["F1"].dropna().empty:
                ax.text(i, 0.03, "n/a", ha="center", va="bottom", fontsize=8, color="grey")
    return g


def overview(df: pd.DataFrame, tag: str):
    sel = main_rows(df, tag)
    cols = [m for m in OVERVIEW if m in sel and sel[m].notna().any()]
    agg = sel.groupby(["Dataset", "Source"])[cols].agg(["median", "max"])
    agg.columns = pd.MultiIndex.from_tuples([(OVERVIEW[m], "best" if a == "max" else a) for m, a in agg.columns])
    agg[("$n$", "")] = sel.groupby(["Dataset", "Source"]).size()
    save_table(agg, "overview", "Agent runs, user sessions and the true ontology (extracted by the same "
               "extractor): median and best per dataset.")


def ontology(df: pd.DataFrame, tag: str):
    """Ontology level: the designed schema against the reference (Enron, GutBrainIE)."""
    sel = main_rows(df, tag)
    sel = sel[sel["source"] != "reference"]  # the reference scores 1 against itself
    long = sel.melt(id_vars=["Dataset", "Source"], value_vars=[c for c in ONTOLOGY if c in sel],
                    var_name="metric", value_name="F1").dropna()
    if long.empty:
        return
    long["Element"] = long["metric"].map(ONTOLOGY)
    order = [v for v in ONTOLOGY.values() if v in set(long["Element"])]
    g = bars(long, x="Element", hue="Source", col="Dataset", order=order,
             hue_order=[s for s in SOURCE_ORDER if s in set(long["Source"])], palette=PALETTE)
    save_fig(score_axes(g).figure, "ontology")


def ontology_levels(df: pd.DataFrame, tag: str):
    agent = df[(df["source"] == "agent") & (df["tag"] == tag) & df["dataset"].isin(["enron", "gutbrainie"])]
    rows = []
    for _, r in agent.iterrows():
        for level, level_name in LEVEL_NAMES.items():
            for kind, name in (("class", "Classes"), ("rel_label", "Relation names"), ("rel_triple", "Relations"),
                               ("field", "Fields")):
                if pd.notna(r.get(f"{kind}_{level}_f1")):
                    rows.append({"Dataset": r["Dataset"], "Matching": level_name, "Element": name,
                                 "P": r[f"{kind}_{level}_p"], "R": r[f"{kind}_{level}_r"], "F1": r[f"{kind}_{level}_f1"]})
    if not rows:
        return
    long = pd.DataFrame(rows)
    fmt = lambda s: f"{s.mean():.2f} $\\pm$ {s.std():.2f}" if len(s) > 1 else f"{s.mean():.2f}"
    table = long.groupby(["Dataset", "Element", "Matching"])[["P", "R", "F1"]].agg(fmt).unstack("Matching")
    save_table(table, f"ontology_{tag}", f"Ontology alignment of the agent's ontologies ({tag}) by name "
               "matching strictness, mean $\\pm$ sd over runs.")
    g = bars(long, x="Element", hue="Matching", col="Dataset", hue_order=list(LEVEL_NAMES.values()),
             palette="Blues")
    save_fig(score_axes(g).figure, "ontology_levels")


def kg_gutbrainie(df: pd.DataFrame, tag: str):
    sel = main_rows(df, tag)
    sel = sel[sel["dataset"] == "gutbrainie"]
    rows = []
    for _, r in sel.iterrows():
        for col, name in KG.items():
            for match, match_name in (("len", "Lenient names"), ("strict", "Strict names")):
                c = col.replace("_len_", f"_{match}_")
                if pd.notna(r.get(c)):
                    rows.append({"Source": r["Source"], "Element": name, "Names": match_name,
                                 "P": r[c[:-3] + "_p"], "R": r[c[:-3] + "_r"], "F1": r[c]})
    if not rows:
        return
    long = pd.DataFrame(rows)
    table = long.groupby(["Source", "Element", "Names"])[["P", "R", "F1"]].median().unstack("Names")
    save_table(table, "kg_gutbrainie", "KG level: extracted instances against the GutBrainIE dev annotations "
               "(median over runs/sessions; lenient: containment or fuzzy name match).")
    g = bars(long, x="Element", hue="Source", col="Names", order=list(KG.values()),
             hue_order=[s for s in SOURCE_ORDER if s in set(long["Source"])], palette=PALETTE, aspect=1.4)
    save_fig(score_axes(g).figure, "kg_gutbrainie")


def text2onto_long(df: pd.DataFrame, key: str = "Domain") -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        for prefix, (level, name) in TEXT2ONTO.items():
            if pd.notna(r.get(f"{prefix}_f1")) and r.get(f"{prefix}_n_gold", 1) > 1:
                rows.append({**{k: r[k] for k in r.index if k in ("Domain", "variant")}, "prefix": prefix,
                             "Level": level, "Element": name, "P": r[f"{prefix}_p"], "R": r[f"{prefix}_r"],
                             "F1": r[f"{prefix}_f1"]})
    return pd.DataFrame(rows)


def llms4ol(df: pd.DataFrame, tag: str):
    sel = df[df["dataset"].str.startswith("llms4ol") & (df["source"] == "agent") & (df["tag"] == tag)].copy()
    if sel.empty:
        return
    sel["Domain"] = sel["Dataset"]
    long = text2onto_long(sel)
    table = long.groupby(["Element", "Domain"]).agg(P=("P", "mean"), R=("R", "mean"), F1=("F1", "mean"),
                                                    F1_sd=("F1", "std"), F1_best=("F1", "max"))
    table["challenge"] = [CHALLENGE_BEST.get((d, p), (None, None))[1] for d, p in
                          zip(table.index.get_level_values("Domain"),
                              ["a2_types" if e.startswith("Classes") else "a1_terms" for e in table.index.get_level_values("Element")])]
    table.columns = ["$P$", "$R$", "$F_1$", "sd", "$F_1$ best run", "$F_1$ challenge best$^*$"]
    save_table(table, "llms4ol", "LLMs4OL 2025 Text2Onto on the held-out split (mean over runs). Classes are the "
               "A2 types (ontology level), named entities the A1 terms (KG level). $^*$Best challenge system on the "
               "official test set, which has no released gold: for orientation only.")
    g = bars(long, x="Domain", hue="Element", col="Level", order=["Ecology", "Engineering", "Scholarly"],
             palette="colorblind", aspect=1.2)
    g.legend.set_title("")
    save_fig(score_axes(g).figure, "llms4ol")


def kg_yield(df: pd.DataFrame, tag: str):
    """KG yield per dataset and source (the only KG-level view for Enron, which has no gold)."""
    sel = main_rows(df, tag)
    cols = {"kg_instances_per_doc": "named entities/doc", "kg_doc_coverage": "docs covered",
            "kg_instances": "named entities", "n_classes": "classes", "n_links": "relations", "n_fields": "fields"}
    cols = {k: v for k, v in cols.items() if k in sel and sel[k].notna().any()}
    if "kg_instances" not in cols:
        return
    table = sel[sel["kg_instances"].notna()].groupby(["Dataset", "Source"])[list(cols)].median().rename(columns=cols)
    save_table(table, "kg_yield", "KG yield, median per dataset and source (true ontology: the reference "
               "extracted by the same extractor).")


def aids():
    """The extraction-aid ablation (extraction-aids.py), split into ontology and KG level."""
    frames = [pd.read_csv(p) for p in sorted(RESULTS.glob("aids_*.csv"))]
    if not frames:
        return
    df = pd.concat(frames, ignore_index=True)
    df["Domain"] = df["dataset"].map(DATASET_NAMES)
    names = {"none": "none", "retrieved": "retrieved ex.", "vocab_terms": "vocab. entities",
             "vocab_types": "vocab. classes", "vocab_both": "vocab. both", "retrieved_vocab_terms": "retr. + vocab. ent."}
    df["variant"] = df["variant"].map(names).fillna(df["variant"])
    long = text2onto_long(df)
    table = long.pivot_table(index=["Domain", "variant"], columns="Element", values="F1")
    save_table(table, "aids", "Extraction aids with a fixed Type/Term ontology (no agent): retrieved examples and "
               "vocabulary matching from the annotated train split, $F_1$.")
    g = bars(long, x="variant", hue="Domain", col="Element", order=[v for v in names.values() if v in set(long["variant"])],
             palette="colorblind", aspect=1.4)
    g.legend.set_title("")
    save_fig(score_axes(g).figure, "aids")


def ablation(df: pd.DataFrame):
    agent = df[df["source"] == "agent"]
    if agent["tag"].nunique() < 2:
        return
    tags = {"guided_r1": "task + refine", "blind_r1": "no task + refine", "guided_r0": "task, no refine"}
    agent = agent[agent["tag"].isin(tags)].copy()
    # only the datasets that were run in more than one setting
    ablated = agent.groupby("dataset")["tag"].nunique()
    agent = agent[agent["dataset"].isin(ablated[ablated > 1].index)]
    agent["Setting"] = agent["tag"].map(tags)
    cols = {"class_sem_f1": ("Ontology", "Classes"), "a2_types_f1": ("Ontology", "Classes"),
            "kg_ent_typed_len_f1": ("KG", "Named entities"), "a1_terms_f1": ("KG", "Named entities")}
    rows = []
    for _, r in agent.iterrows():
        for col, (level, name) in cols.items():
            if pd.notna(r.get(col)) and not (col == "a1_terms_f1" and r.get("a1_terms_n_gold", 0) <= 1):
                rows.append({"Dataset": r["Dataset"], "Setting": r["Setting"], "Level": level, "F1": r[col]})
    long = pd.DataFrame(rows)
    table = long.groupby(["Level", "Dataset", "Setting"])["F1"].agg(["mean", "std", "count"]).unstack("Setting")
    save_table(table, "ablation", "Scripted user: task description and refinement turn ($F_1$, mean, sd, runs).")
    g = bars(long, x="Dataset", hue="Setting", col="Level", hue_order=[t for t in tags.values() if t in set(long["Setting"])],
             palette="Greens_r", aspect=1.5)
    g.legend.set_title("")
    save_fig(score_axes(g).figure, "ablation")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tag", default="guided_r1", help="agent configuration of the main tables")
    parser.add_argument("--sessions", nargs="*", default=None, help="sessions_<name> result files (default: all)")
    args = parser.parse_args()
    sns.set_theme(style="whitegrid", font_scale=0.8)
    df = load_results(args.sessions)
    overview(df, args.tag)
    ontology(df, args.tag)
    ontology_levels(df, args.tag)
    kg_gutbrainie(df, args.tag)
    llms4ol(df, args.tag)
    kg_yield(df, args.tag)
    ablation(df)
    aids()
    print("Tables:", sorted(p.name for p in TABLES.glob("*.tex")))
    print("Figures:", sorted(p.name for p in FIGURES.glob("*.pdf")))


if __name__ == "__main__":
    main()
