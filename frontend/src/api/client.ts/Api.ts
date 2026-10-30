/* eslint-disable */
/* tslint:disable */
// @ts-nocheck
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

/** VectorSortModality */
export enum VectorSortModality {
  Image = "image",
  Text = "text",
}

/** VectorSortDistance */
export enum VectorSortDistance {
  Cosine = "cosine",
  Euclidean = "euclidean",
  Manhattan = "manhattan",
}

/** VectorSortDirection */
export enum VectorSortDirection {
  Ascending = "ascending",
  Descending = "descending",
}

/** ResultAttributionType */
export enum ResultAttributionType {
  Topic = "topic",
  Query = "query",
}

/** RETURN_TYPE */
export enum RETURN_TYPE {
  Subject = "subject",
  Link = "link",
  Both = "both",
}

/** RELATION_TYPE */
export enum RELATION_TYPE {
  Property = "property",
  Instance = "instance",
}

/** OperationType */
export enum OperationType {
  Add = "add",
  Remove = "remove",
}

/** ModificationKind */
export enum ModificationKind {
  Start = "start",
  Link = "link",
  Constraint = "constraint",
}

/** ManifoldAlg */
export enum ManifoldAlg {
  TSNE = "TSNE",
  MDS = "MDS",
  Smacof = "smacof",
}

/** LinkSemanticType */
export enum LinkSemanticType {
  Structural = "structural",
  Similarity = "similarity",
}

/**
 * LinkQuantifierType
 * SPARQL property path modifiers, values of the editor's LinkQuantifierType.
 */
export enum LinkQuantifierType {
  Value = "+",
  Value1 = "*",
  Value2 = "?",
  BETWEEN = "BETWEEN",
  EXACTLY = "EXACTLY",
}

/** FUZZY_QUERY_ORDER */
export enum FUZZY_QUERY_ORDER {
  Score = "score",
  Instances = "instances",
}

/** ConstraintKind */
export enum ConstraintKind {
  Percentile = "percentile",
  Category = "category",
}

/** AssistantStringConstraintType */
export enum AssistantStringConstraintType {
  Equals = "equals",
  Value = "!=",
  Contains = "contains",
  Startswith = "startswith",
  Endswith = "endswith",
  Regex = "regex",
}

/** AssistantNumberConstraintType */
export enum AssistantNumberConstraintType {
  Equals = "equals",
  Less = "less",
  Greater = "greater",
}

/** AssistantLink */
export interface AssistantLink {
  /** Uri */
  uri: string;
  /** Label */
  label: string;
  /** Id */
  id?: string | null;
  /** From Subject Id */
  from_subject_id?: string | null;
  /** To Subject Id */
  to_subject_id?: string | null;
  /** From Subject Label */
  from_subject_label?: string | null;
  /** From Subject Uri */
  from_subject_uri?: string | null;
  /** To Subject Label */
  to_subject_label?: string | null;
  /** To Subject Uri */
  to_subject_uri?: string | null;
  /** Property Type */
  property_type?: string | null;
  /** Allow Arbitrary */
  allow_arbitrary?: boolean | null;
  quantifier?: LinkQuantifier | null;
  semantic_link_type?: LinkSemanticType | null;
}

/** AssistantSubject */
export interface AssistantSubject {
  /** Uri */
  uri: string;
  /** Label */
  label: string;
  /** Id */
  id?: string | null;
  /**
   * Subqueries
   * @default []
   */
  subqueries?: (
    | ({
        type: "boolean";
      } & BooleanSubQuery)
    | ({
        type: "date";
      } & DateSubQuery)
    | ({
        type: "image_prop";
      } & ImagePropSubQuery)
    | ({
        type: "instance_prop";
      } & InstancePropSubQuery)
    | ({
        type: "number";
      } & NumberSubQuery)
    | ({
        type: "query_prop";
      } & QueryPropSubQuery)
    | ({
        type: "string";
      } & StringSubQuery)
    | ({
        type: "subject";
      } & SubjectSubQuery)
    | ({
        type: "vector_sort";
      } & VectorSortSubQuery)
  )[];
}

/** Body_dim_reduce_search_dim_reduce_post */
export interface BodyDimReduceSearchDimReducePost {
  /** Query */
  query: string;
  /** Target Properties */
  target_properties: string[];
  /**
   * Algorithm
   * @default "umap"
   */
  algorithm?: string;
  /**
   * Remove Vectors
   * @default true
   */
  remove_vectors?: boolean;
}

/** Body_load_ontology_management_ontology_post */
export interface BodyLoadOntologyManagementOntologyPost {
  /** Ontology */
  ontology: File | Blob;
}

/** BooleanSubQuery */
export interface BooleanSubQuery {
  /**
   * Type
   * @default "boolean"
   */
  type?: "boolean";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /**
   * Value
   * @default false
   */
  value?: boolean;
}

