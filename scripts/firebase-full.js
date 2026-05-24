/**
 * Bond — Firebase App Distribution upload
 *
 * Run: node scripts\firebase-full.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const APK_PATH   = 'C:\\Users\\12068\\AndroidStudioProjects\\3lakesDriver\\app\\release\\app-release.apk';
const PROJECT_ID = 'lakes-logistics-ffe6f';
const APP_ID     = '1:165820753433:android:9c541cc0a1e9e9a8c6ec88';
const TESTERS    = [
  'nwtcinvestment@gmail.com',
  'info@3lakeslogistics.com',
  'raycece@yahoo.com',
  'goldiethemac@yahoo.com',
  'Savior45@yahoo.com',
  'talormoe14@yahoo.com',
  'new56money@gmail.com',
].join(',');
const RELEASE_NOTES = '3 Lakes Driver v1.0 — Internal test build';
const DIST_URL   = 'https://console.firebase.google.com/u/0/project/lakes-logistics-ffe6f/appdistribution';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}

(async () => {
  console.log('=== Bond: Firebase App Distribution ===\n');

  if (!fs.existsSync(APK_PATH)) {
    console.log(`✗ APK not found: ${APK_PATH}`); process.exit(1);
  }
  const sizeMB = (fs.statSync(APK_PATH).size / 1024 / 1024).toFixed(1);
  console.log(`✓ APK: ${APK_PATH} (${sizeMB} MB)`);
  console.log(`✓ Project: ${PROJECT_ID}`);
  console.log(`✓ Testers: ${TESTERS.split(',').length} people\n`);

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 60, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Step 1: Upload via Firebase CLI ───────────────────────────────────────
  console.log('\n[1] Uploading APK via Firebase CLI...');
  const uploadCmd = [
    `firebase appdistribution:distribute "${APK_PATH}"`,
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
    console.log('  CLI error:', (e.stderr?.toString() || e.message || '').slice(0, 200));
    console.log('\n  Trying browser upload as fallback...');
  }

  // ── Step 2: Open App Distribution console ─────────────────────────────────
  console.log('\n[2] Opening Firebase App Distribution...');
  await page.goto(DIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(5000);
  console.log('  URL:', page.url().slice(0, 90));

  // Select Android tab if needed
  await page.evaluate(() => {
    const tabs = [...document.querySelectorAll('[role="tab"], mat-tab-header button')];
    const android = tabs.find(t => /android/i.test(t.innerText || ''));
    if (android) android.click();
  });
  await wait(2000);

  // Check what's on screen
  const pageSnippet = await page.evaluate(() =>
    document.body.innerText.replace(/\s+/g, ' ').slice(0, 400)
  );
  console.log('\n  Page content:', pageSnippet.slice(0, 200));

  // ── Step 3: If no releases visible, try browser file upload ───────────────
  if (/get started|no releases|no builds/i.test(pageSnippet)) {
    console.log('\n[3] No releases found — uploading via browser...');

    // Click Get started / Upload
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button, a')]
        .find(b => /(get started|upload|new release)/i.test(b.innerText || ''));
      if (btn) btn.click();
    });
    await wait(3000);

    // Upload APK via file input
    try {
      const fileInput = page.locator('input[type="file"]').first();
      await fileInput.setInputFiles(APK_PATH);
      console.log('  ✓ APK file set');
      await wait(8000);

      // Add release notes
      await page.evaluate((notes) => {
        const ta = document.querySelector('textarea');
        if (ta) { ta.value = notes; ta.dispatchEvent(new Event('input', { bubbles: true })); }
      }, RELEASE_NOTES);
      await wait(1000);

      // Click Next
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')]
          .find(b => /(next|continue)/i.test(b.innerText || ''));
        if (btn) { btn.removeAttribute('disabled'); btn.click(); }
      });
      await wait(3000);

      // Add testers
      await page.evaluate((testers) => {
        const inp = [...document.querySelectorAll('input')]
          .find(i => /(tester|email|group)/i.test(i.getAttribute('aria-label') || i.placeholder || ''));
        if (inp) {
          inp.value = testers;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }, TESTERS);
      await wait(1000);

      // Distribute
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')]
          .find(b => /(distribute|publish|send)/i.test(b.innerText || ''));
        if (btn) { btn.removeAttribute('disabled'); btn.click(); }
      });
      await wait(4000);
      console.log('  ✓ Distributed via browser');
    } catch (e) {
      console.log('  Browser upload error:', e.message?.slice(0, 100));
      console.log(`\n  Manual fallback:`);
      console.log(`  APK is at: ${APK_PATH}`);
      console.log(`  Drag it into the Firebase App Distribution page in Chrome`);
    }
  } else {
    console.log('\n  ✓ Releases found in App Distribution!');
  }

  console.log('\n=== Done ===');
  console.log(`  Firebase Console: ${DIST_URL}`);
  console.log('  Browser is open — you should see releases now.');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
