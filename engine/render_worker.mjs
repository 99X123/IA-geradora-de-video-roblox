#!/usr/bin/env node
/**
 * AutoShorts AI — Headless Chromium + Playwright 3D Render Worker
 *
 * Modes:
 *   node engine/render_worker.mjs probe [--out probe.json]
 *   node engine/render_worker.mjs still --storyboard sb.json [--sync sync.json] --out-dir stills --times 0.5,2.0
 *   node engine/render_worker.mjs board --storyboard sb.json [--sync sync.json] --out-dir board
 *   node engine/render_worker.mjs part  --storyboard sb.json [--sync sync.json] --out parts/part_00.mp4 --f0 0 --f1 90
 *
 * Key engineering guarantees:
 * - Serves project root over local HTTP (ES modules cannot load via file://).
 * - Attempts hardware WebGL first and INSPECTS the real WebGL renderer string
 *   (NEVER lies about GPU acceleration if SwiftShader / software rendering is active).
 * - Falls back safely to SwiftShader when CPU=1 or hardware WebGL fails.
 * - Pipes JPEG frame buffers directly into FFmpeg (`-f image2pipe`), creating ZERO
 *   temporary PNG files on disk.
 * - Writes to `.tmp.mp4` and renames atomically only on FFmpeg exit code 0.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function parseArgs(argv) {
  const mode = argv[2] || 'probe';
  const args = { mode };
  for (let i = 3; i < argv.length; i++) {
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

function startStaticServer(extraMounts = {}) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
        if (urlPath === '/favicon.ico') {
          res.writeHead(204);
          res.end();
          return;
        }

        // Virtual mounted project files (e.g., /__project/storyboard.json)
        if (extraMounts[urlPath]) {
          const target = extraMounts[urlPath];
          const ext = path.extname(target).toLowerCase();
          res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] || 'application/octet-stream' });
          fs.createReadStream(target).pipe(res);
          return;
        }

        const relPath = urlPath === '/' ? '/engine/index.html' : urlPath;
        const fullPath = path.resolve(PROJECT_ROOT, '.' + relPath);
        if (!fullPath.startsWith(PROJECT_ROOT) || !fs.existsSync(fullPath) || fs.statSync(fullPath).isDirectory()) {
          res.writeHead(404);
          res.end('Not Found');
          return;
        }

        const ext = path.extname(fullPath).toLowerCase();
        res.writeHead(200, { 'Content-Type': MIME_TYPES[ext] || 'application/octet-stream' });
        fs.createReadStream(fullPath).pipe(res);
      } catch (err) {
        res.writeHead(500);
        res.end(String(err));
      }
    });

    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address();
      resolve({ server, port: addr.port });
    });
  });
}

function findBrowserExecutable() {
  if (process.env.CHROMIUM_PATH && fs.existsSync(process.env.CHROMIUM_PATH)) {
    return process.env.CHROMIUM_PATH;
  }
  const candidates =
    process.platform === 'win32'
      ? [
          'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
          'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
          'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
          'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        ]
      : [
          '/usr/bin/chromium',
          '/usr/bin/chromium-browser',
          '/usr/bin/google-chrome',
          '/usr/bin/google-chrome-stable',
        ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

async function launchBrowserWithProbe(width, height) {
  const forceCpu = process.env.CPU === '1' || process.env.FORCE_CPU === '1';
  const isWin = process.platform === 'win32';
  const isLinux = process.platform === 'linux';

  const baseArgs = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--autoplay-policy=no-user-gesture-required',
  ];

  const gpuArgs = isWin
    ? [...baseArgs, '--ignore-gpu-blocklist', '--enable-gpu', '--use-angle=d3d11']
    : isLinux
      ? [...baseArgs, '--ignore-gpu-blocklist', '--enable-gpu', '--enable-webgl', '--use-gl=angle', '--use-angle=vulkan', '--enable-features=Vulkan']
      : [...baseArgs, '--ignore-gpu-blocklist', '--enable-gpu'];

  const swArgs = [
    ...baseArgs,
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--ignore-gpu-blocklist',
  ];

  async function tryLaunch(args, label) {
    const launchOpts = { headless: true, args };
    // Prefer Playwright's bundled Chromium; fall back to system Chrome/Chromium if bundled binary not downloaded
    try {
      const browser = await chromium.launch(launchOpts);
      return { browser, label, executable: 'playwright-chromium' };
    } catch (firstErr) {
      const sysExe = findBrowserExecutable();
      if (!sysExe) throw firstErr;
      const browser = await chromium.launch({ ...launchOpts, executablePath: sysExe });
      return { browser, label, executable: sysExe };
    }
  }

  let launched = null;
  let fallbackUsed = false;
  let gpuAttemptError = null;

  if (!forceCpu) {
    try {
      launched = await tryLaunch(gpuArgs, 'gpu_attempt');
    } catch (err) {
      gpuAttemptError = String(err.message || err);
      fallbackUsed = true;
    }
  } else {
    fallbackUsed = true;
  }

  if (!launched) {
    launched = await tryLaunch(swArgs, 'swiftshader_fallback');
  }

  const context = await launched.browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  return {
    browser: launched.browser,
    context,
    page,
    launchMode: launched.label,
    executable: launched.executable,
    fallbackUsed,
    gpuAttemptError,
    forceCpu,
  };
}

function getFfmpegBin(args) {
  return args.ffmpeg || process.env.FFMPEG_BINARY || 'ffmpeg';
}

async function run() {
  const args = parseArgs(process.argv);
  const mode = args.mode;

  let storyboardPath = args.storyboard ? path.resolve(args.storyboard) : null;
  let syncPath = args.sync ? path.resolve(args.sync) : null;

  let width = Number(args.width || 1080);
  let height = Number(args.height || 1920);
  let fps = Number(args.fps || 30);
  let crf = String(args.crf || 18);
  let preset = String(args.preset || 'veryfast');

  let storyboardJson = null;
  if (storyboardPath && fs.existsSync(storyboardPath)) {
    storyboardJson = JSON.parse(fs.readFileSync(storyboardPath, 'utf-8'));
    width = Number(args.width || storyboardJson.width || 1080);
    height = Number(args.height || storyboardJson.height || 1920);
    fps = Number(args.fps || storyboardJson.fps || 30);
  }

  const mounts = {};
  if (storyboardPath) mounts['/__project/storyboard.json'] = storyboardPath;
  if (syncPath && fs.existsSync(syncPath)) mounts['/__project/sync.json'] = syncPath;

  const { server, port } = await startStaticServer(mounts);
  const baseUrl = `http://127.0.0.1:${port}`;

  let session = null;
  try {
    session = await launchBrowserWithProbe(width, height);
    const { page } = session;

    const consoleErrors = [];
    page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(`console.error: ${msg.text()}`);
    });
    page.on('requestfailed', (req) => {
      consoleErrors.push(`requestfailed: ${req.url()} (${req.failure()?.errorText || 'unknown'})`);
    });

    await page.goto(`${baseUrl}/engine/index.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    try {
      await page.waitForFunction(() => window.runtimeLoaded === true, { timeout: 20000 });
    } catch (waitErr) {
      throw new Error(
        `Runtime 3D não carregou no Chromium: ${waitErr.message}\nErros do navegador:\n${consoleErrors.join('\n')}`
      );
    }

    // Probe real WebGL renderer BEFORE deciding whether to fall back
    let webglInfo = null;
    try {
      webglInfo = await page.evaluate(() => window.probeWebGL());
    } catch (webglErr) {
      // If hardware GPU attempt failed WebGL context creation, relaunch with SwiftShader
      if (!session.fallbackUsed) {
        await session.browser.close();
        process.env.CPU = '1';
        session = await launchBrowserWithProbe(width, height);
        session.fallbackUsed = true;
        session.gpuAttemptError = `WebGL context failed in GPU mode: ${webglErr.message}`;
        await session.page.goto(`${baseUrl}/engine/index.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await session.page.waitForFunction(() => window.runtimeLoaded === true, { timeout: 20000 });
        webglInfo = await session.page.evaluate(() => window.probeWebGL());
      } else {
        throw webglErr;
      }
    }

    const activePage = session.page;
    const probeReport = {
      platform: process.platform,
      launch_mode: session.launchMode,
      browser_executable: session.executable,
      forced_cpu: session.forceCpu,
      fallback_used: session.fallbackUsed,
      gpu_attempt_error: session.gpuAttemptError,
      webgl: webglInfo,
      hardware_accelerated: webglInfo ? !webglInfo.isSoftware && webglInfo.classification === 'gpu_hardware' : false,
      note:
        webglInfo && webglInfo.isSoftware
          ? `AVISO: Chromium está usando renderização por SOFTWARE (${webglInfo.unmaskedRenderer || webglInfo.renderer}). Não há aceleração WebGL por GPU ativa.`
          : `WebGL por hardware confirmado: ${webglInfo?.unmaskedRenderer || webglInfo?.renderer || 'desconhecido'}`,
      console_errors: consoleErrors,
    };

    console.log(`Renderer: ${webglInfo?.unmaskedRenderer || webglInfo?.renderer} [${webglInfo?.classification}]`);

    if (mode === 'probe') {
      if (args.out) {
        fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
        fs.writeFileSync(path.resolve(args.out), JSON.stringify(probeReport, null, 2), 'utf-8');
      }
      console.log(JSON.stringify(probeReport, null, 2));
      return;
    }

    if (!storyboardPath) {
      throw new Error(`Modo '${mode}' requer --storyboard <arquivo.json>`);
    }

    await activePage.evaluate(
      async ({ sbUrl, syncUrl }) => {
        await window.loadFilmProject(sbUrl, syncUrl);
      },
      {
        sbUrl: '/__project/storyboard.json',
        syncUrl: syncPath && fs.existsSync(syncPath) ? '/__project/sync.json' : null,
      }
    );
    await activePage.waitForFunction(() => window.ready === true, { timeout: 20000 });

    if (mode === 'still' || mode === 'board') {
      const outDir = path.resolve(args['out-dir'] || (mode === 'board' ? 'board' : 'stills'));
      fs.mkdirSync(outDir, { recursive: true });

      let sampleTimes = [];
      if (mode === 'board') {
        sampleTimes = (storyboardJson.shots || []).map((sh, idx) => ({
          label: `shot_${String(idx + 1).padStart(2, '0')}`,
          t: Number(((sh.start + sh.end) * 0.5).toFixed(3)),
          shotIndex: idx + 1,
        }));
      } else {
        const rawTimes = String(args.times || '0.5')
          .split(',')
          .map((s) => Number(s.trim()))
          .filter((n) => !Number.isNaN(n));
        sampleTimes = rawTimes.map((t, idx) => ({
          label: `still_${String(idx + 1).padStart(2, '0')}_${t.toFixed(2)}s`,
          t,
        }));
      }

      const manifest = [];
      for (const item of sampleTimes) {
        const { dataUrl, overshoot } = await activePage.evaluate((timeVal) => {
          const url = window.renderFrame(timeVal);
          return { dataUrl: url, overshoot: window.getAuditOvershoot() };
        }, item.t);

        const b64 = dataUrl.split(',')[1];
        const filePath = path.join(outDir, `${item.label}.jpg`);
        fs.writeFileSync(filePath, Buffer.from(b64, 'base64'));
        manifest.push({
          label: item.label,
          time_sec: item.t,
          file: filePath,
          framing_overshoot: Number(overshoot.toFixed(4)),
        });
      }

      const manifestPath = path.join(outDir, 'manifest.json');
      fs.writeFileSync(
        manifestPath,
        JSON.stringify({ mode, probe: probeReport, frames: manifest }, null, 2),
        'utf-8'
      );
      console.log(`Rendered ${manifest.length} ${mode} frames to ${outDir}`);
      return;
    }

    if (mode === 'part') {
      const outFile = path.resolve(args.out || 'parts/part_00.mp4');
      const f0 = Number(args.f0 ?? 0);
      const f1 = Number(args.f1 ?? Math.ceil((storyboardJson.duration_sec || 5) * fps));
      if (f1 <= f0) {
        throw new Error(`Intervalo de frames inválido: f0=${f0}, f1=${f1}`);
      }

      fs.mkdirSync(path.dirname(outFile), { recursive: true });
      const tmpFile = outFile.replace(/\.mp4$/i, '.tmp.mp4');
      if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);

      const ffmpegBin = getFfmpegBin(args);
      const ffArgs = [
        '-y',
        '-hide_banner',
        '-loglevel',
        'error',
        '-f',
        'image2pipe',
        '-c:v',
        'mjpeg',
        '-framerate',
        String(fps),
        '-i',
        '-',
        '-vf',
        'scale=in_range=full:out_range=tv,format=yuv420p',
        '-c:v',
        'libx264',
        '-crf',
        crf,
        '-preset',
        preset,
        '-pix_fmt',
        'yuv420p',
        '-color_range',
        'tv',
        '-r',
        String(fps),
        '-movflags',
        '+faststart',
        tmpFile,
      ];

      const ff = spawn(ffmpegBin, ffArgs, { stdio: ['pipe', 'pipe', 'pipe'] });
      let ffStderr = '';
      ff.stderr.on('data', (d) => {
        ffStderr += d.toString();
      });

      const ffExitPromise = new Promise((resolve, reject) => {
        ff.on('error', reject);
        ff.on('close', (code) => resolve(code));
      });

      const total = f1 - f0;
      const startTime = Date.now();
      let maxOvershoot = 0;

      for (let f = f0; f < f1; f++) {
        const t = f / fps;
        const { dataUrl, overshoot } = await activePage.evaluate((timeVal) => {
          const url = window.renderFrame(timeVal);
          return { dataUrl: url, overshoot: window.getAuditOvershoot() };
        }, t);

        if (overshoot > maxOvershoot) maxOvershoot = overshoot;
        const buf = Buffer.from(dataUrl.split(',')[1], 'base64');

        if (!ff.stdin.write(buf)) {
          await new Promise((resolve) => ff.stdin.once('drain', resolve));
        }

        const done = f - f0 + 1;
        if (done % 30 === 0 || done === total) {
          const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
          console.log(`[${path.basename(outFile)}] ${done}/${total} frames (${elapsed}s)`);
        }
      }

      ff.stdin.end();
      const exitCode = await ffExitPromise;
      if (exitCode !== 0) {
        if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);
        throw new Error(`FFmpeg falhou com código ${exitCode}: ${ffStderr}`);
      }

      fs.renameSync(tmpFile, outFile);
      console.log(
        JSON.stringify({
          part: outFile,
          f0,
          f1,
          frames: total,
          elapsed_sec: Number(((Date.now() - startTime) / 1000).toFixed(2)),
          max_framing_overshoot: Number(maxOvershoot.toFixed(4)),
          hardware_accelerated: probeReport.hardware_accelerated,
          webgl_renderer: webglInfo?.unmaskedRenderer || webglInfo?.renderer,
        })
      );
      return;
    }

    throw new Error(`Modo desconhecido: ${mode}`);
  } finally {
    if (session?.browser) {
      await session.browser.close().catch(() => {});
    }
    server.close();
  }
}

run().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
