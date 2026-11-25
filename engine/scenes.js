/**
 * AutoShorts AI — Detailed Toon 3D Sets & Props Library
 *
 * Sets (each is an isolated THREE.Group with its own Hemisphere + Shadowed Key + Rim lights):
 *  - living_room (day / night): wood floor, wallpaper, window with drawn city, curtains,
 *    bookshelf, rug, couch, floor lamp, side table, wilting plant.
 *  - kitchen (day / night): checkerboard floor, cabinets, sink with dishes, window, fridge with opening door.
 *  - entry_hall: hinged front door, stormy exterior backdrop, sconce, coat hooks, shoe rack.
 *  - town_square (day / attack / golden): sky dome, cobble plaza, animated fountain,
 *    Academy building with sign, distant shop rows (kept far out of camera paths!), lamps, bench, trees, statue pedestal.
 *  - studio: clean tintable montage stage with soft floor & rim lighting.
 *
 * Props: phone, laptop, scroll, box, coffee_mug, clock, briefcase, papers, party_hat,
 *        cape, flame, ice_block, medal, trophy, megaphone.
 */
import * as THREE from 'three';
import { hash11, makeOutlined, roundedBoxGeo, toonMat } from './renderer.js';

// ---------- Helper Canvas Textures (kept <= 0xc6c6c6 for MeshBasicMaterial so bloom never blows out) ----------

