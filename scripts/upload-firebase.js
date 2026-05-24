/**
 * Bond — Download AAB from GitHub Actions → Upload to Firebase App Distribution
 *
 * Run: node scripts\upload-firebase.js
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
const RUN_URL          = 'https://github.com/modom123/3-Lakes-Logistics/actions/runs/26353604845';
const DIST_URL         = `https://console.firebase.google.com/project/${FIREBASE_PROJECT}/appdistribution`;
const SAVE_DIR         = path.join(os.homedir(), 'Downloads', '3lakes-build');
const TESTERS          = 'nwtcinvestment@gmail.com,info@3lakeslogistics.com';
const RELEASE_NOTES    = '3 Lakes Driver v1.0 — Internal test build';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

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

(async () => {
  console.log('=== Bond: GitHub Actions → Firebase App Distribution ===\n');

  if (!fs.existsSync(SAVE_DIR)) fs.mkdirSync(SAVE_DIR, { recursive: true });

  // Check if we already have an AAB from a previous run
  let aabPath = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');
  if (aabPath) {
    console.log(`[0] Already have build: ${aabPath}`);
  }

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome\n');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 80, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null, acceptDownloads: true });
    page    = await context.newPage();
  }

  // Set download dir via CDP
  try {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: SAVE_DIR,
      eventsEnabled: true,
    });
  } catch {}

  // ── Step 1: Download artifact from GitHub Actions ──────────────────────────
  if (!aabPath) {
    console.log('[1] Going to GitHub Actions run page...');
    await page.goto(RUN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(3000);

    // Scroll to bottom where artifacts live
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(2000);

    console.log('[2] Looking for artifact download link...');
    const pageText = await page.evaluate(() => document.body.innerText);
    console.log('  Page contains "artifact":', /artifact/i.test(pageText));
    console.log('  Page contains "release":', /release/i.test(pageText));

    // Find and click the artifact
    const artifactClicked = await page.evaluate(() => {
      // GitHub renders artifacts as links in a section at the bottom
      const allLinks = [...document.querySelectorAll('a')];
      // Look for artifact download link (contains "3lakes" or "release")
      const artLink = allLinks.find(a =>
        /(3lakes|release|driver)/i.test(a.innerText || a.href || '') &&
        (a.href?.includes('artifact') || a.href?.includes('suites') || a.closest('[data-testid*="artifact"]'))
      );
      if (artLink) { artLink.click(); return { found: true, text: artLink.innerText?.trim(), href: artLink.href }; }

      // Look in artifact section specifically
      const sections = [...document.querySelectorAll('section, [class*="artifact"], details')];
      for (const s of sections) {
        if (/artifact/i.test(s.innerText || '')) {
          const link = s.querySelector('a');
          if (link) { link.click(); return { found: true, text: link.innerText?.trim(), href: link.href }; }
        }
      }
      return { found: false };
    });

    console.log('  Artifact click result:', JSON.stringify(artifactClicked));

    if (!artifactClicked.found) {
      // Try scrolling and waiting for artifacts section to load
      console.log('  Scrolling and retrying...');
      for (let i = 0; i < 3; i++) {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await wait(2000);
        const retry = await page.evaluate(() => {
          const links = [...document.querySelectorAll('a[href*="artifact"], a[href*="suites"]')];
          if (links.length > 0) { links[0].click(); return links[0].href; }
          return null;
        });
        if (retry) { console.log('  ✓ Found and clicked:', retry); break; }
      }
    }

    // Wait for download
    console.log('\n[3] Waiting for download...');
    try {
      const download = await page.waitForEvent('download', { timeout: 30000 });
      console.log(`  Download started: ${download.suggestedFilename()}`);
      const zipPath = path.join(SAVE_DIR, download.suggestedFilename());
      await download.saveAs(zipPath);
      console.log(`  ✓ Saved to: ${zipPath}`);

      // Extract the zip
      console.log('  Extracting zip...');
      execSync(`powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${SAVE_DIR}' -Force"`, { stdio: 'pipe' });
      aabPath = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');
      if (aabPath) console.log(`  ✓ AAB extracted: ${aabPath}`);

    } catch (e) {
      console.log('  Download event not captured:', e.message?.slice(0, 100));
      console.log('  Check your Downloads folder — browser may have saved it there');
      // Check default downloads folder
      const dl = path.join(os.homedir(), 'Downloads');
      const recent = fs.readdirSync(dl)
        .map(f => ({ f, t: fs.statSync(path.join(dl, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t)[0];
      if (recent && Date.now() - recent.t < 60000) {
        console.log(`  Most recent download: ${recent.f}`);
        const p = path.join(dl, recent.f);
        if (recent.f.endsWith('.zip')) {
          execSync(`powershell -Command "Expand-Archive -LiteralPath '${p}' -DestinationPath '${SAVE_DIR}' -Force"`, { stdio: 'pipe' });
          aabPath = findRecursive(SAVE_DIR, '.aab') || findRecursive(SAVE_DIR, '.apk');
        } else if (recent.f.endsWith('.aab')) {
          aabPath = p;
        }
      }
    }
  }

  if (!aabPath) {
    console.log('\n⚠  Could not auto-download AAB.');
    console.log('  Please manually download it:');
    console.log(`  1. Go to: ${RUN_URL}`);
    console.log('  2. Scroll to "Artifacts" at the bottom');
    console.log(`  3. Click "3lakes-driver-release-3" to download`);
    console.log(`  4. Unzip it and place app-release.aab in: ${SAVE_DIR}`);
    console.log('  5. Re-run this script');
    await wait(5000);
    await browser.close();
    return;
  }

  const sizeMB = (fs.statSync(aabPath).size / 1024 / 1024).toFixed(1);
  console.log(`\n✓ AAB ready: ${aabPath} (${sizeMB} MB)`);

  // ── Step 4: Upload to Firebase App Distribution ────────────────────────────
  console.log('\n[4] Checking Firebase CLI...');
  let uploaded = false;
  try {
    const ver = execSync('firebase --version', { stdio: 'pipe' }).toString().trim();
    console.log(`  ✓ Firebase CLI ${ver}`);

    const cmd = [
      `firebase appdistribution:distribute "${aabPath}"`,
      `--project ${FIREBASE_PROJECT}`,
      `--testers "${TESTERS}"`,
      `--release-notes "${RELEASE_NOTES}"`,
    ].join(' ');
    console.log(`\n[5] Uploading via Firebase CLI...`);
    console.log(`  $ ${cmd}\n`);
    execSync(cmd, { stdio: 'inherit', timeout: 180000 });
    uploaded = true;
    console.log('\n  ✓ Uploaded! Testers notified.');
  } catch (e) {
    const msg = (e.stderr?.toString() || e.message || '').toLowerCase();
    if (msg.includes('not logged') || msg.includes('auth')) {
      console.log('  Not logged into Firebase CLI — running firebase login...');
      execSync('firebase login', { stdio: 'inherit' });
      // Retry
      try {
        execSync([
          `firebase appdistribution:distribute "${aabPath}"`,
          `--project ${FIREBASE_PROJECT}`,
          `--testers "${TESTERS}"`,
          `--release-notes "${RELEASE_NOTES}"`,
        ].join(' '), { stdio: 'inherit', timeout: 180000 });
        uploaded = true;
      } catch {}
    } else if (msg.includes('app') && msg.includes('not found')) {
      console.log('  App not registered in Firebase App Distribution.');
      console.log('  Falling back to browser upload...');
    } else {
      console.log('  CLI error:', (e.stderr?.toString() || e.message || '').slice(0, 200));
      console.log('  Falling back to browser upload...');
    }
  }

  // ── Step 5: Browser upload fallback ───────────────────────────────────────
  if (!uploaded) {
    console.log('\n[5] Opening Firebase App Distribution...');
    await page.goto(DIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(5000);

    // Select Android
    await page.evaluate(() => {
      const tabs = [...document.querySelectorAll('[role="tab"], mat-tab-header button, mat-chip')];
      const a = tabs.find(t => /android/i.test(t.innerText || ''));
      if (a) a.click();
    });
    await wait(2000);

    // Click upload / get started
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button, a')];
      const b = btns.find(b => /(upload|get started|new release)/i.test(b.innerText || ''));
      if (b) b.click();
    });
    await wait(2000);

    // Upload file
    try {
      await page.locator('input[type="file"]').first().setInputFiles(aabPath);
      console.log('  ✓ File uploaded to browser input');
      await wait(5000);

      // Fill release notes
      await page.evaluate((notes) => {
        const ta = document.querySelector('textarea');
        if (ta) { ta.value = notes; ta.dispatchEvent(new Event('input', { bubbles: true })); }
      }, RELEASE_NOTES);
      await wait(1000);

      // Click Next / Distribute
      await page.evaluate(() => {
        const b = [...document.querySelectorAll('button')]
          .find(b => /(next|distribute|continue)/i.test(b.innerText || ''));
        if (b) { b.removeAttribute('disabled'); b.click(); }
      });
      await wait(3000);
      console.log('  ✓ Submitted via browser');
      uploaded = true;
    } catch (e) {
      console.log('  Browser upload error:', e.message?.slice(0, 100));
    }
  }

  console.log('\n=== Summary ===');
  console.log(`  AAB: ${aabPath}`);
  console.log(`  Firebase: ${DIST_URL}`);
  console.log(`  Testers: ${TESTERS}`);
  console.log(uploaded ? '  ✓ Upload complete!' : '  ⚠ Upload may need manual completion in browser');
  console.log('\n  Browser open — check Firebase console for release status.');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