/** CandidateEntity */
export interface CandidateEntity {
  /** Identifier */
  identifier: string;
  /** Type */
  type: string;
  /**
   * Constraints
   * @default []
   */
  constraints?: Constraint[];
  /** Score */
  score: number;
  subject?: Subject | null;
}

/** CandidateRelation */
export interface CandidateRelation {
  /** Entity */
  entity: string;
  /** Relation */
  relation: string;
  /** Target */
  target: string;
  /** Score */
  score: number;
  link?: SubjectLink | null;
}

/** Candidates */
export interface Candidates {
  /**
   * Relations
   * @default []
   */
  relations?: CandidateRelation[];
  /**
   * Entities
   * @default []
   */
  entities?: CandidateEntity[];
  /**
   * Message
   * @default "Found Relations and Entities"
   */
  message?: string;
}

/** ClosestRequest */
export interface ClosestRequest {
  /** Embedding */
  embedding: number[] | null;
  /** Query */
  query: string | null;
  /** All Embeddings */
  all_embeddings: number[][];
  /**
   * N Closest
   * @default 5
   */
  n_closest?: number;
}

/** ClosestResponse */
export interface ClosestResponse {
  /** Index */
  index: number;
  /** Distance */
  distance: number;
}

/** ConfigCollection */
export interface ConfigCollection {
  /** Id */
  id: string;
  /** Name */
  name: string;
  /** Description */
  description: string;
  multimodal: MultimodalConfig;
  /** The progressive discovery limits the frontend panel needs (eval_config.ProgressiveConfig). */
  progressive: ProgressiveSettings;
}

/** Constraint */
export interface Constraint {
  /** Property */
  property: string;
  /** Value */
  value: string | null;
  /** Modifier */
  modifier: string | null;
}

/** DataTensorResp */
export interface DataTensorResp {
  /** Data */
  data: number[];
  /** Type */
  type: "float32" | "float64" | "int32" | "int64";
  /** Shape */
  shape: number[];
}

/** DateSubQuery */
export interface DateSubQuery {
  /**
   * Type
   * @default "date"
   */
  type?: "date";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /** Value */
  value: string;
  /** @default "greater" */
  operator?: AssistantNumberConstraintType;
}

/** EnrichedEntitiesRelations */
export interface EnrichedEntitiesRelations {
  /**
   * Relations
   * @default []
   */
  relations?: EnrichedRelation[];
  /**
   * Entities
   * @default []
   */
  entities?: EnrichedEntity[];
  /**
   * Message
   * @default "Found Relations and Entities"
   */
  message?: string;
}

/** EnrichedEntity */
export interface EnrichedEntity {
  /** Identifier */
  identifier: string;
  /** Type */
  type: string;
  /**
   * Constraints
   * @default []
   */
  constraints?: Constraint[];
  subject: Subject;
}

/** EnrichedRelation */
export interface EnrichedRelation {
  /** Entity */
  entity: string;
  /** Relation */
  relation: string;
  /** Target */
  target: string;
  link: SubjectLink | null;
}

/** EntitiesRelations */
export interface EntitiesRelations {
  /**
   * Relations
   * @default []
   */
  relations?: Relation[];
  /**
   * Entities
   * @default []
   */
  entities?: Entity[];
  /**
   * Message
   * @default "Found Relations and Entities"
   */
  message?: string;
}

/** Entity */
export interface Entity {
  /** Identifier */
  identifier: string;
  /** Type */
  type: string;
  /**
   * Constraints
   * @default []
   */
  constraints?: Constraint[];
}

/** FuzzyQuery */
export interface FuzzyQuery {
  /** Q */
  q?: string | null;
  /** Topic Ids */
  topic_ids?: number[] | null;
  /**
   * Mix Topic Factor
   * @default 0.5
   */
  mix_topic_factor?: number | null;
  /** From Id */
  from_id?: string | string[] | null;
  /** To Id */
  to_id?: string | null;
  /**
   * Limit
   * @default 25
   */
  limit?: number | null;
  /**
   * Skip
   * @default 0
   */
  skip?: number | null;
  /** @default "both" */
  type?: RETURN_TYPE;
  /** @default "instance" */
  relation_type?: RELATION_TYPE | null;
  /** @default "score" */
  order?: FUZZY_QUERY_ORDER;
  /**
   * Include Thing
   * @default false
   */
  include_thing?: boolean;
  /**
   * Entity Type
   * @default "class"
   */
  entity_type?: string | null;
}

/** FuzzyQueryResult */
export interface FuzzyQueryResult {
  link?: SubjectLink | null;
  subject?: Subject | null;
  /**
   * Score
   * @default 0
   */
  score?: number;
  /**
   * Attributions
   * @default []
   */
  attributions?: ResultAttribution[];
}

/** FuzzyQueryResults */
export interface FuzzyQueryResults {
  /** Results */
  results: FuzzyQueryResult[];
}

/** GeneralizationQuery */
export interface GeneralizationQuery {
  /**
   * Cls
   * @default ""
   */
  cls?: string;
  /**
   * Out Link Ids
   * @default []
   */
  out_link_ids?: string[];
  /**
   * In Link Ids
   * @default []
   */
  in_link_ids?: string[];
}

