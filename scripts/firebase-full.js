/**
 * Bond — Full Firebase App Distribution setup and upload
 *
 * Run: node scripts\firebase-full.js
 *
 * Opens Firebase, switches to correct account, uploads APK, adds all testers.
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

const PROJECT_ID   = 'lakes-logistics-ffe6f';
const APP_ID       = '1:165820753433:android:9c541cc0a1e9e9a8c6ec88';
const APK_PATH     = 'C:\\Users\\12068\\AndroidStudioProjects\\3lakesDriver\\app\\release\\app-release.apk';
const RELEASE_URL  = `https://console.firebase.google.com/project/${PROJECT_ID}/appdistribution/app/android:com.threelakes.driver/releases/50facklgv6040`;
const DIST_URL     = `https://console.firebase.google.com/project/${PROJECT_ID}/appdistribution`;
const TESTERS      = [
  'nwtcinvestment@gmail.com',
  'info@3lakeslogistics.com',
  'raycece@yahoo.com',
  'goldiethemac@yahoo.com',
  'Savior45@yahoo.com',
  'talormoe14@yahoo.com',
];
const RELEASE_NOTES = '3 Lakes Driver v1.0 — Internal test build';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}

(async () => {
  console.log('=== Bond: Firebase App Distribution — Full Setup ===\n');
  console.log(`Project : ${PROJECT_ID}`);
  console.log(`APK     : ${APK_PATH}`);
  console.log(`Testers : ${TESTERS.length} people\n`);

  if (!fs.existsSync(APK_PATH)) {
    console.log(`✗ APK not found at: ${APK_PATH}`);
    process.exit(1);
  }

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

  // ── Step 1: Go to the release URL directly ────────────────────────────────
  console.log('[1] Opening Firebase App Distribution release...');
  await page.goto(RELEASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(5000);

  const url1 = page.url();
  console.log('  URL:', url1.slice(0, 90));

  // Check if we need to sign in or switch accounts
  if (url1.includes('accounts.google') || url1.includes('signin')) {
    console.log('\n  Need to sign in to Google...');
    await pause('  Please sign in with nwtcinvestment@gmail.com in Chrome, then press Enter... ');
    await page.goto(RELEASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(5000);
  }

  // Check if wrong account — look for account switcher
  const pageText = await page.evaluate(() => document.body.innerText);
  const hasApp = /appdistribution|app distribution|release|3 lakes/i.test(pageText);
  const hasPermError = /permission|access denied|don't have access|403/i.test(pageText);

  if (hasPermError || !hasApp) {
    console.log('\n  Wrong account or no access — switching to nwtcinvestment@gmail.com...');

    // Try account switcher in Firebase
    await page.evaluate(() => {
      // Look for profile/account button in Firebase header
      const btns = [...document.querySelectorAll('button, [aria-label]')];
      const profile = btns.find(b =>
        /account|profile|sign|user/i.test(b.getAttribute('aria-label') || b.className || '')
      );
      if (profile) profile.click();
    });
    await wait(2000);

    // Try switching account via Google account switcher
    await page.evaluate(() => {
      const links = [...document.querySelectorAll('a, button')];
      const switchBtn = links.find(l => /switch|add account|nwtcinvestment/i.test(l.innerText || ''));
      if (switchBtn) switchBtn.click();
    });
    await wait(3000);

    // Navigate to account switch URL for Google
    const switchUrl = `https://accounts.google.com/AccountChooser?continue=${encodeURIComponent(RELEASE_URL)}`;
    await page.goto(switchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(3000);

    // Click nwtcinvestment account if visible
    const accountClicked = await page.evaluate(() => {
      const divs = [...document.querySelectorAll('[data-email], [data-identifier], li, div')];
      const acc = divs.find(d =>
        /nwtcinvestment/i.test(d.getAttribute('data-email') || d.innerText || '')
      );
      if (acc) { acc.click(); return true; }
      return false;
    });

    if (!accountClicked) {
      console.log('\n╔══════════════════════════════════════════════════════════╗');
      console.log('║  ACTION REQUIRED: Switch Google account                  ║');
      console.log('║                                                          ║');
      console.log('║  In Chrome, sign in with:  nwtcinvestment@gmail.com     ║');
      console.log('║  This is the account that owns the Firebase project.    ║');
      console.log('║                                                          ║');
      console.log('╚══════════════════════════════════════════════════════════╝');
      await pause('  Press Enter after switching accounts in Chrome... ');
    }

    await page.goto(RELEASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(5000);
  }

  // ── Step 2: Confirm we can see the project ────────────────────────────────
  console.log('\n[2] Checking project access...');
  const text2 = await page.evaluate(() => document.body.innerText.slice(0, 500));
  console.log('  Page preview:', text2.replace(/\n/g, ' ').slice(0, 200));

  // ── Step 3: Upload new release via Firebase CLI ───────────────────────────
  console.log('\n[3] Uploading new release via Firebase CLI...');
  const uploadCmd = [
    `firebase appdistribution:distribute "${APK_PATH}"`,
    `--app "${APP_ID}"`,
    `--project ${PROJECT_ID}`,
    `--testers "${TESTERS.join(',')}"`,
    `--release-notes "${RELEASE_NOTES}"`,
  ].join(' ');

  console.log(`  $ ${uploadCmd}\n`);
  try {
    execSync(uploadCmd, { stdio: 'inherit', timeout: 180000 });
    console.log('\n  ✓ Upload complete!');
  } catch (e) {
    console.log('  CLI error:', (e.stderr?.toString() || e.message || '').slice(0, 200));
  }

  // ── Step 4: Navigate to the release in Firebase Console ───────────────────
  console.log('\n[4] Opening App Distribution in browser...');
  await page.goto(DIST_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(4000);
  console.log('  URL:', page.url().slice(0, 90));
  console.log('  Firebase App Distribution is open in Chrome.');
  console.log(`  Look for: "3 Lakes Driver" → Releases`);

  console.log('\n=== Summary ===');
  console.log(`  ✓ APK: ${APK_PATH}`);
  console.log(`  ✓ Testers: ${TESTERS.join(', ')}`);
  console.log(`  ✓ Console: ${DIST_URL}`);
  console.log('\n  Browser is open — you should see the release in Firebase now.');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
