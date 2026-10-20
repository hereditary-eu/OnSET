from dataclasses import dataclass
from explorative.explorative_support import GuidanceManager
from assistant.assistant_model import (
    QueryGraph,
    Operation,
    Operations,
    AssistantLink,
    AssistantSubject,
    OperationType,
    StringSubQuery,
    NumberSubQuery,
    BooleanSubQuery,
    DateSubQuery,
    VectorSortSubQuery,
)
from pydantic import create_model, Field, BaseModel
from llama_cpp.llama import Llama, LlamaGrammar, ChatCompletionMessage

from llama_cpp_agent.gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import (
    generate_gbnf_grammar_from_pydantic_models,
)
from explorative.exp_model import (
    FuzzyQuery,
    RETURN_TYPE,
    RELATION_TYPE,
    SubjectLinkDB,
    SubjectInDB,
)
from typing import Literal
from enum import Enum
from sqlalchemy.orm import Session


@dataclass
class LinkCandidate:
    uri: str
    label: str
    from_label: str
    to_label: str

    @property
    def key(self):
        # readable value the LLM picks from in the grammar
        return f"{self.label}|{self.from_label}|{self.to_label}"


@dataclass
class Candidates:
    # label -> uri
    subjects: dict[str, str]
    # LinkCandidate.key -> LinkCandidate
    links: dict[str, LinkCandidate]