/**
 * GraphDetails
 * Ontology data (keyed by graph id) the editor needs to render new elements.
 */
export interface GraphDetails {
  /**
   * Subjects
   * @default {}
   */
  subjects?: Record<string, Subject>;
  /**
   * Links
   * @default {}
   */
  links?: Record<string, SubjectLink>;
}

/** HTTPValidationError */
export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
}

/**
 * ImagePropSubQuery
 * Query prop whose values are images (property_type in the config's image_types).
 *
 * The editor has no own class for it (a QueryProp with an image range), so it
 * always sends query_prop; this is accepted and turned into a QueryProp.
 */
export interface ImagePropSubQuery {
  /**
   * Type
   * @default "image_prop"
   */
  type?: "image_prop";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id: string;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
}

/** Instance */
export interface Instance {
  /**
   * Id
   * @default ""
   */
  id?: string;
  /**
   * Label
   * @default ""
   */
  label?: string;
}

/**
 * InstancePropSubQuery
 * Query prop of a result instance (InstanceQueryProp), with its value.
 */
export interface InstancePropSubQuery {
  /**
   * Type
   * @default "instance_prop"
   */
  type?: "instance_prop";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id: string;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /** Value */
  value?: string | null;
}

/** LinkQuantifier */
export interface LinkQuantifier {
  /**
   * SPARQL property path modifiers, values of the editor's LinkQuantifierType.
   * @default "+"
   */
  type?: LinkQuantifierType;
  /** Min */
  min?: number | null;
  /** Max */
  max?: number | null;
}

/** ManifoldRequest */
export interface ManifoldRequest {
  /** Embeddings */
  embeddings: number[][];
  /**
   * N Out
   * @default 2
   */
  n_out?: number;
  /** @default "TSNE" */
  alg?: ManifoldAlg;
  /**
   * Metric
   * @default "cosine"
   */
  metric?: string;
}

/** Match */
export interface Match {
  /**
   * Colname
   * @default ""
   */
  colname?: string;
  /**
   * Idx
   * @default ""
   */
  idx?: string;
  /**
   * Score
   * @default -1
   */
  score?: number;
  /**
   * Rank
   * @default -1
   */
  rank?: number;
}

/** MultimodalConfig */
export interface MultimodalConfig {
  /**
   * Encoding Model
   * @default "clip-ViT-B-32"
   */
  encoding_model?: string;
  /**
   * Image Vector Properties
   * @default ["dbo:thumbnail_embedding"]
   */
  image_vector_properties?: string[];
  /**
   * Image Properties
   * @default ["dbo:thumbnail"]
   */
  image_properties?: string[];
  /**
   * Image Types
   * @default ["<http://dbpedia.org/ontology/Image>"]
   */
  image_types?: string[];
}

/** NumberSubQuery */
export interface NumberSubQuery {
  /**
   * Type
   * @default "number"
   */
  type?: "number";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /**
   * Value
   * @default 0
   */
  value?: number;
  /** @default "greater" */
  operator?: AssistantNumberConstraintType;
}

/** Operation */
export interface Operation {
  operation: OperationType;
  /** Data */
  data:
    | AssistantLink
    | AssistantSubject
    | (
        | ({
            type: "boolean";
          } & BooleanSubQuery)
        | ({
            type: "date";
          } & DateSubQuery)
        | ({
            type: "image_prop";
          } & ImagePropSubQuery)
        | ({
            type: "instance_prop";
          } & InstancePropSubQuery)
        | ({
            type: "number";
          } & NumberSubQuery)
        | ({
            type: "query_prop";
          } & QueryPropSubQuery)
        | ({
            type: "string";
          } & StringSubQuery)
        | ({
            type: "subject";
          } & SubjectSubQuery)
        | ({
            type: "vector_sort";
          } & VectorSortSubQuery)
      );
  /** Subject Id */
  subject_id?: string | null;
}

/** Operations */
export interface Operations {
  /**
   * Operations
   * @default []
   */
  operations?: Operation[];
}

/** OutLink */
export interface OutLink {
  target?: RelationsFound;
  /**
   * Count
   * @default 0
   */
  count?: number;
  /** Instances */
  instances?: string[];
}

/**
 * ProgressiveConstraint
 * What a constraint modification restricts, for display.
 */
export interface ProgressiveConstraint {
  kind: ConstraintKind;
  /** Subject Id */
  subject_id: string;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Value */
  value: string;
  /** Percentile */
  percentile?: number | null;
  /** Frequency */
  frequency?: number | null;
}

/** ProgressiveModification */
export interface ProgressiveModification {
  /** Id */
  id: string;
  /** @default "link" */
  kind?: ModificationKind;
  /**
   * Operations
   * @default []
   */
  operations?: Operation[];
  /** Count */
  count?: number | null;
  /** Label */
  label: string;
  /** Description */
  description?: string | null;
  details?: GraphDetails | null;
  constraint?: ProgressiveConstraint | null;
  /** Parent Id */
  parent_id?: string | null;
  /**
   * Depth
   * @default 1
   */
  depth?: number;
  /** Step Operations */
  step_operations?: Operation[] | null;
}

