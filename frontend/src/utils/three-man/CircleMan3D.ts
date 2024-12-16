

import * as d3 from 'd3'
import * as THREE from 'three'
import { Api, type Subject, type Topic } from '@/api/client.ts/Api';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
export class SubjectInCircle implements Subject {
    subject_id: string;
    label: string;
    spos: Record<string, string[]> = {};
    subject_type?: string = 'split';
    refcount?: number = 0;
    descendants?: Record<string, Subject[]> = {};
    total_descendants?: number = 0;
    expanded: boolean = false
    children?: SubjectInCircle[]
    n_id: number = 0
    position?: THREE.Vector3
}
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
export class CircleMan3D {
    nodes: SubjectInCircle[] = []
    topics_root: TopicInCircle = null

    color = d3.scaleLinear<number, string, string>()
        .domain([0, 10])
        .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
        .interpolate(d3.interpolateHcl as any);
    color_type = d3.scaleOrdinal(d3.schemePastel2);

    width = 1000
    height = 500
    clicked_node: (node: SubjectInCircle) => void = null

    root: d3.HierarchyCircularNode<SubjectInCircle> = null
    focus: d3.HierarchyCircularNode<SubjectInCircle> = null
    hierarchy: d3.HierarchyNode<SubjectInCircle> = null

    three_div: HTMLElement = null
    camera: THREE.PerspectiveCamera = null
    scene: THREE.Scene = null
    dimensions = {
        width: 1000,
        height: 50,
        depth: 1000
    }


    pool = {
        geometry: null as THREE.CylinderGeometry,
        materials: {} as Record<number, THREE.MeshBasicMaterial>,
        text_material: null as THREE.MeshBasicMaterial,
        edge_geometry: null as THREE.EdgesGeometry,
        line_materials: {} as Record<number, THREE.MeshBasicMaterial>,
    };

    tree_params = {
        segments: 16,
        radius: 0.5,
        level_height: 16,
        radial_segments: 8
    }

    subjects_by_id: Record<string, SubjectInCircle> = {}

    private node_counter = 0
    constructor() {

    }
    private mapNodesToChildren(node: SubjectInCircle): SubjectInCircle {
        let children: SubjectInCircle[] = []
        for (let key in node.descendants) {
            let child = new SubjectInCircle()
            child.subject_id = `${node.subject_id}_${key}`
            child.label = `${key} of ${node.label}`
            child.expanded = true
            if (node.descendants[key].length == 0) {
                child.subject_type = 'leaf'
            } else {
                child.children = node.descendants[key].map(this.mapNodesToChildren.bind(this))
                child.children.forEach(child => child.n_id = this.node_counter++)
                child.total_descendants = child.children.reduce((acc, child) => acc + child.refcount, 0)
                child.n_id = this.node_counter++
                children.push(child)
            }


        }
        node.expanded = true
        return {
            ...node,
            children: children
        }
    }
    private computePacking() {

        const mapped_nodes: SubjectInCircle[] = this.nodes.map(this.mapNodesToChildren.bind(this))
        mapped_nodes.forEach(child => child.n_id = this.node_counter++)

        console.log('restarting graph', this.nodes, mapped_nodes)
        const data: SubjectInCircle = {
            subject_id: 'root',
            expanded: true,
            spos: {},
            label: 'root',
            refcount: 0,
            subject_type: 'root',
            total_descendants: mapped_nodes.reduce((acc, child) => acc + child.total_descendants, 0),
            children: mapped_nodes,
            n_id: this.node_counter++
        }
        this.hierarchy = d3.hierarchy(data, (d) => d.children)
            .sum(d => d.children?.length || 0)
            .sort((a, b) => b.value - a.value)
        this.root = d3.pack<SubjectInCircle>()
            .size([this.width, this.height])
            .radius(d => Math.sqrt(d.data.total_descendants) || 0)

            .padding(d => d.data.children ? 0.5 : 1)(this.hierarchy);
        console.log('root', this.root)
        let max_depth = 0
        this.root.each(d => {
            if (d.depth > max_depth) {
                max_depth = d.depth
            }
            console.log('node', d.data.subject_id, d.data)
            this.subjects_by_id[d.data.subject_id] = d.data
        })

        this.color = d3.scaleLinear<number, string, string>()
            .domain([0, max_depth])
            .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
            .interpolate(d3.interpolateHcl as any);


    }

