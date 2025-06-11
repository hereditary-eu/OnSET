# OnSET

## Live Demo

> In progress...

## Description

OnSET should enable a more explorative ontology querying experience for non-expert users, and to build a quick understanding of the scale and nature of a KG that is in use. The toolkit consists of multiple smaller systems, complimenting each other. We have three default views ready:

* a query view; where users can construct queries either from topics or from natural language prompts,
* the explorative view; enabling users to view the ontology as a whole, view sparse relations and explore the named instances, and
* the linked view; showing users the hierarchical ontology *and* topic model at the same time, creating a rich visualization of multiple dimensions within the ontology. 


## Setup instruction

1. Install Apache Fuseki such that you have a working `riot` command line tool (https://jena.apache.org/documentation/fuseki2/)
2. Setup a local `qlever` instance (https://github.com/ad-freiburg/qlever-control) (the used configurations can be found in `docker/bto-data` and `docker/dbpedia-data`), you should be able to just run from the `docker/*-data`-directories:
```bash
qlever get-data
qlever index
qlever start
```
3. Start auxiliary DB using `cd docker/onset-data && docker-compose up -d`
4. Backend setup:
   - install `uv` (https://docs.astral.sh/uv/getting-started/installation/)
   - install dependencies using `uv sync`
   - start backend (should initialize DB on first start) using the correct Python  installation using `python -m uvicorn api:app --reload --port 8001`
5. Frontend setup:
   - install a somewhat recent Node version
   - install dependencies by first `cd frontend && npm i -D`
   - then start the frontend using `npm run dev`
* Profit?


## Citations

If you feel inspired or want to refer our work in some way, cite SIGIR 2025 Demo Paper (on the Visual Query Builder):

```bib
@misc{kantz2025onsetontologysemanticexploration,
      title={OnSET: Ontology and Semantic Exploration Toolkit}, 
      author={Benedikt Kantz and Kevin Innerebner and Peter Waldert and Stefan Lengauer and Elisabeth Lex and Tobias Schreck},
      year={2025},
      eprint={2504.08373},
      archivePrefix={arXiv},
      primaryClass={cs.IR},
      url={https://arxiv.org/abs/2504.08373}, 
}
```

If you find the intersection of language tooling and ontologies interesting, cite the VINCI '25 paper: (TBA)

Additionally, if you see an application of the LM queries for parsing natural language query to our visual queries cite the IEEE VIS 2025 Short Paper (tba):

Furthermore, for the aspects of this code referencing the differential query view, cite the IEE VIS '25 paper: (TBA)
Furthermore, for the aspects of this code referencing the differential views, cite the IEE VIS '25 paper: (TBA)

