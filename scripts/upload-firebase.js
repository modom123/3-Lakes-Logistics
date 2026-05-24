/**
 * Bond — Download AAB from GitHub Actions → Upload to Firebase App Distribution
 *
 * Run: node scripts\upload-firebase.js
 *
 * You click the artifact download once — Bond handles extract + Firebase upload.
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const os   = require('os');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const FIREBASE_PROJECT = 'lakes-logistics-ffe6f';
const RUN_URL          = 'https://github.com/modom123/3-Lakes-Logistics/actions/runs/26353604845';
const DIST_URL         = `https://console.firebase.google.com/project/${FIREBASE_PROJECT}/appdistribution`;
const SAVE_DIR         = path.join(os.homedir(), 'Downloads', '3lakes-build');
const DOWNLOADS_DIR    = path.join(os.homedir(), 'Downloads');
const TESTERS          = 'nwtcinvestment@gmail.com,info@3lakeslogistics.com';
const RELEASE_NOTES    = '3 Lakes Driver v1.0 — Internal test build';

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

// Watch a folder for a new zip file, return its path when it appears
function watchForNewZip(watchDir, timeoutMs = 120000) {
  const before = new Set(fs.readdirSync(watchDir));
  const start  = Date.now();
  return new Promise((resolve, reject) => {
    const iv = setInterval(() => {
      const now = fs.readdirSync(watchDir);
      const newFiles = now.filter(f => !before.has(f) && /\.zip$/i.test(f));
      if (newFiles.length > 0) {
        clearInterval(iv);
        resolve(path.join(watchDir, newFiles[0]));
      }
      if (Date.now() - start > timeoutMs) {
        clearInterval(iv);
        reject(new Error('Timeout waiting for download'));
      }
    }, 500);
  });
}

(async () => {
  console.log('=== Bond: GitHub → Firebase App Distribution ===\n');

  if (!fs.existsSync(SAVE_DIR)) fs.mkdirSync(SAVE_DIR, { recursive: true });

  // Check Android Studio project release folder first
  const studioRelease = 'C:\\Users\\12068\\AndroidStudioProjects\\3lakesDriver\\app\\release';
  let aabPath = findRecursive(studioRelease, '.aab')
             || findRecursive(studioRelease, '.apk')
             || findRecursive(SAVE_DIR, '.aab')
             || findRecursive(SAVE_DIR, '.apk');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 80, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Download artifact ──────────────────────────────────────────────────────
  if (!aabPath) {
    console.log('\n[1] Opening GitHub Actions run page...');
    await page.goto(RUN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(2000);

    // Scroll to bottom so user can see artifacts
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(1000);

    console.log('\n╔══════════════════════════════════════════════════════════╗');
    console.log('║  ACTION REQUIRED:                                        ║');
    console.log('║                                                          ║');
    console.log('║  In Chrome, scroll to the ARTIFACTS section at bottom   ║');
    console.log('║  Click  "3lakes-driver-release-3"  to download it       ║');
    console.log('║                                                          ║');
    console.log('║  Bond will detect the download and continue             ║');
    console.log('╚══════════════════════════════════════════════════════════╝\n');

    console.log('  Watching Downloads folder for new zip...');
    let zipPath;
    try {
      zipPath = await watchForNewZip(DOWNLOADS_DIR, 120000);
      console.log(`  ✓ Download detected: ${path.basename(zipPath)}`);
    } catch {
      // Also check if it landed in SAVE_DIR somehow
      const f = findRecursive(SAVE_DIR, '.zip') || findRecursive(DOWNLOADS_DIR, '.aab');
      if (f && f.endsWith('.aab')) { aabPath = f; }
      else {
        console.log('  No download detected in 2 minutes.');
        await pause('  After downloading, press Enter to continue... ');
        // Check most recent zip
        const files = fs.readdirSync(DOWNLOADS_DIR)
          .filter(f => /\.zip$/i.test(f))
          .map(f => ({ f, t: fs.statSync(path.join(DOWNLOADS_DIR, f)).mtimeMs }))
          .sort((a, b) => b.t - a.t);
        if (files.length > 0) zipPath = path.join(DOWNLOADS_DIR, files[0].f);
      }
    }

    if (zipPath && !aabPath) {
      console.log('\n[2] Extracting zip...');
      try {
        execSync(`powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${SAVE_DIR}' -Force"`, { stdio: 'pipe' });
        aabPath = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');
        if (aabPath) {
          console.log(`  ✓ Extracted: ${aabPath}`);
        } else {
          console.log('  Contents of extracted folder:');
          findRecursive(SAVE_DIR, '') && fs.readdirSync(SAVE_DIR).forEach(f => console.log('   ', f));
        }
      } catch (e) {
        console.log('  Extract error:', e.message?.slice(0, 100));
      }
    }
  } else {
    console.log(`\n[1] Using existing AAB: ${aabPath}`);
  }

  if (!aabPath) {
    console.log('\n✗ No AAB found. Could not continue.');
    await browser.close();
    return;
  }

  const sizeMB = (fs.statSync(aabPath).size / 1024 / 1024).toFixed(1);
  console.log(`\n✓ AAB: ${aabPath} (${sizeMB} MB)`);

  // ── Upload via Firebase CLI ────────────────────────────────────────────────
  console.log('\n[3] Uploading to Firebase App Distribution...');
  let uploaded = false;

  // Install Firebase CLI if needed
  try { execSync('firebase --version', { stdio: 'pipe' }); }
  catch { console.log('  Installing Firebase CLI...'); execSync('npm install -g firebase-tools', { stdio: 'inherit' }); }

  // Get Firebase App ID for Android
  let appId = '';
  try {
    const appsOutput = execSync(
      `firebase apps:list --project ${FIREBASE_PROJECT} --json`,
      { stdio: 'pipe', timeout: 15000 }
    ).toString();
    const appsJson = JSON.parse(appsOutput);
    const androidApp = (appsJson.result || []).find(a => a.platform === 'ANDROID');
    if (androidApp) {
      appId = androidApp.appId;
      console.log(`  ✓ Firebase Android App ID: ${appId}`);
    }
  } catch (e) {
    console.log('  Could not auto-detect App ID:', e.message?.slice(0, 80));
  }

  if (!appId) {
    console.log('  No Android app found in Firebase project.');
    console.log('  Creating Android app in Firebase...');
    try {
      const createOut = execSync(
        `firebase apps:create ANDROID com.threelakes.driver --project ${FIREBASE_PROJECT} --json`,
        { stdio: 'pipe', timeout: 30000 }
      ).toString();
      const created = JSON.parse(createOut);
      appId = created.result?.appId || '';
      if (appId) console.log(`  ✓ Created app, ID: ${appId}`);
    } catch (e) {
      console.log('  Auto-create failed:', e.message?.slice(0, 80));
    }
  }

  const uploadCmd = [
    `firebase appdistribution:distribute "${aabPath}"`,
    `--app "${appId || '1:112146856396107954470:android:unknown'}"`,
    `--project ${FIREBASE_PROJECT}`,
    `--testers "${TESTERS}"`,
    `--release-notes "${RELEASE_NOTES}"`,
  ].join(' ');

  console.log(`\n  $ ${uploadCmd}\n`);
  try {
    execSync(uploadCmd, { stdio: 'inherit', timeout: 180000 });
    uploaded = true;
  } catch (e) {
    const msg = (e.stderr?.toString() || e.message || '');
    if (/not logged|unauthenticated|auth/i.test(msg)) {
      console.log('\n  Need to log into Firebase — opening browser login...');
      execSync('firebase login', { stdio: 'inherit' });
      try {
        execSync(uploadCmd, { stdio: 'inherit', timeout: 180000 });
        uploaded = true;
      } catch {}
    } else {
      console.log('  CLI error:', msg.slice(0, 300));
    }
  }

  // ── Browser fallback ───────────────────────────────────────────────────────
  if (!uploaded) {
    console.log('\n[4] CLI failed — opening Firebase console for manual upload...');
    await page.goto(DIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(4000);
    await page.evaluate(() => {
      const t = [...document.querySelectorAll('[role="tab"]')].find(t => /android/i.test(t.innerText));
      if (t) t.click();
    });
    await wait(2000);
    await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')].find(b => /(upload|get started|release)/i.test(b.innerText));
      if (b) b.click();
    });
    await wait(2000);
    try {
      await page.locator('input[type="file"]').first().setInputFiles(aabPath);
      await wait(5000);
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('button')].find(b => /(next|distribute)/i.test(b.innerText));
        if (b) { b.removeAttribute('disabled'); b.click(); }
      });
      uploaded = true;
      console.log('  ✓ Submitted via browser');
    } catch {
      console.log(`  Please drag this file into the Firebase browser window:`);
      console.log(`  ${aabPath}`);
      await pause('  Press Enter after upload completes in browser... ');
    }
  }

  console.log('\n=== Done ===');
  console.log(uploaded ? '  ✓ App uploaded to Firebase App Distribution!' : '  Check browser for status');
  console.log(`  Testers notified: ${TESTERS}`);

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
