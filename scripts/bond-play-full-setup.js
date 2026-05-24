/**
 * Bond — Complete Google Play Service Account Setup
 * One command does everything:
 *   1. Opens Play Console API access page
 *   2. Navigates to Google Cloud Console
 *   3. Creates service account + JSON key
 *   4. Waits for download
 *   5. Encodes JSON → base64
 *   6. Adds GOOGLE_PLAY_KEY_BASE64 to GitHub secrets
 *   7. Triggers the Android build workflow
 *
 * Run: node scripts/bond-play-full-setup.js
 * Chrome must be open with remote debugging and logged into Google as nwtcinvestment@gmail.com
 */

const { chromium } = require('playwright');
const https   = require('https');
const sodium  = require('libsodium-wrappers');
const fs      = require('fs');
const path    = require('path');

const OWNER        = 'modom123';
const REPO         = '3-lakes-logistics';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || 'PASTE_TOKEN_HERE';
const DOWNLOADS    = path.join(process.env.USERPROFILE || process.env.HOME || '', 'Downloads');
const SA_NAME      = 'threelakes-play';
const SA_DISPLAY   = '3 Lakes Play Store';

// ── GitHub API ────────────────────────────────────────────────────────────────
function ghApi(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req  = https.request({
      hostname: 'api.github.com', path: p, method,
      headers: {
        'Authorization': `Bearer ${GITHUB_TOKEN}`, 'User-Agent': 'Bond-3Lakes',
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
        ...(data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}),
      },
    }, res => { let b = ''; res.on('data', c => b += c); res.on('end', () => resolve({ status: res.statusCode, body: b ? JSON.parse(b) : {} })); });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

async function encryptAndAddSecret(name, value) {
  await sodium.ready;
  const pkRes     = await ghApi('GET', `/repos/${OWNER}/${REPO}/actions/secrets/public-key`);
  const { key, key_id } = pkRes.body;
  const sealed    = sodium.crypto_box_seal(sodium.from_string(value), sodium.from_base64(key, sodium.base64_variants.ORIGINAL));
  const encrypted = sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
  const res       = await ghApi('PUT', `/repos/${OWNER}/${REPO}/actions/secrets/${name}`, { encrypted_value: encrypted, key_id });
  return res.status === 201 || res.status === 204;
}

// ── Wait for new JSON file in Downloads ───────────────────────────────────────
function getExistingJsonFiles() {
  return fs.readdirSync(DOWNLOADS).filter(f => f.endsWith('.json'))
    .map(f => path.join(DOWNLOADS, f));
}

