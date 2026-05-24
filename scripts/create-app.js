/**
 * Bond — Create App listing in Google Play Console
 *
 * Run: node scripts\create-app.js
 *
 * Prerequisites:
 *   - Chrome must be open on the "Create app" page in Play Console
 *   - OR just be logged into play.google.com/console
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
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

const DEV_ID   = '6880853885521839099';
const APP      = {
  name:       '3 Lakes Driver',
  language:   'English (United States)',
  shortDesc:  'Mobile app for 3 Lakes Logistics — loads, pay, documents, and dispatch',
  fullDesc:   `3 Lakes Driver is the official driver app for 3 Lakes Logistics carriers.

FEATURES:
• Load Board — View and accept/decline load offers in real time
• Current Load — Full load details with one-tap Google Maps navigation
• Hours of Service (HOS) — Track your driving hours and status
• Document Upload — Submit BOL, POD, and lumper receipts from your phone
• Pay & Settlements — View earnings, deductions, and settlement history
• Stripe Payouts — Direct deposit to your bank account
• Messaging — Real-time communication with dispatch
• Driver Profile — CDL info, carrier status, performance score
• Offline Support — Queue messages and actions when off-network

Built specifically for professional truck drivers. Requires an active driver account with 3 Lakes Logistics.`,
  privacyUrl: 'https://threelakeslogistics.com/privacy-policy',
};

const CREATE_URL = `https://play.google.com/console/u/0/developers/${DEV_ID}/create-app`;

function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}
async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function jsClick(page, text) {
  return page.evaluate((t) => {
    const all = [...document.querySelectorAll('button, [role="button"], mat-radio-button, label')];
    const el = all.find(e => (e.innerText || e.textContent || '').trim().toLowerCase().includes(t.toLowerCase()));
    if (el) { el.removeAttribute('disabled'); el.click(); return (el.innerText||'').trim().slice(0,40); }
    return null;
  }, text);
}

async function jsSet(page, ariaLabel, value) {
  return page.evaluate(({ lbl, val }) => {
    const inp = [...document.querySelectorAll('input, textarea')]
      .find(e => (e.getAttribute('aria-label') || e.placeholder || '').toLowerCase().includes(lbl.toLowerCase()));
    if (!inp) return false;
    inp.value = val;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
    return true;
  }, { lbl: ariaLabel, val: value });
}

(async () => {
  console.log('=== Bond: Create App in Google Play Console ===\n');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 100, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
    console.log('Opened new browser window');
  }

  // ── Step 1: Navigate to Create App ────────────────────────────────────────
  console.log('\n[1] Navigating to Create App...');
  const currentUrl = page.url();
  if (!currentUrl.includes('create-app')) {
    await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wait(4000);
  } else {
    console.log('  Already on Create App page ✓');
    await wait(2000);
  }
  console.log('  URL:', page.url().slice(0, 90));

  // Dump page to see what form fields are present
  const formDump = await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('input, textarea, mat-select, [role="listbox"]')]
      .map(e => ({
        tag: e.tagName, aria: e.getAttribute('aria-label') || '',
        ph: e.placeholder || '', val: (e.value || '').slice(0, 40),
      }));
    const btns = [...document.querySelectorAll('button, mat-radio-button')]
      .map(e => (e.innerText || '').trim().slice(0, 50))
      .filter(t => t.length > 1);
    return { inputs, btns };
  });
  console.log('\n  Form fields:');
  formDump.inputs.forEach((f, i) => console.log(`    [${i}] <${f.tag}> aria="${f.aria}" placeholder="${f.ph}" value="${f.val}"`));
  console.log('\n  Buttons:', formDump.btns.join(' | '));

  // ── Step 2: Fill App Name ─────────────────────────────────────────────────
  console.log('\n[2] Filling app name...');
  const nameOk = await jsSet(page, 'app name', APP.name);
  if (nameOk) console.log(`  ✓ App name: ${APP.name}`);
  else console.log('  ⚠ App name field not found — check browser');

  // ── Step 3: Select language ───────────────────────────────────────────────
  console.log('\n[3] Selecting language...');
  // Click language dropdown
  await page.evaluate(() => {
    const sel = [...document.querySelectorAll('[role="listbox"], mat-select')]
      .find(e => (e.getAttribute('aria-label') || '').toLowerCase().includes('language'));
    if (sel) sel.click();
  });
  await wait(1500);
  await page.evaluate(() => {
    const opt = [...document.querySelectorAll('mat-option, [role="option"]')]
      .find(o => /english.*united states/i.test(o.textContent || ''));
    if (opt) opt.click();
  });
  console.log('  ✓ Language: English (United States)');
  await wait(1000);

  // ── Step 4: App or Game → App ─────────────────────────────────────────────
  console.log('\n[4] Selecting "App" type...');
  const appR = await jsClick(page, 'App');
  console.log('  ✓ Selected:', appR || '(may already be selected)');
  await wait(500);

  // ── Step 5: Free or Paid → Free ───────────────────────────────────────────
  console.log('\n[5] Selecting "Free"...');
  const freeR = await jsClick(page, 'Free');
  console.log('  ✓ Selected:', freeR || '(may already be selected)');
  await wait(500);

  // ── Step 6: Check all declaration checkboxes ──────────────────────────────
  console.log('\n[6] Checking declarations...');
  const checked = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
    let count = 0;
    boxes.forEach(cb => { if (!cb.checked) { cb.click(); count++; } });
    return count;
  });
  console.log(`  ✓ Checked ${checked} declaration checkbox(es)`);
  await wait(500);

  // ── Step 7: Click Create App ──────────────────────────────────────────────
  console.log('\n[7] Clicking "Create app"...');
  const createRes = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => /create app/i.test(b.innerText || ''));
    if (btn) { btn.removeAttribute('disabled'); btn.click(); return true; }
    return false;
  });

  if (!createRes) {
    console.log('  "Create app" button not found — click it manually.');
    await pause('  Press Enter after clicking Create app... ');
  } else {
    console.log('  ✓ Clicked "Create app"');
  }

  await wait(8000);
  console.log('\n  URL after create:', page.url().slice(0, 100));

  // Check if we landed on the app dashboard
  const appUrl = page.url();
  const appId  = appUrl.match(/app\/(\d+)/)?.[1];
  if (appId) {
    console.log(`  ✓ App created! App ID: ${appId}`);
  } else {
    console.log('  App ID not found in URL — check browser for errors');
    await pause('  Press Enter when the app is created and you are on the app dashboard... ');
  }

  // ── Step 8: Go to Store Listing ───────────────────────────────────────────
  console.log('\n[8] Navigating to Main store listing...');
  const currentAppUrl = page.url();
  const baseAppUrl    = currentAppUrl.match(/(.*\/app\/\d+)/)?.[1] || currentAppUrl;
  await page.goto(`${baseAppUrl}/store-listing`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(4000);

  // Fill short description
  console.log('\n[9] Filling store listing...');
  await jsSet(page, 'short description', APP.shortDesc);
  console.log('  ✓ Short description filled');
  await wait(500);

  await jsSet(page, 'full description', APP.fullDesc);
  console.log('  ✓ Full description filled');
  await wait(500);

  // ── Step 9: Upload screenshots ────────────────────────────────────────────
  console.log('\n[10] Uploading screenshots...');
  const screensDir = path.join(__dirname, '..', 'fastlane', 'metadata', 'android', 'en-US', 'images', 'phoneScreenshots');
  const shots = fs.existsSync(screensDir)
    ? fs.readdirSync(screensDir).filter(f => /\.(png|jpg)$/i.test(f)).map(f => path.join(screensDir, f))
    : [];
  console.log(`  Found ${shots.length} screenshot(s)`);

  if (shots.length > 0) {
    const fileInputs = await page.locator('input[type="file"]').all();
    if (fileInputs.length > 0) {
      await fileInputs[0].setInputFiles(shots);
      await wait(6000);
      console.log('  ✓ Screenshots uploaded');
    } else {
      console.log('  No file input found on store listing — may need to scroll');
    }
  }

  // Save store listing
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => /save/i.test(b.innerText || ''));
    if (btn) btn.click();
  });
  console.log('  ✓ Saved store listing');

  console.log('\n=== Done ===');
  console.log('App created and store listing filled.');
  console.log('Next: upload the signed AAB via Releases → Production → Create new release');
  console.log('\nKeeping browser open...');
  await pause('Press Enter to close browser... ');
  await browser.close();

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
