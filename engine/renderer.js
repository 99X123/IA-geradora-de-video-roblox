/**
 * AutoShorts AI — Core Three.js Toon Renderer, Materials, Outlines & Deterministic Math
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

// ---------- Deterministic Math & Hash Helpers (NEVER use Math.random) ----------

export function hash11(n) {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
}

export function hash21(x, y) {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123;
  return s - Math.floor(s);
}

export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

export function ss(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0 || 1e-6), 0, 1);
  return t * t * (3 - 2 * t);
}

export function win(t, a, b, fade = 0.12) {
  if (t < a || t > b) return 0;
  const f = Math.min(fade, (b - a) * 0.45);
  return ss(a, a + f, t) * (1 - ss(b - f, b, t));
}

export function pop(k) {
  const t = clamp(k, 0, 1);
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

export function L3(a, b, t) {
  return new THREE.Vector3(lerp(a.x, b.x, t), lerp(a.y, b.y, t), lerp(a.z, b.z, t));
}

export function wp(obj, x = 0, y = 0, z = 0) {
  if (obj.parent) {
    let root = obj;
    while (root.parent) root = root.parent;
    root.updateMatrixWorld(true);
  } else {
    obj.updateMatrixWorld(true);
  }
  return obj.localToWorld(new THREE.Vector3(x, y, z));
}

// ---------- 4-Step Toon Gradient Map & Inverted Hull Outlines ----------

let _sharedGradientMap = null;

export function getToonGradientMap() {
  if (_sharedGradientMap) return _sharedGradientMap;
  const steps = new Uint8Array([95, 165, 225, 255]);
  const tex = new THREE.DataTexture(steps, 4, 1, THREE.RedFormat, THREE.UnsignedByteType);
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  _sharedGradientMap = tex;
  return tex;
}

export function toonMat(color, opts = {}) {
  return new THREE.MeshToonMaterial({
    color: new THREE.Color(color),
    gradientMap: getToonGradientMap(),
    emissive: opts.emissive ? new THREE.Color(opts.emissive) : new THREE.Color(0x000000),
    emissiveIntensity: opts.emissiveIntensity ?? (opts.emissive ? 1.0 : 0.0),
    emissiveMap: opts.emissiveMap || null,
    map: opts.map || null,
    transparent: Boolean(opts.transparent),
    opacity: opts.opacity ?? 1.0,
    side: opts.side ?? THREE.FrontSide,
  });
}

const _outlineCache = new Map();

export function outlineMat(thickness = 0.028, color = 0x12131c) {
  const key = `${thickness.toFixed(4)}_${color}`;
  if (_outlineCache.has(key)) return _outlineCache.get(key);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    uniforms: {
      uThickness: { value: thickness },
      uColor: { value: new THREE.Color(color) },
    },
    vertexShader: `
      uniform float uThickness;
      void main() {
        vec3 n = length(normal) > 0.0001 ? normalize(normal) : vec3(0.0, 1.0, 0.0);
        vec3 displaced = position + n * uThickness;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      void main() {
        gl_FragColor = vec4(uColor, 1.0);
      }
    `,
  });
  _outlineCache.set(key, mat);
  return mat;
}

export function makeOutlined(geometry, material, opts = {}) {
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = opts.castShadow ?? true;
  mesh.receiveShadow = opts.receiveShadow ?? true;
  if (opts.name) mesh.name = opts.name;

  if (opts.outline !== false) {
    const thickness = opts.outlineThickness ?? 0.028;
    const outlineColor = opts.outlineColor ?? 0x12131c;
    const hull = new THREE.Mesh(geometry, outlineMat(thickness, outlineColor));
    hull.name = '__outline';
    hull.castShadow = false;
    hull.receiveShadow = false;
    hull.userData.isOutline = true;
    mesh.add(hull);
  }
  return mesh;
}

export function roundedBoxGeo(w, h, d, r = 0.08, segs = 3) {
  const safeR = Math.min(r, w * 0.45, h * 0.45, d * 0.45);
  return new RoundedBoxGeometry(w, h, d, segs, safeR);
}

// ---------- Renderer & Post-Processing Pipeline ----------

export function inspectWebGL(gl) {
  const info = {
    version: gl.getParameter(gl.VERSION) || 'unknown',
    vendor: gl.getParameter(gl.VENDOR) || 'unknown',
    renderer: gl.getParameter(gl.RENDERER) || 'unknown',
    unmaskedVendor: null,
    unmaskedRenderer: null,
    isSoftware: false,
    classification: 'unknown',
  };
  try {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (ext) {
      info.unmaskedVendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
      info.unmaskedRenderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
    }
  } catch {
    // Some locked-down browsers hide debug_renderer_info
  }

  const probeStr = `${info.unmaskedRenderer || ''} ${info.renderer || ''}`.toLowerCase();
  if (probeStr.includes('swiftshader')) {
    info.isSoftware = true;
    info.classification = 'software_swiftshader';
  } else if (
    probeStr.includes('llvmpipe') ||
    probeStr.includes('softpipe') ||
    probeStr.includes('microsoft basic render') ||
    probeStr.includes('mesa offscreen') ||
    probeStr.includes('software')
  ) {
    info.isSoftware = true;
    info.classification = 'software_other';
  } else if (probeStr.trim().length > 0 && probeStr !== 'unknown') {
    info.isSoftware = false;
    info.classification = 'gpu_hardware';
  }
  return info;
}

export function createRenderer(width = 1080, height = 1920, visualConfig = {}) {
  let curW = width;
  let curH = height;

  const glCanvas = document.createElement('canvas');
  glCanvas.width = curW;
  glCanvas.height = curH;

  const renderer = new THREE.WebGLRenderer({
    canvas: glCanvas,
    antialias: true,
    preserveDrawingBuffer: true,
    alpha: false,
    powerPreference: 'high-performance',
  });
  renderer.setSize(curW, curH, false);
  renderer.setPixelRatio(1);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = visualConfig.exposure ?? 1.15;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const gl = renderer.getContext();
  const webglInfo = inspectWebGL(gl);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x8bc9ff);

  const camera = new THREE.PerspectiveCamera(38, curW / curH, 0.1, 220);
  camera.position.set(0, 2.2, 7.5);
  camera.lookAt(0, 1.6, 0);

  let renderTarget;
  try {
    renderTarget = new THREE.WebGLRenderTarget(curW, curH, {
      samples: 4,
      type: THREE.HalfFloatType,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
    });
  } catch {
    renderTarget = new THREE.WebGLRenderTarget(curW, curH, {
      samples: 0,
      type: THREE.UnsignedByteType,
    });
  }

  const composer = new EffectComposer(renderer, renderTarget);
  const renderPass = new RenderPass(scene, camera);
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(curW, curH),
    visualConfig.bloom_strength ?? 0.28,
    visualConfig.bloom_radius ?? 0.6,
    visualConfig.bloom_threshold ?? 0.95
  );
  const outputPass = new OutputPass();

  composer.addPass(renderPass);
  composer.addPass(bloomPass);
  composer.addPass(outputPass);

  function renderTo2D(outCtx, shakeOffset = { x: 0, y: 0 }) {
    composer.render();
    outCtx.save();
    outCtx.fillStyle = '#000000';
    outCtx.fillRect(0, 0, curW, curH);
    outCtx.drawImage(glCanvas, shakeOffset.x, shakeOffset.y, curW, curH);
    outCtx.restore();
  }

  function resize(newW, newH) {
    curW = newW;
    curH = newH;
    glCanvas.width = curW;
    glCanvas.height = curH;
    renderer.setSize(curW, curH, false);
    composer.setSize(curW, curH);
    bloomPass.setSize(curW, curH);
    camera.aspect = curW / curH;
    camera.updateProjectionMatrix();
  }

  return {
    renderer,
    glCanvas,
    scene,
    camera,
    composer,
    bloomPass,
    webglInfo,
    renderTo2D,
    resize,
  };
}
