/**
 * Bond — Upload AAB to Firebase App Distribution
 *
 * Run: node scripts\upload-firebase.js
 *
 * Finds the AAB in Downloads, extracts it, then uploads to Firebase
 * App Distribution so testers get notified immediately.
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const os   = require('os');

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
const DOWNLOADS_DIR    = path.join(os.homedir(), 'Downloads');
const EXTRACT_DIR      = path.join(os.homedir(), 'Downloads', '3lakes-aab');
const TESTERS          = 'nwtcinvestment@gmail.com,info@3lakeslogistics.com';
const RELEASE_NOTES    = '3 Lakes Driver v1.0 — Internal test build';
const DIST_URL         = `https://console.firebase.google.com/project/${FIREBASE_PROJECT}/appdistribution`;

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Find and extract AAB ───────────────────────────────────────────────────
function listRecursive(dir, indent = '  ') {
  try {
    for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, f.name);
      const size = f.isFile() ? ` (${(fs.statSync(full).size/1024).toFixed(0)}kb)` : '';
      console.log(`${indent}${f.name}${size}`);
      if (f.isDirectory()) listRecursive(full, indent + '  ');
    }
  } catch {}
}

function findRecursive(dir, ext) {
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, f.name);
    if (f.isDirectory()) { const r = findRecursive(full, ext); if (r) return r; }
    if (f.name.toLowerCase().endsWith(ext)) return full;
  }
  return null;
}

function extractZip(zipPath, destDir) {
  if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true });
  try {
    execSync(`powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${destDir}' -Force"`, { stdio: 'pipe', timeout: 30000 });
    return true;
  } catch (e) {
    console.log('  PowerShell extract failed:', e.message?.slice(0,100));
    try {
      execSync(`tar -xf "${zipPath}" -C "${destDir}"`, { stdio: 'pipe', timeout: 30000 });
      return true;
    } catch (e2) {
      console.log('  tar extract failed:', e2.message?.slice(0,100));
      return false;
    }
  }
}

function findAab() {
  // Check all zips in Downloads, try each one
  const zips = fs.readdirSync(DOWNLOADS_DIR)
    .filter(f => /\.zip$/i.test(f))
    .map(f => ({ name: f, full: path.join(DOWNLOADS_DIR, f), size: fs.statSync(path.join(DOWNLOADS_DIR, f)).size, mtime: fs.statSync(path.join(DOWNLOADS_DIR, f)).mtimeMs }))
    .filter(z => !/logs/.test(z.name) && z.size > 500_000)
    .sort((a, b) => b.mtime - a.mtime);

  console.log(`  Candidate zips:`);
  zips.forEach(z => console.log(`    ${z.name} (${(z.size/1024/1024).toFixed(1)} MB)`));

  for (const zip of zips) {
    const destDir = path.join(os.tmpdir(), '3lakes-extract-' + Date.now());
    console.log(`\n  Trying: ${zip.name}`);
    const ok = extractZip(zip.full, destDir);
    if (!ok) continue;

    console.log('  Contents:');
    listRecursive(destDir);

    // Look for .aab first, then .apk
    let found = findRecursive(destDir, '.aab');
    if (!found) found = findRecursive(destDir, '.apk');
    if (found) {
      console.log(`  ✓ Found: ${found}`);
      return found;
    }
    console.log('  No AAB/APK in this zip — trying next...');
  }
  return null;
}

(async () => {
  console.log('=== Bond: Upload AAB to Firebase App Distribution ===\n');

  // ── Step 1: Find AAB ───────────────────────────────────────────────────────
  console.log('[1] Finding AAB in Downloads...');
  const aabPath = findAab();

  if (!aabPath) {
    console.log('  ✗ Could not find AAB. Make sure 3 lakes logistics (2).zip is in Downloads.');
    process.exit(1);
  }

  const sizeMB = (fs.statSync(aabPath).size / 1024 / 1024).toFixed(1);
  console.log(`  ✓ Found: ${aabPath} (${sizeMB} MB)`);

  // ── Step 2: Try Firebase CLI first ────────────────────────────────────────
  console.log('\n[2] Checking Firebase CLI...');
  let fbOk = false;
  try {
    const ver = execSync('firebase --version', { stdio: 'pipe' }).toString().trim();
    console.log(`  ✓ Firebase CLI: ${ver}`);
    fbOk = true;
  } catch {
    console.log('  Firebase CLI not found — installing...');
    try {
      execSync('npm install -g firebase-tools', { stdio: 'inherit' });
      fbOk = true;
    } catch {
      console.log('  Could not install Firebase CLI — will use browser upload instead');
    }
  }

  if (fbOk) {
    console.log('\n[3] Uploading via Firebase CLI...');
    try {
      // Get the Android app ID from firebase project
      const uploadCmd = [
        `firebase appdistribution:distribute "${aabPath}"`,
        `--project ${FIREBASE_PROJECT}`,
        `--testers "${TESTERS}"`,
        `--release-notes "${RELEASE_NOTES}"`,
      ].join(' ');

      console.log(`  $ ${uploadCmd}`);
      const result = execSync(uploadCmd, { stdio: 'pipe', timeout: 120000 }).toString();
      console.log('  ' + result.slice(0, 400));
      console.log('\n  ✓ Upload complete! Testers will receive email notifications.');
      process.exit(0);
    } catch (e) {
      const err = (e.stderr?.toString() || e.message || '').slice(0, 300);
      console.log('  CLI upload failed:', err);
      console.log('  Falling back to browser upload...');
    }
  }

  // ── Step 3: Browser upload fallback ───────────────────────────────────────
  console.log('\n[3] Opening Firebase App Distribution in browser...');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('  ✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 80, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null, acceptDownloads: true });
    page    = await context.newPage();
  }

  await page.goto(DIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(4000);
  console.log('  URL:', page.url().slice(0, 80));

  // ── Step 4: Select or create Android app ──────────────────────────────────
  console.log('\n[4] Looking for Android app in App Distribution...');

  // Click Android app if there's a selector
  const appSelected = await page.evaluate(() => {
    const chips = [...document.querySelectorAll('mat-chip, [role="tab"], button')];
    const android = chips.find(c => /android/i.test(c.innerText || c.textContent || ''));
    if (android) { android.click(); return true; }
    return false;
  });
  if (appSelected) console.log('  ✓ Selected Android app');
  await wait(2000);

  // ── Step 5: Click "Get started" or "Upload" ───────────────────────────────
  console.log('\n[5] Finding upload button...');
  const uploadClicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button, a')];
    const btn = btns.find(b => /(upload|get started|new release|browse)/i.test(b.innerText || b.textContent || ''));
    if (btn) { btn.click(); return (btn.innerText || '').trim().slice(0, 40); }
    return null;
  });
  console.log(uploadClicked ? `  ✓ Clicked: ${uploadClicked}` : '  Trying file input...');
  await wait(2000);

  // ── Step 6: Upload the AAB file ───────────────────────────────────────────
  console.log('\n[6] Uploading AAB file...');
  try {
    const fileInput = await page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(aabPath);
    console.log('  ✓ AAB file set on input');
    await wait(3000);
  } catch {
    // Try drag-drop zone
    console.log('  File input not found — looking for drag/drop zone...');
    const dropZone = await page.evaluate(() => {
      const zones = [...document.querySelectorAll('[class*="drop"], [class*="upload"], mat-card')];
      return zones.length > 0;
    });
    if (dropZone) {
      console.log('  Found drop zone — you may need to drag the AAB manually:');
      console.log(`  File: ${aabPath}`);
    }
  }

  // ── Step 7: Add release notes and testers ─────────────────────────────────
  console.log('\n[7] Adding release notes...');
  await page.evaluate((notes) => {
    const ta = [...document.querySelectorAll('textarea')]
      .find(t => /(release|note)/i.test(t.getAttribute('aria-label') || t.placeholder || ''));
    if (ta) {
      ta.value = notes;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }, RELEASE_NOTES);
  await wait(1000);

  // ── Step 8: Submit / Distribute ───────────────────────────────────────────
  console.log('\n[8] Clicking Distribute / Next...');
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const btn = btns.find(b => /(distribute|next|continue|publish)/i.test(b.innerText || ''));
    if (btn) { btn.removeAttribute('disabled'); btn.click(); }
  });
  await wait(3000);

  console.log('\n=== Done ===');
  console.log(`  AAB: ${aabPath}`);
  console.log(`  Testers: ${TESTERS}`);
  console.log('  Check Firebase App Distribution console for upload status.');
  console.log(`  ${DIST_URL}`);
  console.log('\n  Keeping browser open on Firebase console...');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
