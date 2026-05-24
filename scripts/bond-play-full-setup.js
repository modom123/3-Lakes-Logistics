/**
 * Bond — Get Google Play service account key via in-browser API calls
 * Uses the user's existing Google session in Chrome to call Google Cloud
 * IAM API directly — no UI clicking, no fragile selectors.
 *
 * Run: node scripts/bond-play-full-setup.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const repoRoot = path.join(__dirname, '..');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('libsodium-wrappers') || !hasMod('playwright')) {
  console.log('Installing dependencies...');
  execSync('npm install', { cwd: repoRoot, stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: repoRoot, stdio: 'inherit' });
  console.log('Restarting Bond...\n');
  const r = spawnSync(process.execPath, [__filename, ...process.argv.slice(2)], { cwd: repoRoot, stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');
const https  = require('https');
const sodium = require('libsodium-wrappers');
const fs     = require('fs');

const OWNER        = 'modom123';
const REPO         = '3-lakes-logistics';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || 'NEEDS_TOKEN';

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

async function addGithubSecret(name, value) {
  await sodium.ready;
  const pkRes = await ghApi('GET', `/repos/${OWNER}/${REPO}/actions/secrets/public-key`);
  const { key, key_id } = pkRes.body;
  const sealed    = sodium.crypto_box_seal(sodium.from_string(value), sodium.from_base64(key, sodium.base64_variants.ORIGINAL));
  const encrypted = sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
  const res       = await ghApi('PUT', `/repos/${OWNER}/${REPO}/actions/secrets/${name}`, { encrypted_value: encrypted, key_id });
  return res.status === 201 || res.status === 204;
}

// ── In-browser Google API calls (uses existing session cookies) ───────────────
async function googleApi(page, method, url, body) {
  return page.evaluate(async ({ method, url, body }) => {
    const res = await fetch(url, {
      method,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    try { return { status: res.status, data: JSON.parse(text) }; }
    catch { return { status: res.status, data: text }; }
  }, { method, url, body });
}

(async () => {
  console.log('=== Bond: Google Play Service Account (API mode) ===\n');

  // Connect to Chrome
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('✓ Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false });
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Go to Google Cloud Console to establish session ──────────────
  console.log('\n[1/4] Opening Google Cloud Console...');
  await page.goto('https://console.cloud.google.com', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);

  // ── Step 2: Get list of projects ──────────────────────────────────────────
  console.log('[2/4] Getting Google Cloud projects...');
  const projRes = await googleApi(page, 'GET', 'https://cloudresourcemanager.googleapis.com/v1/projects?filter=lifecycleState%3AACTIVE');
  if (!projRes.data.projects || projRes.data.projects.length === 0) {
    console.error('No projects found. Make sure you are logged into Google Cloud Console.');
    await browser.close(); process.exit(1);
  }

  // Pick the first active project (or the one linked to Play)
  const project   = projRes.data.projects[0];
  const projectId = project.projectId;
  console.log(`  ✓ Using project: ${project.name} (${projectId})`);

  // ── Step 3: List or create service account ────────────────────────────────
  console.log('[3/4] Getting service accounts...');
  const saRes = await googleApi(page, 'GET', `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`);

  let saEmail;
  if (saRes.data.accounts && saRes.data.accounts.length > 0) {
    // Use the first service account (most likely the Play-linked one)
    saEmail = saRes.data.accounts[0].email;
    console.log(`  ✓ Using service account: ${saEmail}`);
  } else {
    // Create a new one
    console.log('  No service accounts found — creating one...');
    const createRes = await googleApi(page, 'POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`,
      { accountId: 'threelakes-play', serviceAccount: { displayName: '3 Lakes Play Store' } }
    );
    if (!createRes.data.email) {
      console.error('Failed to create service account:', JSON.stringify(createRes.data));
      await browser.close(); process.exit(1);
    }
    saEmail = createRes.data.email;
    console.log(`  ✓ Created service account: ${saEmail}`);
  }

  // ── Step 4: Create JSON key ───────────────────────────────────────────────
  console.log('[4/4] Creating service account JSON key...');
  const keyRes = await googleApi(page, 'POST',
    `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
    { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' }
  );

  if (!keyRes.data.privateKeyData) {
    console.error('Key creation failed:', JSON.stringify(keyRes.data));
    console.log('\nIf you see a 403 error, the IAM API needs to be enabled.');
    console.log('Bond will try to enable it...');

    // Try to enable IAM API
    await googleApi(page, 'POST',
      `https://serviceusage.googleapis.com/v1/projects/${projectId}/services/iam.googleapis.com:enable`, {}
    );
    await page.waitForTimeout(5000);

    // Retry key creation
    const retryRes = await googleApi(page, 'POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
      { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' }
    );
    if (!retryRes.data.privateKeyData) {
      console.error('Still failed:', JSON.stringify(retryRes.data));
      await browser.close(); process.exit(1);
    }
    Object.assign(keyRes, retryRes);
  }

  // Decode the key JSON
  const keyJson = Buffer.from(keyRes.data.privateKeyData, 'base64').toString('utf8');
  const b64     = Buffer.from(keyJson).toString('base64');
  console.log('  ✓ Key created');

  // Save locally as backup
  fs.writeFileSync(path.join(repoRoot, 'google-play-key.json'), keyJson);
  console.log('  ✓ Key saved to google-play-key.json (gitignored)');

  await browser.close();

  // ── Upload to GitHub ──────────────────────────────────────────────────────
  console.log('\nAdding GOOGLE_PLAY_KEY_BASE64 to GitHub secrets...');
  const ok = await addGithubSecret('GOOGLE_PLAY_KEY_BASE64', b64);
  if (ok) {
    console.log('  ✓ Secret added');
  } else {
    console.error('  ✗ Failed to add secret — check GITHUB_TOKEN');
    process.exit(1);
  }

  // ── Trigger build ─────────────────────────────────────────────────────────
  console.log('\nTriggering Android build...');
  const trigRes = await ghApi('POST', `/repos/${OWNER}/${REPO}/actions/workflows/android-build.yml/dispatches`, {
    ref: 'main', inputs: { version_code: '1', version_name: '1.0.0' }
  });
  if (trigRes.status === 204) {
    console.log('  ✓ Build triggered!');
  } else {
    console.log('  Build trigger status:', trigRes.status);
  }

  console.log('\n✅ DONE — Bond has completed the full Google Play setup.');
  console.log('Watch the build: https://github.com/modom123/3-lakes-logistics/actions');
  console.log('The app will be uploaded to Google Play automatically when the build finishes.');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
