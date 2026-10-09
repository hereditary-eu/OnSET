import type { Vector2 } from "three";

import * as d3 from 'd3'
type Pt = { x: number, y: number };
class SplitPath {
    constructor(public start: Pt, public end: Pt, public idx: number, public path: d3.Path) { }
}
export class CatmullRomSplits {
    _x0: number;
    _x1: number;
    _x2: number;
    _y0: number;
    _y1: number;
    _y2: number;
    _l01_a: number;
    _l12_a: number;
    _l23_a: number;
    _l01_2a: number;
    _l12_2a: number;
    _l23_2a: number;
    _point: number;
    constructor(public points: Pt[], public tension: number = 0.5, private epsilon: number = 1e-6) {

        this._x0 = this._x1 = this._x2 =
            this._y0 = this._y1 = this._y2 = NaN;
        this._l01_a = this._l12_a = this._l23_a =
            this._l01_2a = this._l12_2a = this._l23_2a =
            this._point = 0;
    }

    getPaths(): SplitPath[] {
        let paths: SplitPath[] = []

        let cPrev: Pt[] = []
        let cSucc: Pt[] = []

        let c1: Pt, c2: Pt;
        let p1: Pt, p2: Pt, p: Pt, p3: Pt;
        let v13: Pt, v12: Pt, v23: Pt;
        let l13, l12, l23;
        let v, l, v1, v2
        // var MIN_DIST_CONTROL = 10
        let SMOOTH = this.tension;
        let a = 0;
        let m = 1;

        cSucc.push(this.points[0]) // first node
        for (let i = 1; i < this.points.length - 1; i++) {
            p2 = this.points[i];
            l12 = 0
            l23 = 0
            m = 1;

            p1 = this.points[i - m];
            v12 = { x: p2.x - p1.x, y: p2.y - p1.y }
            l12 = Math.sqrt(v12.x * v12.x + v12.y * v12.y)
            p3 = this.points[i + m];
            v23 = { x: p3.x - p2.x, y: p3.y - p2.y }
            l23 = Math.sqrt(v23.x * v23.x + v23.y * v23.y)

            c1 = null
            c2 = null
            if (l12 == 0)
                c1 = p2
            if (l23 == 0)
                c2 = p2

            if (l12 > 0 || l23 > 0) {
                while (l12 == 0 && (i - m) > 0) {
                    m += 1;
                    p1 = this.points[i - m];
                    v12 = { x: p2.x - p1.x, y: p2.y - p1.y }
                    l12 = Math.sqrt(v12.x * v12.x + v12.y * v12.y)
                }

                m = 1
                while (l23 == 0 && (i + m) < this.points.length - 1) {
                    m += 1;
                    p3 = this.points[i + m];
                    v23 = { x: p3.x - p2.x, y: p3.y - p2.y }
                    l23 = Math.sqrt(v23.x * v23.x + v23.y * v23.y)
                }

                v13 = { x: p3.x - p1.x, y: p3.y - p1.y }
                l13 = Math.sqrt(v13.x * v13.x + v13.y * v13.y)

                v = { x: v13.x, y: v13.y };
                if (l13 == 0) {
                    v.x = v12.y * Math.random()
                    v.y = -v12.x * Math.random()
                }
                l = Math.sqrt(v.x * v.x + v.y * v.y)

                v1 = { x: 0, y: 0 }
                v1.x = v.x / l
                v1.y = v.y / l
                v1.x *= l12 * SMOOTH;
                v1.y *= l12 * SMOOTH;
                v2 = { x: 0, y: 0 }
                v2.x = v.x / l
                v2.y = v.y / l
                v2.x *= l23 * SMOOTH;
                v2.y *= l23 * SMOOTH;
                if (!c1)
                    c1 = { x: p2.x - v1.x, y: p2.y - v1.y };
                if (!c2)
                    c2 = { x: p2.x + v2.x, y: p2.y + v2.y };
            } else {
                // console.log('no segment')
            }

            cPrev.push(c1)
            cSucc.push(c2)
        }

        // add last node
        cPrev.push(this.points[this.points.length - 1])


        for (let i = 0; i < this.points.length - 1; i++) {
            const p1 = this.points[i];
            const p2 = this.points[i + 1];
            const path = d3.path();
            path.moveTo(p1.x, p1.y);
            path.bezierCurveTo(cSucc[i].x, cSucc[i].y, cPrev[i].x, cPrev[i].y, p2.x, p2.y);
            const splitPath = new SplitPath(p1, p2, i, path)
            paths.push(splitPath)
        }



        return paths
    }
}