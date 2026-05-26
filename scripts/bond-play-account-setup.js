/**
 * Bond — Change Play Console account to Organization
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

  // ── Go to /account page and map ALL arrow links with full URLs ────────────
  console.log('[1/5] Mapping all links on /account page...');
  await page.goto(
    `https://play.google.com/console/u/0/developers/${DEV_ID}/account`,
    { waitUntil: 'domcontentloaded', timeout: 60000 }
  );
  await wait(5000);
  await shot(page, '1-account');

  // Print ALL <a> href links (full, not truncated)
  const allLinks = await page.evaluate(() =>
    [...document.querySelectorAll('a[href]')]
      .map(a => ({ text: a.innerText?.trim().slice(0,40), href: a.href }))
      .filter(l => l.href.includes('play.google.com') || l.href.startsWith('/'))
  );
  console.log('  All Play Console links:');
  allLinks.forEach(l => console.log(`    "${l.text}" → ${l.href}`));

  // Map arrow_right_alt buttons to their Y position and nearby text
  const arrowMap = await page.evaluate(() =>
    [...document.querySelectorAll('button, a, [role="button"]')]
      .filter(e => e.innerText?.trim() === 'arrow_right_alt')
      .map(e => {
        const r = e.getBoundingClientRect();
        // Find the closest text above/beside this arrow
        const row = e.closest('[class*="row"], [class*="card"], [class*="item"], tr, li') || e.parentElement?.parentElement;
        return {
          x: Math.round(r.left + r.width/2),
          y: Math.round(r.top + r.height/2),
          rowText: row?.innerText?.trim().replace(/\n/g,' ').slice(0,60) || '',
          tag: e.tagName,
          href: e.href || ''
        };
      })
      .filter(a => a.x > 0 && a.y > 0)
  );
  console.log('\n  Arrow buttons with context:');
  arrowMap.forEach((a,i) => console.log(`    [${i}] y=${a.y} href="${a.href}" rowText="${a.rowText}"`));

  // ── Click the arrow next to "Account type" ────────────────────────────────
  console.log('\n[2/5] Finding Account type arrow and clicking it...');

  // Find the arrow whose row text contains "Account type" or "Personal"
  const acctTypeArrow = arrowMap.find(a =>
    a.rowText.toLowerCase().includes('account type') ||
    a.rowText.toLowerCase().includes('personal') ||
    a.rowText.toLowerCase().includes('about you')
  ) || arrowMap[0]; // fallback to first arrow

  console.log('  Target arrow:', JSON.stringify(acctTypeArrow));

  if (acctTypeArrow) {
    if (acctTypeArrow.href) {
      // Navigate directly if we have an href
      console.log('  Navigating to:', acctTypeArrow.href);
      await page.goto(acctTypeArrow.href, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } else {
      // Use mouse click
      await page.mouse.click(acctTypeArrow.x, acctTypeArrow.y);
    }
    await wait(5000);
    console.log('  URL (full):', page.url());
    await shot(page, '2-edit-page');
  }

  // ── Try each sub-URL pattern for the account edit page ───────────────────
  const currentUrl = page.url();
  if (currentUrl.includes('/account') && !currentUrl.includes('/account/')) {
    console.log('\n  Still on /account — trying sub-page URLs directly...');
    const subUrls = [
      `/console/u/0/developers/${DEV_ID}/account/developer-info`,
      `/console/u/0/developers/${DEV_ID}/account/developer-name`,
      `/console/u/0/developers/${DEV_ID}/account/about-you`,
      `/console/u/0/developers/${DEV_ID}/account/account-type`,
      `/console/u/0/developers/${DEV_ID}/setup/account-details`,
    ];
    for (const sub of subUrls) {
      await page.goto('https://play.google.com' + sub, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await wait(3000);
      const url = page.url();
      const text = await page.evaluate(() => document.body.innerText);
      const hasForm = text.toLowerCase().includes('organization') || text.toLowerCase().includes('account type');
      console.log(`  ${sub} → ${url.includes(sub.split('/').pop()) ? 'OK' : 'redirected'} hasForm=${hasForm}`);
      if (hasForm) {
        console.log('  Found form at:', url);
        await shot(page, '2b-found-form');
        break;
      }
    }
  }

  // ── Log current page state ────────────────────────────────────────────────
  console.log('\n[3/5] Current page:');
  console.log('  URL (full):', page.url());
  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('  Text:', pageText.slice(0, 1000).replace(/\n{3,}/g, '\n'));

  const inputs = await page.evaluate(() =>
    [...document.querySelectorAll('input, mat-radio-button, [role="radio"], select')]
      .map(e => `${e.tagName}[${e.type||''}] value="${e.value||''}" text="${e.innerText?.trim().slice(0,40)||''}" label="${e.getAttribute('aria-label')||''}"`)
  );
  console.log('  Inputs:\n  ' + inputs.join('\n  '));

  const btns2 = await page.evaluate(() =>
    [...document.querySelectorAll('button')]
      .map(e => e.innerText?.trim()).filter(t => t && t.length < 60)
  );
  console.log('  Buttons:', btns2.join(' | '));

  // ── Fill form if found ────────────────────────────────────────────────────
  console.log('\n[4/5] Filling form...');
  for (const sel of ['mat-radio-button:has-text("Organization")','[role="radio"]:has-text("Organization")','input[value="organization" i]','label:has-text("Organization")']) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 2000 })) { await el.click(); await wait(1000); console.log('  Selected Org via:', sel); break; }
    } catch {}
  }

  const textInputs = await page.locator('input[type="text"], input:not([type])').all();
  for (const inp of textInputs) {
    const label = (await inp.getAttribute('aria-label').catch(() => '')||'').toLowerCase();
    const ph = (await inp.getAttribute('placeholder').catch(() => '')||'').toLowerCase();
    const val = await inp.inputValue().catch(() => '');
    if (label.includes('search') || ph.includes('search')) continue;
    console.log(`  Field label="${label}" ph="${ph}" val="${val}"`);
    if (label.includes('duns') || ph.includes('duns')) { await inp.click({clickCount:3}); await inp.fill(DUNS); console.log('  → DUNS'); }
    else if (label || ph || val) { await inp.click({clickCount:3}); await inp.fill(ORG_NAME); console.log('  → name'); }
  }

  for (const sel of ['button:has-text("Save")','button:has-text("Submit")','button:has-text("Continue")','button:has-text("Next")']) {
    try { const el = page.locator(sel).first(); if (await el.isVisible({timeout:2000})) { await el.click(); await wait(5000); console.log('  Saved via:', sel); break; } } catch {}
  }

  await shot(page, '5-done');
  await browser.close();
  console.log('\nDone.');
})().catch(e => { console.error('Bond error:', e.message); process.exit(1); });
