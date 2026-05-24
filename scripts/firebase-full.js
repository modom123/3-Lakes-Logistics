/**
 * Bond — Download AAB from GitHub Actions → Upload to Firebase
 * Run: node scripts\firebase-full.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const os   = require('os');

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
const SAVE_DIR      = path.join(os.homedir(), 'Downloads', '3lakes-new');
const DOWNLOADS_DIR = path.join(os.homedir(), 'Downloads');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

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

function watchForNewFile(dir, timeoutMs = 60000) {
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
  console.log('=== Bond: GitHub Actions → Firebase App Distribution ===\n');

  if (!fs.existsSync(SAVE_DIR)) fs.mkdirSync(SAVE_DIR, { recursive: true });

  // Use already-extracted file if available
  let buildFile = findFile(SAVE_DIR, '.aab', '.apk');

  // Connect to existing Chrome or launch new one
  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome\n');
  } catch {
    console.log('  Chrome CDP not available — launching new browser.');
    console.log('  You will need to sign into GitHub when it opens.\n');
    browser = await chromium.launch({ headless: false, slowMo: 60, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null, acceptDownloads: true });
    page    = await context.newPage();
  }

  // ── Step 1: Download artifact ──────────────────────────────────────────────
  if (!buildFile) {
    console.log('[1] Navigating to GitHub Actions run...');
    await page.goto(RUN_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(3000);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(2000);

    console.log('[2] Finding artifact download link...');

    // GitHub renders artifact links — find one matching our artifact
    const artifactClicked = await page.evaluate(() => {
      // Artifact section links on GitHub Actions run page
      const links = [...document.querySelectorAll('a')];
      const art = links.find(a =>
        /3lakes.*release|release.*3lakes/i.test(a.innerText || a.textContent || a.href || '')
      );
      if (art) { art.click(); return { found: true, text: art.innerText?.trim(), href: art.href }; }

      // Try any link in an artifacts section
      const sections = [...document.querySelectorAll('details, section, [class*="artifact"]')];
      for (const s of sections) {
        if (/artifact/i.test(s.innerText || '')) {
          const link = s.querySelector('a');
          if (link) { link.click(); return { found: true, text: link.innerText?.trim(), href: link.href }; }
        }
      }
      return { found: false, bodySnippet: document.body.innerText.slice(0, 300) };
    });

    console.log('  Result:', JSON.stringify(artifactClicked).slice(0, 120));

    if (!artifactClicked.found) {
      // Dump all links for debugging
      const links = await page.evaluate(() =>
        [...document.querySelectorAll('a')]
          .map(a => ({ text: (a.innerText||'').trim().slice(0,40), href: (a.href||'').slice(0,80) }))
          .filter(l => l.text || l.href)
          .slice(0, 30)
      );
      console.log('  All links on page:');
      links.forEach(l => console.log(`    "${l.text}" → ${l.href}`));
    }

    // Watch for the download to land in Downloads folder
    console.log('\n  Watching Downloads folder for artifact zip...');
    let zipPath;
    try {
      zipPath = await watchForNewFile(DOWNLOADS_DIR, 30000);
      console.log(`  ✓ Download: ${path.basename(zipPath)}`);
    } catch {
      console.log('  Download not auto-detected in 30s.');
      // Check most recent zip anyway
      const recent = fs.readdirSync(DOWNLOADS_DIR)
        .filter(f => /\.zip$/i.test(f))
        .map(f => ({ f, t: fs.statSync(path.join(DOWNLOADS_DIR, f)).mtimeMs }))
        .sort((a, b) => b.t - a.t)[0];
      if (recent && Date.now() - recent.t < 120000) {
        zipPath = path.join(DOWNLOADS_DIR, recent.f);
        console.log(`  Using recent zip: ${recent.f}`);
      }
    }

    if (zipPath) {
      console.log('  Extracting zip...');
      execSync(
        `powershell -Command "Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${SAVE_DIR}' -Force"`,
        { stdio: 'pipe', timeout: 30000 }
      );
      buildFile = findFile(SAVE_DIR, '.aab', '.apk');
      if (buildFile) console.log(`  ✓ Extracted: ${buildFile}`);
    }
  } else {
    console.log(`[1] Using cached build: ${buildFile}`);
  }

  if (!buildFile) {
    console.log('\n✗ Could not get the build file.');
    console.log(`  Go to: ${RUN_URL}`);
    console.log('  Scroll to Artifacts → click "3lakes-driver-release-3"');
    console.log(`  Then unzip into: ${SAVE_DIR}`);
    await browser.close();
    return;
  }

  const sizeMB = (fs.statSync(buildFile).size / 1024 / 1024).toFixed(1);
  console.log(`\n✓ Build: ${path.basename(buildFile)} (${sizeMB} MB)`);

  // ── Step 2: Upload via Firebase CLI ───────────────────────────────────────
  console.log('\n[3] Uploading to Firebase App Distribution...');
  const cmd = [
    `firebase appdistribution:distribute "${buildFile}"`,
    `--app "${APP_ID}"`,
    `--project ${PROJECT_ID}`,
    `--testers "${TESTERS}"`,
    `--release-notes "${RELEASE_NOTES}"`,
  ].join(' ');
  console.log(`  $ ${cmd}\n`);
  execSync(cmd, { stdio: 'inherit', timeout: 180000 });

  // ── Step 3: Open Firebase console ─────────────────────────────────────────
  console.log('\n[4] Opening Firebase App Distribution...');
  await page.goto(
    `https://console.firebase.google.com/u/1/project/${PROJECT_ID}/appdistribution`,
    { waitUntil: 'domcontentloaded', timeout: 30000 }
  );
  await wait(3000);

  console.log('\n=== Done ===');
  console.log(`  ✓ New build uploaded and all ${TESTERS.split(',').length} testers notified`);

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
