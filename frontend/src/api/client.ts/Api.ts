/* eslint-disable */
/* tslint:disable */
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

/** Body_load_ontology_management_ontology_post */
export interface BodyLoadOntologyManagementOntologyPost {
  /**
   * Ontology
   * @format binary
   */
  ontology: File;
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
  from_id?: string | null;
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
}

/** FuzzyQueryResults */
export interface FuzzyQueryResults {
  /** Results */
  results: FuzzyQueryResult[];
}

/** HTTPValidationError */
export interface HTTPValidationError {
  /** Detail */
  detail?: ValidationError[];
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

/** RELATION_TYPE */
export enum RELATION_TYPE {
  Property = "property",
  Instance = "instance",
}

/** RETURN_TYPE */
export enum RETURN_TYPE {
  Subject = "subject",
  Link = "link",
  Both = "both",
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

/** Subject */
export interface Subject {
  /** Subject Id */
  subject_id: string;
  /** Label */
  label: string;
  /** Spos */
  spos: Record<string, string[]>;
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
}

/** SubjectLink */
export interface SubjectLink {
  /** Link Id */
  link_id: number;
  /** Label */
  label: string | null;
  /** From Id */
  from_id: string;
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
}

import type { AxiosInstance, AxiosRequestConfig, AxiosResponse, HeadersDefaults, ResponseType } from "axios";
import axios from "axios";

export type QueryParamsType = Record<string | number, any>;

export interface FullRequestParams extends Omit<AxiosRequestConfig, "data" | "params" | "url" | "responseType"> {
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

export type RequestParams = Omit<FullRequestParams, "body" | "method" | "query" | "path">;

export interface ApiConfig<SecurityDataType = unknown> extends Omit<AxiosRequestConfig, "data" | "cancelToken"> {
  securityWorker?: (
    securityData: SecurityDataType | null,
  ) => Promise<AxiosRequestConfig | void> | AxiosRequestConfig | void;
  secure?: boolean;
  format?: ResponseType;
}

export enum ContentType {
  Json = "application/json",
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

  constructor({ securityWorker, secure, format, ...axiosConfig }: ApiConfig<SecurityDataType> = {}) {
    this.instance = axios.create({ ...axiosConfig, baseURL: axiosConfig.baseURL || "" });
    this.secure = secure;
    this.format = format;
    this.securityWorker = securityWorker;
  }

  public setSecurityData = (data: SecurityDataType | null) => {
    this.securityData = data;
  };

  protected mergeRequestParams(params1: AxiosRequestConfig, params2?: AxiosRequestConfig): AxiosRequestConfig {
    const method = params1.method || (params2 && params2.method);

    return {
      ...this.instance.defaults,
      ...params1,
      ...(params2 || {}),
      headers: {
        ...((method && this.instance.defaults.headers[method.toLowerCase() as keyof HeadersDefaults]) || {}),
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
      const propertyContent: any[] = property instanceof Array ? property : [property];

      for (const formItem of propertyContent) {
        const isFileType = formItem instanceof Blob || formItem instanceof File;
        formData.append(key, isFileType ? formItem : this.stringifyFormItem(formItem));
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

    if (type === ContentType.FormData && body && body !== null && typeof body === "object") {
      body = this.createFormData(body as Record<string, unknown>);
    }

    if (type === ContentType.Text && body && body !== null && typeof body !== "string") {
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
 * @title Ontology Provenance API
 * @version 0.1.0
 */
export class Api<SecurityDataType extends unknown> extends HttpClient<SecurityDataType> {
  /**
   * No description
   *
   * @name ReadRootGet
   * @summary Read Root
   * @request GET:/
   */
  readRootGet = (params: RequestParams = {}) =>
    this.request<any, any>({
      path: `/`,
      method: "GET",
      format: "json",
      ...params,
    });

  sparql = {
    /**
     * No description
     *
     * @name SparqlQuerySparqlPost
     * @summary Sparql Query
     * @request POST:/sparql
     */
    sparqlQuerySparqlPost: (data: SparqlQuery, params: RequestParams = {}) =>
      this.request<object[], HTTPValidationError>({
        path: `/sparql`,
        method: "POST",
        body: data,
        type: ContentType.Json,
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
    loadOntologyManagementOntologyPost: (data: BodyLoadOntologyManagementOntologyPost, params: RequestParams = {}) =>
      this.request<any, HTTPValidationError>({
        path: `/management/ontology`,
        method: "POST",
        body: data,
        type: ContentType.FormData,
        format: "json",
        ...params,
      }),
  };
  classes = {
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
     * @name GetNamedIndividualsClassesNamedIndividualsGet
     * @summary Get Named Individuals
     * @request GET:/classes/named-individuals
     */
    getNamedIndividualsClassesNamedIndividualsGet: (
      query: {
        /** Cls */
        cls: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<Subject[], HTTPValidationError>({
        path: `/classes/named-individuals`,
        method: "GET",
        query: query,
        format: "json",
        ...params,
      }),

    /**
     * No description
     *
     * @name GetLinksClassesLinksGet
     * @summary Get Links
     * @request GET:/classes/links
     */
    getLinksClassesLinksGet: (
      query: {
        /** Subject Id */
        subject_id: string;
      },
      params: RequestParams = {},
    ) =>
      this.request<SparseOutLinks, HTTPValidationError>({
        path: `/classes/links`,
        method: "GET",
        query: query,
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
    searchClassesClassesSearchPost: (data: FuzzyQuery, params: RequestParams = {}) =>
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
}