/** ProgressiveRequest */
export interface ProgressiveRequest {
  graph: QueryGraph;
  /** Sample Size */
  sample_size?: number | null;
  /** Subject Ids */
  subject_ids?: string[] | null;
  /** Seed */
  seed?: number | null;
  /** Count Subject */
  count_subject?: string | null;
  /** Count Limit */
  count_limit?: number | null;
  /** Sample Constraints */
  sample_constraints?: boolean | null;
  /** Constraint Sample Size */
  constraint_sample_size?: number | null;
  /** Numeric Percentiles */
  numeric_percentiles?: number[] | null;
  /** Categorical Samples */
  categorical_samples?: number | null;
  /**
   * Depth
   * @min 1
   * @default 1
   */
  depth?: number;
  /** Branching */
  branching?: number | null;
  /** Child Sample Size */
  child_sample_size?: number | null;
  /** Child Constraint Sample Size */
  child_constraint_sample_size?: number | null;
}

/** ProgressiveResult */
export interface ProgressiveResult {
  /** Base Count */
  base_count?: number | null;
  /**
   * Modifications
   * @default []
   */
  modifications?: ProgressiveModification[];
  /** Candidate Count */
  candidate_count?: number | null;
  /** Count Limit */
  count_limit?: number | null;
  /** Count Subject */
  count_subject?: string | null;
  /** Seed */
  seed?: number | null;
  /** Constraint Candidate Count */
  constraint_candidate_count?: number | null;
  /**
   * Failed Constraints
   * @default []
   */
  failed_constraints?: string[];
  /**
   * Depth
   * @default 1
   */
  depth?: number;
  /**
   * Expanded Ids
   * @default []
   */
  expanded_ids?: string[];
  /**
   * Duplicate Count
   * @default 0
   */
  duplicate_count?: number;
  /** Query Count */
  query_count?: number | null;
  /** Query Budget */
  query_budget?: number | null;
  /**
   * Budget Exhausted
   * @default false
   */
  budget_exhausted?: boolean;
}

/**
 * ProgressiveSettings
 * The progressive discovery limits the frontend panel needs (eval_config.ProgressiveConfig).
 */
export interface ProgressiveSettings {
  /** Default Sample Size */
  default_sample_size: number;
  /** Max Sample Size */
  max_sample_size: number;
  /** Count Limit */
  count_limit: number;
  /** Sample Constraints */
  sample_constraints: boolean;
  /** Constraint Sample Size */
  constraint_sample_size: number;
  /** Max Constraint Sample Size */
  max_constraint_sample_size: number;
  /** Numeric Percentiles */
  numeric_percentiles: number[];
  /** Categorical Samples */
  categorical_samples: number;
  /** Max Depth */
  max_depth: number;
  /** Default Branching */
  default_branching: number;
  /** Max Branching */
  max_branching: number;
  /** Child Sample Size */
  child_sample_size: number;
  /** Max Total Queries */
  max_total_queries: number;
}

/** Property */
export interface Property {
  /**
   * Property
   * @default ""
   */
  property?: string | null;
  /**
   * Label
   * @default ""
   */
  label?: string | null;
  /**
   * Values
   * @default []
   */
  values?: PropertyValue[];
}

/** PropertyValue */
export interface PropertyValue {
  /** Value */
  value: null;
  /** Label */
  label: string | null;
}

/** QueryGraph */
export interface QueryGraph {
  /**
   * Subjects
   * @default []
   */
  subjects?: AssistantSubject[];
  /**
   * Links
   * @default []
   */
  links?: AssistantLink[];
}

/** QueryProgress */
export interface QueryProgress {
  /** Id */
  id: string;
  /** Start Time */
  start_time: string;
  /**
   * Progress
   * @default 0
   */
  progress?: number;
  /** Max Steps */
  max_steps: number;
  /**
   * Message
   * @default ""
   */
  message?: string;
  /**
   * Relations Steps
   * @default []
   */
  relations_steps?: (
    | EntitiesRelations
    | Candidates
    | EnrichedEntitiesRelations
  )[];
  enriched_relations?: EnrichedEntitiesRelations | null;
}

/**
 * QueryPropSubQuery
 * Property of the subject that is selected (an output variable), not filtered.
 */
export interface QueryPropSubQuery {
  /**
   * Type
   * @default "query_prop"
   */
  type?: "query_prop";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id: string;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
}

/** Relation */
export interface Relation {
  /** Entity */
  entity: string;
  /** Relation */
  relation: string;
  /** Target */
  target: string;
}

/** RelationsFound */
export interface RelationsFound {
  /**
   * Id
   * @default 0
   */
  id?: number;
  /** Path */
  path?: string[];
  /**
   * Subject Id
   * @default ""
   */
  subject_id?: string;
  /**
   * Text
   * @default ""
   */
  text?: string;
  /** Matches */
  matches?: Match[];
}

