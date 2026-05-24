/**
 * Bond — Trigger GitHub Actions Android build
 *
 * Run: node scripts\trigger-build.js
 *
 * Opens GitHub Actions and clicks "Run workflow" for the Android AAB build.
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);}

const { chromium } = require('playwright');

const WORKFLOW_URL = 'https://github.com/modom123/3-Lakes-Logistics/actions/workflows/android-build.yml';
const VERSION_CODE = '1';
const VERSION_NAME = '1.0.0';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  console.log('=== Bond: Trigger Android AAB Build ===\n');

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
    console.log('Opened new browser window — please log into GitHub if prompted');
  }

  // ── Step 1: Navigate to workflow ──────────────────────────────────────────
  console.log('\n[1] Opening workflow page...');
  await page.goto(WORKFLOW_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(3000);
  console.log('  URL:', page.url().slice(0, 80));

  // ── Step 2: Click "Run workflow" button ───────────────────────────────────
  console.log('\n[2] Clicking "Run workflow"...');
  const runBtn = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button, summary, [role="button"]')];
    const btn = btns.find(b => /run\s*workflow/i.test(b.innerText || b.textContent || ''));
    if (btn) { btn.click(); return true; }
    return false;
  });

  if (!runBtn) {
    // Try Playwright locator
    try {
      await page.getByRole('button', { name: /run workflow/i }).first().click();
      console.log('  ✓ Clicked via locator');
    } catch {
      console.log('  ⚠ "Run workflow" button not found — may need to log into GitHub');
      console.log('  Please click it manually in the browser');
    }
  } else {
    console.log('  ✓ Clicked "Run workflow"');
  }

  await wait(2000);

  // ── Step 3: Fill version fields in dropdown form ──────────────────────────
  console.log('\n[3] Filling version inputs...');
  const filled = await page.evaluate(({ vc, vn }) => {
    const inputs = [...document.querySelectorAll('input[type="text"], input:not([type])')];
    let count = 0;
    inputs.forEach(inp => {
      const lbl = (inp.getAttribute('aria-label') || inp.placeholder || inp.name || inp.id || '').toLowerCase();
      if (lbl.includes('version_code') || lbl.includes('version code')) {
        inp.value = vc;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        count++;
      }
      if (lbl.includes('version_name') || lbl.includes('version name')) {
        inp.value = vn;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        count++;
      }
    });
    return count;
  }, { vc: VERSION_CODE, vn: VERSION_NAME });

  console.log(`  ✓ Filled ${filled} field(s) — version ${VERSION_NAME} (${VERSION_CODE})`);
  await wait(1000);

  // ── Step 4: Click the submit "Run workflow" button inside the form ─────────
  console.log('\n[4] Submitting the workflow run...');
  const submitted = await page.evaluate(() => {
    // The confirmation button inside the dropdown is typically a green button
    const btns = [...document.querySelectorAll('button')];
    const btn = btns.find(b => {
      const txt = (b.innerText || b.textContent || '').trim();
      return /run\s*workflow/i.test(txt) && b.type === 'submit';
    });
    if (btn) { btn.click(); return true; }
    // Fallback: any green/primary button with "Run workflow" text
    const any = btns.find(b => /run\s*workflow/i.test(b.innerText || ''));
    if (any) { any.click(); return true; }
    return false;
  });

  if (submitted) {
    console.log('  ✓ Workflow triggered!');
  } else {
    try {
      const submitBtns = await page.getByRole('button', { name: /run workflow/i }).all();
      if (submitBtns.length > 1) {
        await submitBtns[submitBtns.length - 1].click();
        console.log('  ✓ Clicked submit button');
      }
    } catch {
      console.log('  ⚠ Could not auto-submit — please click the green "Run workflow" button in Chrome');
    }
  }

  await wait(4000);

  // ── Step 5: Confirm it started ────────────────────────────────────────────
  console.log('\n[5] Checking for running workflow...');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await wait(3000);

  const runStatus = await page.evaluate(() => {
    const items = [...document.querySelectorAll('[aria-label], .run-status, .checks-list-item')];
    const running = document.body.innerText.match(/(queued|in progress|running)/i);
    return running ? running[0] : null;
  });

  console.log(runStatus
    ? `  ✓ Build is: ${runStatus}`
    : '  Check the GitHub Actions tab — the build should be queued');

  console.log('\n=== Done ===');
  console.log(`  Workflow: ${WORKFLOW_URL}`);
  console.log('  The AAB build takes ~10 minutes.');
  console.log('  When done, download the artifact from the workflow run page.');
  console.log('\n  Keeping browser open on Actions page...');

  // Stay on the actions page
  await page.goto(WORKFLOW_URL, { waitUntil: 'domcontentloaded' });

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
