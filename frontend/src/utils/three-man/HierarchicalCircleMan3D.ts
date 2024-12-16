

import * as d3 from 'd3'
import * as THREE from 'three'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CircleMan3D, SubjectInCircle } from './CircleMan3D';
export class TopicTreeLink {
    from_topic?: TopicInCircle
    from_subject?: SubjectInCircle
    curve: THREE.Curve<THREE.Vector3>
    geometry: THREE.BufferGeometry
    material: THREE.LineBasicMaterial
    line_geometry: THREE.Line
    from_position: THREE.Vector3
}
export class TopicInCircle implements Topic {
    subjects_ids: string[];
    property_ids: string[];
    topic_id: number;
    sub_topics: TopicInCircle[];
    parent_topic_id: number;
    topic: string;
    count: number;
    links?: TopicTreeLink[]
    to_position?: THREE.Vector3

}
// 3D circle packing based upon https://observablehq.com/@analyzer2004/3d-circle-packing
// expanded with Topic links and fixed height of nodes (TODO)
export class HierarchicalCircleMan3D extends CircleMan3D {

    topics_root: TopicInCircle = null
    tree_params = {
        segments: 16,
        radius: 0.5,
        level_height: 16,
        radial_segments: 8,
        height_factor: 0.85
    }

    constructor(query_renderer:string) {
        super(query_renderer)
    }
    buildTopicTree() {
        if (!this.topics_root) {
            return
        }
        let depth = 0
        const eval_depth = (topic, depth) => {
            let max_depth = depth
            for (let sub_topic of topic.sub_topics) {
                let sub_topic_depth = eval_depth(sub_topic, depth + 1)
                if (sub_topic_depth > max_depth) {
                    max_depth = sub_topic_depth
                }
            }
            return max_depth
        }
        depth = eval_depth(this.topics_root, 0)
        const build_tree_bottom = (topic: TopicInCircle, depth: number) => {
            let heights = topic.sub_topics.map(sub_topic => build_tree_bottom(sub_topic, depth - 1))
            let height = Math.max(...[0, ...heights]) + 1
            topic.links = [...topic.sub_topics.map(child => {
                let link = new TopicTreeLink()
                link.from_topic = child
                link.from_position = child.to_position
                return link
            }),
            ...topic.subjects_ids.map(subject_id => {
                let link = new TopicTreeLink()
                link.from_subject = this.subjects_by_id[subject_id]
                if (!link.from_subject) {
                    console.log('no subject', subject_id)
                    return
                }
                link.from_position = link.from_subject.position
                return link
            }),
            ...topic.property_ids.map(property_id => {
                let link = new TopicTreeLink()
                link.from_subject = this.properties_by_id[property_id]
                if (!link.from_subject) {
                    console.log('no property', property_id)
                    return
                }
                link.from_position = link.from_subject.position
                return link
            })
            ].filter(link => link)
            topic.to_position = new THREE.Vector3(0, 0, 0)
            let squared_positions = new THREE.Vector3(0, 0, 0)
            let n_valid_links = 0
            let max_y = 0
            topic.links.forEach(link => {
                if (link.from_position) {
                    topic.to_position.add(link.from_position)
                    let squared = new THREE.Vector3().multiplyVectors(link.from_position, link.from_position)
                    // console.log('squared', squared)
                    // sets c=a*b
                    squared_positions.add(squared)
                    n_valid_links++
                    if (link.from_position.y > max_y) {
                        max_y = link.from_position.y
                    }
                }
            })
            if (n_valid_links == 0) {
                return topic
            }
            topic.to_position.divideScalar(n_valid_links)
            squared_positions.divideScalar(n_valid_links)
            squared_positions.sub(new THREE.Vector3().multiplyVectors(topic.to_position, topic.to_position)) //E[X^2] - E[X]^2=Var(X)
            squared_positions = new THREE.Vector3(Math.sqrt(squared_positions.x), 0, Math.sqrt(squared_positions.z))
            let height_add = squared_positions.length() * Math.pow(this.tree_params.height_factor, height)
            if (isNaN(height_add)) {
                height_add = 0
            }
            console.log('height add', height_add, height, depth, topic.topic)
            topic.to_position.setY(max_y + height_add)

            topic.links.map(link => {
                let curve = new THREE.QuadraticBezierCurve3(topic.to_position,
                    link.from_position.clone().add(new THREE.Vector3(0, height_add, 0)),
                    link.from_position)
                let geometry = new THREE.TubeGeometry(curve, this.tree_params.segments,
                    this.tree_params.radius,
                    this.tree_params.radial_segments,
                    false);
                let material = new THREE.MeshBasicMaterial({
                    color: 0x999999,
                    transparent: true,
                    opacity: 0.7
                });
                let tube_mesh = new THREE.Mesh(geometry, material);

                // let line_geometry = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0x7f7f7f }));

                // tube_mesh.add(line_geometry)

                link.curve = curve
                link.geometry = geometry
                // link.line_geometry = line_geometry

                // line.position.y =  / 2
                this.scene.add(tube_mesh)

            })
            return height

        }
        build_tree_bottom(this.topics_root, depth)
    }
    initPackedCircles() {
        super.initPackedCircles()
        this.buildTopicTree()
        if (this.renderer instanceof THREE.WebGLRenderer) {
            this.renderer.clear()
        }
        this.renderer.render(this.scene, this.camera);
    }
}