/** ResultAttribution */
export interface ResultAttribution {
  /** Topic Id */
  topic_id?: number | null;
  /** @default "topic" */
  type?: ResultAttributionType;
  /**
   * Score
   * @default 0
   */
  score?: number;
}

/** SparqlQuery */
export interface SparqlQuery {
  /** Query */
  query: string;
  /**
   * Limit
   * @default 25
   */
  limit?: number | null;
  /**
   * Skip
   * @default 0
   */
  skip?: number | null;
}

/** SparseOutLinks */
export interface SparseOutLinks {
  source?: RelationsFound;
  /** Targets */
  targets?: OutLink[];
}

/** StringSubQuery */
export interface StringSubQuery {
  /**
   * Type
   * @default "string"
   */
  type?: "string";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /**
   * Value
   * @default ""
   */
  value?: string;
  /** @default "contains" */
  operator?: AssistantStringConstraintType;
}

/** Subject */
export interface Subject {
  /** Subject Id */
  subject_id: string;
  /** Label */
  label: string;
  /**
   * Spos
   * @default {}
   */
  spos?: Record<string, Property>;
  /**
   * Subject Type
   * @default "class"
   */
  subject_type?: string;
  /**
   * Refcount
   * @default 0
   */
  refcount?: number;
  /**
   * Descendants
   * @default {}
   */
  descendants?: Record<string, Subject[]>;
  /**
   * Total Descendants
   * @default 0
   */
  total_descendants?: number;
  /**
   * Properties
   * @default {}
   */
  properties?: Record<string, Subject[]>;
  /**
   * Instance Count
   * @default 0
   */
  instance_count?: number;
}

/** SubjectLink */
export interface SubjectLink {
  /** Link Id */
  link_id: number;
  /** Label */
  label: string | null;
  /** From Id */
  from_id: string | null;
  /** Link Type */
  link_type: string;
  /** To Id */
  to_id: string | null;
  /** To Proptype */
  to_proptype: string | null;
  /** Property Id */
  property_id: string | null;
  from_subject: Subject | null;
  to_subject: Subject | null;
  /**
   * Instance Count
   * @default 0
   */
  instance_count?: number;
}

/** SubjectSubQuery */
export interface SubjectSubQuery {
  /**
   * Type
   * @default "subject"
   */
  type?: "subject";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /** Instance Id */
  instance_id?: string | null;
  /** Instance Label */
  instance_label?: string | null;
}

/** Topic */
export interface Topic {
  /** Topic Id */
  topic_id: number;
  /** Sub Topics */
  sub_topics: Topic[];
  /** Parent Topic Id */
  parent_topic_id: number | null;
  /** Topic */
  topic: string;
  /** Count */
  count: number;
  /** Subjects Ids */
  subjects_ids: string[];
  /** Property Ids */
  property_ids: string[];
}

/** ValidationError */
export interface ValidationError {
  /** Location */
  loc: (string | number)[];
  /** Message */
  msg: string;
  /** Error Type */
  type: string;
  /** Input */
  input?: any;
  /** Context */
  ctx?: object;
}

/** VectorSortInputState */
export interface VectorSortInputState {
  /** Image */
  image?: string | null;
  /** Text */
  text?: string | null;
}

/** VectorSortSubQuery */
export interface VectorSortSubQuery {
  /**
   * Type
   * @default "vector_sort"
   */
  type?: "vector_sort";
  /** Id */
  id?: string | null;
  /** Property Id */
  property_id?: string | null;
  /** Property Label */
  property_label?: string | null;
  /** Property Type */
  property_type?: string | null;
  /** @default "image" */
  modality?: VectorSortModality;
  /** @default "descending" */
  direction?: VectorSortDirection;
  /** @default "cosine" */
  distance?: VectorSortDistance;
  /** Vector */
  vector?: number[] | null;
  input_state?: VectorSortInputState;
}

import type {
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  HeadersDefaults,
  ResponseType,
} from "axios";
import axios from "axios";

export type QueryParamsType = Record<string | number, any>;

export interface FullRequestParams
  extends Omit<AxiosRequestConfig, "data" | "params" | "url" | "responseType"> {
  /** set parameter to `true` for call `securityWorker` for this request */
  secure?: boolean;
  /** request path */
  path: string;
  /** content type of request body */
  type?: ContentType;
  /** query params */
  query?: QueryParamsType;
  /** format of response (i.e. response.json() -> format: "json") */
  format?: ResponseType;
  /** request body */
  body?: unknown;
}

export type RequestParams = Omit<
  FullRequestParams,
  "body" | "method" | "query" | "path"
>;

export interface ApiConfig<SecurityDataType = unknown>
  extends Omit<AxiosRequestConfig, "data" | "cancelToken"> {
  securityWorker?: (
    securityData: SecurityDataType | null,
  ) => Promise<AxiosRequestConfig | void> | AxiosRequestConfig | void;
  secure?: boolean;
  format?: ResponseType;
}

