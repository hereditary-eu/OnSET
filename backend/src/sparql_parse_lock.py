"""Serialises rdflib's SPARQL parser, which is not thread-safe.

rdflib's SPARQL grammar is a set of module-level pyparsing singletons. pyparsing finds the arity
of each parse action on its first call by trial (``_trim_arity``) and keeps the result in
closure variables shared by all threads, without a lock. When two threads use a grammar element
for the first time at once, the arity can be stored wrong, and every later parse using that
element fails until the process restarts, e.g. with
``TypeError: Param.postParse2() missing 1 required positional argument: 'tokenList'``
(RDFLib/rdflib#765, #2821, pyparsing/pyparsing#89).

Importing this module wraps rdflib's parse entry points in one process-wide ``PARSE_LOCK``, so
every ``Graph.query``/``Graph.update`` on a local store (memory, Tentris, ...) and every
``prepareQuery`` parses under it. Only parsing is locked, evaluation runs concurrently.
``SPARQLStore`` sends the query string unparsed and needs no lock. The lock is reentrant, as
rdflib parses nested SERVICE queries while evaluating.
"""

import threading
from functools import wraps

import rdflib.plugins.sparql.parser as _parser
import rdflib.plugins.sparql.processor as _processor

PARSE_LOCK = threading.RLock()


def _locked(fn):
    if getattr(fn, "__parse_locked__", False):
        return fn

    @wraps(fn)
    def wrapper(*args, **kwargs):
        with PARSE_LOCK:
            return fn(*args, **kwargs)

    wrapper.__parse_locked__ = True
    return wrapper


def install() -> None:
    """Patches the parse functions (idempotent); ``processor`` imported them by name."""
    for name in ("parseQuery", "parseUpdate"):
        locked = _locked(getattr(_parser, name))
        setattr(_parser, name, locked)
        if hasattr(_processor, name):
            setattr(_processor, name, locked)


install()
