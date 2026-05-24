/**
 * Bond — Add new56money@gmail.com as Firebase project owner
 *
 * Run: node scripts\firebase-add-member.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const PROJECT_ID  = 'lakes-logistics-ffe6f';
const NEW_EMAIL   = 'new56money@gmail.com';
const MEMBERS_URL = `https://console.firebase.google.com/project/${PROJECT_ID}/settings/iam`;

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  console.log('=== Bond: Add Firebase Project Member ===\n');
  console.log(`Adding ${NEW_EMAIL} to project ${PROJECT_ID}\n`);

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 80, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  console.log('\n[1] Opening Firebase IAM settings...');
  await page.goto(MEMBERS_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(4000);
  console.log('  URL:', page.url().slice(0, 80));

  // Click "Add member" button
  console.log('\n[2] Clicking Add member...');
  const addClicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button, a')];
    const btn = btns.find(b => /(add member|add principal|grant access)/i.test(b.innerText || b.textContent || ''));
    if (btn) { btn.click(); return (btn.innerText || '').trim(); }
    return null;
  });
  console.log(addClicked ? `  ✓ Clicked: ${addClicked}` : '  Button not found — trying alternate...');
  await wait(2000);

  // Fill email
  console.log('\n[3] Filling email...');
  const emailFilled = await page.evaluate((email) => {
    const inputs = [...document.querySelectorAll('input[type="email"], input[type="text"]')];
    const inp = inputs.find(i => {
      const a = (i.getAttribute('aria-label') || i.placeholder || '').toLowerCase();
      return a.includes('email') || a.includes('member') || a.includes('principal') || i.type === 'email';
    });
    if (!inp) return false;
    inp.value = email;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }, NEW_EMAIL);
  console.log(emailFilled ? `  ✓ Email: ${NEW_EMAIL}` : '  ⚠ Email field not found');
  await wait(1000);

  // Select Owner role
  console.log('\n[4] Selecting Owner role...');
  await page.evaluate(() => {
    const selects = [...document.querySelectorAll('mat-select, select, [role="listbox"], [role="combobox"]')];
    const roleSelect = selects.find(s => /(role|permission)/i.test(s.getAttribute('aria-label') || s.innerText || ''));
    if (roleSelect) roleSelect.click();
  });
  await wait(1500);
  await page.evaluate(() => {
    const opts = [...document.querySelectorAll('mat-option, option, [role="option"]')];
    const owner = opts.find(o => /owner|editor/i.test(o.innerText || o.textContent || ''));
    if (owner) owner.click();
  });
  await wait(1000);

  // Click Save / Add
  console.log('\n[5] Saving...');
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    const save = btns.find(b => /(save|add|done|confirm)/i.test(b.innerText || '') && b.type !== 'button' || /(save|add|done)/i.test(b.innerText || ''));
    if (save) { save.removeAttribute('disabled'); save.click(); }
  });
  await wait(3000);

  console.log('\n=== Done ===');
  console.log(`  ${NEW_EMAIL} should now have access to ${PROJECT_ID}`);
  console.log(`  Verify at: ${MEMBERS_URL}`);
  console.log('\n  If the above steps failed, do it manually:');
  console.log(`  1. Go to: ${MEMBERS_URL}`);
  console.log(`  2. Click "Add member"`);
  console.log(`  3. Enter: ${NEW_EMAIL}`);
  console.log('  4. Role: Owner (or Editor)');
  console.log('  5. Save');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
