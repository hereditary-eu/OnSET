"""Streaming protocol of progressive discovery (/{config_id}/progressive/ws,
api/router/progressive.py; frontend/src/utils/progressive/protocol.ts)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from assistant.progressive.models import (
    ProgressiveModification,
    ProgressiveRequest,
    ProgressiveResult,
    ProgressiveSummary,
    complete,
    summary,
)

# Client -> server
#     sample  {request_id, request}   start sampling ``request`` (a ProgressiveRequest);
#                                     cancels the running one of the connection
#     cancel  {}                      cancel the running sampling
#
# Server -> client, every event with the request_id of its sample message; events of a
# cancelled request are not sent any more. Per request, in order of occurrence:
#     start          the request's parameters and the first-level link (or start)
#                    modifications, uncounted (count None) in a live run
#     count          {id, count} as soon as a count finished (id None: the base count);
#                    count None if it failed or timed out; once per modification
#     modifications  {depth, parent_id, modifications} modifications that became known:
#                    first-level constraint modifications (parent_id None) once their
#                    value distributions are in, children of an expanded parent
#     level          {depth, parent_ids} a tree level starts (its parents are expanded)
#     done           the summary (ProgressiveSummary), whether it is complete (cached)
#     error          {message} invalid request or failed sampling, instead of done
# A cached result is replayed as start (all modifications, counted, and the base count)
# and done, both with cached true.


class ProgressiveSample(BaseModel):
    type: Literal["sample"] = "sample"
    request_id: str
    request: ProgressiveRequest


class ProgressiveCancel(BaseModel):
    type: Literal["cancel"] = "cancel"


PROGRESSIVE_CLIENT_MESSAGE = TypeAdapter(
    Annotated[ProgressiveSample | ProgressiveCancel, Field(discriminator="type")]
)


class ProgressiveStart(BaseModel):
    type: Literal["start"] = "start"
    request_id: str | None = None
    seed: int
    candidate_count: int
    count_limit: int
    count_subject: str | None = None
    constraint_candidate_count: int | None = None
    # requested levels and query cap of the tree expansion (None for depth 1)
    depth: int = 1
    query_budget: int | None = None
    # known counts: None in a live run (a count event follows), set in a replay
    base_count: int | None = None
    modifications: list[ProgressiveModification] = Field([])
    cached: bool = False


class ProgressiveCount(BaseModel):
    type: Literal["count"] = "count"
    request_id: str | None = None
    # modification id, None for the base count
    id: str | None = None
    count: int | None = None


class ProgressiveModifications(BaseModel):
    type: Literal["modifications"] = "modifications"
    request_id: str | None = None
    depth: int = 1
    parent_id: str | None = None
    modifications: list[ProgressiveModification] = Field([])


class ProgressiveLevel(BaseModel):
    type: Literal["level"] = "level"
    request_id: str | None = None
    depth: int
    parent_ids: list[str] = Field([])


class ProgressiveDone(ProgressiveSummary):
    type: Literal["done"] = "done"
    request_id: str | None = None
    # every count and lookup succeeded (see complete), only then the result is cached
    complete: bool = False
    cached: bool = False


class ProgressiveError(BaseModel):
    type: Literal["error"] = "error"
    request_id: str | None = None
    message: str


ProgressiveEvent = Annotated[
    ProgressiveStart | ProgressiveCount | ProgressiveModifications | ProgressiveLevel | ProgressiveDone | ProgressiveError,
    Field(discriminator="type"),
]
PROGRESSIVE_EVENT = TypeAdapter(ProgressiveEvent)


def replay(result: ProgressiveResult) -> list[BaseModel]:
    """The events of a (cached) result: start with every modification counted, and done."""
    return [
        ProgressiveStart(
            seed=result.seed,
            candidate_count=result.candidate_count or 0,
            count_limit=result.count_limit or 0,
            count_subject=result.count_subject,
            constraint_candidate_count=result.constraint_candidate_count,
            depth=result.depth,
            query_budget=result.query_budget,
            base_count=result.base_count,
            modifications=result.modifications,
            cached=True,
        ),
        ProgressiveDone(**summary(result).model_dump(), complete=complete(result), cached=True),
    ]
