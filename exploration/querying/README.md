# RAG Query setup

## llama-cpp-agent setup

```
git clone git@github.com:Dakantz/llama-cpp-agent.git
git checkout fix-gbnf-generation-trailing-bracket
pip install -e ./llama-cpp-agent
```

## Approach

* extract entities, relations and constraints from the query
* search through db for similar relations/...
* re-run extraction with available similar relation OR even constrain it to only the found relations!