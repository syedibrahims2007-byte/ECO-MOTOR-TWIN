/**
 * EcoMotorTwin Frontend — 3D Digital Twin + Dashboard
 * Uses Three.js for 3D visualization and Chart.js for live charts.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import Chart from 'chart.js/auto';

// ============================================================
// Configuration
// ============================================================
const API_BASE = '/api';
const WS_URL = `ws://${window.location.host}/ws/live`;
const MOTOR_ORDER = ['M1_Conveyor', 'M2_Pump', 'M3_Compressor', 'M4_ProcessMachine'];
const MOTOR_POSITIONS = [
  { x: -6, z: 0 },
  { x: -2, z: 0 },
  { x: 2, z: 0 },
  { x: 6, z: 0 },
];
const HEALTH_COLORS = {
  Healthy: 0x00ff88,
  Warning: 0xffaa00,
  Critical: 0xff3333,
};

// ============================================================
// Global State
// ============================================================
let ws = null;
let reconnectInterval = null;
let motorModels = {};
let motorStates = {};
let charts = {};
let scene, camera, renderer, controls;
let motorGroup;
let flowLines = [];
let selectedMotor = null;

// ============================================================
// Initialization
// ============================================================
async function init() {
  initThreeJS();
  await loadMotorModel();
  createMotorInstances();
  createFlowLines();
  initCharts();
  initMotorCards();
  initHealthGauges();
  connectWebSocket();
  startAnimation();
  document.getElementById('loading-overlay').style.display = 'none';
}

// ============================================================
// Three.js 3D Scene
// ============================================================
function initThreeJS() {
  const container = document.getElementById('three-container');
  const width = container.clientWidth;
  const height = container.clientHeight;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a1628);
  scene.fog = new THREE.Fog(0x0a1628, 20, 50);

  camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 100);
  camera.position.set(0, 8, 14);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.maxPolarAngle = Math.PI / 2.1;

  // Lighting
  const ambientLight = new THREE.AmbientLight(0x404060, 0.5);
  scene.add(ambientLight);

  const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
  dirLight.position.set(5, 10, 7);
  dirLight.castShadow = true;
  scene.add(dirLight);

  const pointLight = new THREE.PointLight(0x00ccff, 0.5, 30);
  pointLight.position.set(0, 5, 0);
  scene.add(pointLight);

  // Floor
  const floorGeo = new THREE.PlaneGeometry(30, 10);
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0x0d1f3c,
    roughness: 0.8,
    metalness: 0.2,
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.5;
  floor.receiveShadow = true;
  scene.add(floor);

  // Grid
  const grid = new THREE.GridHelper(30, 30, 0x1a3a5c, 0x0d2240);
  grid.position.y = -0.49;
  scene.add(grid);

  motorGroup = new THREE.Group();
  scene.add(motorGroup);

  // Click handler
  renderer.domElement.addEventListener('click', onMotorClick);

  // Resize handler
  window.addEventListener('resize', onWindowResize);
}

async function loadMotorModel() {
  return new Promise((resolve, reject) => {
    const loader = new GLTFLoader();
    loader.load(
      '/models/motor.glb',
      (gltf) => {
        motorModels.template = gltf.scene;
        resolve();
      },
      (progress) => {
        const pct = Math.round((progress.loaded / progress.total) * 100);
        console.log(`Loading motor model: ${pct}%`);
      },
      (error) => {
        console.error('Failed to load motor.glb:', error);
        // Create fallback box geometry
        motorModels.template = createFallbackMotor();
        resolve();
      }
    );
  });
}

function createFallbackMotor() {
  const group = new THREE.Group();
  const bodyGeo = new THREE.CylinderGeometry(0.5, 0.5, 1.5, 16);
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x3366aa, metalness: 0.6, roughness: 0.4 });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.rotation.z = Math.PI / 2;
  group.add(body);

  const shaftGeo = new THREE.CylinderGeometry(0.1, 0.1, 2.0, 8);
  const shaft = new THREE.Mesh(shaftGeo, bodyMat);
  shaft.rotation.z = Math.PI / 2;
  group.add(shaft);

  return group;
}

function createMotorInstances() {
  MOTOR_ORDER.forEach((motorId, i) => {
    const pos = MOTOR_POSITIONS[i];
    let model;

    if (motorModels.template) {
      model = motorModels.template.clone();
    } else {
      model = createFallbackMotor();
    }

    model.position.set(pos.x, 0.5, pos.z);
    model.userData = { motorId, index: i };

    // Add emissive material for health indication
    model.traverse((child) => {
      if (child.isMesh) {
        child.material = child.material.clone();
        child.material.emissive = new THREE.Color(0x00ff88);
        child.material.emissiveIntensity = 0.3;
        child.castShadow = true;
      }
    });

    motorGroup.add(model);
    motorModels[motorId] = model;

    // Add label
    createMotorLabel(motorId, pos);
  });
}

function createMotorLabel(motorId, pos) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = 'rgba(10, 22, 40, 0.8)';
  ctx.fillRect(0, 0, 256, 128);

  ctx.fillStyle = '#00ccff';
  ctx.font = 'bold 20px monospace';
  ctx.textAlign = 'center';
  ctx.fillText(motorId, 128, 30);

  ctx.fillStyle = '#ffffff';
  ctx.font = '16px monospace';
  ctx.fillText('— kW  |  — °C', 128, 60);
  ctx.fillText('— g  |  — %', 128, 85);

  const texture = new THREE.CanvasTexture(canvas);
  const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.position.set(pos.x, 2.2, pos.z);
  sprite.scale.set(2.5, 1.25, 1);
  sprite.userData = { motorId, isLabel: true };
  motorGroup.add(sprite);
  motorModels[motorId + '_label'] = sprite;
}

function createFlowLines() {
  // Animated flow lines between motors
  for (let i = 0; i < MOTOR_ORDER.length - 1; i++) {
    const start = MOTOR_POSITIONS[i];
    const end = MOTOR_POSITIONS[i + 1];

    const points = [];
    for (let t = 0; t <= 1; t += 0.05) {
      points.push(new THREE.Vector3(
        start.x + (end.x - start.x) * t,
        0.5,
        start.z + (end.z - start.z) * t
      ));
    }

    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
      color: 0x00ccff,
      transparent: true,
      opacity: 0.4,
    });
    const line = new THREE.Line(geometry, material);
    motorGroup.add(line);
    flowLines.push(line);
  }
}

function onMotorClick(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1
  );

  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, camera);

  const intersects = raycaster.intersectObjects(motorGroup.children, true);
  if (intersects.length > 0) {
    let obj = intersects[0].object;
    while (obj.parent && !obj.userData.motorId) {
      obj = obj.parent;
    }
    if (obj.userData.motorId) {
      selectMotor(obj.userData.motorId);
    }
  }
}

function selectMotor(motorId) {
  selectedMotor = motorId;
  document.getElementById('chart-motor-select').value = motorId;
  updateMotorDetailPanel(motorId);
}

function onWindowResize() {
  const container = document.getElementById('three-container');
  const width = container.clientWidth;
  const height = container.clientHeight;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}

// ============================================================
// Animation Loop
// ============================================================
function startAnimation() {
  function animate() {
    requestAnimationFrame(animate);

    // Rotate motors proportional to RPM
    MOTOR_ORDER.forEach((motorId) => {
      const state = motorStates[motorId];
      const model = motorModels[motorId];
      if (model && state) {
        const rpm = state.rpm || 0;
        model.rotation.x += (rpm / 60) * 0.01;
      }
    });

    // Animate flow lines
    const time = Date.now() * 0.001;
    flowLines.forEach((line, i) => {
      line.material.opacity = 0.3 + 0.2 * Math.sin(time * 2 + i);
    });

    // Pulse critical motors
    MOTOR_ORDER.forEach((motorId) => {
      const state = motorStates[motorId];
      const model = motorModels[motorId];
      if (model && state && state.health_state === 'Critical') {
        const pulse = 0.5 + 0.5 * Math.sin(time * 5);
        model.traverse((child) => {
          if (child.isMesh && child.material.emissive) {
            child.material.emissiveIntensity = 0.3 + 0.5 * pulse;
          }
        });
      }
    });

    controls.update();
    renderer.render(scene, camera);
  }
  animate();
}

// ============================================================
// WebSocket Connection
// ============================================================
function connectWebSocket() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log('WebSocket connected');
    updateConnectionBadge(true);
    if (reconnectInterval) {
      clearInterval(reconnectInterval);
      reconnectInterval = null;
    }
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboard(data);
    } catch (e) {
      console.error('WebSocket message error:', e);
    }
  };

  ws.onclose = () => {
    console.log('WebSocket disconnected');
    updateConnectionBadge(false);
    scheduleReconnect();
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
}

function scheduleReconnect() {
  if (reconnectInterval) return;
  reconnectInterval = setInterval(() => {
    console.log('Attempting WebSocket reconnect...');
    connectWebSocket();
  }, 3000);
}

function updateConnectionBadge(connected) {
  const badge = document.getElementById('connection-badge');
  const text = document.getElementById('connection-text');
  if (connected) {
    badge.className = 'badge badge-connected';
    text.textContent = 'Live';
  } else {
    badge.className = 'badge badge-disconnected';
    text.textContent = 'Disconnected';
  }
}

// ============================================================
// Dashboard Updates
// ============================================================
function updateDashboard(data) {
  if (!data || !data.motors) return;

  // Update motor states
  data.motors.forEach((motor) => {
    motorStates[motor.motor_id] = motor;
    updateMotorCard(motor);
    updateMotorLabel(motor);
    updateMotorColor(motor);
  });

  // Update cell KPIs
  if (data.cell) {
    document.getElementById('kpi-power').textContent =
      data.cell.total_power_kw?.toFixed(1) || '—';
    document.getElementById('kpi-energy').textContent =
      data.cell.total_energy_kwh?.toFixed(1) || '—';
    document.getElementById('kpi-production').textContent =
      data.cell.cell_production_units_h?.toFixed(0) || '—';
    document.getElementById('kpi-sec').textContent =
      data.cell.cell_sec_kwh_per_unit?.toFixed(3) || '—';
  }

  // Update health gauges
  updateHealthGauges();

  // Update charts
  updateCharts();
}

function updateMotorCard(motor) {
  const cardsContainer = document.getElementById('motor-cards');
  let card = document.getElementById(`card-${motor.motor_id}`);
  if (!card) {
    card = document.createElement('div');
    card.id = `card-${motor.motor_id}`;
    card.className = 'motor-card';
    cardsContainer.appendChild(card);
  }

  const healthClass = motor.health_state?.toLowerCase() || 'healthy';
  card.className = `motor-card ${healthClass}`;
  card.innerHTML = `
    <div class="motor-card-header">
      <span class="motor-name">${motor.motor_id}</span>
      <span class="motor-status-icon">${getStatusIcon(motor.health_state)}</span>
    </div>
    <div class="motor-card-body">
      <div class="motor-metric">
        <span class="metric-label">Power</span>
        <span class="metric-value">${motor.power_kw?.toFixed(1) || '—'} kW</span>
      </div>
      <div class="motor-metric">
        <span class="metric-label">Temp</span>
        <span class="metric-value">${motor.temperature_c?.toFixed(1) || '—'} °C</span>
      </div>
      <div class="motor-metric">
        <span class="metric-label">Vibration</span>
        <span class="metric-value">${motor.vibration_g?.toFixed(3) || '—'} g</span>
      </div>
      <div class="motor-metric">
        <span class="metric-label">Health</span>
        <span class="metric-value">${motor.health_score?.toFixed(0) || '—'}%</span>
      </div>
    </div>
  `;
}

function updateMotorLabel(motor) {
  const label = motorModels[motor.motor_id + '_label'];
  if (!label) return;

  const canvas = label.material.map.image;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 256, 128);

  ctx.fillStyle = 'rgba(10, 22, 40, 0.8)';
  ctx.fillRect(0, 0, 256, 128);

  ctx.fillStyle = '#00ccff';
  ctx.font = 'bold 20px monospace';
  ctx.textAlign = 'center';
  ctx.fillText(motor.motor_id, 128, 30);

  ctx.fillStyle = '#ffffff';
  ctx.font = '16px monospace';
  ctx.fillText(
    `${motor.power_kw?.toFixed(1) || '—'} kW  |  ${motor.temperature_c?.toFixed(1) || '—'} °C`,
    128, 60
  );
  ctx.fillText(
    `${motor.vibration_g?.toFixed(3) || '—'} g  |  ${motor.health_score?.toFixed(0) || '—'}%`,
    128, 85
  );

  label.material.map.needsUpdate = true;
}

function updateMotorColor(motor) {
  const model = motorModels[motor.motor_id];
  if (!model) return;

  const color = HEALTH_COLORS[motor.health_state] || HEALTH_COLORS.Healthy;
  model.traverse((child) => {
    if (child.isMesh && child.material.emissive) {
      child.material.emissive.setHex(color);
      child.material.emissiveIntensity = 0.3;
    }
  });
}

function getStatusIcon(state) {
  switch (state) {
    case 'Healthy': return '✓';
    case 'Warning': return '⚠';
    case 'Critical': return '✖';
    default: return '—';
  }
}

// ============================================================
// Health Gauges
// ============================================================
function initHealthGauges() {
  const container = document.getElementById('health-gauges');
  MOTOR_ORDER.forEach((motorId) => {
    const gauge = document.createElement('div');
    gauge.className = 'health-gauge';
    gauge.id = `gauge-${motorId}`;
    gauge.innerHTML = `
      <div class="gauge-label">${motorId}</div>
      <div class="gauge-bar">
        <div class="gauge-fill" id="gauge-fill-${motorId}"></div>
      </div>
      <div class="gauge-value" id="gauge-value-${motorId}">—</div>
    `;
    container.appendChild(gauge);
  });
}

function updateHealthGauges() {
  MOTOR_ORDER.forEach((motorId) => {
    const state = motorStates[motorId];
    const fill = document.getElementById(`gauge-fill-${motorId}`);
    const value = document.getElementById(`gauge-value-${motorId}`);
    if (!fill || !value) return;

    const score = state?.health_score ?? 100;
    fill.style.width = `${score}%`;

    const healthClass = state?.health_state?.toLowerCase() || 'healthy';
    fill.className = `gauge-fill ${healthClass}`;
    value.textContent = `${score.toFixed(0)}%`;
  });
}

// ============================================================
// Charts
// ============================================================
function initCharts() {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      x: { display: false },
      y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#88aacc' } },
    },
    plugins: { legend: { display: false } },
    elements: { point: { radius: 0 } },
  };

  charts.current = new Chart(document.getElementById('chart-current'), {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#00ccff', borderWidth: 2, fill: false }] },
    options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: 'Current (A)', color: '#88aacc' } } } },
  });

  charts.power = new Chart(document.getElementById('chart-power'), {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#00ff88', borderWidth: 2, fill: false }] },
    options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: 'Power (kW)', color: '#88aacc' } } } },
  });

  charts.temp = new Chart(document.getElementById('chart-temp'), {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#ff6644', borderWidth: 2, fill: false }] },
    options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: 'Temp (°C)', color: '#88aacc' } } } },
  });

  charts.vibration = new Chart(document.getElementById('chart-vibration'), {
    type: 'line',
    data: { labels: [], datasets: [{ data: [], borderColor: '#ffaa00', borderWidth: 2, fill: false }] },
    options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: 'Vibration (g)', color: '#88aacc' } } } },
  });
}

function updateCharts() {
  const motorId = document.getElementById('chart-motor-select').value;
  const state = motorStates[motorId];
  if (!state) return;

  const maxPoints = 60;
  const chartsConfig = [
    { chart: charts.current, key: 'current_a', color: '#00ccff' },
    { chart: charts.power, key: 'power_kw', color: '#00ff88' },
    { chart: charts.temp, key: 'temperature_c', color: '#ff6644' },
    { chart: charts.vibration, key: 'vibration_g', color: '#ffaa00' },
  ];

  chartsConfig.forEach(({ chart, key }) => {
    if (!chart) return;
    const value = state[key];
    if (value === undefined) return;

    const data = chart.data.datasets[0].data;
    const labels = chart.data.labels;
    data.push(value);
    labels.push(new Date().toLocaleTimeString());
    if (data.length > maxPoints) {
      data.shift();
      labels.shift();
    }
    chart.update('none');
  });
}

// ============================================================
// Motor Cards
// ============================================================
function initMotorCards() {
  // Cards are created dynamically in updateMotorCard
}

function updateMotorDetailPanel(motorId) {
  const state = motorStates[motorId];
  if (!state) return;

  // Could expand to show more details
  console.log('Selected motor:', motorId, state);
}

// ============================================================
// Alerts
// ============================================================
async function fetchAlerts() {
  try {
    const resp = await fetch(`${API_BASE}/alerts?limit=20`);
    if (!resp.ok) return;
    const alerts = await resp.json();
    renderAlerts(alerts);
  } catch (e) {
    console.error('Failed to fetch alerts:', e);
  }
}

function renderAlerts(alerts) {
  const container = document.getElementById('alert-feed');
  if (!alerts || alerts.length === 0) {
    container.innerHTML = '<div class="alert-empty">No alerts</div>';
    return;
  }

  container.innerHTML = alerts.map((alert) => `
    <div class="alert-item alert-${alert.severity?.toLowerCase() || 'info'}">
      <div class="alert-header">
        <span class="alert-motor">${alert.motor}</span>
        <span class="alert-time">${new Date(alert.timestamp).toLocaleTimeString()}</span>
      </div>
      <div class="alert-message">${alert.message || alert.probable_cause || ''}</div>
      ${alert.recommended_action ? `<div class="alert-action">→ ${alert.recommended_action}</div>` : ''}
    </div>
  `).join('');
}

// ============================================================
// Maintenance Panel
// ============================================================
function updateMaintenancePanel() {
  const container = document.getElementById('maintenance-panel');
  MOTOR_ORDER.forEach((motorId) => {
    const state = motorStates[motorId];
    if (!state) return;

    let panel = document.getElementById(`maint-${motorId}`);
    if (!panel) {
      panel = document.createElement('div');
      panel.id = `maint-${motorId}`;
      panel.className = 'maintenance-item';
      container.appendChild(panel);
    }

    panel.innerHTML = `
      <div class="maintenance-header">
        <span>${motorId}</span>
        <span class="maintenance-hours">${state.operating_hours?.toFixed(0) || '—'} h</span>
      </div>
      <div class="maintenance-status">
        <span class="status-badge ${state.health_state?.toLowerCase() || 'healthy'}">${state.health_state || '—'}</span>
        ${state.predicted_fault && state.predicted_fault !== 'normal' ? `<span class="fault-badge">${state.predicted_fault}</span>` : ''}
      </div>
    `;
  });
}

// ============================================================
// Fault Injection
// ============================================================
document.getElementById('btn-inject-fault')?.addEventListener('click', async () => {
  const motor = document.getElementById('fault-motor').value;
  const faultType = document.getElementById('fault-type').value;

  try {
    const resp = await fetch(`${API_BASE}/simulate/fault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ motor, fault_type: faultType, duration_sec: 300 }),
    });
    if (resp.ok) {
      showNotification(`Fault '${faultType}' injected on ${motor}`);
    }
  } catch (e) {
    console.error('Fault injection failed:', e);
  }
});

document.getElementById('btn-reset-sim')?.addEventListener('click', async () => {
  try {
    const resp = await fetch(`${API_BASE}/simulate/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
    });
    if (resp.ok) {
      showNotification('Simulator reset');
    }
  } catch (e) {
    console.error('Reset failed:', e);
  }
});

function showNotification(message) {
  const div = document.createElement('div');
  div.className = 'notification';
  div.textContent = message;
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 3000);
}

// ============================================================
// Periodic Updates
// ============================================================
setInterval(fetchAlerts, 5000);
setInterval(updateMaintenancePanel, 2000);

// ============================================================
// Start
// ============================================================
init().catch((error) => {
  console.error('Initialization failed:', error);
  document.getElementById('loading-overlay').innerHTML =
    '<p style="color: #ff4444;">Failed to initialize. Check console for details.</p>';
});