async function waitForNewJson(before, timeoutMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const after = getExistingJsonFiles();
    const newFiles = after.filter(f => !before.includes(f));
    if (newFiles.length > 0) {
      // Find newest
      return newFiles.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  return null;
}

// ── Trigger GitHub Actions build ──────────────────────────────────────────────
async function triggerBuild() {
  const res = await ghApi('POST', `/repos/${OWNER}/${REPO}/actions/workflows/android-build.yml/dispatches`, {
    ref: 'main',
    inputs: { version_code: '1', version_name: '1.0.0' }
  });
  return res.status === 204;
}

// ── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  console.log('=== Bond: Complete Google Play Setup ===\n');

  // Connect to Chrome
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('✓ Connected to Chrome');
  } catch {
    console.log('Launching new Chrome window...');
    browser = await chromium.launch({ headless: false, slowMo: 500 });
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();
  page.setDefaultTimeout(30000);

  // Record existing JSON files before we start
  const existingJsons = getExistingJsonFiles();

  // ── PHASE 1: Play Console API access ──────────────────────────────────────
  console.log('\n[1/5] Opening Play Console API access...');
  await page.goto('https://play.google.com/console/u/0/developers/setup/api-access', {
    waitUntil: 'domcontentloaded', timeout: 60000
  });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: 'scripts/bond-p1-play-api.png' });

  // Click "Create new project" or "Link existing" if available
  try {
    const btn = page.locator('button:has-text("Create new project"), button:has-text("Link")').first();
    if (await btn.isVisible({ timeout: 4000 })) { await btn.click(); await page.waitForTimeout(3000); }
  } catch {}

  // Click "Create service account" if shown
  try {
    const btn = page.locator('button:has-text("Create service account")').first();
    if (await btn.isVisible({ timeout: 4000 })) {
      await btn.click();
      await page.waitForTimeout(2000);
      // This opens Google Cloud Console in a new tab
    }
  } catch {}
  console.log('  ✓ Play Console API page visited');

  // ── PHASE 2: Get the Cloud project ID ─────────────────────────────────────
  console.log('\n[2/5] Getting Cloud project info...');
  // Extract project ID from Play Console URL or page content
  let projectId = '';
  try {
    const content = await page.content();
    const match   = content.match(/projects\/([a-z][a-z0-9-]+)/i);
    if (match) projectId = match[1];
  } catch {}
  console.log(`  Project ID: ${projectId || '(will auto-detect in Cloud Console)'}`);

  // ── PHASE 3: Navigate to Cloud Console Service Accounts ───────────────────
  console.log('\n[3/5] Opening Google Cloud Console Service Accounts...');
  const cloudUrl = projectId
    ? `https://console.cloud.google.com/iam-admin/serviceaccounts?project=${projectId}`
    : 'https://console.cloud.google.com/iam-admin/serviceaccounts';

  await page.goto(cloudUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);
  await page.screenshot({ path: 'scripts/bond-p3-cloud-sa.png' });

  // Try to find and click the Play-linked service account
  let saEmail = '';
  try {
    // Look for service account rows
    const rows = page.locator('table tbody tr, .cfc-data-table-row');
    const count = await rows.count();
    console.log(`  Found ${count} service account(s)`);

    if (count > 0) {
      // Get email from first row
      const firstRow = rows.first();
      saEmail = await firstRow.locator('td').nth(1).innerText().catch(() => '');
      console.log(`  Using service account: ${saEmail || '(first in list)'}`);
      await firstRow.click();
      await page.waitForTimeout(3000);
    } else {
      // Create new service account
      console.log('  No service accounts found — creating one...');
      const createBtn = page.locator('button:has-text("Create service account"), a:has-text("Create service account")').first();
      if (await createBtn.isVisible({ timeout: 5000 })) {
        await createBtn.click();
        await page.waitForTimeout(2000);

        // Fill in name
        const nameField = page.locator('input[placeholder*="name" i], input[aria-label*="name" i]').first();
        if (await nameField.isVisible({ timeout: 5000 })) {
          await nameField.fill(SA_DISPLAY);
          const nextBtn = page.locator('button:has-text("Create"), button:has-text("Next")').first();
          await nextBtn.click();
          await page.waitForTimeout(2000);
          // Skip optional role screens
          const doneBtn = page.locator('button:has-text("Done"), button:has-text("Continue")').first();
          if (await doneBtn.isVisible({ timeout: 3000 })) { await doneBtn.click(); await page.waitForTimeout(2000); }
        }
      }
    }
  } catch (e) { console.log('  SA navigation note:', e.message); }

  // ── PHASE 4: Create JSON key ───────────────────────────────────────────────
  console.log('\n[4/5] Creating JSON key...');
  await page.screenshot({ path: 'scripts/bond-p4-before-key.png' });

  try {
    // Click Keys tab
    const keysTab = page.locator('[role="tab"]:has-text("Keys"), button:has-text("Keys")').first();
    if (await keysTab.isVisible({ timeout: 5000 })) {
      await keysTab.click();
      await page.waitForTimeout(2000);
    }

    // Click Add Key
    const addKeyBtn = page.locator('button:has-text("Add key"), button:has-text("Add Key")').first();
    await addKeyBtn.waitFor({ state: 'visible', timeout: 10000 });
    await addKeyBtn.click();
    await page.waitForTimeout(1000);

    // Click "Create new key"
    const createKeyOption = page.locator('[role="menuitem"]:has-text("Create new key"), li:has-text("Create new key")').first();
    if (await createKeyOption.isVisible({ timeout: 3000 })) {
      await createKeyOption.click();
      await page.waitForTimeout(1000);
    }

    // Select JSON (usually default)
    const jsonOption = page.locator('input[value="json"]').first();
    if (await jsonOption.isVisible({ timeout: 3000 })) { await jsonOption.click(); }

    // Click Create
    const createBtn = page.locator('button:has-text("Create")').last();
    await createBtn.waitFor({ state: 'visible', timeout: 5000 });

    console.log('  Clicking Create — file will download...');
    await createBtn.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'scripts/bond-p4-key-created.png' });

  } catch (e) {
    console.log('  Key creation error:', e.message);
    console.log('  Check screenshot: scripts/bond-p4-before-key.png');
  }

  // ── PHASE 5: Wait for download, encode, upload to GitHub ──────────────────
  console.log('\n[5/5] Waiting for JSON file to download (up to 60 seconds)...');
  const newFile = await waitForNewJson(existingJsons, 60000);

  if (!newFile) {
    console.log('\n⚠️  JSON file did not download automatically.');
    console.log('  Check screenshots in scripts/ to see where it stopped.');
    console.log('  Manually download the JSON from Google Cloud Console, then run:');
    console.log('  node scripts/encode-play-key.js');
    await browser.close();
    process.exit(1);
  }

  console.log(`  ✓ Downloaded: ${path.basename(newFile)}`);
  const keyJson = fs.readFileSync(newFile, 'utf8');
  const b64     = Buffer.from(keyJson).toString('base64');

  console.log('  Uploading GOOGLE_PLAY_KEY_BASE64 to GitHub...');
  const ok = await encryptAndAddSecret('GOOGLE_PLAY_KEY_BASE64', b64);
  if (ok) {
    console.log('  ✓ Secret added to GitHub');
  } else {
    console.log('  ✗ Secret upload failed — check GitHub token');
    await browser.close();
    process.exit(1);
  }

  // Trigger the build
  console.log('  Triggering Android build workflow...');
  const triggered = await triggerBuild();
  if (triggered) {
    console.log('  ✓ Build triggered!');
  } else {
    console.log('  Build trigger returned unexpected status — check GitHub Actions manually');
  }

  await browser.close();

  console.log('\n✅ COMPLETE — Bond has finished the full Play Store setup.');
  console.log('Watch the build at:');
  console.log('  https://github.com/modom123/3-lakes-logistics/actions');
  console.log('\nThe build will:');
  console.log('  1. Compile the Android app');
  console.log('  2. Sign it with the release keystore');
  console.log('  3. Upload the AAB to Google Play internal track');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
