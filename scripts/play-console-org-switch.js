/**
 * Bond — Switch Google Play Console from Personal to Organization account
 *
 * Run: node scripts\play-console-org-switch.js
 *
 * Google blocks automated login — connect to your existing Chrome session.
 * Make sure Chrome is open and signed in to Play Console first.
 */

const { execSync, spawnSync } = require('child_process');
const path    = require('path');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}
const { chromium } = require('playwright');

// ── Config ────────────────────────────────────────────────────────────────────
const ORG_NAME    = '3 Lakes Logistics LLC';
const ORG_WEBSITE = 'https://www.3lakeslogistics.com';
const ORG_EMAIL   = 'info@3lakeslogistics.com';
const ORG_PHONE   = '+12686022947';

const ACCOUNT_URL  = 'https://play.google.com/console/developers';
const SETTINGS_URL = 'https://play.google.com/console/u/0/developers/account';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function prompt(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, ans => { rl.close(); resolve(ans); });
  });
}

(async () => {
  console.log('=== Bond: Play Console → Switch to Organization ===\n');

  // ── Connect to existing Chrome ─────────────────────────────────────────────
  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome\n');
  } catch {
    console.log('⚠ Could not connect to Chrome on port 9222');
    console.log('  Starting fresh browser — you may need to sign in manually\n');
    browser = await chromium.launch({ headless: false, slowMo: 60, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Step 1: Go to Play Console account settings ────────────────────────────
  console.log('[1] Opening Play Console account settings...');
  await page.goto(SETTINGS_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(3000);

  const url = page.url();
  console.log('  Current URL:', url.slice(0, 80));

  if (url.includes('accounts.google.com') || url.includes('signin')) {
    console.log('\n  ⚠ Not signed in to Play Console.');
    console.log('  Please sign in to https://play.google.com/console in Chrome first.');
    console.log('  Then re-run this script.\n');
    process.exit(1);
  }

  // ── Step 2: Find the account type / organization switch option ────────────
  console.log('\n[2] Looking for account type settings...');
  await wait(2000);

  // Screenshot the page state
  const pageText = await page.evaluate(() => document.body.innerText);
  const hasOrg   = /organization|organisation/i.test(pageText);
  const hasSwitch = /switch|change account type|upgrade/i.test(pageText);
  const alreadyOrg = /organization account/i.test(pageText) && !/personal/i.test(pageText);

  if (alreadyOrg) {
    console.log('\n  ✓ Account is already set to Organization type!');
    process.exit(0);
  }

  console.log(`  Page mentions "organization": ${hasOrg}`);
  console.log(`  Page has switch option: ${hasSwitch}`);

  // Try to find and click the switch/upgrade button
  const clicked = await page.evaluate(() => {
    const texts = ['switch to organization', 'change account type', 'upgrade account', 'organization account'];
    const els = [...document.querySelectorAll('button, a, [role="button"], mat-button')];
    for (const t of texts) {
      const el = els.find(e => e.innerText?.toLowerCase().includes(t));
      if (el) { el.click(); return el.innerText.trim(); }
    }
    // Try links
    const links = [...document.querySelectorAll('a')];
    for (const t of texts) {
      const l = links.find(e => e.href?.includes('organization') || e.innerText?.toLowerCase().includes(t));
      if (l) { l.click(); return l.innerText.trim() || l.href; }
    }
    return null;
  });

  if (clicked) {
    console.log(`\n  ✓ Clicked: "${clicked}"`);
    await wait(3000);
  } else {
    console.log('\n  Switch button not found on this page.');
    console.log('  Trying alternate URL...');
    // Try the account type change URL directly
    await page.goto(
      'https://play.google.com/console/u/0/developers/account-change-type',
      { waitUntil: 'domcontentloaded', timeout: 20000 }
    ).catch(() => {});
    await wait(3000);
  }

  // ── Step 3: Fill in organization details if a form appeared ───────────────
  console.log('\n[3] Checking for organization details form...');
  await wait(2000);

  const formFilled = await page.evaluate((cfg) => {
    const results = [];

    // Helper to fill a visible input matching label keywords
    function fillField(keywords, value) {
      const inputs = [...document.querySelectorAll('input, textarea')];
      for (const inp of inputs) {
        const label = (
          inp.getAttribute('aria-label') ||
          inp.getAttribute('placeholder') ||
          inp.id || ''
        ).toLowerCase();
        if (keywords.some(k => label.includes(k))) {
          inp.value = value;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
          results.push(label.slice(0, 40) + ' = ' + value.slice(0, 30));
          return true;
        }
      }
      return false;
    }

    fillField(['organization', 'company', 'business name', 'legal name'], cfg.name);
    fillField(['website', 'url'], cfg.website);
    fillField(['email'], cfg.email);
    fillField(['phone'], cfg.phone);

    return results;
  }, { name: ORG_NAME, website: ORG_WEBSITE, email: ORG_EMAIL, phone: ORG_PHONE });

  if (formFilled && formFilled.length > 0) {
    console.log('  ✓ Filled fields:');
    formFilled.forEach(f => console.log(`    • ${f}`));
  } else {
    console.log('  No form fields found to auto-fill.');
  }

  // ── Step 4: Check current page state and guide user ───────────────────────
  console.log('\n[4] Current page analysis...');
  await wait(1500);
  const currentUrl  = page.url();
  const currentText = await page.evaluate(() => document.body.innerText.slice(0, 600));

  console.log('  URL:', currentUrl.slice(0, 80));
  console.log('  Page preview:');
  currentText.split('\n').slice(0, 8).forEach(l => l.trim() && console.log('  ', l.trim()));

  // ── Manual guidance ────────────────────────────────────────────────────────
  console.log('\n' + '─'.repeat(60));
  console.log('MANUAL STEPS (if Bond could not auto-complete):');
  console.log('─'.repeat(60));
  console.log('');
  console.log('1. In Play Console, go to:');
  console.log('   Settings → Developer account → Account details');
  console.log('');
  console.log('2. Look for "Account type" section');
  console.log('   Click "Switch to organization account"');
  console.log('');
  console.log('3. Fill in:');
  console.log(`   Organization name : ${ORG_NAME}`);
  console.log(`   Website           : ${ORG_WEBSITE}`);
  console.log(`   Email             : ${ORG_EMAIL}`);
  console.log(`   Phone             : ${ORG_PHONE}`);
  console.log('');
  console.log('4. Submit → Google will send a verification email');
  console.log(`   Check: info@3lakeslogistics.com`);
  console.log('');
  console.log('5. Click the verification link in the email');
  console.log('');
  console.log('─'.repeat(60));

  await prompt('\nPress Enter when done (or to close Bond)... ');
  console.log('\n=== Done ===');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
