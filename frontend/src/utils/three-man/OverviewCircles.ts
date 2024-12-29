

import * as THREE from 'three'
import { CircleMan3D, SubjectInCircle } from './CircleMan3D';
import type { Link, Node } from '../sparql/representation';
import type { NodeLinkRepository } from '../sparql/store';
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

    links: Record<string, LinkCircles> = {}

    link_params = {
        segments: 16,
        radius: 0.5,
        level_height: 16,
        radial_segments: 8,
        height_factor: 0.5,
        min_height: 25
    }
    constructor(query_renderer: string) {
        super(query_renderer)
    }
    addLink(link: Link) {
        let link_circle = new LinkCircles()
        let from = this.subjects_by_id[link.from_id]
        let to = this.subjects_by_id[link.to_id]
        if (!from || !to) {
            console.error("Missing subjects for link", link)
            return
        }
        console.log("Adding link", link, from, to)
        link_circle.from_subject = from
        link_circle.to_subject = to
        let height = from.position.distanceTo(to.position) * this.link_params.height_factor + this.link_params.min_height
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

        this.links[`${link.from_id}-${link.to_id}`] = link_circle
    }
    updateLinks(store: NodeLinkRepository) {
        let new_links: Record<string, Link> = {}
        if (!this.renderer) {
            console.warn('No renderer (yet?)')
            return
        }
        store.links.forEach(link => {
            new_links[`${link.from_id}-${link.to_id}`] = link
        })

        let changes = false
        //Add new links
        Object.keys(new_links).forEach(link_id => {
            if (!this.links[link_id]) {
                this.addLink(new_links[link_id])
                changes = true
            }
        })
        //Remove old links
        Object.keys(this.links).forEach(link_id => {
            if (!new_links[link_id]) {
                this.scene.remove(this.links[link_id].mesh)
                delete this.links[link_id]
                changes = true
            }
        })
        if (changes) {
            console.log('re-rendering')
            this.renderer.render(this.scene, this.camera);
        }
    }
    initPackedCircles() {
        super.initPackedCircles()
        console.log('init packed circles')
        if (this.renderer instanceof THREE.WebGLRenderer) {
            this.renderer.clear()
        }
        this.renderer.render(this.scene, this.camera);
    }
}