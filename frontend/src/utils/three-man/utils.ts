import { Curve, Vector3 } from "three";

export class TreeConnector extends Curve<Vector3>{

    constructor(public start: Vector3, public end: Vector3) {
        super();
    }

    getPoint(t: number, optionalTarget?: Vector3): Vector3 {
        const point = optionalTarget || new Vector3();

        point.set(this.start.x, this.start.y, this.start.z);

        

        point.x = this.start.x + (this.end.x - this.start.x) * t;
        point.y = this.start.y + (this.end.y - this.start.y) * t;
        point.z = this.start.z + (this.end.z - this.start.z) * t;
        return point;
    }

}