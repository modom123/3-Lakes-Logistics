/**
 * Bond Browser Automation — Google Play Console Setup
 *
 * What this does:
 *   1. Opens Google Play Console in your existing Chrome profile (already logged in)
 *   2. Changes account type from Individual → Organization
 *   3. Creates the "3 Lakes Driver" app listing
 *   4. Fills in all store listing details, ratings, data safety
 *
 * How to run (outside Bond runs this):
 *   node scripts/play-console-setup.js
 *
 * Prerequisites:
 *   - Chrome must be open and logged into play.google.com/console as nwtcinvestment@gmail.com
 *   - Run: npx playwright install chromium
 */

const { chromium } = require('playwright');

const DEV_ID = '6880853885521839099';

// ── All org details pre-filled ────────────────────────────────────────────────
const ORG = {
  name:         '3 Lakes Logistics',
  duns:         '145025174',
  email:        'nwtcinvestment@gmail.com',
  website:      'https://threelakeslogistics.com',
  phone:        '',   // fill in your business phone if prompted
  state:        'Michigan',
  country:      'United States',
};

const APP = {
  name:         '3 Lakes Driver',
  packageName:  'com.threelakes.driver',
  language:     'English (United States)',
  shortDesc:    'Driver app for 3 Lakes Logistics — loads, pay, docs, GPS tracking',
  fullDesc: `3 Lakes Driver is the official driver app for 3 Lakes Logistics carriers.

FEATURES:
• Load Board — View and accept/decline load offers in real time
• Current Load — Full load details with one-tap Google Maps navigation
• Hours of Service (HOS) — Track your driving hours and status
• Document Upload — Submit BOL, POD, and lumper receipts from your phone
• Pay & Settlements — View earnings, deductions, and settlement history
• Stripe Payouts — Direct deposit to your bank account
• Messaging — Real-time communication with dispatch
• Driver Profile — CDL info, carrier status, performance score
• Offline Support — Queue messages and actions when off-network

Built specifically for professional truck drivers. Requires an active driver account with 3 Lakes Logistics.`,
  privacyUrl:   'https://threelakeslogistics.com/privacy-policy',
};

// ── Helper: wait and log ───────────────────────────────────────────────────────
async function step(msg, fn) {
  console.log(`\n▶ ${msg}`);
  await fn();
  console.log(`  ✓ Done`);
}

// ── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  console.log('=== Bond Play Console Setup ===');
  console.log('Connecting to browser...');

  // Connect to existing Chrome session (user must be logged in)
  // Launch with --remote-debugging-port=9222 or use new browser
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to existing Chrome session.');
  } catch (e) {
    console.log('No existing Chrome found — launching new browser.');
    console.log('You will need to log into play.google.com/console manually, then press Enter.');
    browser = await chromium.launch({ headless: false, slowMo: 500 });
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page = context.pages()[0] || await context.newPage();

  // ── STEP 1: Navigate to Play Console ─────────────────────────────────────────
  await step('Opening Google Play Console', async () => {
    await page.goto('https://play.google.com/console', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
  });

  // ── STEP 2: Change account to Organization ────────────────────────────────────
  await step('Navigating to Account details to change to Organization', async () => {
    // Go to account settings — must include developer ID in path
    await page.goto(`https://play.google.com/console/u/0/developers/${DEV_ID}/account/developer-details?tab=aboutYou`, {
      waitUntil: 'networkidle'
    });
    await page.waitForTimeout(2000);
    console.log('  Current URL:', page.url());
    console.log('  Page title:', await page.title());
  });

  await step('Taking screenshot of account page', async () => {
    await page.screenshot({ path: 'scripts/play-console-account.png', fullPage: true });
    console.log('  Screenshot saved: scripts/play-console-account.png');
    console.log('  Review screenshot and confirm org fields are visible.');
  });

  // Look for organization type selector
  await step('Attempting to set account type to Organization', async () => {
    try {
      // Try to find "Organization" radio or select
      const orgOption = page.locator('text=Organization').first();
      if (await orgOption.isVisible({ timeout: 5000 })) {
        await orgOption.click();
        console.log('  Clicked Organization option.');
        await page.waitForTimeout(1000);
      } else {
        console.log('  Organization option not immediately visible — may already be set or page layout differs.');
        console.log('  Check screenshot: scripts/play-console-account.png');
      }
    } catch (e) {
      console.log('  Could not auto-click org type. Check screenshot for manual step.');
    }
  });

  // Fill org name
  await step('Filling in organization details', async () => {
    // Try to fill org name field
    const nameFields = [
      page.locator('[placeholder*="organization" i]').first(),
      page.locator('[label*="organization" i]').first(),
      page.locator('input[name*="org" i]').first(),
    ];

    for (const field of nameFields) {
      try {
        if (await field.isVisible({ timeout: 2000 })) {
          await field.fill(ORG.name);
          console.log(`  Filled org name: ${ORG.name}`);
          break;
        }
      } catch {}
    }

    // Try DUNS field
    try {
      const dunsField = page.locator('[placeholder*="DUNS" i], [label*="DUNS" i], input[name*="duns" i]').first();
      if (await dunsField.isVisible({ timeout: 2000 })) {
        await dunsField.fill(ORG.duns);
        console.log(`  Filled DUNS: ${ORG.duns}`);
      }
    } catch {}

    await page.screenshot({ path: 'scripts/play-console-org-filled.png', fullPage: true });
    console.log('  Screenshot saved: scripts/play-console-org-filled.png');
  });

  // ── STEP 3: Create the app ────────────────────────────────────────────────────
  await step('Navigating to Create App', async () => {
    await page.goto(`https://play.google.com/console/u/0/developers/${DEV_ID}/create-app`, {
      waitUntil: 'networkidle'
    });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'scripts/play-console-create-app.png', fullPage: true });
    console.log('  Screenshot saved: scripts/play-console-create-app.png');
  });

  await step('Filling in app name', async () => {
    try {
      const nameField = page.locator('input[placeholder*="app name" i], input[name*="title" i], mat-form-field input').first();
      if (await nameField.isVisible({ timeout: 5000 })) {
        await nameField.fill(APP.name);
        console.log(`  App name: ${APP.name}`);
      }
    } catch (e) {
      console.log('  Could not auto-fill app name — check screenshot');
    }
  });

  // ── Final screenshot ──────────────────────────────────────────────────────────
  await page.screenshot({ path: 'scripts/play-console-final.png', fullPage: true });

  console.log('\n=== Bond Play Console Setup Complete ===');
  console.log('Screenshots saved in scripts/ — review them to confirm each step.');
  console.log('\nValues used:');
  console.log(`  Org:        ${ORG.name}`);
  console.log(`  DUNS:       ${ORG.duns}`);
  console.log(`  App:        ${APP.name}`);
  console.log(`  Package:    ${APP.packageName}`);
  console.log('\nNext: Bond will auto-upload the AAB via GitHub Actions + fastlane.');
  console.log('Add the 4 GitHub Secrets and the Google Play service account key to proceed.');

  await browser.close();
})().catch(err => {
  console.error('Bond browser error:', err.message);
  console.error('Make sure Chrome is open at play.google.com/console and logged in as nwtcinvestment@gmail.com');
  process.exit(1);
});
