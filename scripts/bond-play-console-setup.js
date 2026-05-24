/**
 * Bond — Google Play Console Setup
 * Creates the app listing, links API access, grants service account
 * permissions, and uploads screenshots.
 *
 * Run: node scripts/bond-play-console-setup.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const repoRoot = path.join(__dirname, '..');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
  execSync('npm install', { cwd: repoRoot, stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: repoRoot, stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename, ...process.argv.slice(2)], { cwd: repoRoot, stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const APP_NAME     = '3 Lakes Driver';
const PACKAGE_NAME = 'com.threelakes.driver';
const SA_EMAIL     = 'james-bond@lakes-mobile-app.iam.gserviceaccount.com';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, name) {
  const p = path.join(__dirname, `play-${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log(`  Screenshot saved: scripts/play-${name}.png`);
  return p;
}

// Try multiple selectors, return first visible one
async function findVisible(page, selectors, timeout = 5000) {
  for (const sel of selectors) {
    const el = page.locator(sel).first();
    if (await el.isVisible({ timeout }).catch(() => false)) return el;
  }
  return null;
}

// Click using JS if normal click fails
async function jsClick(page, selector) {
  return page.evaluate(sel => {
    const el = document.querySelector(sel) ||
      [...document.querySelectorAll('button,a,[role="button"]')]
        .find(e => e.textContent.includes(sel.replace(/.*text="?|"?.*/g,'')));
    if (el) { el.click(); return true; }
    return false;
  }, selector);
}

