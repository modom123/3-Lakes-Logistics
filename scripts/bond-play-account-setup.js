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

const DEV_ID   = '6880853885521839099';
const ORG_NAME = '3 Lakes Logistics';
const DUNS     = '145025174';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: path.join(__dirname, `acct-${name}.png`), fullPage: false });
  console.log('  Screenshot: scripts/acct-' + name + '.png');
}

(async () => {
  console.log('=== Bond: Play Console → Organization Account ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 200 });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Navigate directly to the developer dashboard ──────────────────────────
  console.log('\n[1/3] Opening developer dashboard...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/app-list`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(6000);
  console.log('  URL:', page.url().slice(0, 90));
  await shot(page, '1-dashboard');

  // ── Find Account details via sidebar ──────────────────────────────────────
  console.log('\n[2/3] Finding Account details in navigation...');

  // Print all links/nav items visible to debug
  const navItems = await page.evaluate(() =>
    [...document.querySelectorAll('a, [role="menuitem"], nav *')]
      .map(e => e.innerText?.trim())
      .filter(t => t && t.length > 1 && t.length < 60)
      .filter((v, i, a) => a.indexOf(v) === i)
      .slice(0, 50)
  );
  console.log('  Nav items found:', navItems.join(' | '));

  // Try clicking Account details in sidebar
  let clickedSettings = false;
  const settingsSelectors = [
    'a:has-text("Account details")',
    'a[href*="account-details"]',
    '[aria-label*="Account details"]',
    'a:has-text("Settings")',
    // Setup section
    'a:has-text("Setup")',
  ];
  for (const sel of settingsSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await wait(3000);
        const t = await page.evaluate(() => document.body.innerText);
        if (t.toLowerCase().includes('account type') ||
            t.toLowerCase().includes('developer name') ||
            t.toLowerCase().includes('organization')) {
          console.log('  Landed on account details via:', sel);
          clickedSettings = true;
          break;
        }
        // If it opened a section, look for Account details sub-link
        const subLink = page.locator('a:has-text("Account details")').first();
        if (await subLink.isVisible({ timeout: 2000 }).catch(() => false)) {
          await subLink.click();
          await wait(3000);
          clickedSettings = true;
          break;
        }
      }
    } catch {}
  }

  if (!clickedSettings) {
    // Navigate directly — now that we're inside the dev console, try the URL
    console.log('  Trying direct URL navigation from within the console...');
    await page.evaluate((devId) => {
      window.location.href = `/console/u/0/developers/${devId}/account-details`;
    }, DEV_ID);
    await wait(6000);
    console.log('  URL after JS nav:', page.url().slice(0, 90));
  }

  await shot(page, '2-account-details');
  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('  Page text:', pageText.slice(0, 500).replace(/\n+/g, ' '));

  // ── Make the changes ──────────────────────────────────────────────────────
  console.log('\n[3/3] Updating account type and name...');

  // Log all inputs, labels, radio buttons
  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, select, mat-radio-button, [role="radio"]')]
      .map(e => ({
        tag: e.tagName,
        type: e.type || '',
        name: e.name || '',
        value: e.value || '',
        label: e.getAttribute('aria-label') || '',
        text: e.innerText?.trim().slice(0, 40) || '',
        id: e.id || '',
      }))
  );
  console.log('  Inputs on page:');
  inputs.forEach(i => console.log(`    ${i.tag} type=${i.type} name=${i.name} value=${i.value} label=${i.label} text=${i.text}`));

  // Try to select Organization
  let orgSelected = false;
  for (const sel of [
    'input[value="organization"]',
    'input[value="ORGANIZATION"]',
    'mat-radio-button:has-text("Organization")',
    '[role="radio"]:has-text("Organization")',
    'label:has-text("Organization") input',
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
  if (!orgSelected) console.log('  Organization radio not found on this page');

  // Fill name
  for (const sel of [
    'input[aria-label*="name" i]',
    'input[placeholder*="name" i]',
    'input[name*="name"]',
    'input[formcontrolname*="name"]',
    'mat-form-field:has-text("name") input',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click({ clickCount: 3 });
        await el.fill(ORG_NAME);
        console.log('  Filled name via:', sel);
        break;
      }
    } catch {}
  }

  // Fill DUNS
  for (const sel of [
    'input[aria-label*="DUNS" i]',
    'input[placeholder*="DUNS" i]',
    'input[name*="duns"]',
    'input[formcontrolname*="duns"]',
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

  await shot(page, '3-before-save');

  // Save
  for (const sel of [
    'button:has-text("Save")',
    'button:has-text("Submit")',
    'button[type="submit"]:not([disabled])',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await wait(4000);
        console.log('  Clicked save');
        break;
      }
    } catch {}
  }

  await shot(page, '4-final');
  const finalText = await page.evaluate(() => document.body.innerText);
  console.log('\n  Final page text:', finalText.slice(0, 400).replace(/\n+/g, ' '));

  await browser.close();
  console.log('\nDone. If account type changed successfully, run:');
  console.log('  node scripts/bond-play-console-setup.js');

})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
