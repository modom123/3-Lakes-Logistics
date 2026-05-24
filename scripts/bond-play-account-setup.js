/**
 * Bond — Convert Play Console account to Organization via Developer Verification
 * Per Google support article 16260648: account type change goes through
 * the "Android developer verification" page, not Account details.
 *
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
  console.log('=== Bond: Play Console → Organization via Developer Verification ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 150 });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Navigate to Android Developer Verification ────────────────────────────
  console.log('\n[1/4] Opening Android Developer Verification page...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/android-developer-verification`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(6000);
  console.log('  URL:', page.url().slice(0, 90));
  await shot(page, '1-verification');

  // Print full page text
  const text1 = await page.evaluate(() => document.body.innerText);
  console.log('\n  === PAGE TEXT ===');
  console.log(text1.slice(0, 1500).replace(/\n{3,}/g, '\n'));
  console.log('  =================\n');

  // All clickable buttons
  const btns = await page.evaluate(() =>
    [...document.querySelectorAll('button, a, [role="button"]')]
      .map(e => e.innerText?.trim() || e.getAttribute('aria-label') || '')
      .filter(t => t && t.length > 1 && t.length < 80)
      .filter((v,i,a) => a.indexOf(v) === i)
  );
  console.log('  Buttons/links:', btns.join(' | '));

  // All inputs
  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select, textarea')]
      .map(e => `${e.tagName}[${e.type||''}] value="${e.value||''}" label="${e.getAttribute('aria-label')||''}" placeholder="${e.getAttribute('placeholder')||''}" text="${e.innerText?.trim().slice(0,50)||''}"`)
  );
  console.log('  Inputs:\n  ' + inputs.join('\n  '));

  // ── Look for "Get started" or "Start verification" or "Organization" ───────
  console.log('\n[2/4] Looking for verification start or organization option...');

  // Try to click "Get started", "Start", "Verify", "Organization", etc.
  const startSelectors = [
    'button:has-text("Get started")',
    'button:has-text("Start verification")',
    'button:has-text("Start")',
    'button:has-text("Begin")',
    'button:has-text("Verify")',
    'button:has-text("Organization")',
    'button:has-text("Continue")',
    'a:has-text("Get started")',
    'mat-radio-button:has-text("Organization")',
    '[role="radio"]:has-text("Organization")',
  ];
  let clicked = null;
  for (const sel of startSelectors) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        await wait(3000);
        clicked = sel;
        console.log('  Clicked:', sel);
        break;
      }
    } catch {}
  }
  if (!clicked) console.log('  No start/org button found yet');
  await shot(page, '2-after-start');

  // ── Print what's now on the page ──────────────────────────────────────────
  console.log('\n[3/4] Page after interaction:');
  console.log('  URL:', page.url().slice(0, 90));
  const text2 = await page.evaluate(() => document.body.innerText);
  console.log('  Text:', text2.slice(0, 1000).replace(/\n{3,}/g, '\n'));

  const inputs2 = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select')]
      .map(e => ({
        tag: e.tagName, type: e.type||'', value: e.value||'',
        label: e.getAttribute('aria-label')||'',
        placeholder: e.getAttribute('placeholder')||'',
        text: e.innerText?.trim().slice(0,50)||'',
        rect: (() => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top) }; })()
      }))
  );
  console.log('  Inputs after click:\n  ' + JSON.stringify(inputs2, null, 2).slice(0, 1000));

  // ── Fill org name and DUNS if form fields appeared ────────────────────────
  console.log('\n[4/4] Filling form if available...');

  const textInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of textInputs) {
    const label = (await inp.getAttribute('aria-label').catch(() => '') || '').toLowerCase();
    const ph = (await inp.getAttribute('placeholder').catch(() => '') || '').toLowerCase();
    const val = await inp.inputValue().catch(() => '');
    if (label.includes('search') || ph.includes('search')) continue;
    console.log(`  Field: label="${label}" ph="${ph}" val="${val}"`);
    if (label.includes('duns') || ph.includes('duns')) {
      await inp.click({ clickCount: 3 }); await inp.fill(DUNS);
      console.log('  → Filled DUNS');
    } else if (label.includes('name') || ph.includes('name') || label.includes('org') || ph.includes('org')) {
      await inp.click({ clickCount: 3 }); await inp.fill(ORG_NAME);
      console.log('  → Filled name:', ORG_NAME);
    }
  }

  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")','button:has-text("Next")','button[type="submit"]:not([disabled])']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click(); await wait(4000);
        console.log('  Submitted via:', sel); break;
      }
    } catch {}
  }

  await shot(page, '4-done');
  const final = await page.evaluate(() => document.body.innerText);
  console.log('\n  Final URL:', page.url().slice(0, 90));
  console.log('  Final text:', final.slice(0, 500).replace(/\n{3,}/g, '\n'));

  await browser.close();
  console.log('\nDone — paste the full output so Bond can see what step the verification is on.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
