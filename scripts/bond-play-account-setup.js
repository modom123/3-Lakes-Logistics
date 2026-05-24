/**
 * Bond — Convert Play Console account to Organization + set name
 * Changes: Personal → Organization, name → "3 Lakes Logistics"
 * DUNS: 145025174
 *
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

const ORG_NAME = '3 Lakes Logistics';
const DUNS     = '145025174';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  const p = path.join(__dirname, `acct-${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log('  Screenshot:', `scripts/acct-${name}.png`);
}
async function findVisible(page, selectors, timeout = 6000) {
  for (const sel of selectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout })) return el;
    } catch {}
  }
  return null;
}

(async () => {
  console.log('=== Bond: Play Console Account → Organization ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 200 });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Open Play Console and select account ──────────────────────────
  console.log('\n[1/4] Opening Play Console...');
  await page.goto('https://play.google.com/console', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(6000);
  await shot(page, '1-landing');

  // Click "3 lakes logistics" if on account selection screen
  const bodyText = await page.evaluate(() => document.body.innerText);
  if (bodyText.toLowerCase().includes('choose developer') || bodyText.toLowerCase().includes('3 lakes')) {
    console.log('  Account selection screen detected — selecting "3 lakes logistics"...');
    await page.evaluate(() => {
      const all = [...document.querySelectorAll('*')];
      const el = all.find(e => e.children.length === 0 &&
        e.innerText?.toLowerCase().includes('3 lakes logistics'));
      if (el) { el.click(); return; }
      // Try parent elements
      const el2 = all.find(e => e.innerText?.toLowerCase() === '3 lakes logistics');
      if (el2) el2.click();
    });
    await wait(6000);
    console.log('  URL after click:', page.url().slice(0, 90));
    await shot(page, '1b-after-account-select');
  }

  // Extract developer ID
  let devId = page.url().match(/developers\/(\d+)/)?.[1];
  if (!devId) {
    // Wait a bit more for redirect
    await wait(5000);
    devId = page.url().match(/developers\/(\d+)/)?.[1];
  }
  console.log('  Developer ID:', devId || '(not found)');

  // ── Step 2: Go to Account Details ────────────────────────────────────────
  console.log('\n[2/4] Opening account details...');
  const settingsUrls = [
    devId && `https://play.google.com/console/u/0/developers/${devId}/account-details`,
    devId && `https://play.google.com/console/u/0/developers/${devId}/setup/account-details`,
    'https://play.google.com/console/u/0/developers/account-details',
    'https://play.google.com/console/u/0/developers/setup/account-details',
  ].filter(Boolean);

  let landed = false;
  for (const url of settingsUrls) {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(4000);
    const t = await page.evaluate(() => document.body.innerText);
    if (t.includes('account type') || t.toLowerCase().includes('developer name') ||
        t.toLowerCase().includes('organization') || t.toLowerCase().includes('account details')) {
      console.log('  Account details page loaded:', url.slice(0, 80));
      landed = true;
      break;
    }
  }
  if (!landed) {
    // Try finding Settings in nav
    const settingsLink = await findVisible(page, [
      'a:has-text("Account details")',
      'a:has-text("Settings")',
      'nav a:has-text("Setup")',
      '[aria-label*="account" i]',
    ], 5000);
    if (settingsLink) {
      await settingsLink.click();
      await wait(3000);
    }
  }
  await shot(page, '2-account-details');
  const pageText2 = await page.evaluate(() => document.body.innerText);
  console.log('  Page text preview:', pageText2.slice(0, 300).replace(/\n/g, ' '));

  // ── Step 3: Change account type to Organization ───────────────────────────
  console.log('\n[3/4] Changing account type to Organization...');

  // Look for "Organization" radio/option
  const orgOption = await findVisible(page, [
    'input[value="organization"]',
    'input[value="ORGANIZATION"]',
    'label:has-text("Organization")',
    '[data-value="organization"]',
    'mat-radio-button:has-text("Organization")',
    'input[type="radio"] + * :has-text("Organization")',
  ], 5000);

  if (orgOption) {
    await orgOption.click();
    await wait(2000);
    console.log('  Selected Organization');
    await shot(page, '3-org-selected');
  } else {
    console.log('  Organization option not found — printing page buttons:');
    const els = await page.evaluate(() =>
      [...document.querySelectorAll('input,label,button,select,mat-radio-button')]
        .map(e => `${e.tagName}|${e.type||''}|${(e.innerText||e.value||'').trim().slice(0,40)}`)
        .filter(s => s.length > 5).slice(0, 30)
    );
    console.log( els.join('\n'));
    await shot(page, '3-no-org-option');
  }

  // ── Step 4: Fill developer/org name and DUNS ─────────────────────────────
  console.log('\n[4/4] Updating name and DUNS...');

  // Developer / Org name field
  const nameField = await findVisible(page, [
    'input[aria-label*="name" i]',
    'input[placeholder*="name" i]',
    'input[name*="name"]',
    'input[id*="name"]',
    'mat-form-field:has-text("Developer name") input',
    'mat-form-field:has-text("Organization name") input',
  ], 5000);

  if (nameField) {
    await nameField.click({ clickCount: 3 });
    await nameField.fill(ORG_NAME);
    console.log('  Set name to:', ORG_NAME);
  } else {
    console.log('  Name field not found');
  }

  // DUNS field
  const dunsField = await findVisible(page, [
    'input[aria-label*="DUNS" i]',
    'input[placeholder*="DUNS" i]',
    'input[name*="duns"]',
    'input[id*="duns"]',
    'mat-form-field:has-text("DUNS") input',
  ], 5000);

  if (dunsField) {
    await dunsField.click({ clickCount: 3 });
    await dunsField.fill(DUNS);
    console.log('  Set DUNS to:', DUNS);
  } else {
    console.log('  DUNS field not found (may appear after selecting Organization)');
  }

  await shot(page, '4-filled');

  // Save
  const saveBtn = await findVisible(page, [
    'button:has-text("Save")',
    'button:has-text("Submit")',
    'button[type="submit"]',
    'button:has-text("Apply")',
  ], 5000);

  if (saveBtn) {
    await saveBtn.click();
    await wait(5000);
    await shot(page, '5-saved');
    const saved = await page.evaluate(() => document.body.innerText);
    if (saved.toLowerCase().includes('saved') || saved.toLowerCase().includes('success')) {
      console.log('\nAccount updated to Organization successfully!');
    } else {
      console.log('\nSave clicked — check screenshot to confirm');
    }
  } else {
    console.log('  Save button not found — check screenshot');
    await shot(page, '5-no-save');
  }

  await browser.close();
  console.log('\nDone. After account is set to Organization:');
  console.log('  Run: node scripts/bond-play-console-setup.js');
  console.log('  (to create the app listing and grant API access)');

})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