    private restartPackedCircles() {
        this.scene.clear()
        this.root.each(d => {
            const node = d.data
            const circle = new THREE.Mesh(this.pool.geometry, this.pool.materials[d.depth]);
            node.position = new THREE.Vector3(d.x, d.depth, d.y)
            circle.position.copy(node.position);
            circle.scale.set(d.r, 1, d.r);


            const frame = new THREE.LineSegments(this.pool.edge_geometry, this.pool.line_materials[d.depth]);
            circle.add(frame);
            this.scene.add(circle);
            // console.log('added circle', d.x, d.y, d.depth * 10, d.r)
            // const text = new THREE.Mesh(new (THREE as any).TextGeometry(node.label, { size: 1, height: 0.1 }), this.pool.text_material);
            // text.position.set(d.x, d.y, d.depth * 10 + 1);
            // // this.scene.add(text);
            // if (d.parent) {
            //     const parent = d.parent
            //     const line = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 1, 32), this.pool.materials[d.depth]);
            //     line.position.set((d.x + parent.x) / 2, (d.y + parent.y) / 2, d.depth * 10);
            //     line.lookAt(new THREE.Vector3(d.x, d.y, d.depth * 10));
            //     line.scale.set(1, 1, Math.sqrt((d.x - parent.x) ** 2 + (d.y - parent.y) ** 2));
            //     this.scene.add(line);
            // }
        });

    }
    private buildTopicTree() {
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
            let children = topic.sub_topics.map(sub_topic => build_tree_bottom(sub_topic, depth - 1))
            topic.links = [...children.map(child => {
                let link = new TopicTreeLink()
                link.from_topic = child
                link.from_position = child.to_position
                return link
            }), ...topic.subjects_ids.map(subject_id => {
                let link = new TopicTreeLink()
                link.from_subject = this.subjects_by_id[subject_id]
                if (!link.from_subject) {
                    console.log('no subject', subject_id)
                    return
                }
                link.from_position = link.from_subject.position
                return link
            })].filter(link => link)
            topic.to_position = new THREE.Vector3(0, 0, 0)
            let n_valid_links = 0
            topic.links.forEach(link => {
                if (link.from_position) {
                    topic.to_position.add(link.from_position)
                    n_valid_links++
                }
            })
            topic.to_position.divideScalar(n_valid_links)
            topic.to_position.add(new THREE.Vector3(0, this.tree_params.level_height, 0))

            topic.links.map(link => {
                let curve = new THREE.QuadraticBezierCurve3(topic.to_position,
                    link.from_position.clone().add(new THREE.Vector3(0, this.tree_params.level_height, 0)),
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
            return topic

        }
        build_tree_bottom(this.topics_root, depth)
    }
    initPackedCircles() {

        this.computePacking()


        d3.select('.graph_wrapper').selectAll("*").remove()
        this.three_div = d3.select('.graph_wrapper').append("div").attr("class", "threed_graph").node()
        this.width = this.three_div.clientWidth
        this.height = this.three_div.clientHeight

        const renderer = new THREE.WebGLRenderer();
        renderer.setSize(this.width, this.height);
        this.three_div.appendChild(renderer.domElement);

        this.camera = new THREE.PerspectiveCamera(75, this.width / this.height, 0.2, 1500);
        this.camera.aspect = this.width / this.height;
        this.camera.updateProjectionMatrix();
        this.camera.position.set(0, 250, 0);


        this.scene = new THREE.Scene();
        this.scene.position.x = -this.dimensions.width / 2;
        // this.scene.position.y = -this.dimensions.height / 2;
        this.scene.position.z = -this.dimensions.depth / 4;
        this.scene.background = new THREE.Color(0xffffff);

        this.pool.geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
        this.pool.edge_geometry = new THREE.EdgesGeometry(this.pool.geometry);
        this.pool.materials = {}
        this.root.each(nd => {
            if (nd.depth in this.pool.materials) {
                return
            }
            this.pool.materials[nd.depth] = new THREE.MeshBasicMaterial({
                color: this.color(nd.depth),
                transparent: true,
                opacity: 0.8
            });
            this.pool.line_materials[nd.depth] = new THREE.MeshBasicMaterial({ color: d3.color(this.color(nd.depth)).darker(0.5).formatHex() });
        });
        this.pool.text_material = new THREE.MeshBasicMaterial({ color: 0x000000 });
        // this.pool.edge_geometry = new THREE.EdgesGeometry(this.pool.geometry);
        // this.pool.line_material = new THREE.MeshBasicMaterial({ color: 0x000000 });
        this.restartPackedCircles()

        this.buildTopicTree()

        const controls = new OrbitControls(this.camera, renderer.domElement);
        controls.screenSpacePanning = true;
        controls.maxPolarAngle = Math.PI / 2.5;
        controls.minDistance = 50;
        controls.maxDistance = 650;
        controls.addEventListener("change", () => {
            // tooltip.clear();
            renderer.clear();
            renderer.render(this.scene, this.camera);
        });
        controls.update();
        renderer.render(this.scene, this.camera);
    }
    addLink(from: string, to: string, count: number) {


    }
    removeLinks() {
    }
}