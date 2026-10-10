
import type { Api } from "@/api/client.ts/Api";
import { CONSTRAINT_HEIGHT, toVar } from "../helpers";

import { registerClass } from "../../parsing";
import { SubQuery, SubQueryType } from "./subqueries";

export enum VectorSortModality {
    IMAGE = "image",
    TEXT = "text",
}
export enum VectorSortDirection {
    ASCENDING = "ascending",
    DESCENDING = "descending",
}
export enum VectorSortDistance {
    COSINE = "cosine",
    EUCLIDEAN = "euclidean",
    MANHATTAN = "manhattan",
}
@registerClass
export class VectorData {
    data: number[];
    type: string;
    shape: number[];
    static propType: string = "<https://w3id.org/rdf-tensor/datatypes#NumericDataTensor>"
    constructor(data: number[] = [], type: string = "float32", shape: number[] = []) {
        this.data = data;
        this.type = type;
        this.shape = shape.length > 0 ? shape : [data.length];

    }
    toString(): string {
        let json_str = JSON.stringify({
            "type": this.type,
            "shape": this.shape,
            "data": this.data,
        })
        json_str = json_str.replace(/"/g, '\\"')
        return `"${json_str}"^^${VectorData.propType}`
    }

}
@registerClass
export class VectorSort extends SubQuery {
    modality: VectorSortModality;
    direction: VectorSortDirection;
    distance: VectorSortDistance;
    vector: number[] | null = null;

    input_state: {
        image: string | null;
        text: string | null;
    } = {
            image: null,
            text: null,
        }
    constructor(modality: VectorSortModality = VectorSortModality.IMAGE, direction: VectorSortDirection = VectorSortDirection.DESCENDING, distance: VectorSortDistance = VectorSortDistance.COSINE) {
        super();
        this.modality = modality;
        this.direction = direction;
        this.distance = distance;
        this.constraint_type = SubQueryType.VECTOR_SORT
    }
    set height(value: number) {
        // no-op, height is determined by modality
    }
    get height(): number {
        switch (this.modality) {
            case VectorSortModality.IMAGE:
                return CONSTRAINT_HEIGHT * 4
            case VectorSortModality.TEXT:
                return CONSTRAINT_HEIGHT * 1
        }
    }

    async reloadVectorFromState(api: Api<any>) {
        this.vector = null
        let vector_resp = null
        switch (this.modality) {
            case VectorSortModality.TEXT:
                if (this.input_state.text && this.input_state.text.length > 0) {
                    vector_resp = await api.classes.encodeTextClassesSearchEncodeTextPost(this.input_state.text)
                }
                break
            case VectorSortModality.IMAGE:
                if (this.input_state.image) {
                    vector_resp = await api.classes.encodeImageClassesSearchEncodeImagePost(this.input_state.image)
                }
                break
        }
        this.vector = vector_resp.data.data
    }
    expression(property: string): string {
        let distance_func = ""
        switch (this.distance) {
            case VectorSortDistance.COSINE:
                distance_func = "dtf:cosineSimilarity"
                break;
            case VectorSortDistance.EUCLIDEAN:
                distance_func = "dtf:euclideanDistance"
                break;
            case VectorSortDistance.MANHATTAN:
                distance_func = "dtf:manhattanDistance"
                break;
        }
        return `BIND(${distance_func}(${property}, ${this.vectorExpression()}) AS ?sim_${toVar(this.id)})`
    }
    postQueryExpression(property: string): string {
        let order_dir = this.direction == VectorSortDirection.ASCENDING ? "ASC" : "DESC"
        return `ORDER BY ${order_dir}(?sim_${toVar(this.id)})`
    }
    static validPropType(propType: string): boolean {
        // console.log("Checking if propType is valid for vector sort", propType, VectorData.propType)
        return propType == VectorData.propType
    }
    vectorExpression(): string {
        if (!this.vector) {
            return ""
        } else {
            return new VectorData(this.vector).toString()
        }

    }
}
