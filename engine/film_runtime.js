/**
 * AutoShorts AI — Deterministic Storyboard-Driven 3D Film Runtime
 *
 * Pure function of time `t`:
 *   1. Parks all characters and props in a hidden staging group and resets poses/faces.
 *   2. Activates the current shot's set, character placements, deterministic animations,
 *      audio-envelope lip-sync (restricted strictly to the speaking co-star/character),
 *      prop attachments, 3D particle bursts, and camera move.
 *   3. Renders via EffectComposer + draws 2D overlays & word-by-word captions on #out.
 */
import * as THREE from 'three';
import {
  clamp,
  createRenderer,
  hash11,
  lerp,
  ss,
  wp,
} from './renderer.js';
import { applyCam, audit, bodyBox, fit, headBox, move, moves, pointsBox } from './camera.js';
import { createCharacterBySpec, EMOTION_FACES } from './characters.js';
import { createAllSets, createProps } from './scenes.js';
import { drawCaptions } from './captions.js';
import {
  computeShakeOffset,
  drawConfetti,
  drawFlash,
  drawHearts,
  drawImpactMark,
  drawSparks,
  drawSpeedLines,
  drawVignette,
  projToScreen,
} from './effects.js';

const outCanvas = document.getElementById('out');
const outCtx = outCanvas.getContext('2d');

let state = {
  width: 1080,
  height: 1920,
  fps: 30,
  duration: 10.0,
  engine: null,
  hiddenGroup: null,
  sets: null,
  props: null,
  cast: {},
  storyboard: null,
  syncData: null,
  captionStyle: {},
  lastAuditOvershoot: 0,
};

function initEngine(width = 1080, height = 1920, visualConfig = {}) {
  state.width = width;
  state.height = height;
  outCanvas.width = width;
  outCanvas.height = height;
  outCanvas.style.width = `${width}px`;
  outCanvas.style.height = `${height}px`;

  if (!state.engine) {
    state.engine = createRenderer(width, height, visualConfig);
    state.hiddenGroup = new THREE.Group();
    state.hiddenGroup.visible = false;
    state.engine.scene.add(state.hiddenGroup);

    state.sets = createAllSets();
    for (const setObj of Object.values(state.sets)) {
      setObj.group.visible = false;
      state.engine.scene.add(setObj.group);
    }

    state.props = createProps();
    for (const p of Object.values(state.props)) {
      state.hiddenGroup.add(p);
    }
  } else {
    state.engine.resize(width, height);
  }
}

function buildCast(characters = []) {
  // Remove previous cast
  for (const rig of Object.values(state.cast)) {
    if (rig.root.parent) rig.root.parent.remove(rig.root);
  }
  state.cast = {};

  const defaults = [
    {
      id: 'narrator',
      speaker_code: 'N',
      rig: 'human',
      name: 'Leo',
      shirt: '#3B7BFF',
      pants: '#28314A',
      skin: '#FFCCA4',
      hairColor: '#241C24',
      hairStyle: 'messy',
    },
    {
      id: 'costar',
      speaker_code: 'C',
      rig: 'bot',
      name: 'Bip',
      bodyColor: '#E8EFFB',
      accentColor: '#35D4FF',
    },
  ];

  const specs = characters.length ? characters : defaults;
  for (const spec of specs) {
    const rig = createCharacterBySpec(spec);
    rig.meta = spec;
    state.hiddenGroup.add(rig.root);
    state.cast[spec.id] = rig;
    if (spec.speaker_code) {
      state.cast[spec.speaker_code] = rig;
    }
  }
}

function resetFrameState() {
  for (const setObj of Object.values(state.sets)) {
    setObj.group.visible = false;
  }
  const seen = new Set();
  for (const rig of Object.values(state.cast)) {
    if (seen.has(rig)) continue;
    seen.add(rig);
    state.hiddenGroup.add(rig.root);
    rig.root.position.set(0, 0, 0);
    rig.root.rotation.set(0, 0, 0);
    rig.root.scale.set(1, 1, 1);
    rig.reset();
  }
  for (const prop of Object.values(state.props)) {
    state.hiddenGroup.add(prop);
    prop.position.set(0, 0, 0);
    prop.rotation.set(0, 0, 0);
    prop.scale.set(1, 1, 1);
  }
}

