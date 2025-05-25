
import * as d3 from 'd3'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

import cylinderFrag from '@/assets/shaders/cylinder.frag?raw'
import cylinderVer from '@/assets/shaders/cylinder.vert?raw'
import { PlaneControls } from './plane-controls';

export class CylinderMan {

    three_div: HTMLElement = null
    camera: THREE.PerspectiveCamera = null
    scene: THREE.Scene = null
    renderer: THREE.Renderer = null
    dimensions = {
        width: 1000,
        height: 1000,
        depth: 1000
    }

    cylinder = {
        geometry: null as THREE.CylinderGeometry,
        material: null as THREE.ShaderMaterial,
        // text_material: null as THREE.MeshBasicMaterial,
        // edge_geometry: null as THREE.EdgesGeometry,
        // line_materials: {} as Record<number, THREE.MeshBasicMaterial>,
    };
    plane = {
        // normal: new THREE.Vector3(0, 0, 1),
        // position: new THREE.Vector3(0, 0, 0),
        // radius_point: new THREE.Vector3(1, 0, 0),

        plane_geometry: null as THREE.PlaneGeometry,
        plane_material: null as THREE.MeshBasicMaterial,
        plane_obj: null as THREE.Mesh,

        radius_geometry: null as THREE.SphereGeometry,
        radius_material: null as THREE.MeshBasicMaterial,
        radius_point: null as THREE.Mesh,


    }
    width = 1500
    height = 1500
    constructor(public query_renderer: string) {
    }
    init() {


        d3.select(this.query_renderer).selectAll("*").remove()
        this.three_div = d3.select(this.query_renderer).append("div").attr("class", "threed_graph").node()
        this.width = this.three_div.clientWidth
        this.height = this.three_div.clientHeight
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        // this.renderer.
        this.renderer.setSize(this.width, this.height);
        this.three_div.appendChild(this.renderer.domElement);

        this.camera = new THREE.PerspectiveCamera(90, this.width / this.height, 0.2, 1500);
        this.camera.aspect = this.width / this.height;
        this.camera.updateProjectionMatrix();

        this.camera.position.set(2, 2, 2);
        this.camera.lookAt(0, 0, 0);


        this.scene = new THREE.Scene();
        this.scene.position.x = 0;
        // this.scene.position.y = -this.dimensions.height / 2;
        this.scene.position.z = 0;
        this.scene.background = new THREE.Color(0xffffff);

        this.cylinder.geometry = new THREE.CylinderGeometry(1, 1, 1, 16);
        setupAttributes(this.cylinder.geometry);
        this.cylinder.material = new THREE.ShaderMaterial({
            uniforms: {
                borderRadius: { value: 2 },
                color: { value: new THREE.Vector3(0.1, 0.1, 0.1) },
            },
            vertexShader: cylinderVer,
            fragmentShader: cylinderFrag,
            transparent: true,
        })
        console.log(this.cylinder.geometry.attributes)
        // this.scene.add(new THREE.Mesh(
        //     this.pool.geometry.clone().scale(1.02, 1.02, 1.02),
        //     new THREE.MeshBasicMaterial({ color: 0xff00ff, wireframe: true })
        // ))
        this.scene.add(new THREE.AxesHelper(2));

        this.plane.plane_geometry = new THREE.PlaneGeometry(3, 3);
        this.plane.plane_geometry.translate(0, 0,0);
        this.plane.plane_geometry.rotateX(Math.PI / 2);

        this.plane.plane_material = new THREE.MeshBasicMaterial({ color: 0x00ff00, side: THREE.DoubleSide, transparent: true, opacity: 0.5 });
        this.plane.plane_obj = new THREE.Mesh(this.plane.plane_geometry, this.plane.plane_material);
        this.plane.plane_obj.position.copy(new THREE.Vector3(0, 0, 0));

        this.plane.radius_geometry = new THREE.SphereGeometry(0.05, 16, 16);
        this.plane.radius_material = new THREE.MeshBasicMaterial({ color: 0x0000ff, transparent: true, opacity: 0.5 });
        this.plane.radius_point = new THREE.Mesh(this.plane.radius_geometry, this.plane.radius_material);
        this.plane.radius_point.position.copy(new THREE.Vector3(1, 0, 0));


        this.scene.add(this.plane.plane_obj);
        this.scene.add(this.plane.radius_point);

        this.scene.add(new THREE.Mesh(
            this.cylinder.geometry,
            this.cylinder.material
        ))
        const controls = new PlaneControls(
            this.plane.plane_obj,
            this.plane.radius_point,
            this.camera,
            this.renderer.domElement,
        );
        controls.addEventListener('drag', () => {
            this.plane.plane_obj.updateMatrixWorld();
            this.plane.radius_point.updateMatrixWorld();
            this.cylinder.geometry.attributes.center.needsUpdate = true;
            this.cylinder.geometry.attributes.position.needsUpdate = true;
            this.cylinder.material.needsUpdate = true;
        });


        this.renderer.render(this.scene, this.camera);
        (this.renderer as any).setAnimationLoop(() => {
            // console.log('rendering', this)
            this.renderer.render(this.scene, this.camera);
        });




    }
}

function setupAttributes(geometry: THREE.BufferGeometry) {

    const vectors = [
        new THREE.Vector3(1, 0, 0),
        new THREE.Vector3(0, 1, 0),
        new THREE.Vector3(0, 0, 1)
    ];

    const position = geometry.attributes.position;
    const centers = new Float32Array(position.count * 3);

    for (let i = 0, l = position.count; i < l; i++) {

        vectors[i % 3].toArray(centers, i * 3);

    }

    geometry.setAttribute('center', new THREE.BufferAttribute(centers, 3));
    return geometry
}