export enum ContentType {
  Json = "application/json",
  JsonApi = "application/vnd.api+json",
  FormData = "multipart/form-data",
  UrlEncoded = "application/x-www-form-urlencoded",
  Text = "text/plain",
}

export class HttpClient<SecurityDataType = unknown> {
  public instance: AxiosInstance;
  private securityData: SecurityDataType | null = null;
  private securityWorker?: ApiConfig<SecurityDataType>["securityWorker"];
  private secure?: boolean;
  private format?: ResponseType;

  constructor({
    securityWorker,
    secure,
    format,
    ...axiosConfig
  }: ApiConfig<SecurityDataType> = {}) {
    this.instance = axios.create({
      ...axiosConfig,
      baseURL: axiosConfig.baseURL || "",
    });
    this.secure = secure;
    this.format = format;
    this.securityWorker = securityWorker;
  }

  public setSecurityData = (data: SecurityDataType | null) => {
    this.securityData = data;
  };

  protected mergeRequestParams(
    params1: AxiosRequestConfig,
    params2?: AxiosRequestConfig,
  ): AxiosRequestConfig {
    const method = params1.method || (params2 && params2.method);

    return {
      ...this.instance.defaults,
      ...params1,
      ...(params2 || {}),
      headers: {
        ...((method &&
          this.instance.defaults.headers[
            method.toLowerCase() as keyof HeadersDefaults
          ]) ||
          {}),
        ...(params1.headers || {}),
        ...((params2 && params2.headers) || {}),
      },
    };
  }

  protected stringifyFormItem(formItem: unknown) {
    if (typeof formItem === "object" && formItem !== null) {
      return JSON.stringify(formItem);
    } else {
      return `${formItem}`;
    }
  }

  protected createFormData(input: Record<string, unknown>): FormData {
    if (input instanceof FormData) {
      return input;
    }
    return Object.keys(input || {}).reduce((formData, key) => {
      const property = input[key];
      const propertyContent: any[] =
        property instanceof Array ? property : [property];

      for (const formItem of propertyContent) {
        const isFileType = formItem instanceof Blob || formItem instanceof File;
        formData.append(
          key,
          isFileType ? formItem : this.stringifyFormItem(formItem),
        );
      }

      return formData;
    }, new FormData());
  }

  public request = async <T = any, _E = any>({
    secure,
    path,
    type,
    query,
    format,
    body,
    ...params
  }: FullRequestParams): Promise<AxiosResponse<T>> => {
    const secureParams =
      ((typeof secure === "boolean" ? secure : this.secure) &&
        this.securityWorker &&
        (await this.securityWorker(this.securityData))) ||
      {};
    const requestParams = this.mergeRequestParams(params, secureParams);
    const responseFormat = format || this.format || undefined;

    if (
      type === ContentType.FormData &&
      body &&
      body !== null &&
      typeof body === "object"
    ) {
      body = this.createFormData(body as Record<string, unknown>);
    }

    if (
      type === ContentType.Text &&
      body &&
      body !== null &&
      typeof body !== "string"
    ) {
      body = JSON.stringify(body);
    }

    return this.instance.request({
      ...requestParams,
      headers: {
        ...(requestParams.headers || {}),
        ...(type ? { "Content-Type": type } : {}),
      },
      params: query,
      responseType: responseFormat,
      data: body,
      url: path,
    });
  };
}

/**
 * @title Ontology Provenance API (configuration scoped)
 * @version 0.1.0
 */
export class Api<
  SecurityDataType extends unknown,
