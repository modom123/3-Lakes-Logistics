/**
 * Bond — Convert Play Console account to Organization + set name
 * Developer ID: 6880853885521839099
 * Run: node scripts/bond-play-account-setup.js
 */
const { execSync, spawnSync } = require('child_process');
const path = require('path');
function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install', { cwd: path.join(__dirname,'..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname,'..'), stdio: 'inherit' });
  spawnSync(process.execPath, [__filename, ...process.argv.slice(2)], { stdio: 'inherit', env: process.env });
  process.exit(0);
}
const { chromium } = require('playwright');

const DEV_ID   = '6880853885521839099';
const ORG_NAME = '3 Lakes Logistics';
const DUNS     = '145025174';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: path.join(__dirname, `acct-${name}.png`), fullPage: false });
  console.log('  Screenshot: scripts/acct-' + name + '.png');
}

(async () => {
  console.log('=== Bond: Play Console → Organization ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 150 });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Go directly to the /account page (we know this URL works) ─────────────
  console.log('\n[1/5] Opening Developer Account page...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/account`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(5000);
  console.log('  URL:', page.url().slice(0, 90));
  await shot(page, '1-account');

  // Print all clickable elements so we can see what's there
  const clickables = await page.evaluate(() =>
    [...document.querySelectorAll('a, button, [role="button"], [tabindex="0"]')]
      .map(e => e.innerText?.trim() || e.getAttribute('aria-label') || '')
      .filter(t => t && t.length > 1 && t.length < 80)
      .filter((v,i,a) => a.indexOf(v) === i)
  );
  console.log('  Clickable elements:', clickables.join(' | '));

  // ── Click "Account type" row to open the edit form ────────────────────────
  console.log('\n[2/5] Clicking Account type to change it...');

  // The "Account type" row has an arrow — click the row or the arrow
  const clicked = await page.evaluate(() => {
    // Find element containing "Account type"
    const all = [...document.querySelectorAll('*')];
    // Try the row/card containing "Account type" text
    const candidates = all.filter(e =>
      e.children.length < 5 &&
      e.innerText?.includes('Account type') &&
      e.innerText?.length < 200
    );
    if (candidates.length > 0) {
      // Click the last (most specific) match
      candidates[candidates.length - 1].click();
      return 'clicked Account type element';
    }
    return 'not found';
  });
  console.log('  JS click result:', clicked);
  await wait(3000);
  await shot(page, '2-after-acct-type-click');
  console.log('  URL:', page.url().slice(0, 90));

  // Check if a form/modal appeared or we navigated somewhere
  const afterText = await page.evaluate(() => document.body.innerText);
  console.log('  Page text:', afterText.slice(0, 400).replace(/\n+/g, ' '));

  // If we navigated to an edit page, look for the Organization option
  // Also try clicking an arrow_right_alt or edit button near "Account type"
  if (!afterText.includes('Organization') && !afterText.includes('organization')) {
    console.log('  Organization option not visible yet — trying arrow/edit button...');
    // Try clicking arrow_right_alt SVG or button near "Account type"
    await page.evaluate(() => {
      const els = [...document.querySelectorAll('*')];
      // Find the row that has "Account type" and click its last child (usually the arrow)
      const row = els.find(e =>
        e.innerText?.trim() === 'Account type' ||
        (e.innerText?.includes('Account type') && e.innerText?.includes('Personal') && e.innerText?.length < 100)
      );
      if (row) {
        // Click the row itself or its arrow child
        const arrow = row.querySelector('[class*="arrow"], mat-icon, [data-mat-icon-name]') || row;
        arrow.click();
      }
    });
    await wait(3000);
    await shot(page, '2b-after-arrow-click');
    console.log('  URL after arrow:', page.url().slice(0, 90));
  }

  // ── Select Organization ────────────────────────────────────────────────────
  console.log('\n[3/5] Selecting Organization...');
  const currentText = await page.evaluate(() => document.body.innerText);
  console.log('  Page text:', currentText.slice(0, 500).replace(/\n+/g, ' '));

  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"]')]
      .map(e => `${e.tagName} type=${e.type||''} value=${e.value||''} text="${e.innerText?.trim().slice(0,40)||''}" label="${e.getAttribute('aria-label')||''}"`)
  );
  console.log('  Inputs:', inputs.join('\n  '));

  // Click Organization option
  let orgFound = false;
  for (const sel of [
    'input[value="organization" i]',
    'input[value="ORGANIZATION"]',
    'mat-radio-button:has-text("Organization")',
    '[role="radio"]:has-text("Organization")',
    'label:has-text("Organization")',
    'text=Organization',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        await wait(1000);
        console.log('  Selected Organization via:', sel);
        orgFound = true;
        break;
      }
    } catch {}
  }
  if (!orgFound) console.log('  Organization option not found on this page');
  await shot(page, '3-org-select');

  // ── Fill name field ────────────────────────────────────────────────────────
  console.log('\n[4/5] Filling in org name and DUNS...');

  // Find name input (skip search boxes)
  const allInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of allInputs) {
    const label = await inp.getAttribute('aria-label').catch(() => '') || '';
    const placeholder = await inp.getAttribute('placeholder').catch(() => '') || '';
    const val = await inp.inputValue().catch(() => '');
    console.log(`  Input: label="${label}" placeholder="${placeholder}" value="${val}"`);
    if (label.toLowerCase().includes('search') || placeholder.toLowerCase().includes('search')) continue;
    if (label || placeholder || val) {
      await inp.click({ clickCount: 3 });
      await inp.fill(ORG_NAME);
      console.log('  Set name to:', ORG_NAME);
      break;
    }
  }

  // DUNS
  for (const sel of [
    'input[aria-label*="DUNS" i]',
    'input[placeholder*="DUNS" i]',
    'input[formcontrolname*="duns" i]',
    'input[id*="duns" i]',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click({ clickCount: 3 });
        await el.fill(DUNS);
        console.log('  Filled DUNS:', DUNS);
        break;
      }
    } catch {}
  }

  await shot(page, '4-before-save');

  // ── Save ──────────────────────────────────────────────────────────────────
  console.log('\n[5/5] Saving...');
  for (const sel of [
    'button:has-text("Save")',
    'button:has-text("Submit")',
    'button:has-text("Continue")',
    'button[type="submit"]:not([disabled])',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await wait(5000);
        console.log('  Clicked:', sel);
        break;
      }
    } catch {}
  }

  await shot(page, '5-done');
  const finalText = await page.evaluate(() => document.body.innerText);
  console.log('  Result:', finalText.slice(0, 300).replace(/\n+/g, ' '));

  await browser.close();
  console.log('\nDone.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
