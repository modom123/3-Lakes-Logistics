/**
 * Bond — Download AAB artifact from GitHub Actions
 *
 * Run: node scripts\download-aab.js
 *
 * Opens GitHub Actions, finds the latest successful Android build,
 * and downloads the AAB artifact to your Downloads folder.
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

const ACTIONS_URL   = 'https://github.com/modom123/3-Lakes-Logistics/actions/workflows/android-build.yml';
const ARTIFACT_URL  = 'https://github.com/modom123/3-Lakes-Logistics/actions/runs/26353604845/artifacts/7187569108';
const DOWNLOADS_DIR = path.join(os.homedir(), 'Downloads');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  console.log('=== Bond: Download Android AAB ===\n');
  console.log(`Saving to: ${DOWNLOADS_DIR}\n`);

  // Make sure Downloads dir exists
  if (!fs.existsSync(DOWNLOADS_DIR)) fs.mkdirSync(DOWNLOADS_DIR, { recursive: true });

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({
      headless: false,
      slowMo: 80,
      args: ['--start-maximized'],
      downloadsPath: DOWNLOADS_DIR,
    });
    context = await browser.newContext({
      viewport: null,
      acceptDownloads: true,
    });
    page = await context.newPage();
    console.log('Opened new browser window');
  }

  // Set download behavior
  try {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: DOWNLOADS_DIR,
      eventsEnabled: true,
    });
    console.log(`✓ Downloads → ${DOWNLOADS_DIR}`);
  } catch { /* CDP not always available on existing browser */ }

  // ── Step 1: Go to the specific artifact ──────────────────────────────────
  console.log('\n[1] Opening artifact download page...');
  await page.goto(ARTIFACT_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(3000);
  console.log('  URL:', page.url().slice(0, 90));

  // ── Step 2: Look for download button ─────────────────────────────────────
  console.log('\n[2] Looking for download link...');

  // GitHub artifact page has a direct download link
  const downloadStarted = await Promise.race([
    // Wait for a download to start
    page.waitForEvent('download', { timeout: 10000 })
      .then(dl => ({ type: 'download', dl }))
      .catch(() => null),
    // Or find and click a download button
    (async () => {
      await wait(2000);
      const clicked = await page.evaluate(() => {
        const links = [...document.querySelectorAll('a[href*="artifact"], a[download], a[href*="zip"]')];
        const btn = links[0];
        if (btn) { btn.click(); return btn.href || 'clicked'; }
        // Try any button with "download" text
        const btns = [...document.querySelectorAll('button, a')]
          .find(b => /download/i.test(b.innerText || b.textContent || ''));
        if (btns) { btns.click(); return 'download-btn'; }
        return null;
      });
      return clicked ? { type: 'clicked', target: clicked } : null;
    })(),
  ]);

  if (downloadStarted?.type === 'download') {
    const dl = downloadStarted.dl;
    console.log(`  ✓ Download started: ${dl.suggestedFilename()}`);
    const savePath = path.join(DOWNLOADS_DIR, dl.suggestedFilename());
    await dl.saveAs(savePath);
    console.log(`  ✓ Saved to: ${savePath}`);
  } else if (downloadStarted?.type === 'clicked') {
    console.log(`  ✓ Clicked download link — check your Downloads folder`);
    await wait(5000);
  } else {
    // Fall back: navigate to artifact list and try from there
    console.log('  Direct link not found — trying artifact list page...');
    await page.goto(ACTIONS_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(2000);

    // Click first successful run
    await page.evaluate(() => {
      const runs = [...document.querySelectorAll('a[href*="/runs/"]')]
        .find(a => document.querySelector('[aria-label="completed successfully"]'));
      if (runs) runs.click();
    });
    await wait(3000);

    // Scroll to artifacts section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await wait(2000);

    const artifactLink = await page.evaluate(() => {
      const links = [...document.querySelectorAll('a')]
        .find(a => /release/i.test(a.innerText || '') && /artifact/i.test(a.closest('section')?.innerText || ''));
      if (links) { links.click(); return links.href; }
      return null;
    });

    console.log(artifactLink
      ? `  ✓ Clicked artifact: ${artifactLink}`
      : '  ⚠ Could not find artifact — GitHub may require login or the run expired');
    await wait(5000);
  }

  // ── Step 3: Show what was downloaded ─────────────────────────────────────
  console.log('\n[3] Checking Downloads folder...');
  const files = fs.readdirSync(DOWNLOADS_DIR)
    .filter(f => /\.(aab|zip|apk)$/i.test(f))
    .sort((a, b) => {
      const ta = fs.statSync(path.join(DOWNLOADS_DIR, a)).mtimeMs;
      const tb = fs.statSync(path.join(DOWNLOADS_DIR, b)).mtimeMs;
      return tb - ta;
    });

  if (files.length > 0) {
    console.log('  Recent app files in Downloads:');
    files.slice(0, 5).forEach(f => {
      const size = (fs.statSync(path.join(DOWNLOADS_DIR, f)).size / 1024 / 1024).toFixed(1);
      console.log(`    ✓ ${f} (${size} MB)`);
    });
    console.log('\n  ✓ AAB is ready to upload to Google Play Console!');
    console.log('  Play Console → your app → Production → Create new release → Upload');
  } else {
    console.log('  No AAB/ZIP files found yet — check Downloads manually');
    console.log(`  Direct artifact URL: ${ARTIFACT_URL}`);
  }

  console.log('\n=== Done ===');
  console.log('Keeping browser open — you can upload the AAB to Play Console now.');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
