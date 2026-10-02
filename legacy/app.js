import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';
import { GLTFLoader } from 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/GLTFLoader.js';

// Scene
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x050A14);

// Camera
const camera = new THREE.PerspectiveCamera(
    75,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
);

camera.position.set(0, 10, 20);

// Renderer
const renderer = new THREE.WebGLRenderer({
    antialias: true
});

renderer.setSize(
    window.innerWidth,
    window.innerHeight
);

document.body.appendChild(
    renderer.domElement
);

// Lights
const ambientLight = new THREE.AmbientLight(
    0xffffff,
    3
);
scene.add(ambientLight);

const dirLight = new THREE.DirectionalLight(
    0xffffff,
    5
);

dirLight.position.set(
    10,
    20,
    10
);

scene.add(dirLight);

// Grid Floor
const grid = new THREE.GridHelper(
    100,
    100,
    0x00ffff,
    0x444444
);

scene.add(grid);

// Loader
const loader = new GLTFLoader();

let motors = [];

function loadMotor(x, z) {

    loader.load(
        './models/motor.glb',

        (gltf) => {

            const model = gltf.scene;

            // Compute size
            const box = new THREE.Box3().setFromObject(model);

            const size = box.getSize(
                new THREE.Vector3()
            );

            const center = box.getCenter(
                new THREE.Vector3()
            );

            // Center model
            model.position.sub(center);

            // Auto scale
            const maxDim = Math.max(
                size.x,
                size.y,
                size.z
            );

            const scaleFactor = 4 / maxDim;

            model.scale.set(
                scaleFactor,
                scaleFactor,
                scaleFactor
            );

            // Move to location
            model.position.x += x;
            model.position.z += z;

            scene.add(model);

            motors.push(model);

            console.log(
                "Motor loaded:",
                size
            );
        },

        undefined,

        (error) => {

            console.error(
                "GLB Load Error:",
                error
            );

        }
    );
}

// Four Motors

loadMotor(-10, -10);

loadMotor(10, -10);

loadMotor(-10, 10);

loadMotor(10, 10);

// Animation

function animate() {

    requestAnimationFrame(
        animate
    );

    motors.forEach(
        motor => {

            motor.rotation.y += 0.003;

        }
    );

    renderer.render(
        scene,
        camera
    );
}

animate();

// Resize

window.addEventListener(
    'resize',
    () => {

        camera.aspect =
            window.innerWidth /
            window.innerHeight;

        camera.updateProjectionMatrix();

        renderer.setSize(
            window.innerWidth,
            window.innerHeight
        );

    }
);