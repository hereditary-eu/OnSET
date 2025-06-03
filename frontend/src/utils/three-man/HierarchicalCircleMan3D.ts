

import * as d3 from 'd3'
import * as THREE from 'three'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CircleMan3D, SubjectInCircle } from './CircleMan3D';
import { registerClass } from '../parsing';
export class TopicTreeLink {
    from_topic?: TopicInCircle
    from_subject?: SubjectInCircle
    curve: THREE.Curve<THREE.Vector3>
    geometry: THREE.BufferGeometry
    material: THREE.LineBasicMaterial
    line_geometry: THREE.Line
    from_position: THREE.Vector3
    mesh: THREE.Mesh<THREE.TubeGeometry, THREE.MeshBasicMaterial, THREE.Object3DEventMap>;
}
@registerClass
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
    color_position?: THREE.Vector2
    color_angle?: number
    n_children?: number
    parent?: TopicInCircle | null
    depth: number = 0
    get id() {
        return `topic-${this.topic_id}`
    }
    get position() {
        // console.warn('TopicInCircle.position is deprecated, use to_position instead')
        return this.to_position || new THREE.Vector3(0, 0, 0)
    }
    get children() {
        return this.sub_topics || []
    }
    get label() {
        return `${this.topic} / ${this.depth}`
    }

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

    constructor(query_renderer: string) {
        super(query_renderer)
    }
    buildTopicTree() {
        if (!this.topics_root) {
            return
        }
        const revive_topic = (topic: Topic, parent?: TopicInCircle): TopicInCircle => {
            let topic_in_circle = new TopicInCircle()
            for (let key in topic) {
                topic_in_circle[key] = topic[key]
            }
            topic_in_circle.parent = parent
            topic_in_circle.sub_topics = topic.sub_topics.map((st) => revive_topic(st, topic_in_circle))
            return topic_in_circle
        }
        this.topics_root = revive_topic(this.topics_root, null)
        let depth = 0
        const eval_depth = (topic, depth) => {
            topic.depth = depth
            let max_depth = depth
            for (let sub_topic of topic.sub_topics) {
                let sub_topic_depth = eval_depth(sub_topic, depth + 1)
                if (sub_topic_depth > max_depth) {
                    max_depth = sub_topic_depth
                }
            }
            return max_depth
        }
        /**
         * 1. get leaf children n. of each topic
         * 2. carve out weighted parts of the circle by child count of the subtopics
         * 3. set color angle to the center of the carved out part
         * 4. go to children and repeat
         */
        const eval_children = (topic: TopicInCircle) => {
            let n_children = topic.sub_topics.reduce((acc, sub_topic) => {
                let sub_topic_children = eval_children(sub_topic)
                if (sub_topic_children > 0) {
                    acc += sub_topic_children
                } else {
                    acc += 1
                }
                return acc
            }, 0)
            topic.n_children = n_children
            return n_children
        }
        eval_children(this.topics_root)


        depth = eval_depth(this.topics_root, 0)
        this.topics_root.color_position = new THREE.Vector2(0, 0)
        const build_colours = (topic: TopicInCircle, start_angle = 0, end_angle = 2 * Math.PI) => {
            let angle = (start_angle + end_angle) / 2
            topic.color_angle = angle
            topic.color_position = new THREE.Vector2(Math.cos(angle), Math.sin(angle))
            let total_children = topic.n_children
            let weights = topic.sub_topics.map(sub_topic => {
                return sub_topic.n_children / total_children
            })
            let angles = weights.map(weight => {
                let angle = (end_angle - start_angle) * weight
                let old_start_angle = start_angle
                start_angle += angle
                return old_start_angle
            })
            // console.log('angles', weights, angles, start_angle, end_angle)
            topic.sub_topics.forEach((sub_topic, i) => {
                let sub_start_angle = angles[i - 1] || start_angle
                let sub_end_angle = angles[i]
                build_colours(sub_topic, sub_start_angle, sub_end_angle)
            })
        }
        build_colours(this.topics_root)

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
            // console.log('height add', height_add, height, depth, topic.topic)
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
                    color: new THREE.Color().setHSL(topic.color_angle, 0.5, 0.5),
                    transparent: true,
                    opacity: 0.7
                });
                let tube_mesh = new THREE.Mesh(geometry, material);
                if (link.from_subject) {

                    let id = `node-${link.from_subject.id}`
                    tube_mesh.name = id
                }
                if (link.from_topic) {
                    let id = `topic-${link.from_topic.topic_id}`
                    tube_mesh.name = id
                }
                // let line_geometry = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0x7f7f7f }));

                // tube_mesh.add(line_geometry)

                link.curve = curve
                link.geometry = geometry
                link.mesh = tube_mesh
                // link.line_geometry = line_geometry

                // line.position.y =  / 2
                this.scene.add(tube_mesh)

            })
            return height

        }
        build_tree_bottom(this.topics_root, depth)
        const add_labels = (topic: TopicInCircle, depth: number) => {
            let id = `topic-${topic.topic_id}`
            let label = this.label_manager.register_label(id, topic, this.scene)

            for (let sub_topic of topic.sub_topics) {
                add_labels(sub_topic, depth + 1)
                for (let subject_id of sub_topic.subjects_ids) {
                    let id = `node-${subject_id}`
                    this.label_manager.register_event(id, (lbl, display) => {
                        label.display(display)
                    })
                }
            }
        }
        add_labels(this.topics_root, 0)

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