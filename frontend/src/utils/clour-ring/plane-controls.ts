import { Controls } from "three";
import * as THREE from "three";
import { type DragControlsEventMap } from "three/examples/jsm/controls/DragControls.js";
enum STATE {
    NONE = -1,
    PAN = 0,
    ROTATE = 1
}
//https://github.com/mrdoob/three.js/blob/master/examples/jsm/controls/DragControls.js
export class PlaneControls extends Controls<DragControlsEventMap> {
    rotateSpeed: number;



    raycaster: THREE.Raycaster;
    mouseButtons: { LEFT: any; MIDDLE: any; RIGHT: any; };
    touches: { ONE: any; };
    private _onPointerMove: any;
    private _onPointerDown: any;
    private _onPointerCancel: any;
    private _onContextMenu: any;
    state: STATE;
    recursive: boolean;
    private _pointer: THREE.Vector2;
    private _previousPointer: THREE.Vector2;
    private _worldPosition: THREE.Vector3 = new THREE.Vector3();
    intersections: THREE.Intersection<THREE.Object3D<THREE.Object3DEventMap>>[];
    private _up= new THREE.Vector3();
    private _right= new THREE.Vector3();
    private _inverseMatrix: THREE.Matrix4 = new THREE.Matrix4();
    private _offset = new THREE.Vector3();

    /**
     * Constructs a new controls instance.
     *
     * @param {Array<Object3D>} objects - An array of draggable 3D objects.
     * @param {Camera} camera - The camera of the rendered scene.
     * @param {?HTMLDOMElement} [domElement=null] - The HTML DOM element used for event listeners.
     */
    constructor(public plane_obj: THREE.Mesh,
        public radius_point: THREE.Mesh,
        public camera,
        public domElement = null,
        public plane_proj: THREE.Plane = new THREE.Plane(),
    ) {

        super(camera, domElement);

        this.rotateSpeed = 1;

        /**
         * The raycaster used for detecting 3D objects.
         *
         * @type {Raycaster}
         */
        this.raycaster = new THREE.Raycaster();
        this._pointer = new THREE.Vector2();
        this._previousPointer = new THREE.Vector2();
        this.recursive = false;
        this.state = STATE.NONE;
        // interaction

        this.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.ROTATE };
        this.touches = { ONE: THREE.TOUCH.PAN };

        // event listeners

        this._onPointerMove = this.onPointerMove.bind(this);
        this._onPointerDown = this.onPointerDown.bind(this);
        this._onPointerCancel = this.onPointerCancel.bind(this);
        this._onContextMenu = this.onContextMenu.bind(this);

        //

