/**
 * Bond — Download AAB from GitHub Actions → Upload to Firebase
 * Run: node scripts\firebase-full.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const os   = require('os');
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
const ARTIFACT_URL  = 'https://github.com/modom123/3-Lakes-Logistics/actions/runs/26353604845';
const SAVE_DIR      = path.join(os.homedir(), 'Downloads', '3lakes-new');
const DOWNLOADS_DIR = path.join(os.homedir(), 'Downloads');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function prompt(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}
function findFile(dir, ...exts) {
  try {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, f.name);
      if (f.isDirectory()) { const r = findFile(full, ...exts); if (r) return r; }
      if (exts.some(e => f.name.toLowerCase().endsWith(e))) return full;
    }
  } catch {}
  return null;
}
function watchForNewFile(dir, timeoutMs = 120000) {
  const before = new Set(fs.readdirSync(dir));
  const start  = Date.now();
  return new Promise((resolve, reject) => {
    const iv = setInterval(() => {
      const newFiles = fs.readdirSync(dir).filter(f =>
        !before.has(f) && /\.(zip|aab|apk)$/i.test(f) && !f.endsWith('.crdownload')
      );
      if (newFiles.length) { clearInterval(iv); resolve(path.join(dir, newFiles[0])); }
      if (Date.now() - start > timeoutMs) { clearInterval(iv); reject(new Error('Timeout')); }
    }, 500);
  });
}

(async () => {
  console.log('=== Bond: New AAB → Firebase App Distribution ===\n');

  if (!fs.existsSync(SAVE_DIR)) fs.mkdirSync(SAVE_DIR, { recursive: true });

  // Check for the known artifact zip first
  const knownZip = path.join(DOWNLOADS_DIR, '3lakes-driver-release-3.zip');
  if (fs.existsSync(knownZip) && !findFile(SAVE_DIR, '.aab', '.apk')) {
    console.log(`[0] Found artifact zip: ${knownZip}`);
    console.log('    Extracting...');
    execSync(
      `powershell -Command "Expand-Archive -LiteralPath '${knownZip}' -DestinationPath '${SAVE_DIR}' -Force"`,
      { stdio: 'pipe', timeout: 30000 }
    );
    console.log('    ✓ Extracted');
  }

  let buildFile = findFile(SAVE_DIR, '.aab', '.apk');

  // ── Step 1: User downloads artifact from their Chrome ─────────────────────
  if (!buildFile) {
    console.log('┌─────────────────────────────────────────────────────────┐');
    console.log('│  ONE ACTION IN YOUR CHROME BROWSER:                     │');
    console.log('│                                                          │');
    console.log('│  1. Open this URL in Chrome:                            │');
    console.log(`│     ${ARTIFACT_URL}  │`);
    console.log('│                                                          │');
    console.log('│  2. Scroll to bottom → ARTIFACTS section                │');
    console.log('│                                                          │');
    console.log('│  3. Click "3lakes-driver-release-3" to download         │');
    console.log('│                                                          │');
    console.log('└─────────────────────────────────────────────────────────┘');
    console.log('\n  Bond is watching your Downloads folder...\n');

    let zipPath;
    try {
      zipPath = await watchForNewFile(DOWNLOADS_DIR, 120000);
      console.log(`\n  ✓ Got it: ${path.basename(zipPath)}`);
    } catch {
      console.log('\n  No download detected — checking most recent zip...');
      await prompt('  After downloading, press Enter here to continue... ');
      const recent = fs.readdirSync(DOWNLOADS_DIR)
        .filter(f => /\.zip$/i.test(f))
        .map(f => ({ f, t: fs.statSync(path.join(DOWNLOADS_DIR, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t)[0];
      if (recent) zipPath = path.join(DOWNLOADS_DIR, recent.f);
    }

    if (zipPath) {
      console.log('  Extracting...');
      execSync(
        `powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${SAVE_DIR}' -Force"`,
        { stdio: 'pipe', timeout: 30000 }
      );
      buildFile = findFile(SAVE_DIR, '.aab', '.apk');
      if (buildFile) console.log(`  ✓ Extracted: ${path.basename(buildFile)}`);
    }
  } else {
    console.log(`[1] Using cached build: ${path.basename(buildFile)}`);
  }

  if (!buildFile) {
    console.log('\n✗ No build file found.');
    process.exit(1);
  }

  const sizeMB = (fs.statSync(buildFile).size / 1024 / 1024).toFixed(1);
  console.log(`\n✓ Build: ${path.basename(buildFile)} (${sizeMB} MB)`);

  // ── Step 2: Upload via Firebase CLI ───────────────────────────────────────
  console.log('\n[2] Uploading to Firebase App Distribution...');
  const cmd = [
    `firebase appdistribution:distribute "${buildFile}"`,
    `--app "${APP_ID}"`,
    `--project ${PROJECT_ID}`,
    `--testers "${TESTERS}"`,
    `--release-notes "${RELEASE_NOTES}"`,
  ].join(' ');
  console.log(`  $ ${cmd}\n`);
  execSync(cmd, { stdio: 'inherit', timeout: 180000 });

  // ── Step 3: Open Firebase console via existing Chrome ─────────────────────
  console.log('\n[3] Opening Firebase console...');
  try {
    const browser = await chromium.connectOverCDP('http://localhost:9222');
    const context = browser.contexts()[0] || await browser.newContext();
    const page    = context.pages()[0]    || await context.newPage();
    await page.goto(
      `https://console.firebase.google.com/u/1/project/${PROJECT_ID}/appdistribution`,
      { waitUntil: 'domcontentloaded', timeout: 30000 }
    );
    await wait(2000);
    console.log('  ✓ Firebase console open in Chrome');
  } catch {
    console.log(`  Open this URL in Chrome to see the release:`);
    console.log(`  https://console.firebase.google.com/u/1/project/${PROJECT_ID}/appdistribution`);
  }

  console.log('\n=== Done ===');
  console.log(`  ✓ New build uploaded — ${TESTERS.split(',').length} testers notified!`);

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
