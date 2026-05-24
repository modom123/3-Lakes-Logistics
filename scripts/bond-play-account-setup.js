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

  // ── Go to /account page ───────────────────────────────────────────────────
  console.log('[1/4] Opening account page...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/account`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(5000);
  await shot(page, '1-account');

  // ── Click "About you" row (has arrow_right_alt, leads to edit form) ───────
  console.log('[2/4] Clicking "About you" row...');

  // Use JS to find and click the "About you" element (it's a clickable row/card)
  const clicked = await page.evaluate(() => {
    const all = [...document.querySelectorAll('a, button, [role="button"], [tabindex="0"], [class*="row"], [class*="card"], [class*="item"], [class*="link"]')];
    // Find element whose text contains "About you" but is small (not the whole page)
    const el = all.find(e => {
      const t = e.innerText?.trim();
      return t && t.includes('About you') && t.length < 300;
    });
    if (el) { el.click(); return el.tagName + ' / ' + el.className.slice(0, 60); }

    // Fallback: find ANY element with exactly "About you" text
    const all2 = [...document.querySelectorAll('*')];
    const el2 = all2.find(e => e.childElementCount < 4 && e.innerText?.trim().startsWith('About you'));
    if (el2) { el2.click(); return 'fallback: ' + el2.tagName + ' / ' + el2.className.slice(0, 60); }
    return 'not found';
  });
  console.log('  Clicked:', clicked);
  await wait(4000);
  console.log('  URL:', page.url().slice(0, 90));
  await shot(page, '2-about-you');

  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('  Page text:', pageText.slice(0, 500).replace(/\n+/g, ' '));

  // ── If we're on an edit page, handle it ───────────────────────────────────
  console.log('[3/4] Looking for account type and name fields...');

  // Log all inputs
  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select, textarea')]
      .map(e => `${e.tagName} type=${e.type||''} value="${e.value||''}" label="${e.getAttribute('aria-label')||''}" placeholder="${e.getAttribute('placeholder')||''}" text="${e.innerText?.trim().slice(0,40)||''}"`)
  );
  console.log('  Inputs:\n  ' + inputs.join('\n  '));

  // Log all buttons
  const btns = await page.evaluate(() =>
    [...document.querySelectorAll('button, [role="button"]')]
      .map(e => e.innerText?.trim() || e.getAttribute('aria-label') || '')
      .filter(t => t && t.length < 60)
  );
  console.log('  Buttons:', btns.join(' | '));

  // Try to select Organization
  let orgSelected = false;
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
        await wait(1500);
        console.log('  Selected Organization via:', sel);
        orgSelected = true;
        break;
      }
    } catch {}
  }

  // Fill developer/org name
  const allInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of allInputs) {
    const label = await inp.getAttribute('aria-label').catch(() => '') || '';
    const placeholder = await inp.getAttribute('placeholder').catch(() => '') || '';
    const val = await inp.inputValue().catch(() => '');
    if (label.toLowerCase().includes('search') || placeholder.toLowerCase().includes('search')) continue;
    if (label || placeholder || val) {
      console.log(`  Filling: label="${label}" placeholder="${placeholder}" current="${val}"`);
      await inp.click({ clickCount: 3 });
      await inp.fill(ORG_NAME);
      break;
    }
  }

  // Fill DUNS if present
  for (const sel of ['input[aria-label*="DUNS" i]','input[placeholder*="DUNS" i]','input[formcontrolname*="duns" i]']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click({ clickCount: 3 }); await el.fill(DUNS);
        console.log('  Filled DUNS:', DUNS); break;
      }
    } catch {}
  }

  await shot(page, '3-filled');

  // ── Save ──────────────────────────────────────────────────────────────────
  console.log('[4/4] Saving...');
  let saved = false;
  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")','button[type="submit"]:not([disabled])']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click(); await wait(5000);
        console.log('  Clicked:', sel); saved = true; break;
      }
    } catch {}
  }
  if (!saved) console.log('  No save button found');

  await shot(page, '4-done');
  const result = await page.evaluate(() => document.body.innerText);
  console.log('  Final page:', result.slice(0, 300).replace(/\n+/g, ' '));

  await browser.close();
  console.log('\nDone.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
