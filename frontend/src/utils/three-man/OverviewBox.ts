

import * as THREE from 'three'
import { CircleMan3D, SubjectInCircle } from './CircleMan3D';
import type { Link, Node } from '../sparql/representation';
import { l } from 'node_modules/vite/dist/node/types.d-aGj9QkWt';
// 3D circle packing based upon https://observablehq.com/@analyzer2004/3d-circle-packing

export class LinkCircles {
    from_subject?: SubjectInCircle
    to_subject?: SubjectInCircle

    curve: THREE.Curve<THREE.Vector3>
    geometry: THREE.BufferGeometry
    material: THREE.Material

    mesh: THREE.Mesh
}

export class OverviewCircles extends CircleMan3D {

    links: LinkCircles[] = []

    link_params = {
        segments: 16,
        radius: 0.5,
        level_height: 16,
        radial_segments: 8,
        height_factor: 0.5
    }
    constructor(query_renderer: string) {
        super(query_renderer)
    }
    addLink(link: Link) {
        let link_circle = new LinkCircles()
        let from = this.subjects_by_id[link.from_id]
        let to = this.subjects_by_id[link.to_id]
        link_circle.from_subject = from
        link_circle.to_subject = to
        let height = from.position.distanceTo(to.position) * this.link_params.height_factor
        let curve_up = new THREE.QuadraticBezierCurve3(from.position.clone(),
            from.position.clone().add(to.position).divideScalar(2).add(new THREE.Vector3(0, height, 0)),
            to.position.clone())
        let geometry = new THREE.TubeGeometry(curve_up, this.link_params.segments,
            this.link_params.radius,
            this.link_params.radial_segments,
            false);
        let material = new THREE.MeshBasicMaterial({
            color: "rgb(240,0,0)",
            transparent: true,
            opacity: 0.7
        });
        let tube_mesh = new THREE.Mesh(geometry, material);

        link_circle.mesh = tube_mesh
        link_circle.curve = curve_up
        link_circle.geometry = geometry
        link_circle.material = material

        this.scene.add(tube_mesh)

        this.links.push(link_circle)
    }
    updateLinks(root: Node) {

        this.links = []
        let eval_links = (node: Node) => {
            if (node.to_links) {
                for (let to_link of node.to_links) {
                    this.addLink(to_link)
                }
            }
            if (node.from_links) {
                for (let from_link of node.from_links) {
                    this.addLink(from_link)
                }
            }
        }
        eval_links(root)
    }
    initPackedCircles() {
        this.scene.remove(...this.links.map(link => link.mesh))
        super.initPackedCircles()
        if (this.renderer instanceof THREE.WebGLRenderer) {
            this.renderer.clear()
        }
        this.renderer.render(this.scene, this.camera);
    }
}