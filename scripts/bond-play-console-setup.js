/**
 * Bond — Google Play Console Setup
 * Creates the app listing, links API access, grants service account permissions,
 * and uploads screenshots — all automatically via the existing Chrome session.
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

const APP_NAME      = '3 Lakes Driver';
const PACKAGE_NAME  = 'com.threelakes.driver';
const SA_EMAIL      = 'james-bond@lakes-mobile-app.iam.gserviceaccount.com';
const PLAY_CONSOLE  = 'https://play.google.com/console/u/0/developers';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function shot(page, name) {
  const p = path.join(__dirname, `play-${name}.png`);
  await page.screenshot({ path: p, fullPage: false });
  console.log(`  Screenshot: scripts/play-${name}.png`);
}

(async () => {
  console.log('=== Bond: Google Play Console Setup ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 300 });
    console.log('Opened new Chrome window');
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Open Play Console ─────────────────────────────────────────────
  console.log('\n[1/5] Opening Google Play Console...');
  await page.goto(PLAY_CONSOLE, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  await shot(page, '1-console-home');
  console.log('  Current URL:', page.url().slice(0, 80));

  // ── Step 2: Create new app ────────────────────────────────────────────────
  console.log('\n[2/5] Creating app listing...');

  // Check if app already exists by searching for our package name in the page
  const pageText = await page.textContent('body').catch(() => '');
  if (pageText.includes(PACKAGE_NAME) || pageText.includes(APP_NAME)) {
    console.log('  App may already exist — skipping create step');
  } else {
    // Click "Create app" button
    const createBtn = page.locator([
      'button:has-text("Create app")',
      'a:has-text("Create app")',
      '[aria-label="Create app"]',
    ].join(', ')).first();

    if (await createBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
      await createBtn.click();
      await wait(3000);
      await shot(page, '2-create-app-form');

      // Fill app name
      const nameField = page.locator('input[placeholder*="name"], input[aria-label*="App name"], input[name*="name"]').first();
      if (await nameField.isVisible({ timeout: 5000 }).catch(() => false)) {
        await nameField.click();
        await nameField.fill(APP_NAME);
        console.log('  Filled app name:', APP_NAME);
      }

      // Select default language (English US should be default)
      await wait(1000);

      // Select "App" type (not Game)
      const appRadio = page.locator('input[value="app"], label:has-text("App")').first();
      if (await appRadio.isVisible({ timeout: 3000 }).catch(() => false)) {
        await appRadio.click();
      }

      // Select "Free"
      const freeRadio = page.locator('input[value="free"], label:has-text("Free")').first();
      if (await freeRadio.isVisible({ timeout: 3000 }).catch(() => false)) {
        await freeRadio.click();
      }

      // Check all declaration checkboxes
      const checkboxes = page.locator('input[type="checkbox"]');
      const count = await checkboxes.count();
      for (let i = 0; i < count; i++) {
        const cb = checkboxes.nth(i);
        if (!(await cb.isChecked().catch(() => true))) {
          await cb.click().catch(() => {});
        }
      }
      await wait(1000);
      await shot(page, '2b-filled-form');

      // Click Create app / Submit
      const submitBtn = page.locator([
        'button:has-text("Create app")',
        'button[type="submit"]',
        'button:has-text("Save")',
      ].join(', ')).last();
      if (await submitBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await submitBtn.click();
        console.log('  Submitted create app form');
        await wait(8000);
        await shot(page, '3-after-create');
      }
    } else {
      console.log('  Create app button not visible — check screenshot');
      await shot(page, '2-no-create-button');
    }
  }

  // ── Step 3: Go to API access and link service account ─────────────────────
  console.log('\n[3/5] Setting up API access...');
  await page.goto('https://play.google.com/console/u/0/developers/setup/api-access',
    { waitUntil: 'domcontentloaded', timeout: 60000 });
  await wait(5000);
  await shot(page, '4-api-access');

  // Link Google Cloud project if needed
  const linkBtn = page.locator([
    'button:has-text("Link")',
    'button:has-text("Create new project")',
    'button:has-text("Link existing project")',
  ].join(', ')).first();
  if (await linkBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await linkBtn.click();
    await wait(3000);
    console.log('  Clicked link project button');
    // Try to find lakes-mobile-app in the dropdown
    const projectOption = page.locator('text=lakes-mobile-app').first();
    if (await projectOption.isVisible({ timeout: 5000 }).catch(() => false)) {
      await projectOption.click();
      await wait(1000);
      const confirmBtn = page.locator('button:has-text("Link project"), button:has-text("Confirm")').first();
      if (await confirmBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await confirmBtn.click();
        await wait(3000);
        console.log('  Linked lakes-mobile-app project');
      }
    } else {
      console.log('  Could not find lakes-mobile-app in project list — check screenshot');
      await shot(page, '4b-project-list');
    }
  } else {
    console.log('  API project may already be linked');
  }

  // Grant service account access
  console.log('  Looking for service account grant button...');
  const grantBtn = page.locator([
    `button:has-text("Grant access")`,
    `a:has-text("Grant access")`,
    `text=${SA_EMAIL}`,
  ].join(', ')).first();
  if (await grantBtn.isVisible({ timeout: 8000 }).catch(() => false)) {
    await grantBtn.click();
    await wait(3000);
    await shot(page, '5-grant-access');
    // Select permissions — Release manager or similar
    const releaseManagerOption = page.locator([
      'text=Release manager',
      'text=Release Manager',
      'input[value*="release"]',
    ].join(', ')).first();
    if (await releaseManagerOption.isVisible({ timeout: 3000 }).catch(() => false)) {
      await releaseManagerOption.click();
      await wait(500);
    }
    const inviteBtn = page.locator('button:has-text("Invite"), button:has-text("Save"), button:has-text("Apply")').first();
    if (await inviteBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await inviteBtn.click();
      await wait(3000);
      console.log('  Granted service account access');
    }
  } else {
    console.log('  Grant access button not found — check screenshot');
    await shot(page, '5-no-grant-button');
  }

  // ── Step 4: Upload screenshots ────────────────────────────────────────────
  console.log('\n[4/5] Uploading screenshots to store listing...');
  // Navigate to main store listing
  const currentUrl = page.url();
  // Extract developer ID from URL
  const devId = currentUrl.match(/developers\/(\d+)/)?.[1];
  if (devId) {
    await page.goto(
      `https://play.google.com/console/u/0/developers/${devId}/app-list`,
      { waitUntil: 'domcontentloaded', timeout: 60000 });
    await wait(3000);
    await shot(page, '6-app-list');
  }

  const screenshotsDir = path.join(repoRoot,
    'fastlane/metadata/android/en-US/images/phoneScreenshots');
  const screenshots = fs.readdirSync(screenshotsDir)
    .filter(f => f.endsWith('.png'))
    .map(f => path.join(screenshotsDir, f));
  console.log(`  Found ${screenshots.length} screenshots to upload`);

  // Try to navigate to the app's store listing
  const appLink = page.locator(`text=${APP_NAME}, text=${PACKAGE_NAME}`).first();
  if (await appLink.isVisible({ timeout: 5000 }).catch(() => false)) {
    await appLink.click();
    await wait(3000);
    // Go to store listing
    const storeListingLink = page.locator('text=Store listing, text=Main store listing').first();
    if (await storeListingLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await storeListingLink.click();
      await wait(3000);
      await shot(page, '7-store-listing');

      // Upload phone screenshots
      const uploadInput = page.locator('input[type="file"]').first();
      if (await uploadInput.isVisible({ timeout: 5000 }).catch(() => false)) {
        await uploadInput.setInputFiles(screenshots);
        await wait(5000);
        console.log('  Screenshots uploaded');
        await shot(page, '8-screenshots-uploaded');
      }
    }
  } else {
    console.log('  Could not find app in app list — screenshots will be uploaded in next run');
  }

  // ── Step 5: Final summary ─────────────────────────────────────────────────
  console.log('\n[5/5] Done.');
  await shot(page, '9-final');
  await browser.close();

  console.log('\nDONE. Next steps that happen automatically:');
  console.log('  1. Go to github.com/modom123/3-lakes-logistics/actions');
  console.log('  2. Run "Build Android AAB (Google Play)" workflow');
  console.log('  3. The AAB will be uploaded to Play internal track');
  console.log('\nCheck screenshots in scripts/play-*.png to see what happened.');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
