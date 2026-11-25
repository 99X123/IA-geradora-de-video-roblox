/**
 * AutoShorts AI — Deterministic 2D Cinematic Overlays & Particle Effects
 * All effects are pure functions of time `t` (zero Math.random).
 */
import { clamp, hash11, pop } from './renderer.js';

export function computeShakeOffset(t, intensity = 0, width = 1080) {
  if (!intensity || intensity <= 0.001) return { x: 0, y: 0 };
  const amp = intensity * (width / 1080) * 18;
  const f = Math.floor(t * 30);
  return {
    x: (hash11(f * 13.7 + 1.1) - 0.5) * 2 * amp,
    y: (hash11(f * 29.3 + 4.7) - 0.5) * 2 * amp,
  };
}

export function drawVignette(ctx, width, height, strength = 0.28) {
  if (strength <= 0) return;
  ctx.save();
  const grad = ctx.createRadialGradient(
    width * 0.5,
    height * 0.45,
    width * 0.35,
    width * 0.5,
    height * 0.5,
    height * 0.72
  );
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(1, `rgba(6,8,16,${clamp(strength, 0, 0.85)})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

export function drawSpeedLines(ctx, width, height, t, intensity = 0.7, color = '#FFFFFF') {
  if (intensity <= 0.01) return;
  ctx.save();
  const cx = width * 0.5;
  const cy = height * 0.42;
  const maxR = Math.hypot(width, height) * 0.72;
  const count = 44;
  const frameBucket = Math.floor(t * 15);

  ctx.strokeStyle = color;
  for (let i = 0; i < count; i++) {
    const seed = hash11(i * 19.3 + frameBucket * 3.1);
    const angle = (i / count) * Math.PI * 2 + (seed - 0.5) * 0.08;
    const innerR = width * (0.38 + seed * 0.28);
    const lineW = (3 + seed * 9) * (width / 1080);

    ctx.globalAlpha = clamp(intensity * (0.25 + seed * 0.5), 0, 0.85);
    ctx.lineWidth = lineW;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
    ctx.lineTo(cx + Math.cos(angle) * maxR, cy + Math.sin(angle) * maxR);
    ctx.stroke();
  }
  ctx.restore();
}

export function drawConfetti(ctx, width, height, t, amount = 55) {
  const colors = ['#FFE44D', '#FF5C8A', '#4DF0FF', '#6EFF8C', '#FF9F43', '#B97AFF'];
  const scale = width / 1080;
  ctx.save();
  for (let i = 0; i < amount; i++) {
    const h1 = hash11(i * 7.13 + 0.5);
    const h2 = hash11(i * 13.37 + 1.9);
    const h3 = hash11(i * 23.11 + 3.2);

    const speedY = 260 + h2 * 380;
    const x = ((h1 * width + Math.sin(t * (2.5 + h3 * 3) + i) * 65 * scale) % width + width) % width;
    const y = ((h2 * height * 1.4 + t * speedY * scale) % (height * 1.15)) - height * 0.08;
    const rot = t * (3.0 + h3 * 6.0) + i;
    const rw = (14 + h3 * 16) * scale;
    const rh = (8 + h1 * 10) * scale;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rot);
    ctx.fillStyle = colors[i % colors.length];
    ctx.fillRect(-rw * 0.5, -rh * 0.5, rw, rh);
    ctx.restore();
  }
  ctx.restore();
}

export function drawSparks(ctx, width, height, t, u, origin = { x: 0.5, y: 0.42 }, color = '#FFE44D') {
  const scale = width / 1080;
  const ox = origin.x * width;
  const oy = origin.y * height;
  const age = clamp(u, 0, 1.2);
  if (age <= 0 || age > 1.0) return;

  ctx.save();
  for (let i = 0; i < 24; i++) {
    const h1 = hash11(i * 11.7 + 2.3);
    const h2 = hash11(i * 31.1 + 5.1);
    const angle = h1 * Math.PI * 2;
    const speed = (220 + h2 * 520) * scale;
    const dist = speed * age;
    const px = ox + Math.cos(angle) * dist;
    const py = oy + Math.sin(angle) * dist + 280 * scale * age * age;
    const r = (6 + h2 * 10) * scale * (1 - age);

    ctx.globalAlpha = clamp(1 - age, 0, 1);
    ctx.fillStyle = i % 3 === 0 ? '#FFFFFF' : color;
    ctx.beginPath();
    ctx.arc(px, py, Math.max(1, r), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function drawHearts(ctx, width, height, t, amount = 18) {
  const scale = width / 1080;
  ctx.save();
  for (let i = 0; i < amount; i++) {
    const h1 = hash11(i * 17.3 + 4.1);
    const h2 = hash11(i * 9.7 + 1.2);
    const x = width * (0.15 + h1 * 0.7) + Math.sin(t * 2.2 + i) * 35 * scale;
    const y = height * 0.7 - (((t * 160 * (0.7 + h2 * 0.6) + h2 * 900) * scale) % (height * 0.65));
    const s = (16 + h2 * 14) * scale;

    ctx.save();
    ctx.translate(x, y);
    ctx.globalAlpha = 0.85;
    ctx.fillStyle = i % 2 === 0 ? '#FF5C8A' : '#FF8FB3';
    ctx.beginPath();
    ctx.moveTo(0, s * 0.35);
    ctx.bezierCurveTo(-s, -s * 0.35, -s * 0.6, -s * 1.1, 0, -s * 0.45);
    ctx.bezierCurveTo(s * 0.6, -s * 1.1, s, -s * 0.35, 0, s * 0.35);
    ctx.fill();
    ctx.restore();
  }
  ctx.restore();
}

export function drawImpactMark(ctx, width, height, screenPos, text, u = 0.2, size = 78, color = '#FFE44D') {
  if (!text) return;
  const scale = width / 1080;
  const anim = pop(clamp(u / 0.16, 0, 1));
  const fs = Math.round(size * scale);

  const px = clamp(screenPos.x, width * 0.16, width * 0.84);
  // Keep impact text above the caption band
  const py = clamp(screenPos.y, height * 0.12, height * 0.6);

  ctx.save();
  ctx.translate(px, py);
  ctx.rotate(-0.08);
  ctx.scale(anim, anim);
  ctx.font = `900 ${fs}px Inter, "Arial Black", Impact, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(8, Math.round(16 * scale));
  ctx.strokeStyle = '#0B0D14';
  ctx.strokeText(text.toUpperCase(), 0, 0);
  ctx.fillStyle = color;
  ctx.fillText(text.toUpperCase(), 0, 0);
  ctx.restore();
}

export function drawFlash(ctx, width, height, opacity = 0, color = '#FFFFFF') {
  if (opacity <= 0.005) return;
  ctx.save();
  ctx.globalAlpha = clamp(opacity, 0, 1);
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

export function projToScreen(worldPoint, camera, width, height) {
  const v = worldPoint.clone().project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * width,
    y: (-v.y * 0.5 + 0.5) * height,
    visible: v.z >= -1 && v.z <= 1,
  };
}