function sampleLoudness(t) {
  const env = state.syncData?.env || state.syncData?.ENV || [];
  if (!env.length) return 0;
  const fps = state.syncData?.fps || state.fps || 30;
  const idx = clamp(Math.floor(t * fps), 0, env.length - 1);
  return clamp(Number(env[idx]) || 0, 0, 1);
}

function getActiveSpeaker(t) {
  const lines = state.syncData?.lines || state.syncData?.LINES || [];
  for (const ln of lines) {
    const s = ln.start ?? ln[2] ?? 0;
    const e = ln.end ?? ln[3] ?? 0;
    if (t >= s - 0.03 && t <= e + 0.04) {
      return ln.speaker ?? ln[0] ?? 'N';
    }
  }
  return null;
}

function applyCharacterAction(rig, placement, u, t, lipOpen) {
  const action = placement.action || 'idle';
  const emotion = placement.emotion || 'neutral';
  const baseFace = { ...(EMOTION_FACES[emotion] || EMOTION_FACES.neutral) };
  if (lipOpen > 0.08) {
    baseFace.mo = lipOpen;
  }

  // Subtle deterministic blink every ~3.2s
  const blinkPhase = (t + hash11(placement.x || 1) * 2.0) % 3.2;
  if (blinkPhase > 3.08 && !baseFace.happy) {
    baseFace.open = 0.08;
  }
  rig.face(baseFace);

  const breath = Math.sin(t * 2.6) * 0.03;
  const pose = {
    y: breath,
    hx: Math.sin(t * 1.9) * 0.04,
    hy: placement.look_yaw ?? 0,
    aLx: 0,
    aLz: -0.14,
    eLx: -0.18,
    aRx: 0,
    aRz: 0.14,
    eRx: -0.18,
    lL: 0,
    lR: 0,
    kL: 0,
    kR: 0,
    mo: lipOpen,
  };

  if (action === 'walk' || action === 'run') {
    const freq = action === 'run' ? 11.5 : 6.8;
    const amp = action === 'run' ? 0.78 : 0.48;
    const ph = t * freq;
    pose.lL = Math.sin(ph) * amp;
    pose.lR = -Math.sin(ph) * amp;
    pose.kL = Math.max(0, -Math.cos(ph)) * amp * 0.9;
    pose.kR = Math.max(0, Math.cos(ph)) * amp * 0.9;
    pose.aLx = -Math.sin(ph) * amp * 0.85;
    pose.aRx = Math.sin(ph) * amp * 0.85;
    pose.y = Math.abs(Math.sin(ph)) * (action === 'run' ? 0.18 : 0.08);
    pose.tx = action === 'run' ? 0.16 : 0.05;
  } else if (action === 'talk' || action === 'explain') {
    const gest = Math.sin(t * 5.2);
    pose.aLz = -0.45 - Math.abs(gest) * 0.25;
    pose.aRz = 0.45 + Math.abs(gest) * 0.25;
    pose.eLx = -0.65 + gest * 0.2;
    pose.eRx = -0.65 - gest * 0.2;
    pose.hy = Math.sin(t * 2.4) * 0.12 + (placement.look_yaw ?? 0);
    pose.tx = Math.sin(t * 3.1) * 0.04;
  } else if (action === 'shock' || action === 'panic') {
    // SKILL.md rule: raise arms out to sides (aLz negative, aRz positive) so hands don't hide face!
    pose.aLz = -1.15 - Math.sin(t * 14) * 0.12;
    pose.aRz = 1.15 + Math.sin(t * 14) * 0.12;
    pose.eLx = -0.9;
    pose.eRx = -0.9;
    pose.y = Math.abs(Math.sin(t * 9)) * 0.14;
    pose.tx = -0.08;
    pose.hz = Math.sin(t * 16) * 0.08;
  } else if (action === 'celebrate' || action === 'jump') {
    const hop = Math.abs(Math.sin(t * 6.5));
    pose.y = hop * 0.42;
    pose.aLz = -2.25;
    pose.aRz = 2.25;
    pose.eLx = -0.25;
    pose.eRx = -0.25;
    pose.lL = -hop * 0.25;
    pose.lR = -hop * 0.25;
    pose.wing = 0.6;
    pose.flap = Math.sin(t * 18) * 0.45;
  } else if (action === 'point') {
    pose.aRx = -1.25;
    pose.aRz = 0.38;
    pose.eRx = -0.15;
    pose.aLz = -0.25;
    pose.ty = 0.18;
  } else if (action === 'sit') {
    pose.y = -0.45;
    pose.lL = -1.35;
    pose.lR = -1.35;
    pose.kL = 1.3;
    pose.kR = 1.3;
    pose.aLx = -0.3;
    pose.aRx = -0.3;
  } else if (action === 'defeat' || action === 'slump') {
    pose.tx = 0.26;
    pose.hx = 0.25;
    pose.aLz = -0.08;
    pose.aRz = 0.08;
    pose.y = -0.12;
  } else if (action === 'flap') {
    pose.wing = 0.45;
    pose.flap = Math.sin(t * 22) * 0.65;
    pose.y = Math.sin(t * 6) * 0.22 + 0.35;
  } else if (action === 'hold_prop') {
    // Arms slightly angled out so prop is clearly visible without blocking the face
    pose.aRx = -0.68;
    pose.aRz = 0.42;
    pose.eRx = -0.55;
  }

  rig.set(pose);
}

