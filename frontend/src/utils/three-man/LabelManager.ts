import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
interface Labelable {
    id: string;
    label?: string;
    position: THREE.Vector3;
    children?: Labelable[];
    parent?: Labelable | null;
}
export class LabelInstance<T extends Labelable = Labelable> {
    id: string
    subj: T
    radius: number = 100
    base_position: THREE.Vector3
    object: CSS2DObject
    connector: THREE.Mesh | null = null;
    label_div: HTMLDivElement
    text: string
    shown: boolean = false
    cbs: ((label: LabelInstance, display: boolean) => void)[] = []
    constructor(obj: T, private man: LabelManager<T> = null, scene: THREE.Scene = null) {
        this.base_position = new THREE.Vector3(0, 0, 0)
        // this.position = new THREE.Vector3(0, 0, 0)
        this.text = ''
        this.subj = obj || null;

        this.text = obj.label;
        this.label_div = document.createElement('div');
        this.label_div.className = 'label';
        this.label_div.textContent = this.text;
        this.label_div.style.color = '#000000';
        this.label_div.style.fontSize = '12px';
        this.label_div.style.backgroundColor = 'rgba(255, 255, 255, 0.59)';
        this.label_div.style.border = '1px solid #000000';
        this.label_div.style.padding = '2px 4px';
        this.label_div.style.width = '128px';
        // label.

        this.object = new CSS2DObject(this.label_div);
        this.object.center.set(0.5, 0.5);
        this.object.visible = false;

        this.update_position();
        this.init_connector(scene);
    }
    init_connector(scene: THREE.Scene) {
        if (this.connector) {
            scene.remove(this.connector);
        }
        let outpos = new THREE.Vector3(0, 0, 0);
        outpos.copy(this.subj.position);
        outpos.y = 0;
        outpos.normalize();
        outpos.multiplyScalar(this.radius);
        outpos.y = this.subj.position.y;
        let curve = new THREE.CatmullRomCurve3([
            this.subj.position,
            outpos,
            this.base_position,])

        let geometry = new THREE.TubeGeometry(curve,
            this.man.link_params.segments,
            this.man.link_params.radius,
            this.man.link_params.radial_segments,
            false
        );
        this.connector = new THREE.Mesh(
            geometry,
            this.man.pool.material
        )
        this.connector.visible = false
        scene.add(this.connector);
        // this.connector = new THREE.Mesh(
    }
    update_position() {
        if (this.subj) {
            this.base_position.copy(this.subj.position);
            this.base_position.y = 0;
            this.base_position.normalize();
            this.base_position.multiplyScalar(this.radius);
            this.base_position.y = this.subj.position.y;
        }
        this.object.position.copy(this.base_position);
    }
    display(shown: boolean = true) {
        this.shown = shown
        for (let cb of this.cbs) {
            cb(this, shown);
        }
        if (this.label_div) {
            // this.label_div.style.display = shown ? 'block' : 'none';
        }
        if (this.connector) {
            this.connector.visible = shown;
        }
        if (this.object) {
            this.object.visible = shown;
        }
        if (this.subj.parent) {
            this.man.labels[this.subj.parent.id]?.display(shown);
        }
    }
}
export class LabelManager<T extends Labelable = Labelable> {
    labels: Record<string, LabelInstance> = {};

    pool: {
        material: THREE.MeshBasicMaterial,
    }
    link_params = {
        segments: 32,
        radius: 0.1,
        level_height: 16,
        radial_segments: 4,
    }
    label_container: HTMLDivElement = null;
    label_parent: HTMLElement = null;

    hovering_labels = {} as Record<string, LabelInstance>;
    constructor(label_parent: HTMLElement) {
        this.pool = {
            material: null,
        };
        this.pool.material = new THREE.MeshBasicMaterial({
            color: 0x000000,
            transparent: true,
            opacity: 0.5,
        });
        // this.label_parent = label_parent;
        // this.label_container = document.createElement('div');
        // this.label_container.className = 'label_container';
        // this.label_container.style.width = '100%';
        // this.label_container.style.height = '100%';
        // this.label_container.style.position = 'relative';
        // this.label_parent.appendChild(this.label_container);

    }
    register_label(id: string, obj: T, scene: THREE.Scene) {
        if (this.labels[id]) {
        } else {
            this.labels[id] = new LabelInstance(obj, this, scene);
            this.labels[id].id = id;
        }
        let label = this.labels[id];

        scene.add(label.object);
        return label;
    }
    register_event(id: string, cb: (label: LabelInstance, display: boolean) => void) {
        if (this.labels[id]) {
            this.labels[id].cbs.push(cb);
        }
    }
    update_labels(camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer) {

        let bounds = renderer.domElement.getBoundingClientRect();
        // for (let key in this.hovering_labels) {
        //     const label = this.labels[key];
        //     // if (label.shown) {
        //     //     // label.update_position();
        //     // }

        // }
    }
    check_hover(camera: THREE.PerspectiveCamera, scene: THREE.Scene, mouse: THREE.Vector2) {
        const raycaster = new THREE.Raycaster();
        let new_hovering_labels = {} as Record<string, LabelInstance>;
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(scene.children, true);
        for (let intersect of intersects) {
            let object = intersect.object;
            if (object.name && this.labels[object.name]) {
                const label = this.labels[object.name];
                new_hovering_labels[label.id] = label;
                break; // only take the first intersected label
            }
        }
        let removed_labels = Object.keys(this.hovering_labels).filter(key => !(key in new_hovering_labels));
        let added_labels = Object.keys(new_hovering_labels).filter(key => !(key in this.hovering_labels));
        // console.log('Removed labels:', removed_labels);
        // console.log('Added labels:', added_labels);
        for (let key of removed_labels) {
            this.hovering_labels[key].display(false);
            delete this.hovering_labels[key];
        }
        for (let key of added_labels) {
            this.hovering_labels[key] = new_hovering_labels[key];
            this.hovering_labels[key].display(true);
        }
    }
}
