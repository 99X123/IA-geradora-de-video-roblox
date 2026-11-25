#!/usr/bin/env node
/**
 * AutoShorts AI — Chunked Parallel Video Renderer & Resumable Concatenator
 *
 * Splits the frame timeline into N parts, runs up to `WORKERS` Playwright/FFmpeg
 * workers in parallel, skips already-completed valid part files (resumable!),
 * supports re-rendering only specific parts (`--only-parts 2,5`), concatenates
 * losslessly with `-c copy`, and muxes final audio (`mix.wav`) to H.264 + AAC MP4.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const WORKER_SCRIPT = path.join(__dirname, 'render_worker.mjs');

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const token = argv[i];
    if (token.startsWith('--')) {
      const key = token.slice(2);
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        args[key] = next;
        i++;
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

function runProcess(cmd, cmdArgs, label = '') {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, cmdArgs, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => {
      const s = d.toString();
      stdout += s;
      process.stdout.write(label ? `[${label}] ${s}` : s);
    });
    proc.stderr.on('data', (d) => {
      const s = d.toString();
      stderr += s;
      process.stderr.write(label ? `[${label}] ${s}` : s);
    });
    proc.on('error', reject);
    proc.on('close', (code) => {
      if (code === 0) resolve({ stdout, stderr });
      else reject(new Error(`${cmd} falhou (exit=${code}): ${stderr.slice(-1500)}`));
    });
  });
}

async function main() {
  const args = parseArgs(process.argv);
  const storyboardPath = path.resolve(args.storyboard || 'storyboard.json');
  const syncPath = args.sync ? path.resolve(args.sync) : null;
  const audioPath = args.audio ? path.resolve(args.audio) : null;
  const partsDir = path.resolve(args['parts-dir'] || path.join(path.dirname(storyboardPath), 'parts'));
  const outPath = path.resolve(args.out || path.join(path.dirname(storyboardPath), 'final.mp4'));
  const ffmpegBin = args.ffmpeg || process.env.FFMPEG_BINARY || 'ffmpeg';

  const sb = JSON.parse(fs.readFileSync(storyboardPath, 'utf-8'));
  const fps = Number(args.fps || sb.fps || 30);
  const durationSec = Number(args.duration || sb.duration_sec || 10);
  const totalFrames = Math.max(1, Math.ceil(durationSec * fps));
  const numParts = Math.min(totalFrames, Math.max(1, Number(args.parts || 10)));
  const workers = Math.max(1, Number(args.workers || process.env.WORKERS || 2));
  const crf = String(args.crf || 18);
  const preset = String(args.preset || 'veryfast');

  const onlyParts = args['only-parts']
    ? new Set(
        String(args['only-parts'])
          .split(',')
          .map((s) => Number(s.trim()))
          .filter((n) => !Number.isNaN(n))
      )
    : null;
  const forceAll = Boolean(args.force);

  fs.mkdirSync(partsDir, { recursive: true });
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const jobs = [];
  const framesPerPart = Math.ceil(totalFrames / numParts);
  for (let i = 0; i < numParts; i++) {
    const f0 = i * framesPerPart;
    const f1 = Math.min(totalFrames, f0 + framesPerPart);
    if (f0 >= f1) break;
    const partFile = path.join(partsDir, `part_${String(i).padStart(2, '0')}.mp4`);
    jobs.push({ idx: i, f0, f1, partFile });
  }

  const queue = jobs.filter((job) => {
    if (onlyParts && !onlyParts.has(job.idx)) return false;
    if (!forceAll && !onlyParts && fs.existsSync(job.partFile) && fs.statSync(job.partFile).size > 1024) {
      console.log(`Pulando parte existente (cache/resume): ${path.basename(job.partFile)}`);
      return false;
    }
    return true;
  });

  console.log(
    `AutoShorts Render: ${totalFrames} frames @ ${fps}fps (${durationSec.toFixed(2)}s) | ` +
      `${jobs.length} partes | ${queue.length} a renderizar | workers=${workers}`
  );

  // Worker pool
  let cursor = 0;
  const workerPromises = [];
  for (let w = 0; w < Math.min(workers, Math.max(1, queue.length)); w++) {
    workerPromises.push(
      (async () => {
        while (cursor < queue.length) {
          const job = queue[cursor++];
          const workerArgs = [
            WORKER_SCRIPT,
            'part',
            '--storyboard',
            storyboardPath,
            '--out',
            job.partFile,
            '--f0',
            String(job.f0),
            '--f1',
            String(job.f1),
            '--fps',
            String(fps),
            '--crf',
            crf,
            '--preset',
            preset,
            '--ffmpeg',
            ffmpegBin,
          ];
          if (syncPath && fs.existsSync(syncPath)) {
            workerArgs.push('--sync', syncPath);
          }
          await runProcess(process.execPath, workerArgs, `P${String(job.idx).padStart(2, '0')}`);
        }
      })()
    );
  }
  await Promise.all(workerPromises);

  // Verify every part exists before concatenating
  for (const job of jobs) {
    if (!fs.existsSync(job.partFile) || fs.statSync(job.partFile).size < 256) {
      throw new Error(`Parte ausente ou corrompida: ${job.partFile}`);
    }
  }

  // Write FFmpeg concat list using forward slashes for cross-platform reliability
  const concatListPath = path.join(partsDir, 'concat_list.txt');
  const lines = jobs.map((j) => `file '${j.partFile.replace(/\\/g, '/').replace(/'/g, "'\\''")}'`);
  fs.writeFileSync(concatListPath, lines.join('\n') + '\n', 'utf-8');

  const tmpFinal = outPath.replace(/\.mp4$/i, '.tmp.mp4');
  if (fs.existsSync(tmpFinal)) fs.unlinkSync(tmpFinal);

  const muxArgs = ['-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', concatListPath];
  if (audioPath && fs.existsSync(audioPath)) {
    muxArgs.push(
      '-i',
      audioPath,
      '-map',
      '0:v:0',
      '-map',
      '1:a:0',
      '-c:v',
      'copy',
      '-c:a',
      'aac',
      '-b:a',
      '192k',
      '-ar',
      '44100',
      '-ac',
      '2',
      '-shortest',
      '-movflags',
      '+faststart',
      tmpFinal
    );
  } else {
    muxArgs.push('-c:v', 'copy', '-movflags', '+faststart', tmpFinal);
  }

  await runProcess(ffmpegBin, muxArgs, 'MUX');
  fs.renameSync(tmpFinal, outPath);
  console.log(`Final MP4 pronto: ${outPath}`);
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
