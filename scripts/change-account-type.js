/**
 * Bond — Change Play Console account: Individual → Organization
 *
 * Run: node scripts/change-account-type.js
 *
 * Prerequisites:
 *   - Chrome must be open and logged into play.google.com/console as nwtcinvestment@gmail.com
 *   - npx playwright install chromium  (first time only)
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');

// Auto-install playwright if missing
function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename, ...process.argv.slice(2)], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const DEV_ID  = '6880853885521839099';
const DUNS    = '145025174';
const ORG     = '3 Lakes Logistics';
const EMAIL   = 'nwtcinvestment@gmail.com';

const ACCOUNT_URL = `https://play.google.com/console/u/0/developers/${DEV_ID}/account/developer-details?tab=aboutYou`;

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, label) {
  const p = path.join(__dirname, `acct-${label}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log(`  📸 Screenshot: scripts/acct-${label}.png`);
}

(async () => {
  console.log('=== Bond: Change Account Type Individual → Organization ===\n');

  // Connect to existing Chrome (must already be open and logged in)
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('✓ Connected to existing Chrome session');
  } catch (e) {
    console.log('No Chrome found on port 9222 — launching new browser window.');
    console.log('Log into play.google.com/console as ' + EMAIL + ', then re-run this script.\n');
    browser = await chromium.launch({ headless: false, slowMo: 300 });
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Go directly to the About You / account details tab ────────────
  console.log('\n[1/4] Navigating to Account Details...');
  await page.goto(ACCOUNT_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  console.log('  URL:', page.url().slice(0, 100));
  await shot(page, '1-account-page');

  // Dump visible text so we can see what's on the page
  const pageText = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('\n  Page text (first 600 chars):');
  console.log('  ' + pageText.slice(0, 600).replace(/\n/g, '\n  '));

  // ── Step 2: Click "Change account type" button ───────────────────────────
  console.log('\n[2/4] Looking for "Change account type" button...');

  const changeSelectors = [
    'button:has-text("Change account type")',
    'a:has-text("Change account type")',
    '[role="button"]:has-text("Change account type")',
    'button:has-text("Change")',
    'text=Change account type',
  ];

  let clicked = false;
  for (const sel of changeSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        console.log(`  ✓ Clicked: ${sel}`);
        clicked = true;
        break;
      }
    } catch {}
  }

  if (!clicked) {
    // Last resort: JS click by button text
    clicked = await page.evaluate(() => {
      const all = [...document.querySelectorAll('button, a, [role="button"]')];
      const btn = all.find(e => e.innerText?.toLowerCase().includes('change account type'));
      if (btn) { btn.click(); return true; }
      return false;
    });
    if (clicked) console.log('  ✓ Clicked via JS');
  }

  if (!clicked) {
    console.log('  ✗ "Change account type" button not found.');
    console.log('    Check screenshot: scripts/acct-1-account-page.png');
    console.log('    The button may not be visible if account is already Organization type.');
    await browser.close();
    return;
  }

  await wait(4000);
  await shot(page, '2-after-click');

  // Dump updated page text
  const afterText = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('\n  Page text after click (first 600 chars):');
  console.log('  ' + afterText.slice(0, 600).replace(/\n/g, '\n  '));

  // ── Step 3: Fill DUNS and org name ───────────────────────────────────────
  console.log('\n[3/4] Filling organization details...');

  // DUNS number
  const dunsSelectors = [
    'input[placeholder*="DUNS" i]',
    'input[aria-label*="DUNS" i]',
    'input[name*="duns" i]',
    'input[id*="duns" i]',
    'label:has-text("DUNS") + * input',
    'label:has-text("D-U-N-S") + * input',
    'mat-form-field:has-text("DUNS") input',
  ];
  let dunsFound = false;
  for (const sel of dunsSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await el.fill(DUNS);
        console.log(`  ✓ DUNS filled: ${DUNS}`);
        dunsFound = true;
        break;
      }
    } catch {}
  }
  if (!dunsFound) console.log('  ⚠ DUNS field not found — may appear after next step or not be required');

  // Org name (may already be pre-filled as "3 Lakes Logistics")
  const orgSelectors = [
    'input[placeholder*="organization name" i]',
    'input[aria-label*="organization" i]',
    'input[name*="org" i]',
    'mat-form-field:has-text("organization") input',
    'mat-form-field:has-text("Organization") input',
  ];
  for (const sel of orgSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        const current = await el.inputValue();
        if (!current) {
          await el.fill(ORG);
          console.log(`  ✓ Org name filled: ${ORG}`);
        } else {
          console.log(`  ✓ Org name already set: ${current}`);
        }
        break;
      }
    } catch {}
  }

  await wait(1000);
  await shot(page, '3-form-filled');

  // ── Step 4: Submit ────────────────────────────────────────────────────────
  console.log('\n[4/4] Submitting...');

  const submitSelectors = [
    'button:has-text("Change account type")',
    'button:has-text("Submit")',
    'button:has-text("Save")',
    'button:has-text("Confirm")',
    'button:has-text("Continue")',
    'button[type="submit"]:not([disabled])',
  ];

  let submitted = false;
  for (const sel of submitSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        console.log(`  ✓ Submitted via: ${sel}`);
        submitted = true;
        break;
      }
    } catch {}
  }

  if (!submitted) {
    console.log('  ⚠ Submit button not found — check screenshot');
  }

  await wait(6000);
  await shot(page, '4-final');

  const finalText = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('\n  Final page text (first 400 chars):');
  console.log('  ' + finalText.slice(0, 400).replace(/\n/g, '\n  '));
  console.log('\n  Final URL:', page.url().slice(0, 100));

  console.log('\n=== Done ===');
  console.log('Check screenshots in scripts/acct-*.png');
  console.log('If account type changed successfully, run the full setup next:');
  console.log('  node scripts/bond-play-console-setup.js');

  await browser.close();
})().catch(err => {
  console.error('\n✗ Error:', err.message);
  console.error('Make sure Chrome is open at play.google.com/console logged in as ' + EMAIL);
  process.exit(1);
});