class IterativeAssistant:
    def __init__(self, guidance: GuidanceManager):
        self.guidance = guidance
        self.SYSTEM_PROMPT = """
        You are an assistant that helps the user to explore an ontology. You are given an existing query graph structure and are tasked to extent it by adding new subjects, links and subqueries.
        """
        self.example_graph = QueryGraph(
            subjects=[
                AssistantSubject(
                    uri="place",
                    label="Place",
                    id="node_1",
                ),
                AssistantSubject(
                    uri="person",
                    label="Person",
                    id="node_2",
                ),
            ],
            links=[
                AssistantLink(
                    uri="birthplace",
                    label="birth place",
                    from_subject="node_2",
                    to_subject="node_1",
                )
            ],
        )
        self.few_shot_messages: list[ChatCompletionMessage] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""
        {self.example_graph.model_dump_json()}
                Add a country to the birth place.""",
            },
            {
                "role": "assistant",
                "content": Operations(
                    operations=[
                        Operation(
                            operation="add",
                            data=AssistantLink(
                                uri="country",
                                label="country",
                                from_subject="node_1",
                                to_subject="node_3",
                            ),
                        )
                    ]
                ).model_dump_json(),
            },
        ]
        self.top_k = 15
        self.max_tokens = 2048
        self.temperature = 0.1

    def __initial_ops(self, query: str, graph: QueryGraph):
        query = query.strip()
        full_query = f"""
        {graph.model_dump_json()}
        {query}
        """
        grammar_constrained = LlamaGrammar.from_string(
            generate_gbnf_grammar_from_pydantic_models(
                [Operations],
                "Operations",
                add_inner_thoughts=False,
            )
        )
        messages = [*self.few_shot_messages, {"role": "user", "content": full_query}]
        response = self.guidance.llama_model.create_chat_completion(
            grammar=grammar_constrained,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        return Operations.model_validate_json(response_msg)

    def __candidates(self, query: str) -> Candidates:
        candidates = Candidates(subjects={}, links={})

        fuzzy_results = self.guidance.search_fuzzy(
            query=FuzzyQuery(
                q=query,
                limit=self.top_k,
                type=RETURN_TYPE.BOTH,
                relation_type=RELATION_TYPE.INSTANCE,
            )
        )
        for res in fuzzy_results.results:
            if res.link is not None:
                link = LinkCandidate(
                    uri=res.link.property_id,
                    label=res.link.label,
                    from_label=res.link.from_subject.label,
                    to_label=res.link.to_subject.label,
                )
                candidates.links[link.key] = link
            elif res.subject is not None:
                candidates.subjects[res.subject.label] = res.subject.subject_id
        return candidates

    def __graph_candidates(self, graph: QueryGraph) -> Candidates:
        subject_labels = {subject.id: subject.label for subject in graph.subjects}
        links = [
            LinkCandidate(
                uri=link.uri,
                label=link.label,
                from_label=subject_labels.get(link.from_subject, ""),
                to_label=subject_labels.get(link.to_subject, ""),
            )
            for link in graph.links
        ]
        return Candidates(
            subjects={subject.label: subject.uri for subject in graph.subjects},
            links={link.key: link for link in links},
        )

    def __build_constrained_model_from_candidates(
        self,
        candidates: Candidates,
        allowed_internal_ids: set[str] = None,
    ):
        internal_ids_type = str
        if allowed_internal_ids:
            internal_ids_type = Enum(
                "InternalID",
                {internal_id: internal_id for internal_id in allowed_internal_ids},
            )
        data_model = None
        if len(candidates.links) > 0:
            link_enum = Enum(
                "LinkLabel",
                {f"link_{i}": key for i, key in enumerate(candidates.links)},
            )
            link_model = create_model(
                "ConstrainedAssistantLink",
                **{
                    "kind": (Literal["link"], "link"),
                    "link": (link_enum, ...),
                    "from_subject": (internal_ids_type, ...),
                    "to_subject": (internal_ids_type, ...),
                },
            )
            data_model = link_model

        if len(candidates.subjects) > 0:
            subject_enum = Enum(
                "SubjectLabel",
                {f"subject_{i}": label for i, label in enumerate(candidates.subjects)},
            )
            # property_id holds the property label, it is resolved in __correct_ops
            subquery_model = (
                StringSubQuery | NumberSubQuery | BooleanSubQuery | DateSubQuery
            )
            subject_model = create_model(
                "ConstrainedAssistantSubject",
                **{
                    "kind": (Literal["subject"], "subject"),
                    "subject": (subject_enum, ...),
                    "id": (internal_ids_type, ...),
                    "subqueries": (list[subquery_model], Field([])),
                },
            )
            if data_model is None:
                data_model = subject_model
            else:
                data_model = data_model | subject_model
        return data_model

    def __build_constrained_model(self, candidates: Candidates, graph: QueryGraph):
        print(candidates)
        # Generate the grammar based on the allowed operations
        data_model = self.__build_constrained_model_from_candidates(candidates)
        if data_model is None:
            # if the data model is None, we constrain on the existing graph
            print("Constraining on the existing graph...")
            data_model = self.__build_constrained_model_from_candidates(
                self.__graph_candidates(graph),
                allowed_internal_ids={subject.id for subject in graph.subjects},
            )
        if data_model is None:
            return None
        constrained_operation_model = create_model(
            "ConstrainedOperation",
            **{
                "operation": (OperationType, ...),
                "data": (
                    data_model,
                    ...,
                ),
            },
        )
        constrained_operations_model = create_model(
            "ConstrainedOperations",
            **{
                "operations": (list[constrained_operation_model], Field([])),
            },
        )
        return constrained_operations_model

    def __constrained_link_op_finalize(
        self, constrained_op: BaseModel, candidates: Candidates
    ):
        print(constrained_op)
        link = candidates.links[constrained_op.link.value]
        return AssistantLink(
            uri=link.uri,
            label=link.label,
            from_subject=self.__enum_value(constrained_op.from_subject),
            to_subject=self.__enum_value(constrained_op.to_subject),
        )

    def __constrained_subject_op_finalize(
        self, constrained_op: BaseModel, candidates: Candidates
    ):
        label = constrained_op.subject.value
        return AssistantSubject(
            uri=candidates.subjects[label],
            label=label,
            id=self.__enum_value(constrained_op.id),
            subqueries=constrained_op.subqueries,
        )

    @staticmethod
    def __enum_value(value):
        return value.value if isinstance(value, Enum) else value

    def __constrained_ops(self, query: str, graph: QueryGraph, candidates: Candidates):
        ConstrainedOperations = self.__build_constrained_model(candidates, graph)
        if ConstrainedOperations is None:
            print("Nothing to constrain on, skipping...")
            return Operations()
        grammar_gbnf = generate_gbnf_grammar_from_pydantic_models(
            [ConstrainedOperations],
            "ConstrainedOperations",
            add_inner_thoughts=False,
        )
        # print(grammar_gbnf)
        grammar_constrained = LlamaGrammar.from_string(grammar_gbnf)
        full_query = f"""
        {graph.model_dump_json()}
        {query}
        """

        messages = [*self.few_shot_messages, {"role": "user", "content": full_query}]

        response = self.guidance.llama_model.create_chat_completion(
            grammar=grammar_constrained,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        constrained_ops = ConstrainedOperations.model_validate_json(response_msg)
        # the graph's own subjects/links may be referenced as well
        graph_candidates = self.__graph_candidates(graph)
        lookup = Candidates(
            subjects={**graph_candidates.subjects, **candidates.subjects},
            links={**graph_candidates.links, **candidates.links},
        )
        finalized_ops = Operations()
        print("Constrained Ops", constrained_ops)
        for constrained_op in constrained_ops.operations:
            data = constrained_op.data
            match data.kind:
                case "link":
                    finalized_ops.operations.append(
                        Operation(
                            operation=constrained_op.operation,
                            data=self.__constrained_link_op_finalize(data, lookup),
                        )
                    )
                case "subject":
                    finalized_ops.operations.append(
                        Operation(
                            operation=constrained_op.operation,
                            data=self.__constrained_subject_op_finalize(data, lookup),
                        )
                    )

        return finalized_ops

    def __find_subject(
        self, internal_id: str, graph: QueryGraph, ops: Operations
    ) -> AssistantSubject | None:
        return next(
            (
                subj
                for subj in [
                    *graph.subjects,
                    *[op.data for op in ops.operations],
                ]
                if isinstance(subj, AssistantSubject) and subj.id == internal_id
            ),
            None,
        )

    def __correct_ops(self, ops: Operations, graph: QueryGraph):
        with Session(self.guidance.engine) as session:
            # resolve the subquery property labels to property ids
            for op in ops.operations:
                if op.operation == OperationType.REMOVE:
                    continue
                if isinstance(op.data, AssistantSubject):
                    for subquery in op.data.subqueries:
                        if subquery.property_id is None:
                            continue
                        db_link = (
                            session.query(SubjectLinkDB)
                            .filter(SubjectLinkDB.label == subquery.property_id)
                            .order_by((SubjectLinkDB.from_id == op.data.uri).desc())
                            .first()
                        )
                        if db_link is not None:
                            subquery.property_id = db_link.property_id
            # find link targets - if not present, add them
            # and remove related links if only subjects are removed
            for op in list(ops.operations):
                if op.operation == OperationType.REMOVE:
                    if isinstance(op.data, AssistantSubject):
                        # remove the link if the subject is removed
                        for link in graph.links:
                            if op.data.id in (link.from_subject, link.to_subject):
                                print("Removing link", link)
                                ops.operations.append(
                                    Operation(
                                        operation=OperationType.REMOVE,
                                        data=link,
                                    )
                                )
                elif isinstance(op.data, AssistantLink):
                    link_db = (
                        session.query(SubjectLinkDB)
                        .filter(SubjectLinkDB.property_id == op.data.uri)
                        .order_by((SubjectLinkDB.to_id != None).desc())
                        .first()
                    )
                    if link_db is None:
                        continue
                    subjects_to_add = [
                        (link_db.from_id, op.data.from_subject),
                        (link_db.to_id, op.data.to_subject),
                    ]

                    for subject_id, internal_id in subjects_to_add:
                        if subject_id is None:
                            continue
                        if self.__find_subject(internal_id, graph, ops) is None:
                            db_subject = session.get(SubjectInDB, subject_id)
                            subj = AssistantSubject(
                                uri=subject_id,
                                label=(
                                    db_subject.label
                                    if db_subject is not None and db_subject.label
                                    else subject_id
                                ),
                                id=internal_id,
                            )
                            ops.operations.append(
                                Operation(
                                    operation=OperationType.ADD,
                                    data=subj,
                                )
                            )
                            print("Adding subject to complete link", subj)
        return ops

    def __simplify_graph(self, graph: QueryGraph):
        simple_graph = QueryGraph.model_validate_json(graph.model_dump_json())
        # drop the (large) vector payloads, they are of no use to the LLM
        for subject in simple_graph.subjects:
            for subquery in subject.subqueries:
                if isinstance(subquery, VectorSortSubQuery):
                    subquery.vector = None
                    subquery.input_state.image = None
        return simple_graph

    def run_query(self, query: str, graph: QueryGraph):
        simple_graph = self.__simplify_graph(graph)
        # # Step 1: Initial Operations -> skip, extract candidates directly from the query!
        # initial_ops = self.__initial_ops(query, simple_graph)
        # print("Initial Ops", initial_ops)
        # Step 2: Candidates
        candidates = self.__candidates(query)
        print("Candidates", candidates)
        # Step 3: Constrained Operations
        finalized_ops = self.__constrained_ops(query, simple_graph, candidates)
        print("Constrained Ops", finalized_ops)
        # Step 4: Correct Operations
        print(" -- Correcting Ops -- ")
        corrected_ops = self.__correct_ops(finalized_ops, graph=graph)
        print("Corrected Ops", corrected_ops)
        return corrected_ops