(async () => {
  console.log('=== Bond: Google Play Console Setup ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 200 });
    console.log('Opened new Chrome window');
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Get developer ID from Play Console ────────────────────────────
  console.log('\n[1/6] Opening Play Console...');
  await page.goto('https://play.google.com/console', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(6000);
  await shot(page, '1-landing');

  // If on account-selection screen, click "3 lakes logistics"
  const bodyText = await page.evaluate(() => document.body.innerText);
  if (bodyText.includes('Choose developer account') || bodyText.includes('3 lakes logistics')) {
    console.log('  Account selection screen — clicking "3 lakes logistics"...');
    const accountBtn = await findVisible(page, [
      'text=3 lakes logistics',
      'text=3 Lakes Logistics',
      '[role="button"]:has-text("3 lakes")',
      'li:has-text("3 lakes")',
      'div:has-text("3 lakes logistics")',
    ], 5000);
    if (accountBtn) {
      await accountBtn.click();
      await wait(6000);
      console.log('  Clicked developer account, URL:', page.url().slice(0, 90));
    } else {
      // Try clicking by evaluating JS
      await page.evaluate(() => {
        const els = [...document.querySelectorAll('*')];
        const el = els.find(e => e.innerText?.trim().toLowerCase() === '3 lakes logistics');
        if (el) el.click();
      });
      await wait(6000);
      console.log('  JS-clicked developer account, URL:', page.url().slice(0, 90));
    }
  }

  // Wait for URL to include the developer ID
  let devId = null;
  for (let i = 0; i < 10; i++) {
    const m = page.url().match(/developers\/(\d+)/);
    if (m) { devId = m[1]; break; }
    await wait(2000);
  }
  console.log('  Developer ID:', devId || '(not found in URL)');
  console.log('  Current URL:', page.url().slice(0, 90));

  if (!devId) {
    // Try to extract from page source
    const src = await page.content();
    const m = src.match(/"developerId":"(\d+)"|\/developers\/(\d+)/);
    devId = m?.[1] || m?.[2];
    console.log('  Developer ID from source:', devId || 'still not found');
  }

  // ── Step 2: Create app ────────────────────────────────────────────────────
  console.log('\n[2/6] Creating app listing...');

  // Navigate to app list
  const appListUrl = devId
    ? `https://play.google.com/console/u/0/developers/${devId}/app-list`
    : 'https://play.google.com/console/u/0/developers/app-list';
  await page.goto(appListUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  await shot(page, '2-app-list');

  // Look for our app
  const bodyText = await page.evaluate(() => document.body.innerText);
  if (bodyText.includes(PACKAGE_NAME) || bodyText.includes(APP_NAME)) {
    console.log('  App already exists in Play Console');
  } else {
    console.log('  App not found — creating...');

    // Find Create app button — try many selectors
    const createBtn = await findVisible(page, [
      'button:has-text("Create app")',
      '[data-testid="create-app-button"]',
      'a:has-text("Create app")',
      'button:has-text("Create")',
      '[aria-label="Create app"]',
      '.create-app-button',
    ], 8000);

    if (createBtn) {
      await createBtn.click();
      await wait(4000);
      await shot(page, '2b-create-form');
    } else {
      // Try direct URL navigation to create form
      const createUrl = devId
        ? `https://play.google.com/console/u/0/developers/${devId}/create-app`
        : null;
      if (createUrl) {
        console.log('  Trying direct create URL...');
        await page.goto(createUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await wait(4000);
        await shot(page, '2b-create-direct');
      } else {
        console.log('  No create button found and no dev ID for direct URL');
        await shot(page, '2b-create-missing');
      }
    }

    // Fill the form
    const nameInput = await findVisible(page, [
      'input[placeholder*="app name" i]',
      'input[aria-label*="App name" i]',
      'input[name="appTitle"]',
      'input[id*="name"]',
      'mat-form-field input',
    ], 6000);

    if (nameInput) {
      await nameInput.click();
      await nameInput.selectAll?.();
      await nameInput.fill(APP_NAME);
      console.log('  Filled app name');
      await wait(1000);

      // Check all declaration checkboxes
      const checkboxes = await page.locator('input[type="checkbox"]').all();
      for (const cb of checkboxes) {
        if (!(await cb.isChecked().catch(() => true))) {
          await cb.click().catch(() => {});
          await wait(300);
        }
      }

      // Submit
      const submitBtn = await findVisible(page, [
        'button:has-text("Create app")',
        'button[type="submit"]:not([disabled])',
        'button:has-text("Save")',
      ], 5000);
      if (submitBtn) {
        await submitBtn.click();
        await wait(8000);
        await shot(page, '2c-after-create');
        console.log('  App creation submitted');
        // Update devId from new URL
        const m = page.url().match(/developers\/(\d+)/);
        if (m && !devId) devId = m[1];
      }
    } else {
      console.log('  Could not find app name input — check screenshot');
    }
  }

  // ── Step 3: API Access — link project and grant service account ───────────
  console.log('\n[3/6] Setting up API access...');
  const apiUrl = devId
    ? `https://play.google.com/console/u/0/developers/${devId}/setup/api-access`
    : 'https://play.google.com/console/u/0/developers/setup/api-access';
  await page.goto(apiUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  await shot(page, '3-api-access');

  // Link GCP project
  const linkBtn = await findVisible(page, [
    'button:has-text("Link existing project")',
    'button:has-text("Link")',
    'button:has-text("Create new project")',
    '[data-testid*="link"]',
  ], 5000);
  if (linkBtn) {
    await linkBtn.click();
    await wait(3000);
    await shot(page, '3b-link-project');
    // Find lakes-mobile-app in project list
    const projectOpt = await findVisible(page, [
      'text=lakes-mobile-app',
      '[data-value*="lakes-mobile"]',
      'option:has-text("lakes-mobile")',
      'li:has-text("lakes-mobile")',
    ], 5000);
    if (projectOpt) {
      await projectOpt.click();
      await wait(1000);
      const confirmBtn = await findVisible(page, [
        'button:has-text("Link project")',
        'button:has-text("Link")',
        'button:has-text("Confirm")',
        'button:has-text("Save")',
      ], 3000);
      if (confirmBtn) {
        await confirmBtn.click();
        await wait(4000);
        console.log('  Linked lakes-mobile-app project');
      }
    } else {
      console.log('  Could not find lakes-mobile-app in project list');
      await shot(page, '3c-project-list');
    }
  } else {
    console.log('  Link project button not visible — may already be linked');
  }

  await wait(3000);
  await shot(page, '3d-after-link');

  // Grant service account access
  const grantBtn = await findVisible(page, [
    `a:has-text("Grant access")`,
    `button:has-text("Grant access")`,
    `[aria-label*="grant" i]`,
    // Sometimes shown as a row button next to the SA email
    `tr:has-text("${SA_EMAIL.split('@')[0]}") button`,
    `tr:has-text("james-bond") a`,
  ], 8000);
  if (grantBtn) {
    await grantBtn.click();
    await wait(3000);
    await shot(page, '3e-grant-form');
    // Select all permissions or "Release manager"
    const permOpts = await page.locator([
      'input[type="checkbox"]',
      'label:has-text("Release manager")',
      'label:has-text("Admin")',
    ].join(', ')).all();
    for (const opt of permOpts.slice(0, 3)) {
      await opt.click().catch(() => {});
      await wait(200);
    }
    const applyBtn = await findVisible(page, [
      'button:has-text("Invite user")',
      'button:has-text("Apply")',
      'button:has-text("Save")',
    ], 3000);
    if (applyBtn) {
      await applyBtn.click();
      await wait(3000);
      console.log('  Granted service account access');
    }
  } else {
    console.log('  Grant access button not found — service account may already have access');
    await shot(page, '3f-no-grant');
  }

  // ── Step 4: Upload screenshots via store listing ───────────────────────────
  console.log('\n[4/6] Navigating to store listing...');
  // Find the app and navigate to store listing
  const appListUrl2 = devId
    ? `https://play.google.com/console/u/0/developers/${devId}/app-list`
    : 'https://play.google.com/console/u/0/developers/app-list';
  await page.goto(appListUrl2, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(4000);
  await shot(page, '4-app-list');

  // Click on our app
  const appRow = await findVisible(page, [
    `text="${APP_NAME}"`,
    `text=${APP_NAME}`,
    `a:has-text("${APP_NAME}")`,
    `[title="${APP_NAME}"]`,
  ], 5000);
  if (appRow) {
    await appRow.click();
    await wait(4000);
    await shot(page, '4b-app-home');

    // Navigate to Main store listing
    const storeLink = await findVisible(page, [
      'a:has-text("Main store listing")',
      'a:has-text("Store listing")',
      'nav a:has-text("Store")',
      'text=Main store listing',
    ], 5000);
    if (storeLink) {
      await storeLink.click();
      await wait(4000);
      await shot(page, '4c-store-listing');

      // Upload screenshots
      const screenshotsDir = path.join(repoRoot, 'fastlane/metadata/android/en-US/images/phoneScreenshots');
      const screenshots = fs.readdirSync(screenshotsDir)
        .filter(f => f.endsWith('.png'))
        .map(f => path.join(screenshotsDir, f));
      console.log(`  Uploading ${screenshots.length} screenshots...`);

      // Find file upload for phone screenshots
      const fileInputs = await page.locator('input[type="file"]').all();
      if (fileInputs.length > 0) {
        await fileInputs[0].setInputFiles(screenshots);
        await wait(8000);
        await shot(page, '4d-screenshots-uploaded');
        console.log('  Screenshots uploaded');

        // Save
        const saveBtn = await findVisible(page, [
          'button:has-text("Save")',
          'button:has-text("Apply")',
        ], 3000);
        if (saveBtn) { await saveBtn.click(); await wait(3000); }
      } else {
        console.log('  No file upload input found on store listing page');
        await shot(page, '4d-no-upload-input');
      }
    } else {
      console.log('  Store listing link not found');
      await shot(page, '4c-no-store-link');
    }
  } else {
    console.log('  App row not found in app list');
    await shot(page, '4b-no-app-row');
  }

  // ── Step 5: Print page text to help debug ─────────────────────────────────
  console.log('\n[5/6] Current page state:');
  const finalUrl = page.url();
  console.log('  URL:', finalUrl.slice(0, 100));
  const finalText = await page.evaluate(() =>
    [...document.querySelectorAll('button,a,h1,h2,h3')]
      .map(e => e.textContent.trim())
      .filter(t => t.length > 2 && t.length < 60)
      .slice(0, 30)
      .join(' | ')
  );
  console.log('  Buttons/links on page:', finalText.slice(0, 300));

  await shot(page, '6-final');
  await browser.close();

  console.log('\nDone. Check screenshots in scripts/play-*.png');
  console.log('Once app is created and service account has access, trigger the build:');
  console.log('  github.com/modom123/3-lakes-logistics/actions');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