function findActiveShot(t) {
  const shots = state.storyboard?.shots || [];
  if (!shots.length) return null;
  for (let i = 0; i < shots.length; i++) {
    const sh = shots[i];
    if (t >= sh.start && t < sh.end) return sh;
  }
  return shots[shots.length - 1];
}

function renderFrame(t) {
  if (!state.engine || !state.storyboard) {
    throw new Error('Film project not loaded yet. Call window.loadFilmProject(...) first.');
  }

  const totalDur = state.duration;
  const { scene, camera, renderTo2D } = state.engine;
  const W = state.width;
  const H = state.height;

  // Cut to black on final ~0.18s per SKILL.md
  if (t >= totalDur - 0.16) {
    outCtx.fillStyle = '#000000';
    outCtx.fillRect(0, 0, W, H);
    return outCanvas.toDataURL('image/jpeg', state.storyboard.jpeg_quality ?? 0.93);
  }

  resetFrameState();

  const shot = findActiveShot(t);
  if (!shot) {
    outCtx.fillStyle = '#000000';
    outCtx.fillRect(0, 0, W, H);
    return outCanvas.toDataURL('image/jpeg', 0.93);
  }

  const dur = Math.max(0.1, shot.end - shot.start);
  const u = clamp(t - shot.start, 0, dur);
  const k = clamp(u / dur, 0, 1);

  // 1. Activate Set
  const setName = shot.set && state.sets[shot.set] ? shot.set : 'town_square';
  const activeSet = state.sets[setName];
  activeSet.group.visible = true;
  if (shot.studio_tint && activeSet.setTint) {
    activeSet.setTint(shot.studio_tint);
  }
  if (activeSet.update) {
    activeSet.update(t, shot.set_state || {});
  }
  scene.background = activeSet.bg;

  // 2. Place & animate characters
  const activeSpeaker = getActiveSpeaker(t);
  const envLoudness = sampleLoudness(t);
  const placedRigs = {};
  const frameSubjects = [];

  for (const pl of shot.characters || []) {
    const rig = state.cast[pl.id];
    if (!rig) continue;
    activeSet.group.add(rig.root);

    // Optional linear movement across shot
    const x = pl.x1 !== undefined ? lerp(pl.x ?? 0, pl.x1, ss(0, 1, k)) : (pl.x ?? 0);
    const y = pl.y1 !== undefined ? lerp(pl.y ?? 0, pl.y1, ss(0, 1, k)) : (pl.y ?? 0);
    const z = pl.z1 !== undefined ? lerp(pl.z ?? 0, pl.z1, ss(0, 1, k)) : (pl.z ?? 0);
    const ry = pl.ry1 !== undefined ? lerp(pl.ry ?? 0, pl.ry1, ss(0, 1, k)) : (pl.ry ?? 0);
    const sc = pl.scale ?? 1.0;

    rig.root.position.set(x, y, z);
    rig.root.rotation.set(0, ry, 0);
    rig.root.scale.setScalar(sc);

    // Lip-sync ONLY when this character is speaking on-screen dialogue
    // Narrator voice-over does not lip-sync unless explicitly flagged `lip_sync: true`
    const speakerCode = rig.meta?.speaker_code || '';
    const isSpeaking =
      activeSpeaker !== null &&
      speakerCode === activeSpeaker &&
      (speakerCode !== 'N' || Boolean(pl.lip_sync));
    const lipOpen = isSpeaking ? clamp(envLoudness * 1.15, 0, 1) : 0;

    applyCharacterAction(rig, pl, u, t, lipOpen);
    placedRigs[pl.id] = rig;

    if (!shot.focus_ids || shot.focus_ids.includes(pl.id)) {
      frameSubjects.push(rig);
    }
  }

  // 3. Place props (in set or attached to a character hand)
  const propWorldPoints = [];
  for (const pr of shot.props || []) {
    const propMesh = state.props[pr.name];
    if (!propMesh) continue;
    let parent = activeSet.group;
    if (pr.attach_to && placedRigs[pr.attach_to]) {
      const targetRig = placedRigs[pr.attach_to];
      parent = pr.hand === 'left' ? targetRig.handL || targetRig.root : targetRig.handR || targetRig.root;
    }
    parent.add(propMesh);
    const pos = pr.pos || [0, 0, 0];
    const rot = pr.rot || [0, 0, 0];
    propMesh.position.set(pos[0], pos[1], pos[2]);
    propMesh.rotation.set(rot[0], rot[1], rot[2]);
    propMesh.scale.setScalar(pr.scale ?? 1.0);
    if (pr.focus) {
      propWorldPoints.push(wp(propMesh, 0, 0, 0));
    }
  }

  scene.updateMatrixWorld(true);

  // 4. Solve mathematical camera framing (never cuts faces or enters caption band!)
  const camCfg = shot.camera || {};
  const framingMode = camCfg.framing || 'body'; // body | head | prop | wide
  let targetBox;
  if (framingMode === 'head' && frameSubjects.length > 0) {
    targetBox = headBox(frameSubjects[0], 0.14);
  } else if (framingMode === 'prop' && propWorldPoints.length > 0) {
    targetBox = pointsBox(propWorldPoints, 0.45);
  } else if (frameSubjects.length > 0) {
    targetBox = bodyBox(frameSubjects, 0.14);
    if (propWorldPoints.length > 0) {
      for (const p of propWorldPoints) targetBox.expandByPoint(p);
    }
  } else {
    targetBox = new THREE.Box3(new THREE.Vector3(-1.5, 0, -1), new THREE.Vector3(1.5, 3.2, 1));
  }

  const aspect = W / H;
  const moveType = camCfg.move || 'pushIn';
  const camOpts = {
    aspect,
    time: t,
    minCamY: state.storyboard.visual?.ground_min_cam_y ?? 0.35,
    yaw0: camCfg.yaw0,
    yaw1: camCfg.yaw1,
    yaw: camCfg.yaw,
    pitch0: camCfg.pitch0,
    pitch1: camCfg.pitch1,
    pitch: camCfg.pitch,
    zoom0: camCfg.zoom0,
    zoom1: camCfg.zoom1,
    zoom: camCfg.zoom,
    fov: camCfg.fov,
    shake: camCfg.shake,
  };

  let camState;
  if (camCfg.from && camCfg.to) {
    camState = move(targetBox, k, camCfg.from, camCfg.to, camOpts);
  } else if (typeof moves[moveType] === 'function') {
    camState = moves[moveType](targetBox, k, camOpts);
  } else {
    camState = fit(targetBox, camOpts);
  }

  applyCam(camera, camState);
  state.lastAuditOvershoot = audit(targetBox, camera);

  // 5. Render 3D scene onto 2D canvas with optional shake
  const fx = shot.effects || {};
  const shakeOffset = computeShakeOffset(t, fx.screen_shake ?? 0, W);
  renderTo2D(outCtx, shakeOffset);

  // 6. Deterministic 2D overlays (above 3D, below captions)
  drawVignette(outCtx, W, H, fx.vignette ?? 0.22);

  if (fx.speed_lines) {
    drawSpeedLines(outCtx, W, H, t, fx.speed_lines === true ? 0.65 : fx.speed_lines);
  }
  if (fx.confetti) {
    drawConfetti(outCtx, W, H, t, 55);
  }
  if (fx.sparks) {
    drawSparks(outCtx, W, H, t, u);
  }
  if (fx.hearts) {
    drawHearts(outCtx, W, H, t, 16);
  }
  if (fx.impact_text) {
    let screenPt = { x: W * 0.5, y: H * 0.24 };
    if (frameSubjects.length > 0) {
      const topWorld = wp(frameSubjects[0].headGroup || frameSubjects[0].root, 0, 1.35, 0);
      const proj = projToScreen(topWorld, camera, W, H);
      if (proj.visible) screenPt = proj;
    }
    drawImpactMark(
      outCtx,
      W,
      H,
      screenPt,
      fx.impact_text,
      u,
      fx.impact_size ?? 78,
      fx.impact_color ?? '#FFE44D'
    );
  }
  if (fx.flash && u < 0.22) {
    drawFlash(outCtx, W, H, (1 - u / 0.22) * 0.72, fx.flash_color || '#FFFFFF');
  }

  // 7. Dynamic Word-by-Word Captions (always crisp & strictly in lower safe band)
  const chunks = state.syncData?.chunks || state.syncData?.CHUNKS || [];
  if (state.storyboard.captions_enabled !== false) {
    drawCaptions(outCtx, W, H, chunks, t, state.captionStyle);
  }

  // Brief fade-in at t < 0.15
  if (t < 0.15) {
    drawFlash(outCtx, W, H, 1 - t / 0.15, '#000000');
  }

  return outCanvas.toDataURL('image/jpeg', state.storyboard.jpeg_quality ?? 0.93);
}