        if (domElement !== null) {

            this.connect(domElement);

        }

    }
    // strange typescript error from three.js, this is how they do it in DragControls
    // @ts-ignore
    connect(element) {
        // @ts-ignore
        super.connect(element);

        this.domElement.addEventListener('pointermove', this._onPointerMove);
        this.domElement.addEventListener('pointerdown', this._onPointerDown);
        this.domElement.addEventListener('pointerup', this._onPointerCancel);
        this.domElement.addEventListener('pointerleave', this._onPointerCancel);
        this.domElement.addEventListener('contextmenu', this._onContextMenu);

        this.domElement.style.touchAction = 'none'; // disable touch scroll

    }



    _updatePointer(event) {

        const rect = this.domElement.getBoundingClientRect();

        this._pointer.x = (event.clientX - rect.left) / rect.width * 2 - 1;
        this._pointer.y = - (event.clientY - rect.top) / rect.height * 2 + 1;

    }

    _updateState(event) {

        // determine action

        let action;

        if (event.pointerType === 'touch') {

            action = this.touches.ONE;

        } else {

            switch (event.button) {

                case 0:

                    action = this.mouseButtons.LEFT;
                    break;

                case 1:

                    action = this.mouseButtons.MIDDLE;
                    break;

                case 2:

                    action = this.mouseButtons.RIGHT;
                    break;

                default:

                    action = null;

            }

        }

        // determine state

        switch (action) {

            case THREE.MOUSE.PAN:
            case THREE.TOUCH.PAN:

                this.state = STATE.PAN;

                break;

            case THREE.MOUSE.ROTATE:
            case THREE.TOUCH.ROTATE:

                this.state = STATE.ROTATE;

                break;

            default:

                this.state = STATE.NONE;

        }

    }

    onPointerDown(event) {
        event.preventDefault();
        this._updatePointer(event);
        this._updateState(event);

        this.raycaster.setFromCamera(this._pointer, this.camera);
        this.intersections = this.raycaster.intersectObjects([
            // this.plane_obj,
            this.radius_point
        ], this.recursive);
        //move the radius point on the plane obj
        if (this.intersections.length > 0) {
            this.plane_proj.setFromNormalAndCoplanarPoint(
                this.camera.getWorldDirection(this.plane_proj.normal),
                this._worldPosition.setFromMatrixPosition(this.plane_obj.matrixWorld));

            this.raycaster.ray.intersectPlane(this.plane_proj, this._worldPosition);

            this.radius_point.position.copy(this._worldPosition);
        } else {
            // pan or rotate the plane

            this.plane_proj.setFromNormalAndCoplanarPoint(
                this.camera.getWorldDirection(this.plane_proj.normal),
                this._worldPosition.setFromMatrixPosition(this.plane_obj.matrixWorld));
            //rotate the plane
            if (this.state === STATE.ROTATE) {
                this._up.set(0, 1, 0).applyQuaternion(this.camera.quaternion).normalize();
                this._right.set(1, 0, 0).applyQuaternion(this.camera.quaternion).normalize();
            } else if (this.state === STATE.PAN) {
                let _intersection = new THREE.Vector3();
                if (this.raycaster.ray.intersectPlane(this.plane_proj, _intersection)) {
                    this._inverseMatrix.copy(this.plane_obj.parent.matrixWorld).invert();
                    this._offset.copy(_intersection).sub(this._worldPosition.setFromMatrixPosition(this.plane_obj.matrixWorld));

                }
            }
        }
        this._previousPointer.copy(this._pointer);

    }
    onPointerMove(event) {
        this._updatePointer(event);
        this._updateState(event);

        this.raycaster.setFromCamera(this._pointer, this.camera);
        if (this.state === STATE.NONE) return;
        if (this.intersections.length === 0) {
            if (this.state === STATE.PAN) {
                let _intersection = new THREE.Vector3();
                if (this.raycaster.ray.intersectPlane(this.plane_proj, _intersection)) {
                    let new_pos = _intersection.sub(this._offset).applyMatrix4(this._inverseMatrix)
                    this.plane_obj.position.y = new_pos.y // only y !

                }
            } else if (this.state === STATE.ROTATE) {
                let _diff = this._pointer.clone().sub(this._previousPointer).multiplyScalar(this.rotateSpeed);
                this.plane_obj.rotateOnWorldAxis(this._up, _diff.x);
                this.plane_obj.rotateOnWorldAxis(this._right.normalize(), - _diff.y);

            }
        }else{
            //move the radius point on the plane obj
            this.plane_proj.setFromNormalAndCoplanarPoint(
                this.camera.getWorldDirection(this.plane_proj.normal),
                this._worldPosition.setFromMatrixPosition(this.plane_obj.matrixWorld));

            this.raycaster.ray.intersectPlane(this.plane_proj, this._worldPosition);

            this.radius_point.position.copy(this._worldPosition);
        }



        this._previousPointer.copy(this._pointer);
    }
    onPointerCancel(event) {
        event.preventDefault();
        this._updatePointer(event);
        this._updateState(event);
    }
    onContextMenu(event) {
        event.preventDefault();
        this._updatePointer(event);
        this._updateState(event);
    }

}