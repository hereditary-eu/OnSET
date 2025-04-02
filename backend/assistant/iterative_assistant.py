from explorative.explorative_support import GuidanceManager
from assistant.model import (
    QueryGraph,
    Operation,
    Operations,
    AssistantLink,
    AssistantSubject,
    AssistantSubQuery,
    OperationType,
    AssistantSubQueryType,
    StringConstraintType,
    StringSubQuery,
    NumberConstraintType,
    NumberSubQuery,
    BooleanSubQuery,
    DateSubQuery,
)
from pydantic import create_model, Field, BaseModel
from llama_cpp.llama import Llama, LlamaGrammar

from llama_cpp_agent.gbnf_grammar_generator.gbnf_grammar_from_pydantic_models import (
    generate_gbnf_grammar_from_pydantic_models,
)
from explorative.exp_model import (
    FuzzyQuery,
    RETURN_TYPE,
    RELATION_TYPE,
    FuzzyQueryResult,
    SubjectLinkDB,
    SubjectLink,
    SubjectInDB,
    Subject,
)
from typing import Literal
from enum import Enum
from sqlalchemy.orm import Session


class IterativeAssistant:
    def __init__(self, guidance: GuidanceManager):
        self.guidance = guidance
        self.SYSTEM_PROMPT = """
        You are an assistant that helps the user to explore an ontology. You are given an existing query graph structure and are tasked to extent it by adding new subjects, links and subqueries.
        """
        self.top_k = 5
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
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ]
        messages.append({"role": "user", "content": full_query})
        response = self.guidance.llama_model.create_chat_completion(
            grammar=grammar_constrained,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        return Operations.model_validate_json(response_msg)

    def __result_to_ops_links(
        self, results: list[FuzzyQueryResult], query_op: Operation
    ):
        return [
            Operation(
                operation=query_op.operation,
                data=AssistantLink(
                    from_id=result.link.from_subject.label,
                    to_id=result.link.to_subject.label,
                    from_internal_id=query_op.data.from_internal_id,
                    to_internal_id=query_op.data.to_internal_id,
                    link_id=result.link.label,
                ),
            )
            for result in results
        ]

    def __result_to_ops_subjects(
        self, results: list[FuzzyQueryResult], query_op: Operation
    ):
        return [
            Operation(
                operation=query_op.operation,
                data=AssistantSubject(
                    subject_id=result.subject.label,
                    internal_id=query_op.data.internal_id,
                    x=query_op.data.x,
                    y=query_op.data.y,
                ),
            )
            for result in results
        ]

    def __result_to_ops_subqueries(
        self, results: list[FuzzyQueryResult], query_op: Operation
    ):
        resulting_datas = []
        match query_op.data.constraint_type:
            case AssistantSubQueryType.STRING:
                resulting_datas = [
                    StringSubQuery(
                        subject_id=result.link.from_subject.label,
                        field=result.link.label,
                        from_internal_id=query_op.data.from_internal_id,
                        value=query_op.data.value,
                        op_type=query_op.data.operation,
                    )
                    for result in results
                ]
            case AssistantSubQueryType.NUMBER:
                resulting_datas = [
                    NumberSubQuery(
                        subject_id=result.link.from_subject.label,
                        field=result.link.label,
                        from_internal_id=query_op.data.from_internal_id,
                        value=query_op.data.value,
                        op_type=query_op.data.operation,
                    )
                    for result in results
                ]
            case AssistantSubQueryType.BOOLEAN:
                resulting_datas = [
                    BooleanSubQuery(
                        subject_id=result.link.from_subject.label,
                        field=result.link.label,
                        from_internal_id=query_op.data.from_internal_id,
                        value=query_op.data.value,
                    )
                    for result in results
                ]
            case AssistantSubQueryType.DATE:
                resulting_datas = [
                    DateSubQuery(
                        subject_id=result.link.from_subject.label,
                        field=result.link.label,
                        from_internal_id=query_op.data.from_internal_id,
                        value=query_op.data.value,
                        op_type=query_op.data.operation,
                    )
                    for result in results
                ]
        return [
            Operation(
                operation=query_op.operation,
                data=data,
            )
            for data in resulting_datas
        ]

    def __candidates_ops(self, query: str, ops: Operations):
        candidate_ops: Operations = Operations()
        for op in ops.operations:
            if op.operation == OperationType.REMOVE:
                continue
            if op.data.type == "link":
                link: AssistantLink = op.data
                fuzzy_results = self.guidance.search_fuzzy(
                    query=FuzzyQuery(
                        q=f"A {link.from_id} is {link.link_id} of {link.to_id}",
                        limit=self.top_k,
                        type=RETURN_TYPE.LINK,
                        relation_type=RELATION_TYPE.INSTANCE,
                    )
                )
                candidate_ops.operations.extend(
                    self.__result_to_ops_links(fuzzy_results.results, op)
                )
            elif op.data.type == "subject":
                subject: AssistantSubject = op.data
                fuzzy_results = self.guidance.search_fuzzy(
                    query=FuzzyQuery(
                        q=f"A {subject.subject_id}",
                        limit=self.top_k,
                        type=RETURN_TYPE.SUBJECT,
                        relation_type=RELATION_TYPE.INSTANCE,
                    )
                )
                candidate_ops.operations.extend(
                    self.__result_to_ops_subjects(fuzzy_results.results, op)
                )
            elif op.data.type == "subquery":
                subquery: AssistantSubQuery = op.data
                fuzzy_results = self.guidance.search_fuzzy(
                    query=FuzzyQuery(
                        q=f"A {subquery.from_id} has {subquery.field}",
                        limit=self.top_k,
                        type=RETURN_TYPE.LINK,
                        relation_type=RELATION_TYPE.PROPERTY,
                    )
                )
                candidate_ops.operations.extend(
                    self.__result_to_ops_subqueries(fuzzy_results.results, op)
                )
        return candidate_ops

    def __build_constrained_model_from_allowed_ids(
        self,
        allowed_subject_ids: set[str],
        allowed_link_ids: set[tuple[str, str, str]],
        allowed_subquery_ids: set[tuple[str, str]],
        allowed_internal_ids: set[str] = None,
    ):
        internal_ids_type = str
        if allowed_internal_ids is not None:
            internal_ids_type = Enum(
                "InternalID",
                {internal_id: internal_id for internal_id in allowed_internal_ids},
            )
        data_model = None
        if len(allowed_link_ids) > 0:
            link_id_enum = Enum(
                "LinkID",
                {
                    f"{from_id}_{link_id}_{to_id}": f"{from_id}|{link_id}|{to_id}"
                    for from_id, link_id, to_id in allowed_link_ids
                },
            )
            link_model = create_model(
                "ConstrainedAssistantLink",
                **{
                    "type": (Literal["link"], "link"),
                    "from_internal_id": (internal_ids_type, ...),
                    "to_internal_id": (internal_ids_type, ...),
                    "link_id": (link_id_enum, ...),
                },
            )

            if data_model is None:
                data_model = link_model
            else:
                data_model = data_model | link_model
        subquery_model = None
        if len(allowed_subquery_ids) > 0:
            subquery_id_enum = Enum(
                "SubQueryID",
                {
                    f"{from_id}_{field}": f"{from_id}|{field}"
                    for from_id, field in allowed_subquery_ids
                },
            )
            constrained_base_props = {
                "type": (Literal["subquery"], "subquery"),
                "field_id": (subquery_id_enum, ...),
                "from_internal_id": (internal_ids_type, ...),
            }
            string_subquery_model = create_model(
                "ConstrainedStringSubQuery",
                **{
                    **constrained_base_props,
                    "constraint_type": (
                        Literal[AssistantSubQueryType.STRING],
                        AssistantSubQueryType.STRING,
                    ),
                    "value": (str, ...),
                    "op_type": (StringConstraintType, ...),
                },
            )
            number_subquery_model = create_model(
                "ConstrainedNumberSubQuery",
                **{
                    **constrained_base_props,
                    "constraint_type": (
                        Literal[AssistantSubQueryType.NUMBER],
                        AssistantSubQueryType.NUMBER,
                    ),
                    "value": (float, ...),
                    "op_type": (NumberConstraintType, ...),
                },
            )
            boolean_subquery_model = create_model(
                "ConstrainedBooleanSubQuery",
                **{
                    **constrained_base_props,
                    "constraint_type": (
                        Literal[AssistantSubQueryType.BOOLEAN],
                        AssistantSubQueryType.BOOLEAN,
                    ),
                    "value": (bool, ...),
                },
            )
            date_subquery_model = create_model(
                "ConstrainedDateSubQuery",
                **{
                    **constrained_base_props,
                    "constraint_type": (
                        Literal[AssistantSubQueryType.DATE],
                        AssistantSubQueryType.DATE,
                    ),
                    "value": (str, ...),
                    "op_type": (NumberConstraintType, ...),
                },
            )
            subquery_model = (
                string_subquery_model
                | number_subquery_model
                | boolean_subquery_model
                | date_subquery_model
            )
            if data_model is None:
                data_model = subquery_model
            else:
                data_model = data_model | subquery_model

        if len(allowed_subject_ids) > 0:
            subject_id_enum = Enum(
                "SubjectID",
                {subject_id: subject_id for subject_id in allowed_subject_ids},
            )
            subquery_model = (
                subquery_model if subquery_model is not None else AssistantSubQuery
            )
            subject_model = create_model(
                "ConstrainedAssistantSubject",
                **{
                    "type": (Literal["subject"], "subject"),
                    "subject_id": (subject_id_enum, ...),
                    "internal_id": (internal_ids_type, ...),
                    "subqueries": (list[subquery_model], Field([])),
                    "x": (float, 0.0),
                    "y": (float, 0.0),
                },
            )
            if data_model is None:
                data_model = subject_model
            else:
                data_model = data_model | subject_model
        return data_model

    def __build_constrained_model_from_graph(self, graph: QueryGraph):
        # Build the model based on the candidate operations
        allowed_subject_ids: set[str] = set()
        allowed_link_ids: set[tuple[str, str, str]] = set()
        allowed_subquery_ids: set[tuple[str, str]] = set()
        allowed_internal_ids: set[str] = set()
        for subject in graph.subjects:
            allowed_subject_ids.add(subject.subject_id)
            allowed_internal_ids.add(subject.internal_id)
        for link in graph.links:
            allowed_link_ids.add(
                (
                    link.from_id,
                    link.link_id,
                    link.to_id,
                )
            )

        return self.__build_constrained_model_from_allowed_ids(
            allowed_subject_ids=allowed_subject_ids,
            allowed_link_ids=allowed_link_ids,
            allowed_subquery_ids=allowed_subquery_ids,
            allowed_internal_ids=allowed_internal_ids,
        )

    def __build_constrained_model(self, candidate_ops: Operations, graph: QueryGraph):
        print(candidate_ops)
        # Build the model based on the candidate operations
        allowed_subject_ids: set[str] = set()
        allowed_link_ids: set[tuple[str, str, str]] = set()
        allowed_subquery_ids: set[tuple[str, str]] = set()
        for candidate_op in candidate_ops.operations:
            if candidate_op.operation == OperationType.REMOVE:
                continue
            if candidate_op.data.type == "link":
                allowed_link_ids.add(
                    (
                        candidate_op.data.from_id,
                        candidate_op.data.link_id,
                        candidate_op.data.to_id,
                    )
                )
            elif candidate_op.data.type == "subject":
                allowed_subject_ids.add(candidate_op.data.subject_id)
            elif candidate_op.data.type == "subquery":
                allowed_subquery_ids.add(
                    (
                        candidate_op.data.from_id,
                        candidate_op.data.field,
                    )
                )
        # Generate the grammar based on the allowed operations
        data_model = self.__build_constrained_model_from_allowed_ids(
            allowed_subject_ids=allowed_subject_ids,
            allowed_link_ids=allowed_link_ids,
            allowed_subquery_ids=allowed_subquery_ids,
        )
        if data_model is None:
            # if the data model is None, we constrain on the existing graph
            print("Constraining on the existing graph...")
            data_model = self.__build_constrained_model_from_graph(graph)
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

    def __constrained_link_op_finalze(self, constrained_op: BaseModel):
        print(constrained_op)
        from_id, link_id, to_id = constrained_op.link_id.value.split("|")
        return AssistantLink(
            from_id=from_id,
            to_id=to_id,
            link_id=link_id,
            from_internal_id=constrained_op.from_internal_id,
            to_internal_id=constrained_op.to_internal_id,
        )

    def __constrained_subject_op_finalize(self, constrained_op: BaseModel):
        return AssistantSubject(
            subject_id=constrained_op.subject_id,
            internal_id=constrained_op.internal_id,
            x=constrained_op.x,
            y=constrained_op.y,
        )

    def __constrained_subquery_op_finalize(self, constrained_op: BaseModel):
        from_id, field = constrained_op.field_id.value.split("|")
        match constrained_op.constraint_type:
            case AssistantSubQueryType.STRING:
                return StringSubQuery(
                    subject_id=from_id,
                    field=field,
                    value=constrained_op.value,
                    operation=constrained_op.operation,
                    from_internal_id=constrained_op.from_internal_id,
                )
            case AssistantSubQueryType.NUMBER:
                return NumberSubQuery(
                    subject_id=from_id,
                    field=field,
                    value=constrained_op.value,
                    operation=constrained_op.operation,
                    from_internal_id=constrained_op.from_internal_id,
                )
            case AssistantSubQueryType.BOOLEAN:
                return BooleanSubQuery(
                    subject_id=from_id,
                    field=field,
                    value=constrained_op.value,
                    operation=constrained_op.operation,
                    from_internal_id=constrained_op.from_internal_id,
                )
            case AssistantSubQueryType.DATE:
                return DateSubQuery(
                    subject_id=from_id,
                    field=field,
                    value=constrained_op.value,
                    operation=constrained_op.operation,
                    from_internal_id=constrained_op.from_internal_id,
                )

    def __constrained_ops(
        self, query: str, graph: QueryGraph, candidate_ops: Operations
    ):
        ConstrainedOperations = self.__build_constrained_model(candidate_ops, graph)
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

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ]
        messages.append({"role": "user", "content": full_query})

        response = self.guidance.llama_model.create_chat_completion(
            grammar=grammar_constrained,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        response_msg = response["choices"][0]["message"]["content"]
        constrained_ops = ConstrainedOperations.model_validate_json(response_msg)
        finalized_ops = Operations()
        print("Constrained Ops", constrained_ops)
        for constrained_op in constrained_ops.operations:
            data = constrained_op.data
            match data.type:
                case "link":
                    finalized_ops.operations.append(
                        Operation(
                            operation=constrained_op.operation,
                            data=self.__constrained_link_op_finalze(data),
                        )
                    )
                case "subject":
                    finalized_ops.operations.append(
                        Operation(
                            operation=constrained_op.operation,
                            data=self.__constrained_subject_op_finalize(data),
                        )
                    )
                case "subquery":
                    finalized_ops.operations.append(
                        Operation(
                            operation=constrained_op.operation,
                            data=self.__constrained_subquery_op_finalize(data),
                        )
                    )

        return finalized_ops

    def __correct_ops(self, ops: Operations, graph: QueryGraph):
        with Session(self.guidance.engine) as session:
            # move to the correct IDs if present
            for op in ops.operations:
                if op.operation == OperationType.REMOVE:
                    continue
                if op.data.type == "link":
                    link: AssistantLink = op.data
                    db_link = (
                        session.query(SubjectLinkDB)
                        .filter(SubjectLinkDB.label == link.link_id)
                        .first()
                    )
                    if db_link is not None:
                        link.from_id = db_link.from_id
                        link.to_id = db_link.to_id
                        link.link_id = db_link.property_id
                if op.data.type == "subject":
                    subject: AssistantSubject = op.data
                    db_subject = (
                        session.query(SubjectInDB)
                        .filter(SubjectInDB.label == subject.subject_id)
                        .first()
                    )
                    if db_subject is not None:
                        subject.subject_id = db_subject.subject_id
                if op.data.type == "subquery":
                    subquery: AssistantSubQuery = op.data
                    db_link = (
                        session.query(SubjectLinkDB)
                        .filter(SubjectLinkDB.label == subquery.field)
                        .first()
                    )
                    if db_link is not None:
                        subquery.from_id = db_link.from_id
                        subquery.field = db_link.link_id
            # find link targets - if not present, add them
            # and remove related links if only subjects are removed
            for op in ops.operations:
                if op.operation == OperationType.REMOVE:
                    if op.data.type =="subject":
                        # remove the link if the subject is removed
                        for link in graph.links:
                            if (
                                link.from_internal_id == op.data.internal_id
                                or link.to_internal_id == op.data.internal_id
                            ):
                                print("Removing link", link)
                                ops.operations.append(
                                    Operation(
                                        operation=OperationType.REMOVE,
                                        data=link,
                                    )
                                )
                elif op.data.type == "link":
                    subjects_to_add = [
                        (op.data.from_id, op.data.from_internal_id),
                        (op.data.to_id, op.data.to_internal_id),
                    ]
                    for subject_id, internal_id in subjects_to_add:
                        subj: AssistantSubject | None = next(
                            filter(
                                lambda subj: subj.subject_id == subject_id,
                                graph.subjects,
                            ),
                            None,
                        )
                        if subj is None:
                            subj = next(
                                filter(
                                    lambda subj: subj.type == "subject"
                                    and subj.subject_id == subject_id,
                                    [op.data for op in ops.operations],
                                ),
                                None,
                            )
                        if subj is None:
                            subj = AssistantSubject(
                                subject_id=subject_id,
                                internal_id=internal_id,
                            )
                            ops.operations.append(
                                Operation(
                                    operation=OperationType.ADD,
                                    data=subj,
                                )
                            )
                            print("Adding subject to complete link", subj)
            for op in ops.operations:
                if op.operation == OperationType.REMOVE:
                    continue
                if op.data.type == "link":
                    # switch internal ids if the from_id and to_id do not match
                    link: AssistantLink = op.data
                    internal_ids = [
                        link.from_internal_id,
                        link.to_internal_id,
                    ]
                    subjects: list[AssistantSubject] = []
                    for internal_id in internal_ids:
                        subj: AssistantSubject | None = next(
                            filter(
                                lambda subj: subj.internal_id == internal_id,
                                graph.subjects,
                            ),
                            None,
                        )
                        if subj is None:
                            subj = next(
                                filter(
                                    lambda subj: subj.type == "subject"
                                    and subj.internal_id == internal_id,
                                    [op.data for op in ops.operations],
                                ),
                                None,
                            )
                        if subj is not None:
                            subjects.append(subj)
                    if len(subjects) == 2:
                        if (
                            subjects[0].subject_id != link.from_id
                            or subjects[1].subject_id != link.to_id
                        ):
                            print("Switching link internal ids", link, subjects)
                            link.from_internal_id, link.to_internal_id = (
                                link.to_internal_id,
                                link.from_internal_id,
                            )
        return ops

    def __simplify_graph(self, graph: QueryGraph):
        simple_graph = QueryGraph.model_validate_json(graph.model_dump_json())
        for subject in simple_graph.subjects:
            full_subject = self.guidance.oman.enrich_subject(subject.subject_id)
            subject.subject_id = full_subject.label
        with Session(self.guidance.engine) as session:
            for link in simple_graph.links:
                full_link = (
                    session.query(SubjectLinkDB)
                    .filter(SubjectLinkDB.label == link.link_id)
                    .first()
                )
                if full_link is None:
                    continue
                full_link = SubjectLink.from_db(full_link, self.guidance.oman)
                link.from_id = full_link.from_subject.label
                link.to_id = full_link.to_subject.label
                link.link_id = full_link.label
        return simple_graph

    def run_query(self, query: str, graph: QueryGraph):
        simple_graph = self.__simplify_graph(graph)
        # Step 1: Initial Operations
        initial_ops = self.__initial_ops(query, simple_graph)
        print("Initial Ops", initial_ops)
        # Step 2: Candidate Operations
        candidate_ops = self.__candidates_ops(query, initial_ops)
        print("Candidate Ops", candidate_ops)
        # Step 3: Constrained Operations
        finalized_ops = self.__constrained_ops(query, simple_graph, candidate_ops)
        print("Constrained Ops", candidate_ops)
        # Step 4: Correct Operations
        print(" -- Correcting Ops -- ")
        corrected_ops = self.__correct_ops(finalized_ops, graph=graph)
        print("Corrected Ops", corrected_ops)
        # TODO: correct ops if they are missing links, subjects, ...
        # correct labels to ids
        # --> should be done!
        return corrected_ops