> extends HttpClient<SecurityDataType> {
  sparql = {
    /**
     * No description
     *
     * @name SparqlQuerySparqlPost
     * @summary Sparql Query
     * @request POST:/sparql
     */
    sparqlQuerySparqlPost: (data: SparqlQuery, params: RequestParams = {}) =>
      this.request<Record<string, any>[], HTTPValidationError>({
        path: `/sparql`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name SparqlQueryGetSparqlGet
     * @summary Sparql Query Get
     * @request GET:/sparql
     */
    sparqlQueryGetSparqlGet: (
      query: {
        /** Query */
        query: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Record<string, any>, HTTPValidationError>({
        path: `/sparql`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),
  };
  ontology = {
    /**
     * No description
     *
     * @name GetOntologyConfigOntologyConfigGet
     * @summary Get Ontology Config
     * @request GET:/ontology/config
     */
    getOntologyConfigOntologyConfigGet: (params: RequestParams = {}) =>
      this.request<ConfigCollection, any>({
        path: `/ontology/config`,
        method: "GET",
        format: "json",
        ...params,
      }),
  };
  management = {
    /**
     * No description
     *
     * @name LoadOntologyManagementOntologyPost
     * @summary Load Ontology
     * @request POST:/management/ontology
     */
    loadOntologyManagementOntologyPost: (
      data: BodyLoadOntologyManagementOntologyPost,
      params: RequestParams = {},
    ) =>
      this.request<any, HTTPValidationError>({
        path: `/management/ontology`,
        method: "POST",
        body: data,
        type: ContentType.FormData,
        format: "json",
        ...params,
      }),
  };
  topics = {
    /**
     * No description
     *
     * @name GetTopicsRootTopicsRootGet
     * @summary Get Topics Root
     * @request GET:/topics/root
     */
    getTopicsRootTopicsRootGet: (
      query?: {
        /**
         * Force Initialize
         * @default false
         */
        force_initialize?: boolean;
      },
      params: RequestParams = {},
    ) =>
      this.request<Topic, HTTPValidationError>({
        path: `/topics/root`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),
  };
  classes = {
    /**
     * No description
     *
     * @name GetLlmResultsClassesSearchLlmGet
     * @summary Get Llm Results
     * @request GET:/classes/search/llm
     */
    getLlmResultsClassesSearchLlmGet: (
      query?: {
        /**
         * Q
         * @default "working field of person"
         */
        q?: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<QueryProgress, HTTPValidationError>({
        path: `/classes/search/llm`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetLlmResultsRunningClassesSearchLlmRunningGet
     * @summary Get Llm Results Running
     * @request GET:/classes/search/llm/running
     */
    getLlmResultsRunningClassesSearchLlmRunningGet: (
      query: {
        /** Query Id */
        query_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<QueryProgress | null, HTTPValidationError>({
        path: `/classes/search/llm/running`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetLlmExamplesClassesSearchLlmExamplesGet
     * @summary Get Llm Examples
     * @request GET:/classes/search/llm/examples
     */
    getLlmExamplesClassesSearchLlmExamplesGet: (params: RequestParams = {}) =>
      this.request<EnrichedEntitiesRelations[], any>({
        path: `/classes/search/llm/examples`,
        method: "GET",
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name SearchClassesClassesSearchPost
     * @summary Search Classes
     * @request POST:/classes/search
     */
    searchClassesClassesSearchPost: (
      data: FuzzyQuery,
      params: RequestParams = {},
    ) =>
      this.request<FuzzyQueryResults, HTTPValidationError>({
        path: `/classes/search`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetAssistantResultsClassesSearchAssistantPost
     * @summary Get Assistant Results
     * @request POST:/classes/search/assistant
     */
    getAssistantResultsClassesSearchAssistantPost: (
      data: QueryGraph,
      query?: {
        /**
         * Q
         * @default "working field of person"
         */
        q?: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Operations, HTTPValidationError>({
        path: `/classes/search/assistant`,
        method: "POST",
        query: query,
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetNamedInstanceClassesInstancesGet
     * @summary Get Named Instance
     * @request GET:/classes/instances
     */
    getNamedInstanceClassesInstancesGet: (
      query: {
        /** Cls */
        cls: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Subject[], HTTPValidationError>({
        path: `/classes/instances`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetNamedInstanceSearchClassesInstancesSearchGet
     * @summary Get Named Instance Search
     * @request GET:/classes/instances/search
     */
    getNamedInstanceSearchClassesInstancesSearchGet: (
      query: {
        /** Cls */
        cls: string;
        /** Q */
        q?: string | null;
        /**
         * Limit
         * @default 10
         */
        limit?: number;
        /**
         * Skip
         * @default 0
         */
        skip?: number;
      },
      params: RequestParams = {},
    ) =>
      this.request<Instance[], HTTPValidationError>({
        path: `/classes/instances/search`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetNamedInstancePropertiesClassesInstancesPropertiesGet
     * @summary Get Named Instance Properties
     * @request GET:/classes/instances/properties
     */
    getNamedInstancePropertiesClassesInstancesPropertiesGet: (
      query: {
        /** Instance Id */
        instance_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Record<string, Property>, HTTPValidationError>({
        path: `/classes/instances/properties`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetOutlinksClassesOutlinksGet
     * @summary Get Outlinks
     * @request GET:/classes/outlinks
     */
    getOutlinksClassesOutlinksGet: (
      query: {
        /** Subject Id */
        subject_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<SparseOutLinks, HTTPValidationError>({
        path: `/classes/outlinks`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetSubjectClassesSubjectsGet
     * @summary Get Subject
     * @request GET:/classes/subjects
     */
    getSubjectClassesSubjectsGet: (
      query: {
        /** Subject Id */
        subject_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Subject | null, HTTPValidationError>({
        path: `/classes/subjects`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetLinkClassesLinksGet
     * @summary Get Link
     * @request GET:/classes/links
     */
    getLinkClassesLinksGet: (
      query: {
        /** Link Id */
        link_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<SubjectLink | null, HTTPValidationError>({
        path: `/classes/links`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetRelationsClassesRelationsGet
     * @summary Get Relations
     * @request GET:/classes/relations
     */
    getRelationsClassesRelationsGet: (
      query?: {
        /** Q */
        q?: string | null;
        /** From Id */
        from_id?: string | null;
        /** To Id */
        to_id?: string | null;
      },
      params: RequestParams = {},
    ) =>
      this.request<SubjectLink[], HTTPValidationError>({
        path: `/classes/relations`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetFullClassesClassesFullGet
     * @summary Get Full Classes
     * @request GET:/classes/full
     */
    getFullClassesClassesFullGet: (params: RequestParams = {}) =>
      this.request<Subject[], any>({
        path: `/classes/full`,
        method: "GET",
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetRootClassesClassesRootsGet
     * @summary Get Root Classes
     * @request GET:/classes/roots
     */
    getRootClassesClassesRootsGet: (params: RequestParams = {}) =>
      this.request<Subject[], any>({
        path: `/classes/roots`,
        method: "GET",
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetClassClassesSubclassesGet
     * @summary Get Class
     * @request GET:/classes/subclasses
     */
    getClassClassesSubclassesGet: (
      query: {
        /** Cls */
        cls: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Subject[], HTTPValidationError>({
        path: `/classes/subclasses`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetClassSearchClassesSubclassesSearchPost
     * @summary Get Class Search
     * @request POST:/classes/subclasses/search
     */
    getClassSearchClassesSubclassesSearchPost: (
      data: FuzzyQuery,
      params: RequestParams = {},
    ) =>
      this.request<FuzzyQueryResults, HTTPValidationError>({
        path: `/classes/subclasses/search`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetMostGenericsClassesParentsMostGenericPost
     * @summary Get Most Generics
     * @request POST:/classes/parents/most_generic
     */
    getMostGenericsClassesParentsMostGenericPost: (
      data: GeneralizationQuery,
      params: RequestParams = {},
    ) =>
      this.request<Subject, HTTPValidationError>({
        path: `/classes/parents/most_generic`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),
  };
  nlp = {
    /**
     * No description
     *
     * @name NlpEmbeddingsNlpEmbeddingsGet
     * @summary Nlp Embeddings
     * @request GET:/nlp/embeddings
     */
    nlpEmbeddingsNlpEmbeddingsGet: (
      query: {
        /** Query */
        query: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Record<string, any>, HTTPValidationError>({
        path: `/nlp/embeddings`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name NlpEmbeddingsClosestNlpEmbeddingsClosestPost
     * @summary Nlp Embeddings Closest
     * @request POST:/nlp/embeddings/closest
     */
    nlpEmbeddingsClosestNlpEmbeddingsClosestPost: (
      data: ClosestRequest,
      params: RequestParams = {},
    ) =>
      this.request<ClosestResponse[], HTTPValidationError>({
        path: `/nlp/embeddings/closest`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name NlpEmbeddingsManifoldNlpEmbeddingsManifoldPost
     * @summary Nlp Embeddings Manifold
     * @request POST:/nlp/embeddings/manifold
     */
    nlpEmbeddingsManifoldNlpEmbeddingsManifoldPost: (
      data: ManifoldRequest,
      params: RequestParams = {},
    ) =>
      this.request<number[][], HTTPValidationError>({
        path: `/nlp/embeddings/manifold`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),
  };
  search = {
    /**
     * No description
     *
     * @name EncodeTextSearchEncodeTextPost
     * @summary Encode Text
     * @request POST:/search/encode/text
     */
    encodeTextSearchEncodeTextPost: (
      data: string,
      params: RequestParams = {},
    ) =>
      this.request<DataTensorResp, HTTPValidationError>({
        path: `/search/encode/text`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name EncodeImageSearchEncodeImagePost
     * @summary Encode Image
     * @request POST:/search/encode/image
     */
    encodeImageSearchEncodeImagePost: (
      data: string,
      params: RequestParams = {},
    ) =>
      this.request<DataTensorResp, HTTPValidationError>({
        path: `/search/encode/image`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name DimReduceSearchDimReducePost
     * @summary Dim Reduce
     * @request POST:/search/dim-reduce
     */
    dimReduceSearchDimReducePost: (
      data: BodyDimReduceSearchDimReducePost,
      params: RequestParams = {},
    ) =>
      this.request<Record<string, any>[], HTTPValidationError>({
        path: `/search/dim-reduce`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name WikimediaProxySearchWikimediaProxyGet
     * @summary Wikimedia Proxy
     * @request GET:/search/wikimedia/proxy
     */
    wikimediaProxySearchWikimediaProxyGet: (
      query: {
        /** Url */
        url: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<any, HTTPValidationError>({
        path: `/search/wikimedia/proxy`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),
  };
  progressive = {
    /**
     * No description
     *
     * @name SampleModificationsProgressiveSamplePost
     * @summary Sample Modifications
     * @request POST:/progressive/sample
     */
    sampleModificationsProgressiveSamplePost: (
      data: ProgressiveRequest,
      params: RequestParams = {},
    ) =>
      this.request<ProgressiveResult, HTTPValidationError>({
        path: `/progressive/sample`,
        method: "POST",
        body: data,
        type: ContentType.Json,
        format: "json",
        ...params,
      }),
  };
}
