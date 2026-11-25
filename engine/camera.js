/**
 * AutoShorts AI — Mathematical Framing & Cinematic Camera System
 *
 * Guarantees:
 * - Subjects stay strictly inside the safe vertical rectangle (6% top/side margin,
 *   above the 66.5% caption band so subtitles NEVER overlap faces).
 * - Camera stays above ground (y >= minCamY, default 0.35) so ground planes never disappear.
 * - Deterministic cinematic moves: orbit, craneUp, craneDown, pushIn, pullOut,
 *   arc, vertigo, dolly, pan, track, lowHero, highDefeat, topDown, revealBehind, dutchPanic, hold.
 */
import * as THREE from 'three';
import { clamp, lerp, ss } from './renderer.js';

export const DEFAULT_SAFE_RECT = {
  minX: -0.88,
  maxX: 0.88,
  minY: -0.33, // 66.5% from top = 1 - 2*0.665 = -0.33 NDC (above caption band)
  maxY: 0.88,  // 6% from top
};

function collectVisibleMeshes(obj, out) {
  if (!obj || !obj.visible) return;
  if (obj.userData && (obj.userData.isOutline || obj.userData.ignoreBounds)) return;
  if (obj.isMesh && obj.geometry) {
    out.push(obj);
  }
  if (obj.children) {
    for (const child of obj.children) {
      collectVisibleMeshes(child, out);
    }
  }
}

function getRoot(obj) {
  let r = obj;
  while (r && r.parent) r = r.parent;
  return r;
}

export function bodyBox(rigs, pad = 0.08) {
  const list = Array.isArray(rigs) ? rigs : [rigs];
  const box = new THREE.Box3();
  const temp = new THREE.Box3();
  for (const item of list) {
    if (!item) continue;
    const obj = item.root || item;
    const root = getRoot(obj);
    if (root) root.updateMatrixWorld(true);
    const meshes = [];
    collectVisibleMeshes(obj, meshes);
    for (const m of meshes) {
      temp.setFromObject(m);
      if (!temp.isEmpty()) box.union(temp);
    }
  }
  if (box.isEmpty()) {
    box.setFromCenterAndSize(new THREE.Vector3(0, 1.6, 0), new THREE.Vector3(1.4, 3.2, 1.2));
  } else if (pad > 0) {
    box.expandByScalar(pad);
  }
  return box;
}

export function headBox(rig, pad = 0.08) {
  if (!rig) {
    return new THREE.Box3().setFromCenterAndSize(
      new THREE.Vector3(0, 2.7, 0),
      new THREE.Vector3(1.3, 1.2, 1.2)
    );
  }
  const target = rig.headGroup || rig.head || rig.root || rig;
  return bodyBox([target], pad);
}

export function pointsBox(items, pad = 0.25) {
  const box = new THREE.Box3();
  for (const it of items) {
    if (!it) continue;
    if (it.isVector3) {
      box.expandByPoint(it);
    } else if (it.isBox3) {
      box.union(it);
    } else if (it.root || it.isObject3D) {
      box.union(bodyBox([it], 0));
    }
  }
  if (box.isEmpty()) {
    box.setFromCenterAndSize(new THREE.Vector3(0, 1.5, 0), new THREE.Vector3(2, 2, 2));
  } else if (pad > 0) {
    box.expandByScalar(pad);
  }
  return box;
}

function boxCorners(box) {
  const { min, max } = box;
  return [
    new THREE.Vector3(min.x, min.y, min.z),
    new THREE.Vector3(min.x, min.y, max.z),
    new THREE.Vector3(min.x, max.y, min.z),
    new THREE.Vector3(min.x, max.y, max.z),
    new THREE.Vector3(max.x, min.y, min.z),
    new THREE.Vector3(max.x, min.y, max.z),
    new THREE.Vector3(max.x, max.y, min.z),
    new THREE.Vector3(max.x, max.y, max.z),
  ];
}

function buildCameraBasis(yaw, pitch, roll = 0) {
  // Vector FROM target TO camera:
  // yaw=0 => +Z (front), yaw=PI => -Z (behind), yaw=+PI/2 => +X (right side)
  // pitch>0 => camera higher (high angle), pitch<0 => camera lower (low angle)
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const sy = Math.sin(yaw);
  const cy = Math.cos(yaw);

  const toCam = new THREE.Vector3(sy * cp, sp, cy * cp).normalize();
  const forward = toCam.clone().negate();

  let worldUp = new THREE.Vector3(0, 1, 0);
  if (Math.abs(forward.dot(worldUp)) > 0.985) {
    // Near top-down: keep orientation stable based on yaw
    worldUp = new THREE.Vector3(-sy, 0, -cy).normalize();
  }

  let right = new THREE.Vector3().crossVectors(forward, worldUp).normalize();
  let up = new THREE.Vector3().crossVectors(right, forward).normalize();

  if (Math.abs(roll) > 1e-5) {
    const q = new THREE.Quaternion().setFromAxisAngle(forward, roll);
    right.applyQuaternion(q).normalize();
    up.applyQuaternion(q).normalize();
  }
  return { toCam, forward, right, up };
}

