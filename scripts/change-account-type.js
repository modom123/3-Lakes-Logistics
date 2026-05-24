/**
 * Bond — Change Play Console account: Individual → Organization
 * v3 — dumps all buttons first to find exact selector, then handles Angular dialog
 *
 * Run: node scripts\change-account-type.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
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
  console.log(`  Screenshot → scripts/acct-${label}.png`);
}

async function dumpButtons(page) {
  return page.evaluate(() => {
    const els = [...document.querySelectorAll('button, a, [role="button"], [role="link"], mat-list-item, .mat-list-item')];
    return els
      .map(e => ({
        tag:  e.tagName,
        text: (e.innerText || e.textContent || '').trim().slice(0, 80),
        aria: e.getAttribute('aria-label') || '',
        id:   e.id || '',
        cls:  e.className?.toString().slice(0, 60) || '',
      }))
      .filter(e => e.text.length > 1 || e.aria.length > 1)
      .slice(0, 60);
  });
}

async function dumpInputs(page) {
  return page.evaluate(() => {
    const els = [...document.querySelectorAll('input, textarea, mat-select, [role="combobox"]')];
    return els.map(e => ({
      tag:         e.tagName,
      type:        e.type || '',
      placeholder: e.placeholder || '',
      ariaLabel:   e.getAttribute('aria-label') || '',
      id:          e.id || '',
      name:        e.name || '',
      value:       e.value?.slice(0, 40) || '',
      visible:     e.offsetParent !== null,
    }));
  });
}

(async () => {
  console.log('=== Bond: Change Account Type → Organization (v3) ===\n');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    console.log('Opening new browser window...');
    browser = await chromium.launch({ headless: false, slowMo: 100, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Go to exact account URL ───────────────────────────────────────────────
  console.log('\n[1] Navigating to account details...');
  await page.goto(ACCOUNT_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(6000);
  await shot(page, '1-account');
  console.log('  URL:', page.url().slice(0, 100));

  // Dump all buttons so we can see exact text
  const buttons = await dumpButtons(page);
  console.log('\n  All clickable elements on page:');
  buttons.forEach((b, i) => {
    if (b.text || b.aria)
      console.log(`    [${i}] <${b.tag}> "${b.text}" aria="${b.aria}" id="${b.id}"`);
  });

  // ── Find and click Change account type ───────────────────────────────────
  console.log('\n[2] Clicking "Change account type"...');

  // Try by text content (Angular renders text in child spans)
  let clicked = await page.evaluate(() => {
    const all = [...document.querySelectorAll('button, a, [role="button"], span, div')];
    const target = all.find(el => {
      const t = (el.innerText || el.textContent || '').trim();
      return t === 'Change account type' || t.toLowerCase().includes('change account type');
    });
    if (target) {
      // Walk up to clickable parent if needed
      let el = target;
      for (let i = 0; i < 5; i++) {
        if (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button') {
          el.click();
          return `clicked <${el.tagName}> "${(el.innerText||'').trim().slice(0,40)}"`;
        }
        el = el.parentElement;
        if (!el) break;
      }
      target.click();
      return `clicked target "${target.innerText?.trim().slice(0,40)}"`;
    }
    return null;
  });

  if (clicked) {
    console.log('  ✓', clicked);
  } else {
    console.log('  Button not found automatically.');
    console.log('  In the browser window, click "Change account type" then come back here.');
    await pause('  Press Enter after clicking it... ');
  }

  await wait(5000);
  await shot(page, '2-after-click');

  // Dump inputs visible after click
  const inputs = await dumpInputs(page);
  console.log('\n  All input fields now visible:');
  inputs.forEach((inp, i) => {
    console.log(`    [${i}] <${inp.tag}> type="${inp.type}" placeholder="${inp.placeholder}" aria="${inp.ariaLabel}" id="${inp.id}" name="${inp.name}" visible=${inp.visible}`);
  });

  // Also dump dialog content if a mat-dialog opened
  const dialogText = await page.evaluate(() => {
    const d = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-container');
    return d ? d.innerText?.slice(0, 500) : null;
  });
  if (dialogText) {
    console.log('\n  Dialog content:', dialogText.replace(/\n+/g, ' | '));
  }

  // Dump updated buttons
  const buttons2 = await dumpButtons(page);
  console.log('\n  Clickable elements after click:');
  buttons2.forEach((b, i) => {
    if (b.text || b.aria)
      console.log(`    [${i}] <${b.tag}> "${b.text}" aria="${b.aria}"`);
  });

  // ── Try to fill DUNS using any visible input ──────────────────────────────
  console.log('\n[3] Attempting to fill DUNS and org name...');

  const visibleInputs = inputs.filter(i => i.visible);
  console.log(`  ${visibleInputs.length} visible input(s) found`);

  // Fill by index for any visible inputs
  const allInputEls = await page.locator('input:visible, textarea:visible').all();
  for (let i = 0; i < allInputEls.length; i++) {
    const inp = allInputEls[i];
    const ph  = await inp.getAttribute('placeholder').catch(() => '');
    const lbl = await inp.getAttribute('aria-label').catch(() => '');
    const id  = await inp.getAttribute('id').catch(() => '');
    console.log(`  Input[${i}]: placeholder="${ph}" aria="${lbl}" id="${id}"`);

    const key = `${ph} ${lbl} ${id}`.toLowerCase();
    if (key.includes('duns') || key.includes('d-u-n-s')) {
      await inp.click(); await inp.fill(DUNS);
      console.log(`    → Filled DUNS: ${DUNS}`);
    } else if (key.includes('org') || key.includes('company') || key.includes('business') || key.includes('name')) {
      const cur = await inp.inputValue().catch(() => '');
      if (!cur) { await inp.click(); await inp.fill(ORG_NAME); console.log(`    → Filled org: ${ORG_NAME}`); }
      else { console.log(`    → Already has value: "${cur}"`); }
    }
  }

  if (allInputEls.length === 0) {
    console.log('  No visible inputs found. May need to click something in the browser first.');
    await pause('  Fill in any fields in the browser, then press Enter... ');
  }

  await wait(1000);
  await shot(page, '3-filled');

  // ── Submit ────────────────────────────────────────────────────────────────
  console.log('\n[4] Submitting...');

  const submitted = await page.evaluate(() => {
    const all = [...document.querySelectorAll('button, [role="button"]')];
    const btn = all.find(el => {
      const t = (el.innerText || el.textContent || '').trim().toLowerCase();
      return t.includes('submit') || t.includes('confirm') || t.includes('save') ||
             t.includes('change account') || t === 'ok' || t === 'continue';
    });
    if (btn && !btn.disabled) { btn.click(); return btn.innerText?.trim(); }
    return null;
  });

  if (submitted) {
    console.log('  ✓ Submitted:', submitted);
  } else {
    console.log('  Submit button not found. Click Save/Submit/Confirm in the browser.');
    await pause('  Press Enter after submitting... ');
  }

  await wait(6000);
  await shot(page, '4-final');
  const finalURL = page.url();
  console.log('\n  Final URL:', finalURL.slice(0, 100));

  console.log('\n=== Done — keeping browser open ===');
  console.log('Check scripts/acct-*.png for screenshots of each step.');
  await pause('Press Enter to close browser... ');
  await browser.close();

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
