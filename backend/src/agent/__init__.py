"""Tool-calling agent that edits the query graph from a chat.

Refactored from exploration/llm_tool_exploration.ipynb:

- tools.py        declaring methods as LLM tools (schema from signature + docstring)
- graph_tools.py  ontology search and query graph editing tools
- llm.py          OpenAI-compatible (llama-server) client, streaming + thinking handling
- agent.py        the tool-calling loop of one turn
- protocol.py     WebSocket message types (documented there)
- session.py      server-side sessions (graph + history) per connection

The WebSocket endpoint is api/router/agent.py, the services are wired up
lazily by api.config.ManMan (``agent_llm``, ``agent_sessions``).
"""
