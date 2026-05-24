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

async function enableApi(page, projectId, apiName) {
  const r = await googleApi(page, 'POST',
    `https://serviceusage.googleapis.com/v1/projects/${projectId}/services/${apiName}:enable`, {});
  return r.status === 200 || r.status === 201;
}

(async () => {
  console.log('=== Bond: Google Play Service Account (API mode) ===\n');

  // Connect to Chrome
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false });
    console.log('Opened new Chrome window');
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  // ── Step 1: Go to Google Cloud Console to establish session ──────────────
  console.log('\n[1/5] Opening Google Cloud Console...');
  await page.goto('https://console.cloud.google.com', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(10000); // wait for session/redirect to settle
  const currentUrl = page.url();
  console.log('  Page loaded:', currentUrl.slice(0, 80));

  // ── Step 2: Get or create a GCP project ──────────────────────────────────
  console.log('[2/5] Getting Google Cloud projects...');
  const projRes = await googleApi(page, 'GET',
    'https://cloudresourcemanager.googleapis.com/v1/projects?filter=lifecycleState%3AACTIVE');
  console.log('  API status:', projRes.status);

  let projectId;

  if (projRes.status !== 200) {
    console.error('  Google Cloud API error:', JSON.stringify(projRes.data).slice(0, 400));
    console.error('\n  Chrome must be logged into nwtcinvestment@gmail.com.');
    console.error('  Open Chrome, go to console.cloud.google.com, log in, then re-run this script.');
    await browser.close(); process.exit(1);
  }

  if (projRes.data.projects && projRes.data.projects.length > 0) {
    const project = projRes.data.projects[0];
    projectId = project.projectId;
    console.log(`  Using project: ${project.name} (${projectId})`);
  } else {
    // No projects — create one automatically
    console.log('  No projects found — creating Google Cloud project...');
    const pid = 'threelakes-' + Date.now().toString().slice(-8);
    const createRes = await googleApi(page, 'POST',
      'https://cloudresourcemanager.googleapis.com/v1/projects',
      { projectId: pid, name: '3 Lakes Logistics' });
    console.log('  Create status:', createRes.status);
    if (createRes.status !== 200 && createRes.status !== 201) {
      console.error('  Failed to create project:', JSON.stringify(createRes.data).slice(0, 400));
      await browser.close(); process.exit(1);
    }
    console.log('  Project created — waiting 30s for it to be ready...');
    await page.waitForTimeout(30000);
    // Verify it's active now
    const projRes2 = await googleApi(page, 'GET',
      'https://cloudresourcemanager.googleapis.com/v1/projects?filter=lifecycleState%3AACTIVE');
    if (projRes2.data.projects && projRes2.data.projects.length > 0) {
      projectId = projRes2.data.projects[0].projectId;
    } else {
      // Use the ID we tried to create
      projectId = pid;
    }
    console.log('  Project ID:', projectId);
  }

  // ── Step 3: Enable required APIs ─────────────────────────────────────────
  console.log('[3/5] Enabling IAM API...');
  await enableApi(page, projectId, 'iam.googleapis.com');
  await enableApi(page, projectId, 'cloudresourcemanager.googleapis.com');
  await page.waitForTimeout(8000);

  // ── Step 4: List or create service account ────────────────────────────────
  console.log('[4/5] Getting service accounts...');
  const saRes = await googleApi(page, 'GET',
    `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`);
  console.log('  SA list status:', saRes.status);

  let saEmail;
  if (saRes.data.accounts && saRes.data.accounts.length > 0) {
    saEmail = saRes.data.accounts[0].email;
    console.log('  Using service account:', saEmail);
  } else {
    console.log('  No service accounts — creating one...');
    const createRes = await googleApi(page, 'POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`,
      { accountId: 'threelakes-play', serviceAccount: { displayName: '3 Lakes Play Store' } });
    console.log('  Create SA status:', createRes.status);
    if (!createRes.data.email) {
      console.error('  Failed to create service account:', JSON.stringify(createRes.data).slice(0, 400));
      await browser.close(); process.exit(1);
    }
    saEmail = createRes.data.email;
    console.log('  Created:', saEmail);
  }

  // ── Step 5: Create JSON key ───────────────────────────────────────────────
  console.log('[5/5] Creating service account JSON key...');
  let keyRes = await googleApi(page, 'POST',
    `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
    { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' });
  console.log('  Key create status:', keyRes.status);

  if (!keyRes.data.privateKeyData) {
    // Try enabling the API and retry
    console.log('  Enabling IAM API and retrying...');
    await enableApi(page, projectId, 'iam.googleapis.com');
    await page.waitForTimeout(10000);
    keyRes = await googleApi(page, 'POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
      { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' });
    console.log('  Retry key status:', keyRes.status);
    if (!keyRes.data.privateKeyData) {
      console.error('  Key creation failed:', JSON.stringify(keyRes.data).slice(0, 400));
      await browser.close(); process.exit(1);
    }
  }

  // Decode the key JSON
  const keyJson = Buffer.from(keyRes.data.privateKeyData, 'base64').toString('utf8');
  const b64     = Buffer.from(keyJson).toString('base64');
  console.log('  Key created successfully');

  fs.writeFileSync(path.join(repoRoot, 'google-play-key.json'), keyJson);
  console.log('  Saved to google-play-key.json (gitignored)');

  await browser.close();

  // ── Upload to GitHub ──────────────────────────────────────────────────────
  if (GITHUB_TOKEN === 'NEEDS_TOKEN') {
    console.log('\nNo GITHUB_TOKEN set — key saved to google-play-key.json only.');
    console.log('Re-run with: $env:GITHUB_TOKEN = "YOUR_TOKEN" ; node scripts/bond-play-full-setup.js');
    process.exit(0);
  }

  console.log('\nAdding GOOGLE_PLAY_KEY_BASE64 to GitHub secrets...');
  const ok = await addGithubSecret('GOOGLE_PLAY_KEY_BASE64', b64);
  if (ok) {
    console.log('  Secret added');
  } else {
    console.error('  Failed to add secret — check GITHUB_TOKEN');
    process.exit(1);
  }

  // ── Trigger build ─────────────────────────────────────────────────────────
  console.log('\nTriggering Android build...');
  const trigRes = await ghApi('POST', `/repos/${OWNER}/${REPO}/actions/workflows/android-build.yml/dispatches`, {
    ref: 'main', inputs: { version_code: '1', version_name: '1.0.0' }
  });
  console.log('  Trigger status:', trigRes.status, trigRes.status === 204 ? '(success)' : '');

  console.log('\nDONE — Bond has completed the full Google Play setup.');
  console.log('Watch the build: https://github.com/modom123/3-lakes-logistics/actions');
  console.log('The app will be compiled, signed, and uploaded to Google Play automatically.');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
