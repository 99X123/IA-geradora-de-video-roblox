/**
 * AutoShorts AI — Dynamic Word-by-Word Vertical Captions
 *
 * Renders bold Inter 900 uppercase captions strictly in the lower safe band
 * (centered at y = 1395 on 1080x1920, well below 66.5% = 1277px) so faces
 * are never covered. Supports per-speaker highlight colors and pop animation.
 */
import { clamp, pop } from './renderer.js';

export const DEFAULT_CAPTION_STYLE = {
  fontFamily: 'Inter, "Arial Black", "Segoe UI Black", Impact, sans-serif',
  fontWeight: 900,
  fontSizePx: 92,
  strokeWidthPx: 18,
  strokeColor: '#0B0D14',
  baseColor: '#FFFFFF',
  yCenterRatio: 1395 / 1920,
  wordGapPx: 44,
  maxLineWidthRatio: 0.88,
  speakerColors: {
    N: '#FFE44D', // Narrador — amarelo vivo
    C: '#4DF0FF', // Co-protagonista — ciano brilhante
    S: '#FF7AE6', // Secundário — magenta neon
  },
};

export function findActiveChunk(chunks, t) {
  if (!chunks || !chunks.length) return null;
  for (let i = 0; i < chunks.length; i++) {
    const ch = chunks[i];
    if (t >= ch.start - 0.02 && t <= ch.end + 0.06) {
      return ch;
    }
  }
  return null;
}

export function drawCaptions(ctx, width, height, chunks, t, styleOverrides = {}) {
  const chunk = findActiveChunk(chunks, t);
  if (!chunk || !chunk.words || !chunk.words.length) return;

  const style = { ...DEFAULT_CAPTION_STYLE, ...styleOverrides };
  const speakerColors = {
    ...DEFAULT_CAPTION_STYLE.speakerColors,
    ...(styleOverrides.speakerColors || {}),
  };

  const scaleFactor = width / 1080;
  let fontSize = Math.round(style.fontSizePx * scaleFactor);
  const strokeWidth = Math.max(6, Math.round(style.strokeWidthPx * scaleFactor));
  // Generous inter-word gap so 1.15x active-word pop + thick outline never touch neighbors
  const wordGap = Math.round((style.wordGapPx + 14) * scaleFactor);
  const maxWidth = width * style.maxLineWidthRatio;
  const centerY = height * style.yCenterRatio;

  const words = chunk.words.map((w) => ({
    ...w,
    label: String(w.word || w.text || '').toUpperCase(),
  }));

  ctx.save();
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'center';
  ctx.lineJoin = 'round';
  ctx.miterLimit = 2;

  // Measure and shrink slightly if chunk is wide (long Portuguese words)
  const measureTotal = (fs) => {
    ctx.font = `${style.fontWeight} ${fs}px ${style.fontFamily}`;
    let total = 0;
    const widths = [];
    for (let i = 0; i < words.length; i++) {
      const w = ctx.measureText(words[i].label).width;
      widths.push(w);
      total += w;
      if (i > 0) total += wordGap;
    }
    return { total, widths };
  };

  let measured = measureTotal(fontSize);
  while (measured.total > maxWidth && fontSize > Math.round(44 * scaleFactor)) {
    fontSize -= Math.max(2, Math.round(4 * scaleFactor));
    measured = measureTotal(fontSize);
  }

  // Chunk entrance pop (smooth subtle scale-in)
  const chunkAge = clamp((t - chunk.start) / 0.1, 0, 1);
  const chunkPop = 0.88 + 0.12 * pop(chunkAge);

  let cursorX = width * 0.5 - measured.total * 0.5;
  const highlightColor = speakerColors[chunk.speaker || 'N'] || speakerColors.N;

  for (let i = 0; i < words.length; i++) {
    const wordObj = words[i];
    const wWidth = measured.widths[i];
    const wordCenterX = cursorX + wWidth * 0.5;
    cursorX += wWidth + wordGap;

    const isActive = t >= wordObj.start - 0.015 && t <= wordObj.end + 0.03;
    const isSpoken = t > wordObj.end + 0.03;

    let wordScale = chunkPop;
    if (isActive) {
      const activeAge = clamp((t - wordObj.start) / 0.11, 0, 1);
      wordScale = chunkPop * (1.0 + 0.15 * pop(activeAge));
    }

    ctx.save();
    ctx.translate(wordCenterX, centerY);
    ctx.scale(wordScale, wordScale);
    ctx.font = `${style.fontWeight} ${fontSize}px ${style.fontFamily}`;

    // Soft dark shadow for readability against bright scenes
    ctx.shadowColor = 'rgba(0, 0, 0, 0.72)';
    ctx.shadowBlur = Math.round(14 * scaleFactor);
    ctx.shadowOffsetY = Math.round(8 * scaleFactor);

    // Thick dark outline
    ctx.lineWidth = strokeWidth;
    ctx.strokeStyle = style.strokeColor;
    ctx.strokeText(wordObj.label, 0, 0);

    // Fill color (active word highlighted in character color)
    ctx.shadowColor = 'transparent';
    ctx.fillStyle = isActive
      ? highlightColor
      : isSpoken
        ? '#F2F4FF'
        : style.baseColor;
    ctx.fillText(wordObj.label, 0, 0);
    ctx.restore();
  }

  ctx.restore();
}