function evaluateFraming(corners, center, basis, dist, fovDeg, aspect, safeRect) {
  const tanHalfY = Math.tan(THREE.MathUtils.degToRad(fovDeg * 0.5));
  const tanHalfX = tanHalfY * aspect;
  const safeCenterY = (safeRect.minY + safeRect.maxY) * 0.5;

  // Shift camera + lookAt along -up so center projects to safeCenterY without tilting
  const yOffset = safeCenterY * dist * tanHalfY;
  const camPos = center
    .clone()
    .addScaledVector(basis.toCam, dist)
    .addScaledVector(basis.up, -yOffset);
  const lookAt = center.clone().addScaledVector(basis.up, -yOffset);

  let worstOvershoot = -Infinity;
  let allInFront = true;

  for (const p of corners) {
    const rel = p.clone().sub(camPos);
    const z = rel.dot(basis.forward);
    if (z <= 0.15) {
      allInFront = false;
      worstOvershoot = Math.max(worstOvershoot, 10.0);
      continue;
    }
    const xNdc = rel.dot(basis.right) / (z * tanHalfX);
    const yNdc = rel.dot(basis.up) / (z * tanHalfY);

    const overLeft = safeRect.minX - xNdc;
    const overRight = xNdc - safeRect.maxX;
    const overBottom = safeRect.minY - yNdc;
    const overTop = yNdc - safeRect.maxY;
    worstOvershoot = Math.max(worstOvershoot, overLeft, overRight, overBottom, overTop);
  }

  return {
    fits: allInFront && worstOvershoot <= 0,
    worstOvershoot,
    camPos,
    lookAt,
  };
}

export function fit(box, params = {}) {
  const yaw = params.yaw ?? 0;
  let pitch = clamp(params.pitch ?? 0.08, -1.25, 1.48);
  const zoom = Math.max(1.0, params.zoom ?? 1.15);
  const fov = clamp(params.fov ?? 38, 22, 60);
  const roll = params.roll ?? 0;
  const aspect = params.aspect ?? 1080 / 1920;
  const minCamY = params.minCamY ?? 0.35;
  const safeRect = params.safeRect ?? DEFAULT_SAFE_RECT;
  const panOffset = params.panOffset || null;

  const center = box.getCenter(new THREE.Vector3());
  if (panOffset) {
    center.add(panOffset);
  }
  const corners = boxCorners(box);

  let basis = buildCameraBasis(yaw, pitch, roll);
  let chosenDist = 8.0;
  let evalResult = null;

  // Iterate pitch upward if camera would dip below minCamY (protects against seeing under ground)
  for (let groundIter = 0; groundIter < 18; groundIter++) {
    basis = buildCameraBasis(yaw, pitch, roll);

    let lo = 0.6;
    let hi = 90.0;
    for (let i = 0; i < 26; i++) {
      const mid = (lo + hi) * 0.5;
      const ev = evaluateFraming(corners, center, basis, mid, fov, aspect, safeRect);
      if (ev.fits) {
        hi = mid;
      } else {
        lo = mid;
      }
    }
    chosenDist = hi * zoom;
    evalResult = evaluateFraming(corners, center, basis, chosenDist, fov, aspect, safeRect);

    if (evalResult.camPos.y >= minCamY || pitch >= 1.42) {
      break;
    }
    pitch = Math.min(1.42, pitch + 0.09);
  }

  // Final safety clamp on camPos.y
  if (evalResult.camPos.y < minCamY) {
    const deltaY = minCamY - evalResult.camPos.y;
    evalResult.camPos.y += deltaY;
    evalResult.lookAt.y += deltaY * 0.35;
  }

  return {
    pos: evalResult.camPos,
    lookAt: evalResult.lookAt,
    up: basis.up.clone(),
    fov,
    roll,
    yaw,
    pitch,
    dist: chosenDist,
  };
}

function shortestYawLerp(a, b, k) {
  let diff = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
  return a + diff * k;
}

