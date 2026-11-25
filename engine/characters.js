/**
 * AutoShorts AI — Original Stylized Toon 3D Character Rigs
 *
 * Zero copyrighted characters. All rigs are procedural stylized toon models
 * following the SKILL.md specification:
 *  - createHumanRig: ~3.3 units tall, 512px canvas face texture, 9 mouth states,
 *    lip-sync `mo`, 4 hair styles (messy, long, bun, slick), full limb pose API.
 *  - createBotRig: Original comic helper robot with glowing visor face & lip-sync bar.
 *  - createPigeonRig: Original deadpan city pigeon with sliding eyelids & hinged beak.
 *  - createPhantomRig: Original comedic robed time-spirit with eyes-only emissive map.
 *  - createGiantMechRig: Giant articulated colossus with break-apart explosion parameter.
 *  - createRockBuddyRig: Expressive deadpan pet rock co-star with hopping aura.
 */
import * as THREE from 'three';
import { clamp, makeOutlined, roundedBoxGeo, toonMat } from './renderer.js';

// ---------- Dynamic 512px Human Face Canvas ----------

function createHumanFaceCanvas(skinHex = '#FFCFA8') {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;

  function draw(p = {}) {
    const open = clamp(p.open ?? 1.0, 0.05, 1.35);
    const pupil = clamp(p.pupil ?? 1.0, 0.45, 1.45);
    const lx = clamp(p.lx ?? 0, -1, 1);
    const ly = clamp(p.ly ?? 0, -1, 1);
    const brow = clamp(p.brow ?? 0, -1, 1); // negative = angry/furrowed, positive = worried
    const raise = clamp(p.raise ?? 0, -1, 1);
    const mouth = p.mouth || 'smile';
    const mo = clamp(p.mo ?? 0, 0, 1);
    const blush = clamp(p.blush ?? 0, 0, 1);
    const sweat = clamp(p.sweat ?? 0, 0, 1);
    const drip = clamp(p.drip ?? 0, 0, 1);
    const happy = Boolean(p.happy);
    const tear = clamp(p.tear ?? 0, 0, 1);
    const pale = clamp(p.pale ?? 0, 0, 1);

    // Base skin fill (+ optional pale dread tint)
    ctx.fillStyle = skinHex;
    ctx.fillRect(0, 0, 512, 512);
    if (pale > 0.01) {
      ctx.fillStyle = `rgba(210, 224, 248, ${pale * 0.6})`;
      ctx.fillRect(0, 0, 512, 512);
      const grad = ctx.createLinearGradient(0, 0, 0, 240);
      grad.addColorStop(0, `rgba(40, 55, 110, ${pale * 0.55})`);
      grad.addColorStop(1, 'rgba(40, 55, 110, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 512, 240);
    }

    // Blush cheeks
    if (blush > 0.02) {
      ctx.fillStyle = `rgba(255, 105, 130, ${blush * 0.42})`;
      ctx.beginPath();
      ctx.ellipse(130, 295, 42, 22, 0, 0, Math.PI * 2);
      ctx.ellipse(382, 295, 42, 22, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // Eyes
    const eyeY = 225;
    const eyeXs = [174, 338];
    for (let i = 0; i < 2; i++) {
      const ex = eyeXs[i];
      if (happy) {
        ctx.strokeStyle = '#141620';
        ctx.lineWidth = 14;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.arc(ex, eyeY + 12, 34, Math.PI * 1.12, Math.PI * 1.88);
        ctx.stroke();
      } else {
        const rx = 38;
        const ry = Math.max(6, 44 * open);
        // Sclera
        ctx.fillStyle = '#FFFFFF';
        ctx.strokeStyle = '#141620';
        ctx.lineWidth = 10;
        ctx.beginPath();
        ctx.ellipse(ex, eyeY, rx, ry, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Pupil clipped inside eye
        ctx.save();
        ctx.beginPath();
        ctx.ellipse(ex, eyeY, rx - 4, Math.max(3, ry - 4), 0, 0, Math.PI * 2);
        ctx.clip();
        const px = ex + lx * 14;
        const py = eyeY - ly * 14;
        const pr = 19 * pupil;
        ctx.fillStyle = '#141620';
        ctx.beginPath();
        ctx.arc(px, py, pr, 0, Math.PI * 2);
        ctx.fill();
        // Specular catchlight
        ctx.fillStyle = '#FFFFFF';
        ctx.beginPath();
        ctx.arc(px - pr * 0.35, py - pr * 0.35, Math.max(4, pr * 0.32), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      // Eyebrow
      const side = i === 0 ? -1 : 1;
      const by = eyeY - 64 - raise * 20;
      const tilt = brow * 18 * side;
      ctx.strokeStyle = '#1B1A24';
      ctx.lineWidth = 14;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(ex - 36, by - tilt);
      ctx.lineTo(ex + 36, by + tilt);
      ctx.stroke();

      // Tears
      if (tear > 0.05) {
        ctx.fillStyle = `rgba(110, 215, 255, ${tear * 0.9})`;
        ctx.beginPath();
        ctx.ellipse(ex + side * 22, eyeY + 46 + tear * 18, 9, 16, 0, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Small stylized nose mark
    ctx.strokeStyle = 'rgba(135, 78, 52, 0.45)';
    ctx.lineWidth = 7;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(256, 268);
    ctx.lineTo(250, 290);
    ctx.lineTo(262, 294);
    ctx.stroke();

    // Mouth (9 styles + dynamic lip-sync `mo`)
    const my = 352;
    ctx.strokeStyle = '#141620';
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const effectiveMouth = mo > 0.14 ? 'talk' : mouth;
    if (effectiveMouth === 'talk') {
      const h = 14 + mo * 58;
      const w = 44 + mo * 22;
      ctx.fillStyle = '#7A1D2E';
      ctx.beginPath();
      ctx.ellipse(256, my + 8, w, h, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      // Teeth strip
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(256 - w * 0.58, my + 8 - h * 0.72, w * 1.16, Math.min(16, h * 0.4));
    } else if (effectiveMouth === 'bigsmile') {
      ctx.fillStyle = '#8F2134';
      ctx.beginPath();
      ctx.arc(256, my - 10, 62, 0.08 * Math.PI, 0.92 * Math.PI);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(204, my - 5, 104, 18);
    } else if (effectiveMouth === 'open') {
      ctx.fillStyle = '#7A1D2E';
      ctx.beginPath();
      ctx.ellipse(256, my + 12, 46, 52, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else if (effectiveMouth === 'o') {
      ctx.fillStyle = '#7A1D2E';
      ctx.beginPath();
      ctx.ellipse(256, my + 10, 28, 36, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    } else if (effectiveMouth === 'flat') {
      ctx.beginPath();
      ctx.moveTo(206, my + 8);
      ctx.lineTo(306, my + 8);
      ctx.stroke();
    } else if (effectiveMouth === 'frown') {
      ctx.beginPath();
      ctx.arc(256, my + 52, 48, Math.PI * 1.18, Math.PI * 1.82);
      ctx.stroke();
    } else if (effectiveMouth === 'grin') {
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.roundRect(198, my - 8, 116, 42, 16);
      ctx.fill();
      ctx.stroke();
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.moveTo(204, my + 13);
      ctx.lineTo(308, my + 13);
      ctx.stroke();
    } else if (effectiveMouth === 'wavy') {
      ctx.beginPath();
      ctx.moveTo(198, my + 10);
      ctx.bezierCurveTo(218, my - 14, 238, my + 34, 256, my + 10);
      ctx.bezierCurveTo(274, my - 14, 294, my + 34, 314, my + 10);
      ctx.stroke();
    } else {
      // default 'smile'
      ctx.beginPath();
      ctx.arc(256, my - 22, 48, 0.18 * Math.PI, 0.82 * Math.PI);
      ctx.stroke();
    }

    // Anime sweat drop
    if (sweat > 0.05) {
      const sy = 104 + drip * 58;
      ctx.fillStyle = '#6EE2FF';
      ctx.strokeStyle = '#141620';
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.moveTo(418, sy - 30);
      ctx.bezierCurveTo(444, sy + 8, 438, sy + 36, 418, sy + 36);
      ctx.bezierCurveTo(398, sy + 36, 392, sy + 8, 418, sy - 30);
      ctx.fill();
      ctx.stroke();
    }

    tex.needsUpdate = true;
  }

  draw({});
  return { canvas, tex, draw };
}

// ---------- 1. Human Rig (~3.3 units tall) ----------

export function createHumanRig(opts = {}) {
  const skinColor = opts.skin || '#FFCFA8';
  const shirtColor = opts.shirt || '#3B7BFF';
  const pantsColor = opts.pants || '#2A314A';
  const shoeColor = opts.shoe || '#E9ECF5';
  const hairColor = opts.hairColor || '#261F29';
  const hairStyle = opts.hairStyle || 'messy'; // messy | long | bun | slick

  const skinMat = toonMat(skinColor);
  const shirtMat = toonMat(shirtColor);
  const shirtDarkMat = toonMat(new THREE.Color(shirtColor).multiplyScalar(0.8));
  const pantsMat = toonMat(pantsColor);
  const shoeMat = toonMat(shoeColor);
  const soleMat = toonMat('#1A1D29');
  const hairMat = toonMat(hairColor);
  const stringMat = toonMat('#F0F2FA');

  const root = new THREE.Group();
  root.name = opts.name || 'human_rig';

  const hips = new THREE.Group();
  hips.position.y = 1.2;
  root.add(hips);

  // Legs
  function buildLeg(side) {
    const legPivot = new THREE.Group();
    legPivot.position.set(side * 0.24, 0, 0);
    hips.add(legPivot);

    const thigh = makeOutlined(new THREE.CapsuleGeometry(0.155, 0.36, 6, 12), pantsMat);
    thigh.position.y = -0.28;
    legPivot.add(thigh);

    const kneePivot = new THREE.Group();
    kneePivot.position.y = -0.58;
    legPivot.add(kneePivot);

    const shin = makeOutlined(new THREE.CapsuleGeometry(0.14, 0.36, 6, 12), pantsMat);
    shin.position.y = -0.26;
    kneePivot.add(shin);

    const shoe = makeOutlined(roundedBoxGeo(0.28, 0.18, 0.44, 0.06, 2), shoeMat);
    shoe.position.set(0, -0.53, 0.07);
    kneePivot.add(shoe);

    const sole = makeOutlined(roundedBoxGeo(0.3, 0.07, 0.46, 0.02, 1), soleMat, { outline: false });
    sole.position.set(0, -0.61, 0.07);
    kneePivot.add(sole);

    return { legPivot, kneePivot };
  }

  const legL = buildLeg(-1);
  const legR = buildLeg(1);

  // Torso
  const torsoPivot = new THREE.Group();
  hips.add(torsoPivot);

  const torsoMesh = makeOutlined(roundedBoxGeo(0.92, 1.06, 0.56, 0.16, 3), shirtMat);
  torsoMesh.position.y = 0.56;
  torsoPivot.add(torsoMesh);

  // Hoodie kangaroo pocket
  const pocket = makeOutlined(roundedBoxGeo(0.56, 0.28, 0.12, 0.05, 2), shirtDarkMat, {
    outlineThickness: 0.018,
  });
  pocket.position.set(0, 0.34, 0.26);
  torsoPivot.add(pocket);

  // Hoodie collar/hood on back
  const hood = makeOutlined(roundedBoxGeo(0.68, 0.32, 0.36, 0.12, 2), shirtDarkMat, {
    outlineThickness: 0.02,
  });
  hood.position.set(0, 1.02, -0.18);
  torsoPivot.add(hood);

  // Drawstrings
  for (const sx of [-0.12, 0.12]) {
    const str = makeOutlined(new THREE.CylinderGeometry(0.018, 0.018, 0.3, 6), stringMat, {
      outline: false,
    });
    str.position.set(sx, 0.84, 0.29);
    torsoPivot.add(str);
  }

  // Arms
  function buildArm(side) {
    const shoulder = new THREE.Group();
    shoulder.position.set(side * 0.58, 0.96, 0);
    torsoPivot.add(shoulder);

    const upper = makeOutlined(new THREE.CapsuleGeometry(0.135, 0.3, 6, 12), shirtMat);
    upper.position.y = -0.22;
    shoulder.add(upper);

    const elbow = new THREE.Group();
    elbow.position.y = -0.46;
    shoulder.add(elbow);

    const forearm = makeOutlined(new THREE.CapsuleGeometry(0.125, 0.28, 6, 12), shirtMat);
    forearm.position.y = -0.2;
    elbow.add(forearm);

    const cuff = makeOutlined(new THREE.CylinderGeometry(0.13, 0.13, 0.07, 10), shirtDarkMat, {
      outline: false,
    });
    cuff.position.y = -0.36;
    elbow.add(cuff);

    const hand = makeOutlined(roundedBoxGeo(0.22, 0.22, 0.2, 0.07, 2), skinMat, {
      outlineThickness: 0.02,
    });
    hand.position.y = -0.48;
    elbow.add(hand);

    const handMarker = new THREE.Group();
    handMarker.position.set(0, -0.52, 0.12);
    elbow.add(handMarker);

    return { shoulder, elbow, hand, handMarker };
  }

  const armL = buildArm(-1);
  const armR = buildArm(1);

  // Head (rounded box 1.24 x 1.1 x 1.1 with +Z canvas face texture)
  const headGroup = new THREE.Group();
  headGroup.position.set(0, 1.16, 0);
  torsoPivot.add(headGroup);

  const neck = makeOutlined(new THREE.CylinderGeometry(0.16, 0.18, 0.18, 10), skinMat, {
    outline: false,
  });
  neck.position.y = 0.04;
  headGroup.add(neck);

  const faceCanvas = createHumanFaceCanvas(skinColor);
  const faceMat = toonMat('#FFFFFF', { map: faceCanvas.tex });
  const headMaterials = [skinMat, skinMat, skinMat, skinMat, faceMat, skinMat];
  const headGeo = roundedBoxGeo(1.24, 1.1, 1.1, 0.3, 4);
  const headMesh = makeOutlined(headGeo, headMaterials, { outlineThickness: 0.03 });
  headMesh.position.y = 0.62;
  headGroup.add(headMesh);

  // Ears
  for (const sx of [-0.64, 0.64]) {
    const ear = makeOutlined(new THREE.SphereGeometry(0.14, 10, 10), skinMat, {
      outlineThickness: 0.02,
    });
    ear.scale.set(0.65, 1.0, 0.75);
    ear.position.set(sx, 0.6, -0.02);
    headGroup.add(ear);
  }

  // Hair styles (messy, long, bun, slick)
  const hairGroup = new THREE.Group();
  hairGroup.position.y = 0.62;
  headGroup.add(hairGroup);

  const cap = makeOutlined(roundedBoxGeo(1.32, 0.44, 1.2, 0.18, 2), hairMat, {
    outlineThickness: 0.024,
  });
  cap.position.set(0, 0.44, -0.04);
  hairGroup.add(cap);

  if (hairStyle === 'messy') {
    const tufts = [
      [-0.36, 0.66, 0.25, 0.42, 0.28, 0.46, 0.15, 0.1, 0.2],
      [0.05, 0.72, 0.32, 0.48, 0.28, 0.5, -0.1, 0, -0.1],
      [0.4, 0.64, 0.2, 0.38, 0.26, 0.44, 0.1, -0.1, -0.22],
      [0, 0.28, -0.58, 1.24, 0.72, 0.28, 0, 0, 0],
    ];
    for (const [x, y, z, w, h, d, rx, ry, rz] of tufts) {
      const m = makeOutlined(roundedBoxGeo(w, h, d, 0.1, 2), hairMat, { outlineThickness: 0.02 });
      m.position.set(x, y, z);
      m.rotation.set(rx, ry, rz);
      hairGroup.add(m);
    }
  } else if (hairStyle === 'long') {
    const back = makeOutlined(roundedBoxGeo(1.36, 1.38, 0.38, 0.14, 2), hairMat);
    back.position.set(0, -0.12, -0.48);
    hairGroup.add(back);
    for (const sx of [-0.62, 0.62]) {
      const sideLock = makeOutlined(roundedBoxGeo(0.24, 1.1, 0.42, 0.08, 2), hairMat);
      sideLock.position.set(sx, -0.08, -0.12);
      hairGroup.add(sideLock);
    }
    const bangs = makeOutlined(roundedBoxGeo(1.12, 0.24, 0.32, 0.09, 2), hairMat);
    bangs.position.set(0, 0.44, 0.48);
    hairGroup.add(bangs);
  } else if (hairStyle === 'bun') {
    const back = makeOutlined(roundedBoxGeo(1.26, 0.72, 0.32, 0.12, 2), hairMat);
    back.position.set(0, 0.15, -0.5);
    hairGroup.add(back);
    const bun = makeOutlined(new THREE.SphereGeometry(0.32, 12, 12), hairMat);
    bun.position.set(0, 0.84, -0.22);
    hairGroup.add(bun);
  } else {
    // slick
    const sweep = makeOutlined(roundedBoxGeo(1.24, 0.28, 1.24, 0.12, 2), hairMat);
    sweep.position.set(0, 0.56, 0.04);
    sweep.rotation.x = -0.12;
    hairGroup.add(sweep);
    const back = makeOutlined(roundedBoxGeo(1.24, 0.62, 0.26, 0.1, 2), hairMat);
    back.position.set(0, 0.2, -0.52);
    hairGroup.add(back);
  }

  // Optional glasses
  if (opts.glasses) {
    const glassMat = toonMat('#181B26');
    for (const sx of [-0.24, 0.24]) {
      const rim = makeOutlined(new THREE.TorusGeometry(0.17, 0.025, 8, 18), glassMat, {
        outline: false,
      });
      rim.position.set(sx, 0.66, 0.57);
      headGroup.add(rim);
    }
  }

  function set(p = {}) {
    hips.position.y = 1.2 + (p.y ?? 0);
    torsoPivot.rotation.set(p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
    headGroup.rotation.set(p.hx ?? 0, p.hy ?? 0, p.hz ?? 0);

    armL.shoulder.rotation.set(p.aLx ?? 0, 0, p.aLz ?? -0.12);
    armL.elbow.rotation.set(p.eLx ?? -0.15, 0, p.eLz ?? 0);

    armR.shoulder.rotation.set(p.aRx ?? 0, 0, p.aRz ?? 0.12);
    armR.elbow.rotation.set(p.eRx ?? -0.15, 0, p.eRz ?? 0);

    legL.legPivot.rotation.set(p.lL ?? 0, 0, p.lLz ?? 0);
    legL.kneePivot.rotation.set(p.kL ?? 0, 0, 0);

    legR.legPivot.rotation.set(p.lR ?? 0, 0, p.lRz ?? 0);
    legR.kneePivot.rotation.set(p.kR ?? 0, 0, 0);
  }

  function face(p = {}) {
    faceCanvas.draw(p);
  }

  function reset() {
    set({});
    face({});
  }

  reset();

  return {
    type: 'human',
    root,
    hips,
    torsoPivot,
    headGroup,
    handL: armL.handMarker,
    handR: armR.handMarker,
    set,
    face,
    reset,
  };
}

// ---------- 2. Original Co-Star: Comic Helper Robot (`bot`) ----------

export function createBotRig(opts = {}) {
  const bodyColor = opts.bodyColor || '#E5ECF8';
  const accentColor = opts.accentColor || '#38C8FF';
  const bodyMat = toonMat(bodyColor);
  const darkMat = toonMat('#242938');
  const accentMat = toonMat(accentColor);

  const root = new THREE.Group();
  root.name = opts.name || 'bot_rig';

  const bodyGroup = new THREE.Group();
  bodyGroup.position.y = 1.35;
  root.add(bodyGroup);

  // Rounded chassis
  const torso = makeOutlined(roundedBoxGeo(0.96, 1.04, 0.72, 0.2, 3), bodyMat);
  bodyGroup.add(torso);

  // Chest core badge
  const core = makeOutlined(new THREE.CylinderGeometry(0.16, 0.16, 0.08, 16), accentMat, {
    outlineThickness: 0.015,
  });
  core.rotation.x = Math.PI * 0.5;
  core.position.set(0, -0.05, 0.36);
  bodyGroup.add(core);

  // Legs
  const legL = makeOutlined(new THREE.CapsuleGeometry(0.13, 0.52, 6, 10), darkMat);
  legL.position.set(-0.24, -0.85, 0);
  bodyGroup.add(legL);

  const legR = makeOutlined(new THREE.CapsuleGeometry(0.13, 0.52, 6, 10), darkMat);
  legR.position.set(0.24, -0.85, 0);
  bodyGroup.add(legR);

  // Arms
  function buildBotArm(side) {
    const sh = new THREE.Group();
    sh.position.set(side * 0.62, 0.26, 0);
    bodyGroup.add(sh);
    const arm = makeOutlined(new THREE.CapsuleGeometry(0.12, 0.56, 6, 10), darkMat);
    arm.position.y = -0.3;
    sh.add(arm);
    const claw = makeOutlined(roundedBoxGeo(0.24, 0.24, 0.24, 0.06, 2), accentMat, {
      outlineThickness: 0.018,
    });
    claw.position.y = -0.66;
    sh.add(claw);
    const marker = new THREE.Group();
    marker.position.set(0, -0.72, 0.1);
    sh.add(marker);
    return { sh, marker };
  }
  const armL = buildBotArm(-1);
  const armR = buildBotArm(1);

  // Head + Visor Screen + Emissive Eyes/Mouth
  const headGroup = new THREE.Group();
  headGroup.position.set(0, 0.62, 0);
  bodyGroup.add(headGroup);

  const visorCanvas = document.createElement('canvas');
  visorCanvas.width = 512;
  visorCanvas.height = 512;
  const vctx = visorCanvas.getContext('2d');
  const visorTex = new THREE.CanvasTexture(visorCanvas);
  visorTex.colorSpace = THREE.SRGBColorSpace;

  const emCanvas = document.createElement('canvas');
  emCanvas.width = 512;
  emCanvas.height = 512;
  const ectx = emCanvas.getContext('2d');
  const emTex = new THREE.CanvasTexture(emCanvas);
  emTex.colorSpace = THREE.SRGBColorSpace;

  function drawVisor(p = {}) {
    const mo = clamp(p.mo ?? 0, 0, 1);
    const lx = clamp(p.lx ?? 0, -1, 1);
    const ly = clamp(p.ly ?? 0, -1, 1);
    const brow = clamp(p.brow ?? 0, -1, 1);
    const happy = Boolean(p.happy);
    const glow = p.glow || '#4DF0FF';

    // Grey-dark background to prevent bloom blow-out
    vctx.fillStyle = '#181F2E';
    vctx.fillRect(0, 0, 512, 512);
    ectx.fillStyle = '#000000';
    ectx.fillRect(0, 0, 512, 512);

    const drawFeatures = (ctx) => {
      ctx.fillStyle = glow;
      ctx.strokeStyle = glow;
      ctx.lineWidth = 18;
      ctx.lineCap = 'round';
      for (const ex of [168, 344]) {
        const px = ex + lx * 18;
        const py = 215 - ly * 16;
        if (happy) {
          ctx.beginPath();
          ctx.arc(px, py + 14, 38, Math.PI * 1.15, Math.PI * 1.85);
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.roundRect(px - 34, py - 38 + Math.max(0, -brow) * 14, 68, 76 - Math.abs(brow) * 18, 22);
          ctx.fill();
        }
      }
      // Equalizer talking mouth
      const bars = 5;
      for (let i = 0; i < bars; i++) {
        const bx = 176 + i * 40;
        const centerBoost = 1 - Math.abs(i - 2) * 0.22;
        const bh = 14 + mo * 72 * centerBoost;
        ctx.beginPath();
        ctx.roundRect(bx - 11, 355 - bh * 0.5, 22, bh, 8);
        ctx.fill();
      }
    };

    drawFeatures(vctx);
    drawFeatures(ectx);
    visorTex.needsUpdate = true;
    emTex.needsUpdate = true;
  }
  drawVisor({});

  const headShell = makeOutlined(roundedBoxGeo(1.18, 0.92, 0.92, 0.24, 3), bodyMat);
  headShell.position.y = 0.52;
  headGroup.add(headShell);

  const visorMat = new THREE.MeshBasicMaterial({
    color: 0xc2c8d4,
    map: visorTex,
  });
  const visorPlane = new THREE.Mesh(new THREE.PlaneGeometry(0.92, 0.66), visorMat);
  visorPlane.position.set(0, 0.52, 0.47);
  headGroup.add(visorPlane);

  // Subtle glowing accent antenna
  const antStem = makeOutlined(new THREE.CylinderGeometry(0.03, 0.03, 0.34, 8), darkMat, {
    outline: false,
  });
  antStem.position.set(0, 1.12, 0);
  headGroup.add(antStem);
  const antOrb = makeOutlined(
    new THREE.SphereGeometry(0.11, 12, 12),
    toonMat(accentColor, { emissive: accentColor, emissiveIntensity: 0.45 })
  );
  antOrb.position.set(0, 1.32, 0);
  headGroup.add(antOrb);

  function set(p = {}) {
    bodyGroup.position.y = 1.35 + (p.y ?? 0);
    bodyGroup.rotation.set(p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
    headGroup.rotation.set(p.hx ?? 0, p.hy ?? 0, p.hz ?? 0);
    armL.sh.rotation.set(p.aLx ?? 0, 0, p.aLz ?? -0.15);
    armR.sh.rotation.set(p.aRx ?? 0, 0, p.aRz ?? 0.15);
    legL.rotation.x = p.lL ?? 0;
    legR.rotation.x = p.lR ?? 0;
  }

  function face(p = {}) {
    drawVisor(p);
  }

  function reset() {
    set({});
    face({});
  }

  return {
    type: 'bot',
    root,
    torsoPivot: bodyGroup,
    headGroup,
    handL: armL.marker,
    handR: armR.marker,
    set,
    face,
    reset,
  };
}

// ---------- 3. Original Co-Star: Deadpan City Pigeon (`pigeon`) ----------

export function createPigeonRig(opts = {}) {
  const root = new THREE.Group();
  root.name = opts.name || 'pigeon_rig';

  const greyMat = toonMat('#8C96A8');
  const darkWingMat = toonMat('#555E70');
  const neckMat = toonMat('#40B89E');
  const beakMat = toonMat('#E59E42');
  const footMat = toonMat('#EA6F46');
  const eyeOrange = toonMat('#FF8A1F');
  const blackMat = toonMat('#141620');

  const bodyPivot = new THREE.Group();
  bodyPivot.position.y = 0.62;
  root.add(bodyPivot);

  // Ellipsoid body
  const body = makeOutlined(new THREE.SphereGeometry(0.46, 16, 14), greyMat);
  body.scale.set(0.85, 0.92, 1.22);
  bodyPivot.add(body);

  // Iridescent neck collar
  const neck = makeOutlined(new THREE.CylinderGeometry(0.24, 0.32, 0.36, 14), neckMat);
  neck.position.set(0, 0.36, 0.2);
  bodyPivot.add(neck);

  // Head
  const headGroup = new THREE.Group();
  headGroup.position.set(0, 0.6, 0.25);
  bodyPivot.add(headGroup);

  const headSphere = makeOutlined(new THREE.SphereGeometry(0.29, 16, 14), greyMat);
  headGroup.add(headSphere);

  // Eyes + sliding deadpan eyelids
  const lids = [];
  for (const sx of [-0.21, 0.21]) {
    const eye = makeOutlined(new THREE.SphereGeometry(0.085, 10, 10), eyeOrange, {
      outlineThickness: 0.014,
    });
    eye.position.set(sx, 0.04, 0.16);
    headGroup.add(eye);
    const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.042, 8, 8), blackMat);
    pupil.position.set(sx * 1.12, 0.04, 0.22);
    headGroup.add(pupil);

    const lid = makeOutlined(roundedBoxGeo(0.18, 0.1, 0.14, 0.02, 1), greyMat, {
      outlineThickness: 0.01,
    });
    lid.position.set(sx, 0.12, 0.17);
    headGroup.add(lid);
    lids.push(lid);
  }

  // Upper beak + hinged lower beak for lip-sync
  const upperBeak = makeOutlined(new THREE.ConeGeometry(0.08, 0.26, 8), beakMat, {
    outlineThickness: 0.012,
  });
  upperBeak.rotation.x = Math.PI * 0.5;
  upperBeak.position.set(0, 0.01, 0.34);
  headGroup.add(upperBeak);

  const lowerBeakPivot = new THREE.Group();
  lowerBeakPivot.position.set(0, -0.04, 0.22);
  headGroup.add(lowerBeakPivot);
  const lowerBeak = makeOutlined(new THREE.ConeGeometry(0.065, 0.22, 8), beakMat, {
    outlineThickness: 0.012,
  });
  lowerBeak.rotation.x = Math.PI * 0.52;
  lowerBeak.position.set(0, -0.02, 0.1);
  lowerBeakPivot.add(lowerBeak);

  // Wings on shoulder pivots
  function makeWing(side) {
    const wpiv = new THREE.Group();
    wpiv.position.set(side * 0.36, 0.08, 0.02);
    bodyPivot.add(wpiv);
    const wmesh = makeOutlined(roundedBoxGeo(0.14, 0.52, 0.72, 0.06, 2), darkWingMat);
    wmesh.position.set(side * 0.05, -0.1, -0.06);
    wpiv.add(wmesh);
    return wpiv;
  }
  const wingL = makeWing(-1);
  const wingR = makeWing(1);

  // Tail
  const tail = makeOutlined(roundedBoxGeo(0.36, 0.08, 0.48, 0.03, 1), darkWingMat);
  tail.position.set(0, -0.04, -0.64);
  tail.rotation.x = -0.25;
  bodyPivot.add(tail);

  // Legs
  for (const sx of [-0.15, 0.15]) {
    const leg = makeOutlined(new THREE.CylinderGeometry(0.03, 0.03, 0.44, 6), footMat, {
      outline: false,
    });
    leg.position.set(sx, -0.4, 0.02);
    bodyPivot.add(leg);
    const foot = makeOutlined(roundedBoxGeo(0.14, 0.05, 0.22, 0.02, 1), footMat, {
      outline: false,
    });
    foot.position.set(sx, -0.61, 0.08);
    bodyPivot.add(foot);
  }

  function set(p = {}) {
    const bob = p.bob ?? 0;
    const tuck = p.tuck ?? 0;
    bodyPivot.position.y = 0.62 + (p.y ?? 0) + bob - tuck * 0.14;
    bodyPivot.rotation.set(p.lean ?? p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
    headGroup.rotation.set(p.hx ?? 0, p.hy ?? 0, p.hz ?? 0);

    const lidDrop = clamp(p.lid ?? 0.35, 0, 1);
    for (const lid of lids) {
      lid.position.y = 0.13 - lidDrop * 0.065;
    }

    const mo = clamp(p.mo ?? 0, 0, 1);
    lowerBeakPivot.rotation.x = mo * 0.68;

    const flap = p.flap ?? 0;
    const wingSpread = p.wing ?? 0;
    wingL.rotation.z = -(wingSpread + flap);
    wingR.rotation.z = wingSpread + flap;
  }

  function face(p = {}) {
    const lid = p.open !== undefined ? clamp(1 - p.open * 0.65, 0, 1) : 0.35;
    set({ mo: p.mo ?? 0, lid });
  }

  function reset() {
    set({});
  }

  return {
    type: 'pigeon',
    root,
    torsoPivot: bodyPivot,
    headGroup,
    handL: wingL,
    handR: wingR,
    set,
    face,
    reset,
  };
}

// ---------- 4. Original Co-Star: Robed Comedic Phantom / Time-Spirit (`phantom`) ----------

export function createPhantomRig(opts = {}) {
  const robeColor = opts.robeColor || '#1C1D2A';
  const glowColor = opts.glowColor || '#66F0FF';

  const root = new THREE.Group();
  root.name = opts.name || 'phantom_rig';

  const robeMat = toonMat(robeColor);
  const ropeMat = toonMat('#B69663');
  const boneMat = toonMat('#EAE6DA');

  const torsoPivot = new THREE.Group();
  root.add(torsoPivot);

  // Lathe robe with flared tattered hem
  const pts = [
    new THREE.Vector2(0.72, 0.02),
    new THREE.Vector2(0.64, 0.45),
    new THREE.Vector2(0.46, 1.3),
    new THREE.Vector2(0.5, 2.15),
    new THREE.Vector2(0.28, 2.38),
  ];
  const robe = makeOutlined(new THREE.LatheGeometry(pts, 18), robeMat);
  torsoPivot.add(robe);

  // Rope belt
  const belt = makeOutlined(new THREE.TorusGeometry(0.47, 0.05, 8, 20), ropeMat, {
    outlineThickness: 0.015,
  });
  belt.rotation.x = Math.PI * 0.5;
  belt.position.y = 1.32;
  torsoPivot.add(belt);

  // Wide sleeves + bone hands
  function makeSleeve(side) {
    const sh = new THREE.Group();
    sh.position.set(side * 0.52, 2.08, 0);
    torsoPivot.add(sh);
    const slv = makeOutlined(new THREE.ConeGeometry(0.28, 0.92, 10), robeMat);
    slv.position.y = -0.4;
    sh.add(slv);
    const hand = makeOutlined(roundedBoxGeo(0.2, 0.22, 0.18, 0.06, 2), boneMat, {
      outlineThickness: 0.016,
    });
    hand.position.y = -0.9;
    sh.add(hand);
    const marker = new THREE.Group();
    marker.position.set(0, -0.94, 0.1);
    sh.add(marker);
    return { sh, marker };
  }
  const armL = makeSleeve(-1);
  const armR = makeSleeve(1);

  // Hood + glowing mask face (eyes-only emissive map!)
  const headGroup = new THREE.Group();
  headGroup.position.set(0, 2.34, 0);
  torsoPivot.add(headGroup);

  const hood = makeOutlined(new THREE.SphereGeometry(0.66, 16, 14), robeMat);
  hood.scale.set(1.0, 1.08, 1.08);
  hood.position.set(0, 0.42, -0.06);
  headGroup.add(hood);

  const fCanvas = document.createElement('canvas');
  fCanvas.width = 512;
  fCanvas.height = 512;
  const fctx = fCanvas.getContext('2d');
  const fTex = new THREE.CanvasTexture(fCanvas);
  fTex.colorSpace = THREE.SRGBColorSpace;

  const eCanvas = document.createElement('canvas');
  eCanvas.width = 512;
  eCanvas.height = 512;
  const ectx = eCanvas.getContext('2d');
  const eTex = new THREE.CanvasTexture(eCanvas);
  eTex.colorSpace = THREE.SRGBColorSpace;

  function drawMask(p = {}) {
    const mo = clamp(p.mo ?? 0, 0, 1);
    const lx = clamp(p.lx ?? 0, -1, 1);
    const ly = clamp(p.ly ?? 0, -1, 1);
    const squint = clamp(p.squint ?? 0, 0, 0.7);
    const happy = Boolean(p.happy);

    fctx.fillStyle = '#EAE6DA';
    fctx.fillRect(0, 0, 512, 512);
    ectx.fillStyle = '#000000';
    ectx.fillRect(0, 0, 512, 512);

    // Dark eye sockets on diffuse, glowing pupils ONLY on emissive map
    for (const ex of [178, 334]) {
      fctx.fillStyle = '#141620';
      fctx.beginPath();
      fctx.ellipse(ex, 224, 46, 52 * (1 - squint * 0.5), 0, 0, Math.PI * 2);
      fctx.fill();

      const px = ex + lx * 14;
      const py = 224 - ly * 12;
      for (const ctx of [fctx, ectx]) {
        ctx.fillStyle = glowColor;
        ctx.strokeStyle = glowColor;
        if (happy) {
          ctx.lineWidth = 14;
          ctx.beginPath();
          ctx.arc(px, py + 10, 24, Math.PI * 1.15, Math.PI * 1.85);
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.arc(px, py, 16, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // Stylized jaw / mouth opening driven by `mo`
    fctx.fillStyle = '#141620';
    const mh = 18 + mo * 64;
    fctx.beginPath();
    fctx.roundRect(184, 342 - mh * 0.35, 144, mh, 18);
    fctx.fill();

    fTex.needsUpdate = true;
    eTex.needsUpdate = true;
  }
  drawMask({});

  const maskMat = toonMat('#FFFFFF', {
    map: fTex,
    emissive: '#FFFFFF',
    emissiveMap: eTex,
    emissiveIntensity: 1.35,
  });
  const maskMats = [boneMat, boneMat, boneMat, boneMat, maskMat, boneMat];
  const mask = makeOutlined(roundedBoxGeo(0.86, 0.88, 0.78, 0.24, 3), maskMats, {
    outlineThickness: 0.022,
  });
  mask.position.set(0, 0.42, 0.16);
  headGroup.add(mask);

  function set(p = {}) {
    torsoPivot.position.y = p.y ?? 0;
    torsoPivot.rotation.set(p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
    headGroup.rotation.set(p.hx ?? 0, p.hy ?? 0, p.hz ?? 0);
    armL.sh.rotation.set(p.aLx ?? 0, 0, p.aLz ?? -0.15);
    armR.sh.rotation.set(p.aRx ?? 0, 0, p.aRz ?? 0.15);
  }

  function face(p = {}) {
    drawMask(p);
  }

  function reset() {
    set({});
    face({});
  }

  return {
    type: 'phantom',
    root,
    torsoPivot,
    headGroup,
    handL: armL.marker,
    handR: armR.marker,
    set,
    face,
    reset,
  };
}

// ---------- 5. Original Co-Star: Giant Mech Colossus (`mech`) ----------

export function createGiantMechRig(opts = {}) {
  const metalMat = toonMat(opts.color || '#5A6782');
  const trimMat = toonMat(opts.trim || '#E64B55');
  const visorMat = toonMat('#FF4D4D', { emissive: '#FF4D4D', emissiveIntensity: 1.4 });

  const root = new THREE.Group();
  root.name = opts.name || 'giant_mech';

  const body = new THREE.Group();
  body.position.y = 4.2;
  root.add(body);

  const chest = makeOutlined(roundedBoxGeo(3.4, 3.2, 2.2, 0.22, 2), metalMat, {
    outlineThickness: 0.06,
  });
  body.add(chest);

  const core = makeOutlined(new THREE.CylinderGeometry(0.56, 0.56, 0.3, 18), visorMat, {
    outlineThickness: 0.04,
  });
  core.rotation.x = Math.PI * 0.5;
  core.position.set(0, 0.15, 1.12);
  body.add(core);

  const headGroup = new THREE.Group();
  headGroup.position.set(0, 2.0, 0);
  body.add(headGroup);
  const head = makeOutlined(roundedBoxGeo(1.9, 1.35, 1.5, 0.16, 2), metalMat, {
    outlineThickness: 0.05,
  });
  head.position.y = 0.65;
  headGroup.add(head);
  const visor = makeOutlined(roundedBoxGeo(1.5, 0.38, 0.18, 0.06, 1), visorMat, {
    outline: false,
  });
  visor.position.set(0, 0.72, 0.72);
  headGroup.add(visor);

  const parts = [];
  for (const sx of [-1, 1]) {
    const leg = makeOutlined(roundedBoxGeo(1.15, 3.8, 1.3, 0.16, 2), metalMat, {
      outlineThickness: 0.06,
    });
    leg.position.set(sx * 1.05, -3.2, 0);
    body.add(leg);
    parts.push({ mesh: leg, base: leg.position.clone(), dir: new THREE.Vector3(sx, -0.4, 0.2) });

    const arm = makeOutlined(roundedBoxGeo(1.05, 3.4, 1.1, 0.16, 2), trimMat, {
      outlineThickness: 0.06,
    });
    arm.position.set(sx * 2.45, -0.2, 0.2);
    body.add(arm);
    parts.push({ mesh: arm, base: arm.position.clone(), dir: new THREE.Vector3(sx * 1.5, 0.5, 0.5) });
  }

  function set(p = {}) {
    const explode = clamp(p.explode ?? 0, 0, 1);
    body.position.y = 4.2 + (p.y ?? 0);
    body.rotation.set(p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
    headGroup.rotation.set(p.hx ?? 0, p.hy ?? 0, p.hz ?? 0);
    for (const part of parts) {
      part.mesh.position.copy(part.base).addScaledVector(part.dir, explode * 3.5);
      part.mesh.rotation.set(explode * 1.1, explode * 0.8, explode * 0.9);
    }
  }

  function face() {}
  function reset() {
    set({});
  }

  return {
    type: 'mech',
    root,
    torsoPivot: body,
    headGroup,
    set,
    face,
    reset,
  };
}

// ---------- 6. Original Co-Star: Expressive Pet Rock (`rock`) ----------

export function createRockBuddyRig(opts = {}) {
  const root = new THREE.Group();
  root.name = opts.name || 'rock_buddy';

  const rockMat = toonMat(opts.color || '#8D9199');
  const whiteMat = toonMat('#FFFFFF');
  const pupilMat = toonMat('#141620');

  const body = new THREE.Group();
  body.position.y = 0.55;
  root.add(body);

  const stone = makeOutlined(new THREE.DodecahedronGeometry(0.56, 1), rockMat, {
    outlineThickness: 0.026,
  });
  stone.scale.set(1.15, 0.88, 0.96);
  body.add(stone);

  for (const sx of [-0.18, 0.18]) {
    const eye = makeOutlined(new THREE.SphereGeometry(0.11, 10, 10), whiteMat, {
      outlineThickness: 0.012,
    });
    eye.position.set(sx, 0.12, 0.45);
    body.add(eye);
    const pup = new THREE.Mesh(new THREE.SphereGeometry(0.055, 8, 8), pupilMat);
    pup.position.set(sx, 0.12, 0.53);
    body.add(pup);
  }

  function set(p = {}) {
    body.position.y = 0.55 + (p.y ?? 0);
    body.rotation.set(p.tx ?? 0, p.ty ?? 0, p.tz ?? 0);
  }
  function face() {}
  function reset() {
    set({});
  }

  return {
    type: 'rock',
    root,
    torsoPivot: body,
    headGroup: body,
    set,
    face,
    reset,
  };
}

// ---------- Pose & Emotion Library ----------

export const EMOTION_FACES = {
  neutral: { open: 1.0, brow: 0, mouth: 'smile' },
  happy: { open: 1.0, happy: true, brow: 0.2, raise: 0.2, mouth: 'bigsmile', blush: 0.35 },
  excited: { open: 1.2, pupil: 1.15, raise: 0.6, mouth: 'bigsmile', blush: 0.25 },
  shock: { open: 1.32, pupil: 0.52, raise: 0.85, mouth: 'open', pale: 0.45, sweat: 0.8 },
  panic: { open: 1.28, pupil: 0.5, brow: 0.7, raise: 0.7, mouth: 'wavy', sweat: 1.0, drip: 0.7, pale: 0.55 },
  angry: { open: 0.85, brow: -0.9, raise: -0.25, mouth: 'grin' },
  deadpan: { open: 0.45, brow: 0, mouth: 'flat' },
  sad: { open: 0.85, brow: 0.75, mouth: 'frown', tear: 0.8 },
  smug: { open: 0.7, brow: -0.25, lx: 0.45, mouth: 'smile' },
  confused: { open: 1.05, brow: 0.45, lx: -0.35, mouth: 'o', sweat: 0.4 },
};

export function createCharacterBySpec(spec) {
  const kind = (spec.rig || 'human').toLowerCase();
  if (kind === 'bot' || kind === 'robot') return createBotRig(spec);
  if (kind === 'pigeon' || kind === 'bird') return createPigeonRig(spec);
  if (kind === 'phantom' || kind === 'spirit') return createPhantomRig(spec);
  if (kind === 'mech' || kind === 'giant_mech') return createGiantMechRig(spec);
  if (kind === 'rock') return createRockBuddyRig(spec);
  return createHumanRig(spec);
}
