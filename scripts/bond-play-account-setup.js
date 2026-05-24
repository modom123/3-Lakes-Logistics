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

  // Log ALL links and their hrefs
  const links = await page.evaluate(() =>
    [...document.querySelectorAll('a')].map(a => `${a.innerText?.trim().slice(0,30)} → ${a.href}`)
  );
  console.log('  All links:\n  ' + links.join('\n  '));

  // Log all elements with routerLink attribute
  const routerLinks = await page.evaluate(() =>
    [...document.querySelectorAll('[routerlink], [ng-reflect-router-link], [_nghost]')]
      .filter(e => e.innerText?.trim().includes('About you') && e.innerText?.length < 300)
      .map(e => `${e.tagName}.${e.className.slice(0,40)} | text="${e.innerText?.trim().slice(0,60)}" | routerlink="${e.getAttribute('routerlink')||''}"`)
  );
  console.log('  Angular router links near "About you":\n  ' + routerLinks.join('\n  '));

  // ── Use real mouse click on the "About you" arrow ─────────────────────────
  console.log('\n[2/4] Clicking "About you" with real mouse...');

  // Find the bounding box of the "About you" section
  const box = await page.evaluate(() => {
    const all = [...document.querySelectorAll('*')];
    const el = all.find(e =>
      e.innerText?.trim().startsWith('About you') &&
      e.innerText?.length < 400 &&
      e.children.length > 0
    );
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, tag: el.tagName, cls: el.className.slice(0,50) };
  });
  console.log('  "About you" element:', JSON.stringify(box));

  if (box && box.x > 0 && box.y > 0) {
    // Click at the right edge where the arrow is
    await page.mouse.click(box.x + box.w / 3, box.y);
    await wait(4000);
    console.log('  URL after mouse click:', page.url().slice(0, 90));
    await shot(page, '2-after-click');
  }

  // If still on same page, try each arrow_right_alt button by position
  if (page.url().includes('/account') && !page.url().includes('/account/')) {
    console.log('  Still on /account — trying arrow buttons one by one...');
    const arrows = await page.evaluate(() => {
      return [...document.querySelectorAll('button, a, [role="button"]')]
        .filter(e => e.innerText?.trim() === 'arrow_right_alt')
        .map(e => {
          const r = e.getBoundingClientRect();
          return { x: r.left + r.width/2, y: r.top + r.height/2, visible: r.width > 0 && r.height > 0 };
        });
    });
    console.log('  Arrow buttons found:', JSON.stringify(arrows));
    for (const arrow of arrows.filter(a => a.visible)) {
      await page.mouse.click(arrow.x, arrow.y);
      await wait(3000);
      const newUrl = page.url();
      console.log('  URL after clicking arrow at y=' + Math.round(arrow.y) + ':', newUrl.slice(0, 90));
      if (!newUrl.endsWith('/account')) {
        console.log('  Navigated to new page!');
        break;
      }
    }
    await shot(page, '2b-after-arrows');
  }

  // ── Log what's now on the page ────────────────────────────────────────────
  console.log('\n[3/4] Current page state...');
  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('  URL:', page.url().slice(0, 90));
  console.log('  Page text:', pageText.slice(0, 600).replace(/\n+/g, ' '));

  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select')]
      .map(e => `${e.tagName} type=${e.type||''} value="${e.value||''}" label="${e.getAttribute('aria-label')||''}" text="${e.innerText?.trim().slice(0,40)||''}"`)
  );
  console.log('  Inputs:\n  ' + inputs.join('\n  '));

  // ── Try to make changes if on edit page ───────────────────────────────────
  console.log('\n[4/4] Attempting changes...');
  let orgSelected = false;
  for (const sel of ['input[value="organization" i]','mat-radio-button:has-text("Organization")','[role="radio"]:has-text("Organization")','label:has-text("Organization")']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) {
        await el.click(); await wait(1000);
        console.log('  Selected Organization via:', sel);
        orgSelected = true; break;
      }
    } catch {}
  }

  const allInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of allInputs) {
    const label = await inp.getAttribute('aria-label').catch(() => '') || '';
    const ph = await inp.getAttribute('placeholder').catch(() => '') || '';
    const val = await inp.inputValue().catch(() => '');
    if (label.toLowerCase().includes('search') || ph.toLowerCase().includes('search')) continue;
    if (label || ph || val) {
      console.log(`  Filling name field: label="${label}" ph="${ph}" val="${val}"`);
      await inp.click({ clickCount: 3 }); await inp.fill(ORG_NAME); break;
    }
  }

  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 3000 })) {
        await el.click(); await wait(5000);
        console.log('  Saved via:', sel); break;
      }
    } catch {}
  }

  await shot(page, '4-done');
  await browser.close();
  console.log('\nDone.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