function applyEase(k, ease = 'smoothstep') {
  const t = clamp(k, 0, 1);
  if (ease === 'linear') return t;
  if (ease === 'easeOut') return 1 - Math.pow(1 - t, 3);
  if (ease === 'easeIn') return t * t * t;
  if (ease === 'easeInOut') return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  return ss(0, 1, t);
}

export function move(box, k, from = {}, to = {}, opts = {}) {
  const e = applyEase(k, opts.ease || 'smoothstep');
  const t = opts.time ?? k;

  const yaw0 = from.yaw ?? 0;
  const yaw1 = to.yaw ?? yaw0;
  const yaw = opts.spin ? lerp(yaw0, yaw1, e) : shortestYawLerp(yaw0, yaw1, e);
  const pitch = lerp(from.pitch ?? 0.08, to.pitch ?? from.pitch ?? 0.08, e);
  const zoom = lerp(from.zoom ?? 1.18, to.zoom ?? from.zoom ?? 1.18, e);
  const fov = lerp(from.fov ?? 38, to.fov ?? from.fov ?? 38, e);
  const roll = lerp(from.roll ?? 0, to.roll ?? from.roll ?? 0, e);

  // Optional deterministic handheld micro-drift
  const drift = opts.shake ?? 0;
  const driftYaw = drift > 0 ? Math.sin(t * 2.7 + 1.3) * 0.015 * drift : 0;
  const driftPitch = drift > 0 ? Math.cos(t * 2.1 + 0.7) * 0.012 * drift : 0;
  const driftRoll = drift > 0 ? Math.sin(t * 3.3 + 2.1) * 0.014 * drift : 0;

  let panOffset = null;
  if (from.pan || to.pan) {
    const p0 = from.pan || [0, 0, 0];
    const p1 = to.pan || p0;
    panOffset = new THREE.Vector3(
      lerp(p0[0], p1[0], e),
      lerp(p0[1], p1[1], e),
      lerp(p0[2], p1[2], e)
    );
  }

  return fit(box, {
    yaw: yaw + driftYaw,
    pitch: pitch + driftPitch,
    zoom,
    fov,
    roll: roll + driftRoll,
    aspect: opts.aspect ?? 1080 / 1920,
    minCamY: opts.minCamY ?? 0.35,
    safeRect: opts.safeRect ?? DEFAULT_SAFE_RECT,
    panOffset,
  });
}

