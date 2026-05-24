/**
 * Bond — Download new AAB from GitHub Actions → Upload to Firebase App Distribution
 *
 * Run: node scripts\firebase-full.js
 *
 * You click the artifact download once — Bond extracts and uploads automatically.
 */

const { execSync, spawnSync } = require('child_process');
const path     = require('path');
const fs       = require('fs');
const os       = require('os');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const PROJECT_ID    = 'lakes-logistics-ffe6f';
const APP_ID        = '1:165820753433:android:9c541cc0a1e9e9a8c6ec88';
const TESTERS       = 'nwtcinvestment@gmail.com,info@3lakeslogistics.com,raycece@yahoo.com,goldiethemac@yahoo.com,Savior45@yahoo.com,talormoe14@yahoo.com,new56money@gmail.com';
const RELEASE_NOTES = '3 Lakes Driver v1.0 — New build from GitHub Actions';
const RUN_URL       = 'https://github.com/modom123/3-Lakes-Logistics/actions/runs/26353604845';
const DOWNLOADS_DIR = path.join(os.homedir(), 'Downloads');
const SAVE_DIR      = path.join(os.homedir(), 'Downloads', '3lakes-new');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}

function findRecursive(dir, ext) {
  try {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, f.name);
      if (f.isDirectory()) { const r = findRecursive(full, ext); if (r) return r; }
      if (f.name.toLowerCase().endsWith(ext)) return full;
    }
  } catch {}
  return null;
}

// Watch Downloads for a NEW zip that didn't exist before
function watchForNewFile(dir, timeoutMs = 120000) {
  const before = new Set(fs.readdirSync(dir));
  const start  = Date.now();
  return new Promise((resolve, reject) => {
    const iv = setInterval(() => {
      const current = fs.readdirSync(dir);
      const newFiles = current.filter(f => !before.has(f) && /\.(zip|aab|apk)$/i.test(f));
      if (newFiles.length > 0) { clearInterval(iv); resolve(path.join(dir, newFiles[0])); }
      if (Date.now() - start > timeoutMs) { clearInterval(iv); reject(new Error('Timeout')); }
    }, 500);
  });
}

(async () => {
  console.log('=== Bond: New AAB → Firebase App Distribution ===\n');

  if (!fs.existsSync(SAVE_DIR)) fs.mkdirSync(SAVE_DIR, { recursive: true });

  // Check if already extracted from a previous run
  let buildFile = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome\n');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 60, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Step 1: Download AAB from GitHub Actions ───────────────────────────────
  if (!buildFile) {
    console.log('[1] Opening GitHub Actions run page...');
    await page.goto(RUN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(3000);
    // Scroll to artifacts at bottom
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(2000);

    console.log('\n╔══════════════════════════════════════════════════════════╗');
    console.log('║  ACTION REQUIRED — do this ONE step in Chrome:           ║');
    console.log('║                                                           ║');
    console.log('║  Scroll to ARTIFACTS at the bottom of the page           ║');
    console.log('║  Click  "3lakes-driver-release-3"                        ║');
    console.log('║                                                           ║');
    console.log('║  Bond will detect the download and continue.             ║');
    console.log('╚══════════════════════════════════════════════════════════╝\n');
    console.log('  Watching Downloads folder...\n');

    let zipPath;
    try {
      zipPath = await watchForNewFile(DOWNLOADS_DIR, 120000);
      console.log(`  ✓ Download detected: ${path.basename(zipPath)}`);
    } catch {
      console.log('  No download detected in 2 minutes.');
      await pause('  Press Enter after downloading the artifact... ');
      // Grab most recent zip
      const files = fs.readdirSync(DOWNLOADS_DIR)
        .filter(f => /\.zip$/i.test(f))
        .map(f => ({ f, t: fs.statSync(path.join(DOWNLOADS_DIR, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t);
      if (files.length) zipPath = path.join(DOWNLOADS_DIR, files[0].f);
    }

    if (zipPath) {
      console.log('  Extracting...');
      try {
        execSync(
          `powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${SAVE_DIR}' -Force"`,
          { stdio: 'pipe', timeout: 30000 }
        );
        buildFile = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');
        if (buildFile) console.log(`  ✓ Extracted: ${buildFile}`);
      } catch (e) {
        console.log('  Extract error:', e.message?.slice(0, 80));
      }
    }
  } else {
    console.log(`[1] Using cached build: ${buildFile}`);
  }

  if (!buildFile) {
    console.log('\n✗ Could not get the build file. Please try again.');
    await browser.close();
    return;
  }

  const sizeMB = (fs.statSync(buildFile).size / 1024 / 1024).toFixed(1);
  console.log(`\n✓ Build file: ${buildFile} (${sizeMB} MB)`);

  // ── Step 2: Upload to Firebase App Distribution ────────────────────────────
  console.log('\n[2] Uploading to Firebase App Distribution...');
  const uploadCmd = [
    `firebase appdistribution:distribute "${buildFile}"`,
    `--app "${APP_ID}"`,
    `--project ${PROJECT_ID}`,
    `--testers "${TESTERS}"`,
    `--release-notes "${RELEASE_NOTES}"`,
  ].join(' ');

  console.log(`  $ ${uploadCmd}\n`);
  try {
    execSync(uploadCmd, { stdio: 'inherit', timeout: 180000 });
    console.log('\n  ✓ Upload complete — all testers notified!');
  } catch (e) {
    console.log('  Error:', (e.stderr?.toString() || e.message || '').slice(0, 200));
  }

  // ── Step 3: Open Firebase console to confirm ──────────────────────────────
  console.log('\n[3] Opening Firebase App Distribution...');
  await page.goto(
    `https://console.firebase.google.com/project/${PROJECT_ID}/appdistribution`,
    { waitUntil: 'domcontentloaded', timeout: 30000 }
  );
  await wait(3000);
  console.log('  ✓ Firebase console open in Chrome');
  console.log('\n=== Done ===');
  console.log(`  Testers: ${TESTERS.split(',').length} people notified`);

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
