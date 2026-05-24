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

  // ── Click the first arrow_right_alt button (navigates to account/developer edit) ─
  console.log('[2/4] Clicking first arrow button to open edit form...');
  const arrows = await page.evaluate(() =>
    [...document.querySelectorAll('button, a, [role="button"]')]
      .filter(e => e.innerText?.trim() === 'arrow_right_alt')
      .map(e => { const r = e.getBoundingClientRect(); return { x: r.left + r.width/2, y: r.top + r.height/2, visible: r.width > 0 && r.height > 0 }; })
      .filter(a => a.visible)
  );
  console.log('  Found', arrows.length, 'arrow buttons at y positions:', arrows.map(a => Math.round(a.y)).join(', '));

  // Click the first arrow (About you section)
  if (arrows.length > 0) {
    await page.mouse.click(arrows[0].x, arrows[0].y);
    await wait(5000);
    console.log('  URL after click:', page.url());
    await shot(page, '2-edit-page');
  }

  // If we navigated, now print everything on this page
  const editUrl = page.url();
  const editText = await page.evaluate(() => document.body.innerText);
  console.log('  Page text:', editText.slice(0, 800).replace(/\n+/g, ' '));

  // Log all inputs on this page
  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select')]
      .map(e => ({
        tag: e.tagName, type: e.type||'', value: e.value||'',
        label: e.getAttribute('aria-label')||'',
        placeholder: e.getAttribute('placeholder')||'',
        text: e.innerText?.trim().slice(0,50)||'',
        checked: e.checked,
        rect: (() => { const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; })()
      }))
  );
  console.log('\n  All inputs:');
  inputs.forEach(i => console.log(`    ${i.tag}[${i.type}] value="${i.value}" label="${i.label}" text="${i.text}" at y=${i.rect.y}`));

  // ── Fill the form ─────────────────────────────────────────────────────────
  console.log('\n[3/4] Filling form...');

  // Select Organization radio
  let orgDone = false;
  for (const inp of inputs) {
    if (inp.text.toLowerCase().includes('organization') || inp.value.toLowerCase().includes('organization')) {
      await page.mouse.click(inp.rect.x + inp.rect.w/2, inp.rect.y + inp.rect.h/2);
      await wait(1000);
      console.log('  Clicked Organization at y=' + inp.rect.y);
      orgDone = true;
      break;
    }
  }
  if (!orgDone) {
    // Also try by selector
    for (const sel of ['mat-radio-button:has-text("Organization")','[role="radio"]:has-text("Organization")','label:has-text("Organization")','input[value="organization" i]']) {
      try {
        const el = page.locator(sel).first();
        if (await el.isVisible({ timeout: 2000 })) { await el.click(); await wait(1000); console.log('  Org via selector:', sel); orgDone = true; break; }
      } catch {}
    }
  }
  if (!orgDone) console.log('  Organization option not found');

  // Re-query inputs after selecting org (may reveal new fields like DUNS)
  await wait(2000);
  await shot(page, '3-after-org-select');

  const inputs2 = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of inputs2) {
    const label = await inp.getAttribute('aria-label').catch(() => '') || '';
    const ph = await inp.getAttribute('placeholder').catch(() => '') || '';
    const val = await inp.inputValue().catch(() => '');
    console.log(`  Text input: label="${label}" ph="${ph}" val="${val}"`);
    if (label.toLowerCase().includes('search') || ph.toLowerCase().includes('search')) continue;
    if (label.toLowerCase().includes('duns') || ph.toLowerCase().includes('duns')) {
      await inp.click({ clickCount: 3 }); await inp.fill(DUNS);
      console.log('  Filled DUNS:', DUNS);
    } else if (label || ph || val) {
      await inp.click({ clickCount: 3 }); await inp.fill(ORG_NAME);
      console.log('  Filled name to:', ORG_NAME);
    }
  }

  await shot(page, '4-before-save');

  // ── Save ──────────────────────────────────────────────────────────────────
  console.log('\n[4/4] Saving...');
  let saved = false;
  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")','button[type="submit"]:not([disabled])']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) { await el.click(); await wait(6000); console.log('  Saved via:', sel); saved = true; break; }
    } catch {}
  }
  if (!saved) {
    const btns = await page.evaluate(() =>
      [...document.querySelectorAll('button')].map(b => b.innerText?.trim()).filter(t=>t)
    );
    console.log('  Buttons available:', btns.join(' | '));
  }

  await shot(page, '5-done');
  const finalText = await page.evaluate(() => document.body.innerText);
  console.log('  Final URL:', page.url().slice(0,90));
  console.log('  Result:', finalText.slice(0, 300).replace(/\n+/g, ' '));

  await browser.close();
  console.log('\nDone.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
