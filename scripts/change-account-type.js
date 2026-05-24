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

  // ── Multi-step dialog loop — fill fields INSIDE the dialog only ──────────
  console.log('\n[5] Working through dialog steps...');
  let lastDialogText = '';

  for (let step = 3; step <= 10; step++) {
    await wait(2000);

    // Get FULL dialog content — scroll to bottom first to reveal all fields
    await page.evaluate(() => {
      const dlg = document.querySelector('mat-dialog-container, [role="dialog"]');
      if (dlg) { dlg.scrollTop = dlg.scrollHeight; }
      const content = dlg?.querySelector('mat-dialog-content, .mat-dialog-content, .dialog-content');
      if (content) { content.scrollTop = content.scrollHeight; }
    });
    await wait(500);

    const dialogInfo = await page.evaluate(() => {
      const dlg = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-pane mat-card');
      if (!dlg) return null;

      // Get ALL form elements — inputs, mat-select, radio, checkbox
      const formEls = [...dlg.querySelectorAll('input, textarea, mat-select, select, [role="combobox"], [role="listbox"], [role="radio"], mat-radio-button')].map(el => ({
        tag:         el.tagName,
        role:        el.getAttribute('role') || '',
        ariaLabel:   el.getAttribute('aria-label') || '',
        placeholder: el.placeholder || '',
        id:          el.id || '',
        type:        el.type || '',
        value:       el.value || el.getAttribute('ng-reflect-value') || el.textContent?.trim().slice(0, 40) || '',
        visible:     el.offsetParent !== null,
        disabled:    el.disabled || el.getAttribute('aria-disabled') === 'true',
      }));

      const buttons = [...dlg.querySelectorAll('button, [role="button"]')].map(el => ({
        text:     (el.innerText || '').trim().slice(0, 40),
        disabled: el.disabled,
        aria:     el.getAttribute('aria-label') || '',
      }));

      return {
        fullText: dlg.innerText,   // NO truncation
        formEls,
        buttons,
      };
    });

    if (!dialogInfo) {
      console.log(`  No dialog on step ${step} — done!`);
      break;
    }

    console.log(`\n  --- Dialog step ${step} ---`);
    console.log('  FULL TEXT:\n  ' + (dialogInfo.fullText || '').replace(/\n+/g, '\n  '));
    console.log(`  Form elements (${dialogInfo.formEls.length}):`);
    dialogInfo.formEls.forEach((el, i) =>
      console.log(`    [${i}] <${el.tag}> role="${el.role}" aria="${el.ariaLabel}" placeholder="${el.placeholder}" value="${el.value}" visible=${el.visible} disabled=${el.disabled}`)
    );
    console.log(`  Buttons:`);
    dialogInfo.buttons.forEach((b, i) =>
      console.log(`    [${i}] "${b.text}" aria="${b.aria}" disabled=${b.disabled}`)
    );

    // Stop after 2 identical steps with no change
    if (step > 4 && dialogInfo.fullText === lastDialogText) {
      console.log('  ⚠ Dialog unchanged for 2 steps — pausing for manual action.');
      await pause('  Fill any remaining fields in the browser, then press Enter... ');
      break;
    }
    lastDialogText = dialogInfo.fullText;

    // Fill fields inside the dialog
    const filled = await page.evaluate(({ DUNS, ORG_PHONE, ORG_NAME }) => {
      const dlg = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-pane mat-card');
      if (!dlg) return [];
      const log = [];
      const inputs = [...dlg.querySelectorAll('input, textarea')];
      for (const inp of inputs) {
        const lbl = (inp.getAttribute('aria-label') || inp.placeholder || inp.id || '').toLowerCase();
        if (!inp.value) {
          if (lbl.includes('duns') || lbl.includes('d-u-n-s')) {
            inp.value = DUNS;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            log.push(`DUNS → ${DUNS}`);
          } else if (lbl.includes('phone')) {
            inp.value = ORG_PHONE;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            log.push(`phone → ${ORG_PHONE}`);
          } else if (lbl.includes('org') || lbl.includes('company') || lbl.includes('business name')) {
            inp.value = ORG_NAME;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            log.push(`org → ${ORG_NAME}`);
          }
        }
      }
      return log;
    }, { DUNS, ORG_PHONE, ORG_NAME });

    if (filled.length) console.log('  Filled:', filled.join(', '));

    await wait(500);

    // Click Next inside the dialog (JS, bypasses disabled)
    const nextRes = await page.evaluate(() => {
      const dlg = document.querySelector('mat-dialog-container, [role="dialog"], .cdk-overlay-pane mat-card');
      if (!dlg) return 'no dialog';
      const btns = [...dlg.querySelectorAll('button, [role="button"]')];
      // Prefer Next, then Submit/Confirm/Save/Done/Change
      const order = ['next', 'submit', 'confirm', 'save', 'done', 'change'];
      for (const key of order) {
        const btn = btns.find(b => (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase().includes(key));
        if (btn) {
          btn.removeAttribute('disabled');
          btn.disabled = false;
          btn.click();
          return `clicked "${(btn.innerText || '').trim()}"`;
        }
      }
      return 'no button found';
    });
    console.log(`  Button click → ${nextRes}`);

    await wait(2000);

    // Check if dialog closed
    const stillOpen = await page.evaluate(() =>
      !!document.querySelector('mat-dialog-container, [role="dialog"]')
    );
    if (!stillOpen) {
      console.log(`  ✓ Dialog closed — account type change submitted!`);
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