export const moves = {
  orbit: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.55, pitch: opts.pitch0 ?? 0.14, zoom: opts.zoom ?? 1.2, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? 0.55, pitch: opts.pitch1 ?? 0.14, zoom: opts.zoom ?? 1.2, fov: opts.fov ?? 38 },
      opts
    ),
  craneUp: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.25, pitch: opts.pitch0 ?? -0.15, zoom: opts.zoom0 ?? 1.15, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? 0.18, pitch: opts.pitch1 ?? 0.45, zoom: opts.zoom1 ?? 1.32, fov: opts.fov ?? 38 },
      opts
    ),
  craneDown: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? 0.28, pitch: opts.pitch0 ?? 0.52, zoom: opts.zoom0 ?? 1.35, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? -0.12, pitch: opts.pitch1 ?? 0.04, zoom: opts.zoom1 ?? 1.12, fov: opts.fov ?? 36 },
      opts
    ),
  pushIn: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? 0.12, pitch: opts.pitch ?? 0.08, zoom: opts.zoom0 ?? 1.48, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? -0.05, pitch: opts.pitch ?? 0.05, zoom: opts.zoom1 ?? 1.04, fov: opts.fov ?? 34 },
      opts
    ),
  pullOut: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.1, pitch: opts.pitch ?? 0.06, zoom: opts.zoom0 ?? 1.05, fov: opts.fov ?? 35 },
      { yaw: opts.yaw1 ?? 0.25, pitch: opts.pitch1 ?? 0.24, zoom: opts.zoom1 ?? 1.55, fov: opts.fov1 ?? 44 },
      opts
    ),
  arc: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.8, pitch: opts.pitch0 ?? 0.05, zoom: opts.zoom0 ?? 1.22, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? 0.75, pitch: opts.pitch1 ?? 0.22, zoom: opts.zoom1 ?? 1.14, fov: opts.fov ?? 38 },
      opts
    ),
  vertigo: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw ?? 0.05, pitch: opts.pitch ?? 0.02, zoom: 1.08, fov: 26 },
      { yaw: opts.yaw ?? 0.05, pitch: opts.pitch ?? 0.02, zoom: 1.12, fov: 56 },
      opts
    ),
  dolly: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.35, pitch: opts.pitch ?? 0.1, zoom: opts.zoom0 ?? 1.28, fov: opts.fov ?? 36 },
      { yaw: opts.yaw1 ?? 0.35, pitch: opts.pitch ?? 0.1, zoom: opts.zoom1 ?? 1.18, fov: opts.fov ?? 36 },
      opts
    ),
  pan: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw ?? 0.0, pitch: opts.pitch ?? 0.1, zoom: opts.zoom ?? 1.22, pan: [-0.45, 0, 0] },
      { yaw: opts.yaw ?? 0.0, pitch: opts.pitch ?? 0.1, zoom: opts.zoom ?? 1.22, pan: [0.45, 0, 0] },
      opts
    ),
  track: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.45, pitch: opts.pitch ?? 0.12, zoom: opts.zoom ?? 1.22, fov: opts.fov ?? 40 },
      { yaw: opts.yaw1 ?? -0.25, pitch: opts.pitch ?? 0.14, zoom: opts.zoom ?? 1.18, fov: opts.fov ?? 40 },
      { ...opts, shake: opts.shake ?? 0.35 }
    ),
  lowHero: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.35, pitch: -0.24, zoom: opts.zoom0 ?? 1.18, fov: opts.fov ?? 42 },
      { yaw: opts.yaw1 ?? 0.25, pitch: -0.18, zoom: opts.zoom1 ?? 1.08, fov: opts.fov ?? 42 },
      opts
    ),
  highDefeat: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? 0.22, pitch: 0.62, zoom: opts.zoom0 ?? 1.24, fov: opts.fov ?? 38 },
      { yaw: opts.yaw1 ?? -0.18, pitch: 0.72, zoom: opts.zoom1 ?? 1.38, fov: opts.fov ?? 40 },
      opts
    ),
  topDown: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? 0.0, pitch: 1.28, zoom: opts.zoom0 ?? 1.25, fov: 42 },
      { yaw: opts.yaw1 ?? 0.35, pitch: 1.36, zoom: opts.zoom1 ?? 1.4, fov: 44 },
      opts
    ),
  revealBehind: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: Math.PI - 0.35, pitch: 0.15, zoom: 1.25, fov: 42 },
      { yaw: Math.PI + 0.35, pitch: 0.22, zoom: 1.45, fov: 48 },
      opts
    ),
  dutchPanic: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw0 ?? -0.18, pitch: -0.08, zoom: 1.12, fov: 44, roll: -0.16 },
      { yaw: opts.yaw1 ?? 0.22, pitch: 0.05, zoom: 1.04, fov: 50, roll: 0.16 },
      { ...opts, shake: opts.shake ?? 0.9 }
    ),
  hold: (box, k, opts = {}) =>
    move(
      box,
      k,
      { yaw: opts.yaw ?? 0.15, pitch: opts.pitch ?? 0.08, zoom: opts.zoom ?? 1.16, fov: opts.fov ?? 36 },
      { yaw: (opts.yaw ?? 0.15) + 0.04, pitch: opts.pitch ?? 0.08, zoom: (opts.zoom ?? 1.16) - 0.03, fov: opts.fov ?? 36 },
      { ...opts, shake: opts.shake ?? 0.4 }
    ),
};

export function blend(stateA, stateB, k) {
  const t = ss(0, 1, k);
  return {
    pos: stateA.pos.clone().lerp(stateB.pos, t),
    lookAt: stateA.lookAt.clone().lerp(stateB.lookAt, t),
    up: stateA.up.clone().lerp(stateB.up, t).normalize(),
    fov: lerp(stateA.fov, stateB.fov, t),
    roll: lerp(stateA.roll || 0, stateB.roll || 0, t),
  };
}

export function applyCam(camera, state) {
  camera.fov = state.fov;
  camera.position.copy(state.pos);
  camera.up.copy(state.up);
  camera.lookAt(state.lookAt);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
}

export function audit(box, camera, safeRect = DEFAULT_SAFE_RECT) {
  camera.updateMatrixWorld(true);
  const corners = boxCorners(box);
  let maxOvershoot = 0;
  for (const c of corners) {
    const projected = c.clone().project(camera);
    const overLeft = safeRect.minX - projected.x;
    const overRight = projected.x - safeRect.maxX;
    const overBottom = safeRect.minY - projected.y;
    const overTop = projected.y - safeRect.maxY;
    const behind = projected.z > 1 || projected.z < -1 ? 1.0 : 0;
    maxOvershoot = Math.max(maxOvershoot, overLeft, overRight, overBottom, overTop, behind);
  }
  return maxOvershoot;
}
