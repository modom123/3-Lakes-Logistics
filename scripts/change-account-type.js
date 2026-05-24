/**
 * Bond — Change Play Console account: Individual → Organization
 *
 * Run: node scripts/change-account-type.js
 *
 * This opens a visible browser window. Log in if prompted, then press Enter.
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const readline = require('readline');

// Auto-install playwright if missing
function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright (one-time setup)...');
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const DEV_ID      = '6880853885521839099';
const DUNS        = '145025174';
const ORG_NAME    = '3 Lakes Logistics';
const ACCOUNT_URL = `https://play.google.com/console/u/0/developers/${DEV_ID}/account/developer-details?tab=aboutYou`;

function pause(prompt) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(prompt, () => { rl.close(); resolve(); });
  });
}

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, label) {
  const p = path.join(__dirname, `acct-${label}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log(`  Screenshot saved → scripts/acct-${label}.png`);
}

async function tryClick(page, selectors, description) {
  for (const sel of selectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        console.log(`  ✓ Clicked ${description}`);
        return true;
      }
    } catch {}
  }
  // JS fallback — search by text
  const found = await page.evaluate((desc) => {
    const all = [...document.querySelectorAll('button, a, [role="button"], [role="link"], span')];
    const el = all.find(e => e.innerText?.trim().toLowerCase().includes(desc.toLowerCase()));
    if (el) { el.click(); return el.innerText.trim(); }
    return null;
  }, description);
  if (found) {
    console.log(`  ✓ JS-clicked "${found}"`);
    return true;
  }
  return false;
}

async function tryFill(page, selectors, value, label) {
  for (const sel of selectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        await el.fill(value);
        console.log(`  ✓ Filled ${label}: ${value}`);
        return true;
      }
    } catch {}
  }
  console.log(`  ⚠ ${label} field not found`);
  return false;
}

(async () => {
  console.log('=== Bond: Change Account Type → Organization ===\n');

  // Always launch a visible browser — no CDP needed
  const browser = await chromium.launch({
    headless: false,
    slowMo: 150,
    args: ['--start-maximized'],
  });

  const context = await browser.newContext({ viewport: null });
  const page    = await context.newPage();

  // ── Step 1: Open Play Console ─────────────────────────────────────────────
  console.log('[1/4] Opening Play Console...');
  await page.goto('https://play.google.com/console', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await wait(4000);

  // Check if we need to log in
  const url1 = page.url();
  const text1 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('  URL:', url1.slice(0, 80));

  if (url1.includes('accounts.google.com') || text1.includes('Sign in')) {
    console.log('\n  ⚠  Google sign-in required.');
    console.log('  Log in as nwtcinvestment@gmail.com in the browser window.');
    await pause('  Press Enter once you are logged into Play Console... ');
    await wait(3000);
  }

  // ── Step 2: Navigate directly to account details ──────────────────────────
  console.log('\n[2/4] Going to Account Details...');
  await page.goto(ACCOUNT_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  await shot(page, '1-account-page');

  const text2 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('  URL:', page.url().slice(0, 90));
  console.log('  Page preview:', text2.slice(0, 300).replace(/\n+/g, ' | '));

  // ── Step 3: Click "Change account type" ───────────────────────────────────
  console.log('\n[3/4] Clicking "Change account type"...');

  const clicked = await tryClick(page, [
    'button:has-text("Change account type")',
    'a:has-text("Change account type")',
    '[role="button"]:has-text("Change account type")',
    'span:has-text("Change account type")',
  ], 'Change account type');

  if (!clicked) {
    console.log('\n  Button not found automatically.');
    console.log('  In the browser window, click "Change account type" manually.');
    await pause('  Press Enter after you have clicked it... ');
  }

  await wait(5000);
  await shot(page, '2-after-click');

  const text3 = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('  Page after click:', text3.slice(0, 300).replace(/\n+/g, ' | '));

  // ── Step 4: Fill form ─────────────────────────────────────────────────────
  console.log('\n[4/4] Filling organization details...');

  // DUNS
  await tryFill(page, [
    'input[placeholder*="DUNS" i]',
    'input[aria-label*="DUNS" i]',
    'input[id*="duns" i]',
    'input[name*="duns" i]',
    'mat-form-field:has-text("DUNS") input',
    'mat-form-field:has-text("D-U-N-S") input',
  ], DUNS, 'DUNS');

  // Org name (may be pre-filled)
  await tryFill(page, [
    'input[placeholder*="organization" i]',
    'input[aria-label*="organization" i]',
    'mat-form-field:has-text("organization") input',
  ], ORG_NAME, 'Org name');

  await wait(1000);
  await shot(page, '3-form-filled');

  // Submit
  const submitted = await tryClick(page, [
    'button:has-text("Change account type")',
    'button:has-text("Submit")',
    'button:has-text("Confirm")',
    'button:has-text("Save")',
    'button:has-text("Continue")',
    'button[type="submit"]:not([disabled])',
  ], 'Submit');

  if (!submitted) {
    console.log('\n  Submit button not found automatically.');
    console.log('  Click the Submit / Confirm / Save button in the browser window.');
    await pause('  Press Enter after submitting... ');
  }

  await wait(6000);
  await shot(page, '4-final');

  const finalText = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('\n  Final URL:', page.url().slice(0, 100));
  console.log('  Final page:', finalText.slice(0, 300).replace(/\n+/g, ' | '));

  console.log('\n=== Done ===');
  console.log('Screenshots saved in scripts/acct-*.png');
  console.log('\nKeeping browser open — press Ctrl+C to close when finished.');

  // Keep browser open so user can review
  await pause('Press Enter to close the browser... ');
  await browser.close();

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
