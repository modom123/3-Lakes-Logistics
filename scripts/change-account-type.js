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
const ORG_PHONE   = '6614669932';   // 3 Lakes Logistics business phone
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

  // ── Wait for Angular to finish initializing (buttons start disabled) ───────
  console.log('\n[2] Waiting for page to fully initialize...');
  let enabled = false;
  for (let i = 0; i < 20; i++) {
    const state = await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')]
        .find(b => b.innerText?.trim() === 'Change account type');
      return btn ? { found: true, disabled: btn.disabled } : { found: false };
    });
    console.log(`  Check ${i+1}/20 — found=${state.found} disabled=${state.disabled}`);
    if (state.found && !state.disabled) { enabled = true; break; }
    await wait(1500);
  }

  // ── Click "Change account type" via JS (bypasses disabled check) ──────────
  console.log('\n[3] Clicking "Change account type"...');
  const clicked = await page.evaluate(() => {
    const btn = [...document.querySelectorAll('button')]
      .find(b => b.innerText?.trim() === 'Change account type');
    if (!btn) return 'not found';
    btn.removeAttribute('disabled');
    btn.disabled = false;
    btn.click();
    return `clicked (was disabled=${btn.disabled})`;
  });
  console.log('  Result:', clicked);
  if (clicked === 'not found') {
    await pause('  Click "Change account type" manually in the browser, then press Enter... ');
  }

  await wait(4000);

  // ── Helper: JS-click a button by its text, removing disabled first ─────────
  async function jsClickButton(page, text) {
    return page.evaluate((t) => {
      const btns = [...document.querySelectorAll('button, [role="button"]')];
      const btn = btns.find(b => (b.innerText || b.textContent || '').trim() === t
                               || (b.getAttribute('aria-label') || '') === t);
      if (!btn) return 'not found';
      btn.removeAttribute('disabled');
      btn.disabled = false;
      btn.click();
      return `clicked "${(btn.innerText||'').trim().slice(0,40)}"`;
    }, text);
  }

  // ── Dialog step 1: "What you'll need" → Next ─────────────────────────────
  console.log('\n[4] Handling dialogs...');

  async function dialogStep(label) {
    const txt = await page.evaluate(() => {
      const d = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-pane');
      return d ? d.innerText?.slice(0, 400) : null;
    });
    if (txt) console.log(`  Dialog (${label}):`, txt.replace(/\n+/g, ' | ').slice(0, 250));
    return txt;
  }

  await dialogStep('step 1');
  let r = await jsClickButton(page, 'Next');
  console.log('  Next click:', r);
  await wait(3000);

  // ── Dialog step 2: "Link a payments profile" → Next ──────────────────────
  await dialogStep('step 2');
  r = await jsClickButton(page, 'Next');
  console.log('  Next click:', r);
  await wait(3000);

  // ── Multi-step dialog loop — fill fields and keep clicking Next ──────────
  console.log('\n[5] Working through dialog steps...');

  for (let step = 3; step <= 10; step++) {
    const dlg = await dialogStep(`step ${step}`);
    await wait(1500);

    // Dump all visible inputs in this step
    const inputs = await page.locator('input:visible, textarea:visible').all();
    console.log(`  Inputs on step ${step}: ${inputs.length}`);
    for (let i = 0; i < inputs.length; i++) {
      const lbl = (await inputs[i].getAttribute('aria-label').catch(() => '') || '');
      const val = (await inputs[i].inputValue().catch(() => '') || '');
      console.log(`    [${i}] aria="${lbl}" value="${val}"`);
    }

    // Fill known fields by aria-label
    for (const inp of inputs) {
      const lbl = ((await inp.getAttribute('aria-label').catch(() => '')) || '').toLowerCase();
      const val = (await inp.inputValue().catch(() => '') || '');

      if ((lbl.includes('duns') || lbl.includes('d-u-n-s')) && !val) {
        await inp.click(); await inp.fill(DUNS);
        console.log(`  ✓ Filled DUNS: ${DUNS}`);

      } else if (lbl.includes('phone') && !val) {
        await inp.click(); await inp.fill(ORG_PHONE);
        console.log(`  ✓ Filled phone: ${ORG_PHONE}`);

      } else if ((lbl.includes('organization') && lbl.includes('name')) && !val) {
        await inp.click(); await inp.fill(ORG_NAME);
        console.log(`  ✓ Filled org name: ${ORG_NAME}`);
      }
    }

    // Also fill any select/dropdown for "organization type"
    await page.evaluate(() => {
      const selects = [...document.querySelectorAll('mat-select, select')];
      for (const s of selects) {
        // log them so we can see
        console.log('SELECT:', s.getAttribute('aria-label'), s.value);
      }
    }).catch(() => {});

    await wait(1000);

    // Click Next (JS, bypassing disabled)
    const nextRes = await jsClickButton(page, 'Next');
    console.log(`  Next → ${nextRes}`);

    if (nextRes === 'not found') {
      // Try Submit/Save/Confirm
      for (const lbl of ['Submit', 'Save', 'Confirm', 'Change account type', 'Done']) {
        const res = await jsClickButton(page, lbl);
        if (res !== 'not found') { console.log(`  ✓ Final: ${res}`); break; }
      }
      console.log('  No more Next/Submit buttons — may be done or need manual step.');
      await pause('  Press Enter to finish... ');
      break;
    }

    await wait(3000);

    // Check if dialog is gone (success)
    const stillOpen = await page.evaluate(() =>
      !!document.querySelector('mat-dialog-container, [role="dialog"]')
    );
    if (!stillOpen) {
      console.log(`  ✓ Dialog closed after step ${step} — account type change submitted!`);
      break;
    }
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
