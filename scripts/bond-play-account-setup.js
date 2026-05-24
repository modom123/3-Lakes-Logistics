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

// Click the first element whose visible text exactly or partially matches
async function clickText(page, texts, timeout = 5000) {
  for (const text of (Array.isArray(texts) ? texts : [texts])) {
    try {
      const el = page.locator(`text="${text}"`).first();
      if (await el.isVisible({ timeout })) { await el.click(); return text; }
    } catch {}
    try {
      const el = page.locator(`a:has-text("${text}"), button:has-text("${text}"), [role="menuitem"]:has-text("${text}")`).first();
      if (await el.isVisible({ timeout: 2000 })) { await el.click(); return text; }
    } catch {}
  }
  return null;
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

  // ── Land on the developer dashboard ───────────────────────────────────────
  console.log('\n[1/4] Opening developer dashboard...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/app-list`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(5000);
  console.log('  URL:', page.url().slice(0, 90));
  await shot(page, '1-dashboard');

  // ── Click Settings in sidebar ──────────────────────────────────────────────
  console.log('\n[2/4] Clicking Settings...');
  const clickedSettings = await clickText(page, ['Settings', 'settings']);
  console.log('  Clicked:', clickedSettings || 'not found');
  await wait(3000);
  await shot(page, '2-settings');
  console.log('  URL:', page.url().slice(0, 90));

  // Print sub-menu items that appeared
  const menuItems = await page.evaluate(() =>
    [...document.querySelectorAll('a, [role="menuitem"]')]
      .map(e => e.innerText?.trim()).filter(t => t && t.length < 60)
      .filter((v,i,a) => a.indexOf(v) === i)
  );
  console.log('  Menu items now:', menuItems.slice(0, 30).join(' | '));

  // ── Click Account details ──────────────────────────────────────────────────
  console.log('\n[3/4] Clicking Account details...');
  const clickedAcct = await clickText(page, ['Account details', 'Developer account', 'Account info']);
  if (clickedAcct) {
    console.log('  Clicked:', clickedAcct);
    await wait(4000);
    await shot(page, '3-account-details');
    console.log('  URL:', page.url().slice(0, 90));
  } else {
    // Try navigating to the settings sub-page URL directly (within existing session)
    await page.goto(
      `https://play.google.com/console/u/0/developers/${DEV_ID}/setup/account-details`,
      { waitUntil: 'domcontentloaded', timeout: 30000 }
    );
    await wait(4000);
    await shot(page, '3-account-details-direct');
    console.log('  URL via direct nav:', page.url().slice(0, 90));
  }

  // Print everything on the current page
  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('\n  Page text:', pageText.slice(0, 600).replace(/\n+/g, ' '));

  const allInputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select')]
      .map(e => `${e.tagName} type=${e.type||''} value=${e.value||''} label="${e.getAttribute('aria-label')||''}" text="${e.innerText?.trim().slice(0,30)||''}"`)
  );
  console.log('\n  All inputs:', allInputs.join('\n  '));

  // ── Make changes ───────────────────────────────────────────────────────────
  console.log('\n[4/4] Making changes...');

  // Try to select Organization type
  for (const sel of [
    'input[value="organization" i]',
    'mat-radio-button:has-text("Organization")',
    '[role="radio"]:has-text("Organization")',
    'label:has-text("Organization")',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        await wait(1000);
        console.log('  Selected Organization');
        break;
      }
    } catch {}
  }

  // Fill developer name (look for a text input that isn't the search box)
  const textInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of textInputs) {
    const label = await inp.getAttribute('aria-label').catch(() => '');
    const placeholder = await inp.getAttribute('placeholder').catch(() => '');
    const val = await inp.inputValue().catch(() => '');
    if (label?.toLowerCase().includes('search') || placeholder?.toLowerCase().includes('search')) continue;
    if (label || placeholder) {
      console.log(`  Filling field: label="${label}" placeholder="${placeholder}" current="${val}"`);
      await inp.click({ clickCount: 3 });
      await inp.fill(ORG_NAME);
      break;
    }
  }

  // Fill DUNS if visible
  for (const sel of ['input[aria-label*="DUNS" i]', 'input[placeholder*="DUNS" i]', 'input[formcontrolname*="duns" i]']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click({ clickCount: 3 });
        await el.fill(DUNS);
        console.log('  Filled DUNS');
        break;
      }
    } catch {}
  }

  await shot(page, '4-before-save');

  // Save
  for (const sel of ['button:has-text("Save")', 'button:has-text("Submit")', 'button[type="submit"]:not([disabled])']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await wait(5000);
        console.log('  Saved');
        break;
      }
    } catch {}
  }

  await shot(page, '5-done');
  await browser.close();
  console.log('\nDone — check screenshots in scripts/acct-*.png');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
