/**
 * Bond — Create App listing in Google Play Console
 *
 * Run: node scripts\create-app.js
 *
 * Prerequisites:
 *   - Chrome must be open and logged into play.google.com/console
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
    rl.question(msg, ans => { rl.close(); resolve(ans ? ans.trim() : ''); });
  });
}
async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// Fill an input by its position among all visible inputs on the form (0-based)
async function fillByIndex(page, idx, value, selector = 'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]), textarea') {
  return page.evaluate(({ idx, value, selector }) => {
    const inputs = [...document.querySelectorAll(selector)].filter(e => {
      const s = window.getComputedStyle(e);
      return s.display !== 'none' && s.visibility !== 'hidden' && e.offsetParent !== null;
    });
    const inp = inputs[idx];
    if (!inp) return false;
    inp.focus();
    inp.value = value;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
    return true;
  }, { idx, value, selector });
}

// Fill by aria-label or placeholder (case-insensitive substring)
async function jsSet(page, label, value) {
  return page.evaluate(({ lbl, val }) => {
    const inp = [...document.querySelectorAll('input, textarea')]
      .find(e => {
        const a = (e.getAttribute('aria-label') || e.placeholder || e.getAttribute('formcontrolname') || '').toLowerCase();
        return a.includes(lbl.toLowerCase());
      });
    if (!inp) return false;
    inp.focus();
    inp.value = val;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
    return true;
  }, { lbl: label, val: value });
}

async function jsClick(page, text, exact = false) {
  return page.evaluate(({ t, exact }) => {
    const all = [...document.querySelectorAll('button, [role="button"], mat-radio-button, label')];
    const el = all.find(e => {
      const txt = (e.innerText || e.textContent || '').trim();
      return exact ? txt === t : txt.toLowerCase().includes(t.toLowerCase());
    });
    if (el) { el.removeAttribute('disabled'); el.click(); return (el.innerText || '').trim().slice(0, 40); }
    return null;
  }, { t: text, exact });
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
  console.log('\n[1] Navigating to Create App page...');
  await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);

  const currentUrl = page.url();
  console.log('  URL:', currentUrl.slice(0, 100));

  // Check if redirected to verification
  if (currentUrl.includes('android-developer-verification') || currentUrl.includes('developer-details')) {
    console.log('\n  ⚠  Google is requiring account verification before you can create an app.');
    console.log('  This means the account type change to "Organization" must be completed first.');
    console.log('\n  What to do:');
    console.log('  1. In the browser, go to: Account → Developer details → Change account type');
    console.log('  2. Fill in the Organization details and complete email verification manually');
    console.log('  3. Once account type is changed, run this script again');
    console.log('\n  Alternatively, contact Google Play support:');
    console.log('  https://support.google.com/googleplay/android-developer/contact/publishing');
    await pause('\n  Press Enter to close... ');
    await browser.close();
    return;
  }

  // Dump form to understand the page structure
  const formDump = await page.evaluate(() => {
    const inputs = [...document.querySelectorAll('input, textarea')]
      .filter(e => {
        const s = window.getComputedStyle(e);
        return s.display !== 'none' && s.visibility !== 'hidden';
      })
      .map((e, i) => ({
        i, tag: e.tagName, type: e.type || '',
        aria: e.getAttribute('aria-label') || '',
        ph: e.placeholder || '',
        fcn: e.getAttribute('formcontrolname') || '',
        val: (e.value || '').slice(0, 40),
      }));
    const btns = [...document.querySelectorAll('button, mat-radio-button')]
      .map(e => (e.innerText || '').trim().slice(0, 50))
      .filter(t => t.length > 1);
    return { inputs, btns };
  });

  console.log('\n  Visible form fields:');
  formDump.inputs.forEach(f =>
    console.log(`    [${f.i}] <${f.tag} type="${f.type}"> aria="${f.aria}" placeholder="${f.ph}" formcontrolname="${f.fcn}" value="${f.val}"`)
  );
  console.log('\n  Buttons:', formDump.btns.slice(0, 10).join(' | '));

  // ── Step 2: Fill App Name ─────────────────────────────────────────────────
  console.log('\n[2] Filling app name...');

  // Try multiple approaches
  let nameOk = await jsSet(page, 'app name', APP.name);
  if (!nameOk) nameOk = await jsSet(page, 'appName', APP.name);
  if (!nameOk) nameOk = await jsSet(page, 'name', APP.name);
  if (!nameOk) {
    // Fill the first non-search, non-hidden text input on the page
    nameOk = await page.evaluate((val) => {
      const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')].filter(e => {
        const aria = e.getAttribute('aria-label') || '';
        if (aria.toLowerCase().includes('search')) return false;
        const s = window.getComputedStyle(e);
        return s.display !== 'none' && s.visibility !== 'hidden' && e.offsetParent !== null;
      });
      // Skip the search field (index 0), use the next one
      const inp = inputs.find(e => !(e.getAttribute('aria-label') || '').toLowerCase().includes('search'));
      if (!inp) return false;
      inp.focus();
      inp.value = val;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
      return true;
    }, APP.name);
  }

  if (nameOk) console.log(`  ✓ App name: ${APP.name}`);
  else {
    console.log('  ⚠ Could not auto-fill app name — please type it manually in the browser');
    await pause('  Type the app name in Chrome, then press Enter here to continue... ');
  }
  await wait(800);

  // ── Step 3: Select language ───────────────────────────────────────────────
  console.log('\n[3] Selecting language...');
  await page.evaluate(() => {
    const sel = [...document.querySelectorAll('[role="listbox"], mat-select')]
      .find(e => (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.id || '').toLowerCase().includes('language'));
    if (sel) sel.click();
  });
  await wait(1500);
  const langSet = await page.evaluate(() => {
    const opt = [...document.querySelectorAll('mat-option, [role="option"]')]
      .find(o => /english.*united states/i.test(o.textContent || ''));
    if (opt) { opt.click(); return true; }
    return false;
  });
  console.log(langSet ? '  ✓ Language: English (United States)' : '  (language already set or not found)');
  await wait(800);

  // ── Step 4: Select "App" (not Game) ──────────────────────────────────────
  console.log('\n[4] Selecting "App" type...');
  const appSet = await page.evaluate(() => {
    // Look for mat-radio-button with exact text "App"
    const radios = [...document.querySelectorAll('mat-radio-button, [role="radio"]')];
    const appRadio = radios.find(r => /^app$/i.test((r.innerText || r.textContent || '').trim()));
    if (appRadio) { appRadio.click(); return 'App'; }
    // Fallback: label containing only "App"
    const labels = [...document.querySelectorAll('label')];
    const appLabel = labels.find(l => /^app$/i.test((l.innerText || '').trim()));
    if (appLabel) { appLabel.click(); return 'App (label)'; }
    return null;
  });
  console.log(appSet ? `  ✓ Selected: ${appSet}` : '  (may already be selected)');
  await wait(500);

  // ── Step 5: Free ──────────────────────────────────────────────────────────
  console.log('\n[5] Selecting "Free"...');
  const freeSet = await page.evaluate(() => {
    const radios = [...document.querySelectorAll('mat-radio-button, [role="radio"]')];
    const r = radios.find(e => /^free$/i.test((e.innerText || e.textContent || '').trim()));
    if (r) { r.click(); return true; }
    return false;
  });
  console.log(freeSet ? '  ✓ Free selected' : '  (may already be selected)');
  await wait(500);

  // ── Step 6: Checkboxes ───────────────────────────────────────────────────
  console.log('\n[6] Checking declaration checkboxes...');
  const checked = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll('input[type="checkbox"]')];
    let count = 0;
    boxes.forEach(cb => { if (!cb.checked) { cb.click(); count++; } });
    return count;
  });
  console.log(`  ✓ Checked ${checked} checkbox(es)`);
  await wait(500);

  // ── Step 7: Create app ───────────────────────────────────────────────────
  console.log('\n[7] Clicking "Create app"...');
  const created = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => /create\s*app/i.test(b.innerText || ''));
    if (btn) {
      btn.removeAttribute('disabled');
      btn.click();
      return true;
    }
    return false;
  });

  if (!created) {
    console.log('  "Create app" button not found — click it manually in Chrome.');
    await pause('  Press Enter after the app is created... ');
  } else {
    console.log('  ✓ Clicked "Create app" — waiting for navigation...');
    await wait(8000);
  }

  const postUrl = page.url();
  console.log('\n  URL after create:', postUrl.slice(0, 100));

  if (postUrl.includes('android-developer-verification')) {
    console.log('\n  ⚠  Redirected to account verification again.');
    console.log('  Google requires the Organization account type change before creating apps.');
    console.log('  Complete the account type change in Play Console, then re-run this script.');
    await pause('\n  Press Enter to close... ');
    await browser.close();
    return;
  }

  const appId = postUrl.match(/app\/(\d+)/)?.[1];
  if (appId) {
    console.log(`  ✓ App created! App ID: ${appId}`);
  } else {
    await pause('  Press Enter once you are on the app dashboard... ');
  }

  // ── Step 8: Store listing ────────────────────────────────────────────────
  console.log('\n[8] Navigating to Main store listing...');
  const appUrl     = page.url();
  const baseAppUrl = appUrl.match(/(.*\/app\/\d+)/)?.[1] || appUrl;
  await page.goto(`${baseAppUrl}/store-listing`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(4000);

  console.log('\n[9] Filling store listing...');
  await jsSet(page, 'short description', APP.shortDesc);
  console.log('  ✓ Short description filled');
  await wait(500);

  await jsSet(page, 'full description', APP.fullDesc);
  console.log('  ✓ Full description filled');
  await wait(500);

  // ── Step 9: Upload screenshots one by one ────────────────────────────────
  console.log('\n[10] Uploading screenshots...');
  const screensDir = path.join(__dirname, '..', 'fastlane', 'metadata', 'android', 'en-US', 'images', 'phoneScreenshots');
  const shots = fs.existsSync(screensDir)
    ? fs.readdirSync(screensDir).filter(f => /\.(png|jpg)$/i.test(f)).map(f => path.join(screensDir, f))
    : [];
  console.log(`  Found ${shots.length} screenshot(s)`);

  if (shots.length > 0) {
    const fileInputs = await page.locator('input[type="file"]').all();
    console.log(`  Found ${fileInputs.length} file input(s)`);
    if (fileInputs.length > 0) {
      for (let i = 0; i < shots.length; i++) {
        try {
          await fileInputs[0].setInputFiles(shots[i]);
          console.log(`  ✓ Uploaded: ${path.basename(shots[i])}`);
          await wait(3000);
        } catch (e) {
          console.log(`  ⚠ Could not upload ${path.basename(shots[i])}: ${e.message.slice(0, 80)}`);
        }
      }
    } else {
      console.log('  No file input found — may need to scroll to screenshot section');
    }
  }

  // Save
  await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => /^save$/i.test((b.innerText || '').trim()));
    if (btn) btn.click();
  });
  await wait(2000);
  console.log('  ✓ Saved store listing');

  console.log('\n=== Done ===');
  console.log('App listing created and store details filled.');
  await pause('\nPress Enter to close browser... ');
  await browser.close();

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
