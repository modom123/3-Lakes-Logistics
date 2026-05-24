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
  try {
    const p = path.join(__dirname, `acct-${label}.png`);
    await page.screenshot({ path: p, fullPage: false, timeout: 8000 });
    console.log(`  Screenshot → scripts/acct-${label}.png`);
  } catch (e) {
    console.log(`  Screenshot skipped (${e.message.slice(0, 60)})`);
  }
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

  // ── Click "Change account type" — use exact button match ─────────────────
  console.log('\n[2] Clicking "Change account type"...');

  // Use Playwright's getByRole for exact button text match (avoids matching parents)
  const changeBtn = page.getByRole('button', { name: 'Change account type', exact: true });
  if (await changeBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await changeBtn.click();
    console.log('  ✓ Clicked "Change account type" button');
  } else {
    // JS fallback: find BUTTON whose own direct text is exactly "Change account type"
    const clicked = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')];
      const btn = btns.find(b => b.innerText?.trim() === 'Change account type');
      if (btn) { btn.click(); return true; }
      return false;
    });
    if (clicked) {
      console.log('  ✓ JS-clicked "Change account type"');
    } else {
      console.log('  Button not found — click it manually in the browser.');
      await pause('  Press Enter after clicking "Change account type"... ');
    }
  }

  await wait(4000);

  // ── Dialog: "What do you want to update?" → click Next ───────────────────
  console.log('\n[3] Handling dialog...');
  const dialogText = await page.evaluate(() => {
    const d = document.querySelector('mat-dialog-container, [role="dialog"]');
    return d ? d.innerText?.slice(0, 300) : null;
  });
  if (dialogText) {
    console.log('  Dialog:', dialogText.replace(/\n+/g, ' | '));
  }

  // Click Next in dialog to proceed to DUNS step
  const nextBtn = page.getByRole('button', { name: 'Next', exact: true });
  if (await nextBtn.first().isVisible({ timeout: 4000 }).catch(() => false)) {
    await nextBtn.first().click();
    console.log('  ✓ Clicked Next');
    await wait(4000);
  } else {
    console.log('  No Next button visible yet.');
  }

  // Dump what's on screen now
  const afterNext = await page.evaluate(() => {
    const d = document.querySelector('mat-dialog-container, [role="dialog"]');
    return d ? d.innerText?.slice(0, 500) : document.body.innerText?.slice(0, 500);
  });
  console.log('  After Next:', afterNext?.replace(/\n+/g, ' | ').slice(0, 300));

  // Dump all inputs
  const allInputEls = await page.locator('input:visible, textarea:visible').all();
  console.log(`\n  Visible inputs: ${allInputEls.length}`);
  for (let i = 0; i < allInputEls.length; i++) {
    const inp = allInputEls[i];
    const ph  = await inp.getAttribute('placeholder').catch(() => '');
    const lbl = await inp.getAttribute('aria-label').catch(() => '');
    const val = await inp.inputValue().catch(() => '');
    console.log(`    Input[${i}]: aria="${lbl}" placeholder="${ph}" value="${val}"`);
  }

  // ── Fill DUNS in any visible input that mentions DUNS ────────────────────
  console.log('\n[4] Filling DUNS...');
  let dunsFilled = false;
  for (let i = 0; i < allInputEls.length; i++) {
    const inp = allInputEls[i];
    const lbl = (await inp.getAttribute('aria-label').catch(() => '') || '').toLowerCase();
    const ph  = (await inp.getAttribute('placeholder').catch(() => '') || '').toLowerCase();
    if (lbl.includes('duns') || ph.includes('duns') || lbl.includes('d-u-n-s')) {
      await inp.click(); await inp.fill(DUNS);
      console.log(`  ✓ Filled DUNS: ${DUNS}`);
      dunsFilled = true;
    }
  }
  if (!dunsFilled) {
    console.log('  DUNS field not found on this step — may appear after another Next click.');
    console.log('  Check the browser and fill DUNS manually if visible.');
    await pause('  Press Enter when ready to continue... ');
  }

  await wait(1000);

  // ── Click Next / Submit / Save to confirm ─────────────────────────────────
  console.log('\n[5] Clicking Next/Submit...');
  const nextBtn2 = page.getByRole('button', { name: 'Next', exact: true });
  const submitBtn = page.getByRole('button', { name: /submit|save|confirm|change account/i });
  let submitted = false;
  if (await nextBtn2.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await nextBtn2.first().click();
    console.log('  ✓ Clicked Next');
    submitted = true;
  } else if (await submitBtn.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await submitBtn.first().click();
    console.log('  ✓ Clicked Submit/Save');
    submitted = true;
  }
  if (!submitted) {
    console.log('  No Next/Submit found — click it manually in the browser.');
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