async function waitForFonts() {
  try {
    await Promise.race([
      Promise.all([
        document.fonts.load('900 92px Inter'),
        document.fonts.ready,
      ]),
      new Promise((resolve) => setTimeout(resolve, 1500)),
    ]);
  } catch {
    // Offline fallback fonts remain immediately usable
  }
}

window.loadFilmProject = async function loadFilmProject(storyboardUrl, syncDataUrl = null) {
  const sbResp = await fetch(storyboardUrl);
  if (!sbResp.ok) throw new Error(`Falha ao carregar storyboard: ${sbResp.status}`);
  const storyboard = await sbResp.json();

  let syncData = { chunks: [], env: [], lines: [], fps: storyboard.fps || 30 };
  if (syncDataUrl) {
    const syncResp = await fetch(syncDataUrl);
    if (syncResp.ok) {
      syncData = await syncResp.json();
    }
  }

  const width = storyboard.width || 1080;
  const height = storyboard.height || 1920;
  initEngine(width, height, storyboard.visual || {});
  buildCast(storyboard.characters || []);

  state.storyboard = storyboard;
  state.syncData = syncData;
  state.fps = storyboard.fps || 30;
  state.duration = storyboard.duration_sec || syncData.duration_sec || 10.0;
  state.captionStyle = storyboard.caption_style || {};

  await waitForFonts();
  window.ready = true;
  return {
    ready: true,
    duration: state.duration,
    shots: (storyboard.shots || []).length,
    webgl: state.engine.webglInfo,
  };
};

window.probeWebGL = function probeWebGL() {
  initEngine(360, 640, {});
  return state.engine.webglInfo;
};

window.renderFrame = renderFrame;
window.getAuditOvershoot = () => state.lastAuditOvershoot;
window.getWebGLInfo = () => (state.engine ? state.engine.webglInfo : window.probeWebGL());
window.runtimeLoaded = true;
