/**
 * Bond — Set Play Console account to Organization via Identity tab
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
  console.log('=== Bond: Play Console Identity → Organization ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 150 });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Go to Android Developer Verification page ─────────────────────────────
  console.log('[1/4] Opening Developer Verification page...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/android-developer-verification`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(5000);
  await shot(page, '1-loaded');

  // ── Click the "Identity" tab ───────────────────────────────────────────────
  console.log('[2/4] Clicking Identity tab...');

  // Try multiple selectors for the Identity tab
  let tabClicked = false;
  for (const sel of [
    'text=Identity',
    '[role="tab"]:has-text("Identity")',
    'mat-tab-header :has-text("Identity")',
    'a:has-text("Identity")',
    'button:has-text("Identity")',
    'li:has-text("Identity")',
    '.mat-tab-label:has-text("Identity")',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click();
        await wait(4000);
        console.log('  Clicked Identity tab via:', sel);
        tabClicked = true;
        break;
      }
    } catch {}
  }

  if (!tabClicked) {
    // Try clicking by coordinates — Identity tab is to the right of Package names
    const tabInfo = await page.evaluate(() => {
      const all = [...document.querySelectorAll('*')];
      const el = all.find(e =>
        e.innerText?.trim() === 'Identity' &&
        e.innerText?.length < 20
      );
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width/2, y: r.top + r.height/2, tag: el.tagName, cls: el.className.slice(0,50) };
    });
    console.log('  Identity element:', JSON.stringify(tabInfo));
    if (tabInfo) {
      await page.mouse.click(tabInfo.x, tabInfo.y);
      await wait(4000);
      tabClicked = true;
    }
  }

  await shot(page, '2-identity-tab');
  console.log('  URL:', page.url().slice(0, 90));

  // Print full page text of the Identity tab
  const text = await page.evaluate(() => document.body.innerText);
  console.log('\n  === IDENTITY TAB TEXT ===');
  console.log(text.slice(0, 2000).replace(/\n{3,}/g, '\n'));
  console.log('  =========================\n');

  // Print all buttons and inputs
  const btns = await page.evaluate(() =>
    [...document.querySelectorAll('button, [role="button"], a')]
      .map(e => e.innerText?.trim() || e.getAttribute('aria-label') || '')
      .filter(t => t && t.length > 1 && t.length < 80)
      .filter((v,i,a) => a.indexOf(v) === i)
  );
  console.log('  Buttons:', btns.join(' | '));

  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select, textarea')]
      .map(e => `${e.tagName}[${e.type||''}] value="${e.value||''}" label="${e.getAttribute('aria-label')||''}" text="${e.innerText?.trim().slice(0,50)||''}"`)
  );
  console.log('  Inputs:\n  ' + inputs.join('\n  '));

  // ── Try to start org verification or fill form ────────────────────────────
  console.log('\n[3/4] Interacting with Identity tab...');

  // Click any "Get started", "Organization", "Change", "Edit" buttons
  for (const sel of [
    'button:has-text("Get started")',
    'button:has-text("Change account type")',
    'button:has-text("Organization")',
    'button:has-text("Edit")',
    'button:has-text("Start")',
    'button:has-text("Verify")',
    'button:has-text("Begin")',
    'mat-radio-button:has-text("Organization")',
    '[role="radio"]:has-text("Organization")',
    'label:has-text("Organization")',
  ]) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click();
        await wait(3000);
        console.log('  Clicked:', sel);
        break;
      }
    } catch {}
  }

  await shot(page, '3-after-interaction');

  // Print what's there now
  const text2 = await page.evaluate(() => document.body.innerText);
  console.log('  Page text after:', text2.slice(0, 1000).replace(/\n{3,}/g, '\n'));

  const inputs2 = await page.locator('input[type="text"], input:not([type]), textarea').all();
  for (const inp of inputs2) {
    const label = (await inp.getAttribute('aria-label').catch(() => '') || '').toLowerCase();
    const ph    = (await inp.getAttribute('placeholder').catch(() => '') || '').toLowerCase();
    const val   = await inp.inputValue().catch(() => '');
    if (label.includes('search') || ph.includes('search')) continue;
    console.log(`  Field label="${label}" ph="${ph}" val="${val}"`);
    if (label.includes('duns') || ph.includes('duns')) {
      await inp.click({ clickCount: 3 }); await inp.fill(DUNS);
      console.log('  → Filled DUNS');
    } else if (label.includes('name') || ph.includes('name') || label.includes('org') || ph.includes('org')) {
      await inp.click({ clickCount: 3 }); await inp.fill(ORG_NAME);
      console.log('  → Filled org name:', ORG_NAME);
    }
  }

  // Save/submit
  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")','button:has-text("Next")','button[type="submit"]:not([disabled])']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click(); await wait(5000);
        console.log('  Submitted via:', sel); break;
      }
    } catch {}
  }

  await shot(page, '4-done');
  await browser.close();
  console.log('\nDone — paste full output.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
