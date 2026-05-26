/**
 * Bond — Google Play Service Account Key Setup
 *
 * Outside Bond runs this in Chrome (logged into play.google.com as nwtcinvestment@gmail.com)
 * It will:
 *   1. Open Play Console → Setup → API access
 *   2. Link/create a Google Cloud project
 *   3. Create a service account with the right permissions
 *   4. Download the JSON key
 *   5. Print the base64 value ready to paste as GOOGLE_PLAY_KEY_BASE64 secret
 *
 * Run: node scripts/get-play-service-account.js
 */

const { chromium } = require('playwright');
const fs   = require('fs');
const path = require('path');

const PLAY_API_URL = 'https://play.google.com/console/u/0/developers/setup/api-access';

async function goto(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3000);
}

(async () => {
  console.log('=== Bond — Google Play Service Account Setup ===\n');

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome.');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 400 });
    console.log('New Chrome window opened. Log into play.google.com as nwtcinvestment@gmail.com, then press Enter...');
    await new Promise(r => process.stdin.once('data', r));
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Open Play Console API access page ─────────────────────────────
  console.log('Step 1: Opening Play Console API access page...');
  await goto(page, PLAY_API_URL);
  await page.screenshot({ path: 'scripts/sa-step1-api-access.png' });
  console.log('  Screenshot: scripts/sa-step1-api-access.png');

  // ── Step 2: Link Google Cloud project if needed ───────────────────────────
  console.log('Step 2: Linking Google Cloud project...');
  try {
    const linkBtn = page.locator('button:has-text("Link"), button:has-text("Create new project"), a:has-text("Link")').first();
    if (await linkBtn.isVisible({ timeout: 5000 })) {
      await linkBtn.click();
      await page.waitForTimeout(3000);
      console.log('  Clicked Link/Create project button.');
    } else {
      console.log('  Project may already be linked. Continuing...');
    }
  } catch { console.log('  Skipping link step.'); }

  await page.screenshot({ path: 'scripts/sa-step2-linked.png' });

  // ── Step 3: Create service account ───────────────────────────────────────
  console.log('Step 3: Creating service account...');
  try {
    const createBtn = page.locator('button:has-text("Create service account"), a:has-text("Create service account")').first();
    if (await createBtn.isVisible({ timeout: 5000 })) {
      await createBtn.click();
      await page.waitForTimeout(3000);
      console.log('  Clicked Create service account.');
      await page.screenshot({ path: 'scripts/sa-step3-create.png' });
    } else {
      console.log('  Create service account button not visible. Check screenshot.');
    }
  } catch { console.log('  Could not click Create service account.'); }

  // ── Step 4: Navigate to Google Cloud Console to create the key ────────────
  console.log('\nStep 4: Opening Google Cloud Console IAM → Service Accounts...');
  await goto(page, 'https://console.cloud.google.com/iam-admin/serviceaccounts');
  await page.screenshot({ path: 'scripts/sa-step4-cloud-console.png' });
  console.log('  Screenshot: scripts/sa-step4-cloud-console.png');

  // Try to find and click the service account for Play
  console.log('  Looking for service account...');
  try {
    // Click first service account row
    const saRow = page.locator('table tbody tr').first();
    if (await saRow.isVisible({ timeout: 8000 })) {
      // Get the email
      const email = await saRow.locator('td').nth(1).innerText().catch(() => '');
      console.log(`  Found service account: ${email}`);
      await saRow.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: 'scripts/sa-step4b-selected.png' });

      // Click Keys tab
      const keysTab = page.locator('tab:has-text("Keys"), button:has-text("Keys"), [aria-label="Keys"]').first();
      if (await keysTab.isVisible({ timeout: 5000 })) {
        await keysTab.click();
        await page.waitForTimeout(2000);
      }

      // Click Add Key → Create new key
      const addKeyBtn = page.locator('button:has-text("Add key"), button:has-text("Add Key")').first();
      if (await addKeyBtn.isVisible({ timeout: 5000 })) {
        await addKeyBtn.click();
        await page.waitForTimeout(1000);
        const createKeyOption = page.locator('[role="menuitem"]:has-text("Create new key")').first();
        if (await createKeyOption.isVisible({ timeout: 3000 })) {
          await createKeyOption.click();
          await page.waitForTimeout(1000);
        }
      }

      // Select JSON and create
      const jsonRadio = page.locator('input[value="json"], label:has-text("JSON")').first();
      if (await jsonRadio.isVisible({ timeout: 3000 })) {
        await jsonRadio.click();
      }
      const createKeyBtn = page.locator('button:has-text("Create")').first();
      if (await createKeyBtn.isVisible({ timeout: 3000 })) {
        await createKeyBtn.click();
        console.log('  Key download triggered!');
        await page.waitForTimeout(5000);
      }
    }
  } catch (e) {
    console.log('  Auto-create failed:', e.message);
  }

  await page.screenshot({ path: 'scripts/sa-step4-final.png' });

  // ── Step 5: Find downloaded JSON and encode it ────────────────────────────
  console.log('\nStep 5: Looking for downloaded JSON key...');
  const downloadsDir = path.join(process.env.USERPROFILE || process.env.HOME, 'Downloads');
  const files = fs.readdirSync(downloadsDir)
    .filter(f => f.endsWith('.json') && f.includes('play'))
    .sort((a, b) => fs.statSync(path.join(downloadsDir, b)).mtimeMs - fs.statSync(path.join(downloadsDir, a)).mtimeMs);

  if (files.length > 0) {
    const keyFile = path.join(downloadsDir, files[0]);
    const keyJson = fs.readFileSync(keyFile, 'utf8');
    const b64     = Buffer.from(keyJson).toString('base64');
    console.log('\n✅ Found key file:', files[0]);
    console.log('\n=== GOOGLE_PLAY_KEY_BASE64 (copy this entire value) ===');
    console.log(b64);
    console.log('\nThen run: node scripts/add-play-secret.js');
    fs.writeFileSync('scripts/play-key-b64.txt', b64);
    console.log('Also saved to: scripts/play-key-b64.txt');
  } else {
    console.log('  No JSON key file found in Downloads yet.');
    console.log('  Check screenshots in scripts/ to see where the process stopped.');
    console.log('  Manual step: In Google Cloud Console, go to:');
    console.log('  IAM & Admin → Service Accounts → click your account → Keys → Add Key → JSON');
    console.log('  Download the file, then run: node scripts/encode-play-key.js');
  }

  await browser.close();
})().catch(err => {
  console.error('Bond error:', err.message);
  process.exit(1);
});