function makeCityWindowTexture(night = false) {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 512;
  const ctx = c.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, 512);
  if (night) {
    grad.addColorStop(0, '#141B3A');
    grad.addColorStop(1, '#2D3A6E');
  } else {
    grad.addColorStop(0, '#5EA8F0');
    grad.addColorStop(1, '#B5D9FA');
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 512, 512);

  // Moon or Sun
  ctx.fillStyle = night ? '#C9D6F0' : '#DCE6B8';
  ctx.beginPath();
  ctx.arc(390, 105, 42, 0, Math.PI * 2);
  ctx.fill();

  // Skyline buildings
  const buildings = [
    [15, 250, 75, 262],
    [95, 195, 88, 317],
    [190, 270, 68, 242],
    [265, 165, 95, 347],
    [368, 230, 82, 282],
    [452, 285, 65, 227],
  ];
  for (let i = 0; i < buildings.length; i++) {
    const [x, y, w, h] = buildings[i];
    ctx.fillStyle = night ? '#1A2036' : '#587196';
    ctx.fillRect(x, y, w, h);
    // Windows
    for (let wy = y + 18; wy < 490; wy += 32) {
      for (let wx = x + 12; wx < x + w - 16; wx += 22) {
        const lit = hash11(i * 31 + wx * 3 + wy * 7) > (night ? 0.35 : 0.65);
        ctx.fillStyle = lit ? (night ? '#C4B368' : '#A9C2D9') : '#29334F';
        ctx.fillRect(wx, wy, 12, 18);
      }
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeCheckerTexture(colA = '#D5DBE5', colB = '#46526A') {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 512;
  const ctx = c.getContext('2d');
  const sq = 64;
  for (let y = 0; y < 8; y++) {
    for (let x = 0; x < 8; x++) {
      ctx.fillStyle = (x + y) % 2 === 0 ? colA : colB;
      ctx.fillRect(x * sq, y * sq, sq, sq);
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 3);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeWoodFloorTexture() {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 512;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#B87C4C';
  ctx.fillRect(0, 0, 512, 512);
  for (let y = 0; y < 512; y += 64) {
    ctx.fillStyle = y % 128 === 0 ? '#AE7243' : '#C28656';
    ctx.fillRect(0, y, 512, 62);
    ctx.fillStyle = '#6D4323';
    ctx.fillRect(0, y + 61, 512, 3);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeSignCanvasTexture(title, subtitle = '', bg = '#273556', fg = '#D6D9E2') {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 256;
  const ctx = c.getContext('2d');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 512, 256);
  ctx.strokeStyle = '#C9B068';
  ctx.lineWidth = 12;
  ctx.strokeRect(10, 10, 492, 236);
  ctx.fillStyle = fg;
  ctx.font = '900 46px Inter, Arial, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(title, 256, subtitle ? 105 : 128);
  if (subtitle) {
    ctx.font = '700 28px Inter, Arial, sans-serif';
    ctx.fillStyle = '#C9B068';
    ctx.fillText(subtitle, 256, 172);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function addSetLights(group, opts = {}) {
  const hemi = new THREE.HemisphereLight(
    opts.skyColor ?? 0xdceeff,
    opts.groundColor ?? 0x5c556e,
    opts.hemiIntensity ?? 1.05
  );
  group.add(hemi);

  const key = new THREE.DirectionalLight(opts.keyColor ?? 0xfff5e4, opts.keyIntensity ?? 1.75);
  key.position.set(...(opts.keyPos ?? [6, 11, 7]));
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 40;
  const d = opts.shadowSpan ?? 14;
  key.shadow.camera.left = -d;
  key.shadow.camera.right = d;
  key.shadow.camera.top = d;
  key.shadow.camera.bottom = -d;
  key.shadow.bias = -0.0005;
  group.add(key);

  const rim = new THREE.DirectionalLight(opts.rimColor ?? 0x8cc9ff, opts.rimIntensity ?? 0.65);
  rim.position.set(...(opts.rimPos ?? [-6, 6, -8]));
  group.add(rim);

  return { hemi, key, rim };
}

// ---------- 1. Living Room Set ----------

function createLivingRoomSet(night = false) {
  const group = new THREE.Group();
  group.name = night ? 'living_room_night' : 'living_room';

  addSetLights(group, {
    skyColor: night ? 0x3b4d82 : 0xeef5ff,
    groundColor: night ? 0x1d1c2e : 0x7a6554,
    hemiIntensity: night ? 0.68 : 1.05,
    keyColor: night ? 0x99b3ff : 0xfff4e0,
    keyIntensity: night ? 0.95 : 1.75,
    rimColor: night ? 0xffb36b : 0x96ceff,
    rimIntensity: night ? 0.55 : 0.6,
  });

  // Floor (pushed wide so cameras never see outside edge)
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(36, 36),
    toonMat('#FFFFFF', { map: makeWoodFloorTexture() })
  );
  floor.rotation.x = -Math.PI * 0.5;
  floor.receiveShadow = true;
  group.add(floor);

  // Back & side walls placed far enough back to prevent camera clipping
  const wallMat = toonMat(night ? '#3D4866' : '#DCE7F4');
  const trimMat = toonMat('#F3F5FA');
  const backWall = new THREE.Mesh(new THREE.PlaneGeometry(24, 11), wallMat);
  backWall.position.set(0, 5.5, -5.2);
  backWall.receiveShadow = true;
  group.add(backWall);

  const leftWall = new THREE.Mesh(new THREE.PlaneGeometry(18, 11), wallMat);
  leftWall.rotation.y = Math.PI * 0.5;
  leftWall.position.set(-8.5, 5.5, 1.5);
  leftWall.receiveShadow = true;
  group.add(leftWall);

  // Baseboard
  const baseboard = makeOutlined(roundedBoxGeo(24, 0.32, 0.14, 0.02, 1), trimMat, { outline: false });
  baseboard.position.set(0, 0.16, -5.12);
  group.add(baseboard);

  // Rug
  const rug = makeOutlined(roundedBoxGeo(6.4, 0.06, 4.2, 0.03, 1), toonMat('#D96B52'), {
    outlineThickness: 0.02,
  });
  rug.position.set(0, 0.03, -0.4);
  group.add(rug);

  // Couch
  const couchMat = toonMat('#4E6EA8');
  const cushionMat = toonMat('#5C7FBE');
  const couch = new THREE.Group();
  couch.position.set(0, 0, -3.55);
  group.add(couch);

  const base = makeOutlined(roundedBoxGeo(4.4, 0.72, 1.65, 0.16, 2), couchMat);
  base.position.y = 0.42;
  couch.add(base);
  const back = makeOutlined(roundedBoxGeo(4.4, 1.25, 0.45, 0.14, 2), couchMat);
  back.position.set(0, 1.12, -0.62);
  couch.add(back);
  for (const sx of [-2.02, 2.02]) {
    const arm = makeOutlined(roundedBoxGeo(0.45, 1.05, 1.65, 0.12, 2), cushionMat);
    arm.position.set(sx, 0.72, 0);
    couch.add(arm);
  }

  // Window with painted city view
  const winFrame = makeOutlined(roundedBoxGeo(3.4, 2.7, 0.2, 0.05, 1), trimMat);
  winFrame.position.set(0, 3.8, -5.06);
  group.add(winFrame);
  const winPane = new THREE.Mesh(
    new THREE.PlaneGeometry(3.0, 2.3),
    new THREE.MeshBasicMaterial({ color: 0xc2c2c2, map: makeCityWindowTexture(night) })
  );
  winPane.position.set(0, 3.8, -4.94);
  group.add(winPane);

  // Curtains
  const curtainMat = toonMat('#51668C');
  for (const sx of [-1.85, 1.85]) {
    const cur = makeOutlined(roundedBoxGeo(0.55, 3.2, 0.24, 0.08, 2), curtainMat);
    cur.position.set(sx, 3.6, -4.92);
    group.add(cur);
  }

  // Bookshelf (left background)
  const woodMat = toonMat('#8C5A38');
  const shelf = makeOutlined(roundedBoxGeo(1.9, 3.6, 0.75, 0.06, 1), woodMat);
  shelf.position.set(-4.6, 1.8, -4.5);
  group.add(shelf);
  const bookColors = ['#E05263', '#49B6FF', '#F2C14E', '#5AD685', '#9E7BFF'];
  for (let row = 0; row < 3; row++) {
    for (let b = 0; b < 5; b++) {
      const book = makeOutlined(
        roundedBoxGeo(0.24, 0.56 + (b % 2) * 0.12, 0.45, 0.02, 1),
        toonMat(bookColors[(row + b) % bookColors.length]),
        { outlineThickness: 0.014 }
      );
      book.position.set(-5.2 + b * 0.3, 1.05 + row * 0.92, -4.38);
      group.add(book);
    }
  }

  // Floor lamp with modest point light (kept <= 14 per SKILL.md)
  const lampGroup = new THREE.Group();
  lampGroup.position.set(3.55, 0, -3.7);
  group.add(lampGroup);
  const pole = makeOutlined(new THREE.CylinderGeometry(0.06, 0.08, 3.1, 10), toonMat('#353A4A'));
  pole.position.y = 1.55;
  lampGroup.add(pole);
  const shade = makeOutlined(
    new THREE.ConeGeometry(0.65, 0.75, 14, 1, true),
    toonMat('#F2DC9B', { emissive: '#D6AA45', emissiveIntensity: night ? 0.5 : 0.15, side: THREE.DoubleSide })
  );
  shade.position.y = 3.1;
  lampGroup.add(shade);
  const lampLight = new THREE.PointLight(0xffd28a, night ? 12 : 4, 14, 1.5);
  lampLight.position.set(0, 2.9, 0);
  lampGroup.add(lampLight);

  // Potted plant (can wilt dynamically)
  const plantGroup = new THREE.Group();
  plantGroup.position.set(-3.2, 0, -3.5);
  group.add(plantGroup);
  const pot = makeOutlined(new THREE.CylinderGeometry(0.42, 0.3, 0.65, 12), toonMat('#C76846'));
  pot.position.y = 0.33;
  plantGroup.add(pot);
  const leaves = [];
  const leafMat = toonMat('#4BB566');
  for (let i = 0; i < 5; i++) {
    const lpiv = new THREE.Group();
    lpiv.position.y = 0.66;
    lpiv.rotation.y = (i / 5) * Math.PI * 2;
    const leaf = makeOutlined(roundedBoxGeo(0.24, 0.72, 0.08, 0.04, 1), leafMat, {
      outlineThickness: 0.015,
    });
    leaf.position.set(0, 0.36, 0.16);
    leaf.rotation.x = 0.38;
    lpiv.add(leaf);
    plantGroup.add(lpiv);
    leaves.push(lpiv);
  }

  return {
    group,
    bg: new THREE.Color(night ? '#1E253D' : '#B5D6F2'),
    update(t, opts = {}) {
      const wilt = opts.wilt ?? 0;
      for (const lp of leaves) {
        lp.rotation.x = wilt * 0.9;
      }
    },
  };
}

// ---------- 2. Kitchen Set ----------

function createKitchenSet(night = false) {
  const group = new THREE.Group();
  group.name = night ? 'kitchen_night' : 'kitchen';

  addSetLights(group, {
    skyColor: night ? 0x354778 : 0xf4f8ff,
    groundColor: 0x5c5b69,
    hemiIntensity: night ? 0.65 : 1.05,
    keyIntensity: night ? 0.9 : 1.7,
  });

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(34, 34),
    toonMat('#FFFFFF', { map: makeCheckerTexture() })
  );
  floor.rotation.x = -Math.PI * 0.5;
  floor.receiveShadow = true;
  group.add(floor);

  const wall = new THREE.Mesh(
    new THREE.PlaneGeometry(24, 11),
    toonMat(night ? '#36445C' : '#E7F0F2')
  );
  wall.position.set(0, 5.5, -5.0);
  wall.receiveShadow = true;
  group.add(wall);

  // Cabinets & countertop
  const cabMat = toonMat('#5D8AA8');
  const topMat = toonMat('#E3E7EE');
  const counter = makeOutlined(roundedBoxGeo(7.6, 1.35, 1.3, 0.08, 2), cabMat);
  counter.position.set(-1.0, 0.68, -4.1);
  group.add(counter);
  const slab = makeOutlined(roundedBoxGeo(7.8, 0.16, 1.44, 0.04, 1), topMat);
  slab.position.set(-1.0, 1.42, -4.08);
  group.add(slab);

  // Dish pile near sink
  const plateMat = toonMat('#EFF3FA');
  for (let i = 0; i < 4; i++) {
    const plate = makeOutlined(new THREE.CylinderGeometry(0.32, 0.28, 0.08, 12), plateMat, {
      outlineThickness: 0.012,
    });
    plate.position.set(-2.3, 1.54 + i * 0.08, -4.0);
    group.add(plate);
  }

  // Fridge with hinged door & modest inner light (intensity <= 4)
  const fridgeMat = toonMat('#DCE6F2');
  const fridge = new THREE.Group();
  fridge.position.set(3.9, 0, -4.0);
  group.add(fridge);
  const fBody = makeOutlined(roundedBoxGeo(1.7, 3.6, 1.4, 0.12, 2), fridgeMat);
  fBody.position.y = 1.8;
  fridge.add(fBody);

  const doorPivot = new THREE.Group();
  doorPivot.position.set(0.82, 1.8, 0.72);
  fridge.add(doorPivot);
  const door = makeOutlined(roundedBoxGeo(1.66, 3.5, 0.14, 0.06, 2), fridgeMat);
  door.position.set(-0.82, 0, 0);
  doorPivot.add(door);

  const fridgeLight = new THREE.PointLight(0xd9f6ff, 4, 6, 2);
  fridgeLight.position.set(0, 2.2, 0.5);
  fridge.add(fridgeLight);

  return {
    group,
    bg: new THREE.Color(night ? '#1B2438' : '#CFE2F0'),
    update(t, opts = {}) {
      doorPivot.rotation.y = (opts.fridgeOpen ?? 0) * 1.35;
      fridgeLight.intensity = (opts.fridgeOpen ?? 0) > 0.05 ? 4 : 0.4;
    },
  };
}

// ---------- 3. Entry Hall Set ----------

function createEntryHallSet() {
  const group = new THREE.Group();
  group.name = 'entry_hall';

  addSetLights(group, {
    skyColor: 0x62739e,
    groundColor: 0x362f3b,
    hemiIntensity: 0.78,
    keyColor: 0xffe4be,
    keyIntensity: 1.35,
    rimColor: 0x6ba6ff,
    rimIntensity: 0.9,
  });

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(34, 34),
    toonMat('#FFFFFF', { map: makeWoodFloorTexture() })
  );
  floor.rotation.x = -Math.PI * 0.5;
  floor.receiveShadow = true;
  group.add(floor);

  const wallMat = toonMat('#505C7A');
  const leftWall = makeOutlined(roundedBoxGeo(8, 9, 0.4, 0.04, 1), wallMat, { outline: false });
  leftWall.position.set(-5.3, 4.5, -4.6);
  group.add(leftWall);
  const rightWall = makeOutlined(roundedBoxGeo(8, 9, 0.4, 0.04, 1), wallMat, { outline: false });
  rightWall.position.set(5.3, 4.5, -4.6);
  group.add(rightWall);
  const topWall = makeOutlined(roundedBoxGeo(3.2, 4.6, 0.4, 0.04, 1), wallMat, { outline: false });
  topWall.position.set(0, 6.7, -4.6);
  group.add(topWall);

  // Stormy backdrop behind door
  const storm = new THREE.Mesh(
    new THREE.PlaneGeometry(14, 10),
    new THREE.MeshBasicMaterial({ color: 0x263252 })
  );
  storm.position.set(0, 4.2, -7.2);
  group.add(storm);

  const backlight = new THREE.PointLight(0x7ab4ff, 8, 12, 1.6);
  backlight.position.set(0, 3.0, -5.6);
  group.add(backlight);

  // Hinged front door
  const doorPivot = new THREE.Group();
  doorPivot.position.set(-1.3, 0, -4.5);
  group.add(doorPivot);
  const doorMesh = makeOutlined(roundedBoxGeo(2.6, 4.4, 0.2, 0.06, 2), toonMat('#7E4D31'));
  doorMesh.position.set(1.3, 2.2, 0);
  doorPivot.add(doorMesh);
  const knob = makeOutlined(new THREE.SphereGeometry(0.11, 10, 10), toonMat('#E5BE5C'), {
    outlineThickness: 0.015,
  });
  knob.position.set(2.3, 2.0, 0.16);
  doorPivot.add(knob);

  // Coat rack & shoe bench
  const rack = makeOutlined(roundedBoxGeo(1.8, 0.25, 0.2, 0.04, 1), toonMat('#8C5A38'));
  rack.position.set(-3.4, 2.8, -4.35);
  group.add(rack);
  const bench = makeOutlined(roundedBoxGeo(2.2, 0.72, 0.85, 0.08, 2), toonMat('#8C5A38'));
  bench.position.set(3.2, 0.36, -3.9);
  group.add(bench);

  return {
    group,
    bg: new THREE.Color('#232C47'),
    update(t, opts = {}) {
      doorPivot.rotation.y = (opts.doorOpen ?? 0) * 1.4;
    },
  };
}

// ---------- 4. Town Square Set (wide occlusion-safe plaza) ----------

function createTownSquareSet(mood = 'day') {
  const group = new THREE.Group();
  group.name = `town_square_${mood}`;

  const palettes = {
    day: { sky: '#7CC6FF', key: 0xfff7e6, keyI: 1.9, hemiSky: 0xdff2ff, hemiI: 1.1 },
    golden: { sky: '#F5A962', key: 0xffc87a, keyI: 1.85, hemiSky: 0xffe2ba, hemiI: 0.95 },
    attack: { sky: '#59344E', key: 0xff8a7a, keyI: 1.5, hemiSky: 0x996588, hemiI: 0.8 },
  };
  const pal = palettes[mood] || palettes.day;

  addSetLights(group, {
    skyColor: pal.hemiSky,
    groundColor: 0x6c6e78,
    hemiIntensity: pal.hemiI,
    keyColor: pal.key,
    keyIntensity: pal.keyI,
    keyPos: [10, 18, 12],
    shadowSpan: 22,
  });

  // Large plaza cobble ground (always visible from low angles!)
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(120, 120),
    toonMat('#C2C8D4')
  );
  ground.rotation.x = -Math.PI * 0.5;
  ground.receiveShadow = true;
  group.add(ground);

  // Decorative inner stone circle
  const plazaPad = new THREE.Mesh(
    new THREE.CylinderGeometry(11.5, 11.8, 0.06, 32),
    toonMat('#D5DBE6')
  );
  plazaPad.position.y = 0.03;
  plazaPad.receiveShadow = true;
  group.add(plazaPad);

  // Central fountain pushed back to z = -10 so central stage z ∈ [-3, 3] is unobstructed
  const fountain = new THREE.Group();
  fountain.position.set(0, 0, -10.5);
  group.add(fountain);
  const fRim = makeOutlined(new THREE.CylinderGeometry(2.8, 3.0, 0.72, 20), toonMat('#DFE5F0'));
  fRim.position.y = 0.36;
  fountain.add(fRim);
  const fWater = new THREE.Mesh(
    new THREE.CylinderGeometry(2.45, 2.45, 0.12, 20),
    toonMat('#4DC4FF', { transparent: true, opacity: 0.85 })
  );
  fWater.position.y = 0.68;
  fountain.add(fWater);
  const fPillar = makeOutlined(new THREE.CylinderGeometry(0.45, 0.65, 2.2, 12), toonMat('#DFE5F0'));
  fPillar.position.y = 1.4;
  fountain.add(fPillar);

  const droplets = [];
  const dropMat = toonMat('#8AE2FF');
  for (let i = 0; i < 12; i++) {
    const drop = new THREE.Mesh(new THREE.SphereGeometry(0.14, 8, 8), dropMat);
    fountain.add(drop);
    droplets.push(drop);
  }

  // Academy Building in far background (z = -22, never blocks camera!)
  const academy = new THREE.Group();
  academy.position.set(0, 0, -22);
  group.add(academy);
  const acadBody = makeOutlined(roundedBoxGeo(16, 8.5, 7, 0.2, 2), toonMat('#E8D9C2'), {
    outlineThickness: 0.05,
  });
  acadBody.position.y = 4.25;
  academy.add(acadBody);
  const acadRoof = makeOutlined(roundedBoxGeo(17, 1.4, 7.6, 0.15, 2), toonMat('#435A8C'), {
    outlineThickness: 0.05,
  });
  acadRoof.position.y = 9.0;
  academy.add(acadRoof);

  const signMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(7.2, 2.2),
    new THREE.MeshBasicMaterial({
      color: 0xc2c2c2,
      map: makeSignCanvasTexture('ACADEMIA CENTRAL', 'PRAÇA DA CIDADE'),
    })
  );
  signMesh.position.set(0, 6.2, 3.55);
  academy.add(signMesh);

  // Distant shop rows pushed far out (±16 on X) so camera orbits NEVER enter buildings!
  const shopColors = ['#E69F83', '#8CC4A7', '#F0CF7D', '#9BB3E8'];
  for (const side of [-1, 1]) {
    for (let i = 0; i < 3; i++) {
      const h = 5.5 + (i % 2) * 2.0;
      const shop = makeOutlined(
        roundedBoxGeo(5.2, h, 5.2, 0.15, 2),
        toonMat(shopColors[(i + (side > 0 ? 2 : 0)) % shopColors.length]),
        { outlineThickness: 0.045 }
      );
      shop.position.set(side * 17.5, h * 0.5, -15 + i * 7.8);
      group.add(shop);
    }
  }

  // Park bench (to the left-back)
  const bench = makeOutlined(roundedBoxGeo(2.6, 0.7, 0.9, 0.08, 2), toonMat('#9E673E'));
  bench.position.set(-6.5, 0.35, -6.5);
  bench.rotation.y = 0.45;
  group.add(bench);

  // Statue Pedestal (to the right-back)
  const pedestal = makeOutlined(roundedBoxGeo(1.8, 1.6, 1.8, 0.08, 2), toonMat('#CFD5E2'));
  pedestal.position.set(6.5, 0.8, -6.8);
  group.add(pedestal);

  // Stylized toon trees kept outside central camera paths
  const trunkMat = toonMat('#7E5233');
  const foliageMat = toonMat('#4BB865');
  const treeCoords = [
    [-11.5, -11.5],
    [11.5, -11.5],
    [-12.5, 3.0],
    [12.5, 3.0],
  ];
  for (const [tx, tz] of treeCoords) {
    const tGroup = new THREE.Group();
    tGroup.position.set(tx, 0, tz);
    const trunk = makeOutlined(new THREE.CylinderGeometry(0.32, 0.44, 2.4, 10), trunkMat);
    trunk.position.y = 1.2;
    tGroup.add(trunk);
    const crown = makeOutlined(new THREE.DodecahedronGeometry(1.65, 1), foliageMat);
    crown.position.y = 3.5;
    tGroup.add(crown);
    group.add(tGroup);
  }

  return {
    group,
    bg: new THREE.Color(pal.sky),
    update(t) {
      for (let i = 0; i < droplets.length; i++) {
        const phase = ((t * 1.4 + i / droplets.length) % 1 + 1) % 1;
        const ang = (i / droplets.length) * Math.PI * 2;
        const r = 0.25 + phase * 1.6;
        const y = 2.4 + Math.sin(phase * Math.PI) * 1.3 - phase * 1.6;
        droplets[i].position.set(Math.cos(ang) * r, Math.max(0.75, y), Math.sin(ang) * r);
      }
    },
  };
}

// ---------- 5. Clean Studio Stage (Montages / Punchlines) ----------

function createStudioSet(tint = '#384B82') {
  const group = new THREE.Group();
  group.name = 'studio';

  addSetLights(group, {
    skyColor: 0xffffff,
    groundColor: 0x3b425c,
    hemiIntensity: 1.1,
    keyIntensity: 1.65,
    rimColor: 0xffe082,
    rimIntensity: 0.9,
  });

  const floorMat = toonMat(tint);
  const floor = new THREE.Mesh(new THREE.CylinderGeometry(18, 18, 0.1, 32), floorMat);
  floor.position.y = -0.05;
  floor.receiveShadow = true;
  group.add(floor);

  const bgColor = new THREE.Color(tint);
  return {
    group,
    bg: bgColor,
    setTint(hex) {
      floorMat.color.set(hex);
      bgColor.set(hex);
    },
    update() {},
  };
}

export function createAllSets() {
  return {
    living_room: createLivingRoomSet(false),
    living_room_night: createLivingRoomSet(true),
    kitchen: createKitchenSet(false),
    kitchen_night: createKitchenSet(true),
    entry_hall: createEntryHallSet(),
    town_square: createTownSquareSet('day'),
    town_square_golden: createTownSquareSet('golden'),
    town_square_attack: createTownSquareSet('attack'),
    studio: createStudioSet('#35487A'),
  };
}

// ---------- 15+ Original Story Props ----------

export function createProps() {
  const props = {};

  // Phone (grey MeshBasicMaterial screen to avoid bloom)
  const phone = new THREE.Group();
  phone.add(makeOutlined(roundedBoxGeo(0.28, 0.5, 0.05, 0.02, 1), toonMat('#1E2230'), { outlineThickness: 0.012 }));
  const pScreen = new THREE.Mesh(
    new THREE.PlaneGeometry(0.22, 0.4),
    new THREE.MeshBasicMaterial({ color: 0xbac8d8 })
  );
  pScreen.position.z = 0.028;
  phone.add(pScreen);
  props.phone = phone;

  // Laptop
  const laptop = new THREE.Group();
  laptop.add(makeOutlined(roundedBoxGeo(0.86, 0.05, 0.58, 0.02, 1), toonMat('#C7CFDC'), { outlineThickness: 0.014 }));
  const lid = makeOutlined(roundedBoxGeo(0.86, 0.56, 0.04, 0.02, 1), toonMat('#C7CFDC'), { outlineThickness: 0.014 });
  lid.position.set(0, 0.28, -0.28);
  lid.rotation.x = -0.18;
  laptop.add(lid);
  const lScr = new THREE.Mesh(
    new THREE.PlaneGeometry(0.76, 0.46),
    new THREE.MeshBasicMaterial({ color: 0xb8c4d4 })
  );
  lScr.position.set(0, 0.28, -0.25);
  lScr.rotation.x = -0.18;
  laptop.add(lScr);
  props.laptop = laptop;

  // Scroll
  const scroll = new THREE.Group();
  scroll.add(makeOutlined(roundedBoxGeo(0.55, 0.68, 0.04, 0.01, 1), toonMat('#EEDDB6'), { outlineThickness: 0.014 }));
  for (const sy of [-0.35, 0.35]) {
    const rod = makeOutlined(new THREE.CylinderGeometry(0.055, 0.055, 0.64, 10), toonMat('#9C6A3C'), { outlineThickness: 0.012 });
    rod.rotation.z = Math.PI * 0.5;
    rod.position.y = sy;
    scroll.add(rod);
  }
  props.scroll = scroll;

  // Mystery Package Box
  props.box = makeOutlined(roundedBoxGeo(0.72, 0.62, 0.72, 0.05, 2), toonMat('#C9945B'));

  // Coffee Mug
  const mug = new THREE.Group();
  mug.add(makeOutlined(new THREE.CylinderGeometry(0.14, 0.12, 0.28, 12), toonMat('#F5F7FA'), { outlineThickness: 0.014 }));
  const handle = makeOutlined(new THREE.TorusGeometry(0.08, 0.025, 6, 12), toonMat('#F5F7FA'), { outline: false });
  handle.position.set(0.14, 0, 0);
  mug.add(handle);
  props.coffee_mug = mug;

  // Clock
  const clock = new THREE.Group();
  clock.add(makeOutlined(new THREE.CylinderGeometry(0.42, 0.42, 0.14, 18), toonMat('#E65151')));
  clock.rotation.x = Math.PI * 0.5;
  props.clock = clock;

  // Briefcase
  props.briefcase = makeOutlined(roundedBoxGeo(0.68, 0.48, 0.18, 0.04, 2), toonMat('#5C3E2A'));

  // Paper Stack
  props.papers = makeOutlined(roundedBoxGeo(0.46, 0.18, 0.58, 0.02, 1), toonMat('#D0D5DE'));

  // Party Hat
  props.party_hat = makeOutlined(new THREE.ConeGeometry(0.32, 0.72, 12), toonMat('#FF5C8A'));

  // Cape
  props.cape = makeOutlined(roundedBoxGeo(1.0, 1.45, 0.08, 0.03, 1), toonMat('#E63946'));

  // Stylized Flame
  props.flame = makeOutlined(
    new THREE.ConeGeometry(0.24, 0.65, 10),
    toonMat('#FF8C24', { emissive: '#FF6B1A', emissiveIntensity: 0.7 }),
    { outlineThickness: 0.015 }
  );

  // Ice Block
  props.ice_block = makeOutlined(
    roundedBoxGeo(1.1, 1.3, 1.1, 0.12, 2),
    toonMat('#9AE8FF', { transparent: true, opacity: 0.72 })
  );

  // Medal
  const medal = new THREE.Group();
  medal.add(makeOutlined(new THREE.CylinderGeometry(0.22, 0.22, 0.06, 16), toonMat('#F2C14E'), { outlineThickness: 0.012 }));
  medal.rotation.x = Math.PI * 0.5;
  props.medal = medal;

  // Trophy
  const trophy = new THREE.Group();
  const cup = makeOutlined(new THREE.CylinderGeometry(0.28, 0.16, 0.42, 14), toonMat('#F2C14E'));
  cup.position.y = 0.42;
  trophy.add(cup);
  const base = makeOutlined(roundedBoxGeo(0.36, 0.18, 0.36, 0.03, 1), toonMat('#4D3624'));
  base.position.y = 0.09;
  trophy.add(base);
  props.trophy = trophy;

  // Megaphone
  const mega = new THREE.Group();
  const cone = makeOutlined(new THREE.ConeGeometry(0.24, 0.56, 12), toonMat('#FF5252'));
  cone.rotation.x = Math.PI * 0.5;
  mega.add(cone);
  props.megaphone = mega;

  return props;
}
