/**
 * Bond — Get Google Play service account key
 * Connects to Chrome, captures the OAuth Bearer token Cloud Console uses
 * for its own API calls, then drives GCP APIs from Node.js with that token.
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

// ── GitHub API (Node HTTPS) ───────────────────────────────────────────────────
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

// ── Google Cloud API (Node HTTPS + captured Bearer token) ─────────────────────
function gcpApi(method, apiUrl, token, body) {
  return new Promise((resolve, reject) => {
    const u    = new URL(apiUrl);
    const data = body ? JSON.stringify(body) : null;
    const req  = https.request({
      hostname: u.hostname,
      path: u.pathname + u.search,
      method,
      headers: {
        'Authorization':  `Bearer ${token}`,
        'Content-Type':   'application/json',
        'User-Agent':     'Bond-3Lakes',
        ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}),
      },
    }, res => {
      let b = '';
      res.on('data', c => b += c);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(b) }); }
        catch { resolve({ status: res.statusCode, data: b }); }
      });
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  console.log('=== Bond: Google Play Service Account ===\n');

  // ── Connect to Chrome ─────────────────────────────────────────────────────
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

  // ── Step 1: Capture Bearer token from Cloud Console's own requests ────────
  console.log('\n[1/5] Capturing Google auth token from Cloud Console...');

  let authToken = null;
  let tokenResolve;
  const tokenReady = new Promise(r => { tokenResolve = r; });

  // Observe every outbound request — capture the first googleapis.com Bearer token
  page.on('request', req => {
    if (authToken) return;
    const auth = req.headers()['authorization'] || req.headers()['Authorization'] || '';
    if (auth.startsWith('Bearer ') && req.url().includes('googleapis.com')) {
      authToken = auth.slice(7);
      console.log('  Token captured from:', req.url().replace(/\?.*/, '').slice(0, 70));
      tokenResolve();
    }
  });

  // Navigate to the Cloud Console dashboard — this triggers googleapis.com API calls
  await page.goto('https://console.cloud.google.com/home/dashboard',
    { waitUntil: 'domcontentloaded', timeout: 60000 });

  // Wait up to 30s for a token to appear
  await Promise.race([tokenReady, sleep(30000)]);

  if (!authToken) {
    // Maybe the page was cached and made no new requests — reload to force fresh calls
    console.log('  No token yet — reloading...');
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
    await Promise.race([tokenReady, sleep(20000)]);
  }

  if (!authToken) {
    console.error('\n  Could not capture auth token.');
    console.error('  Chrome must be logged into nwtcinvestment@gmail.com.');
    console.error('  Open Chrome, go to console.cloud.google.com, sign in, then re-run this script.');
    await browser.close(); process.exit(1);
  }

  console.log('  Auth token ready');
  await browser.close(); // browser not needed beyond this point

  // ── Step 2: Get or create GCP project ────────────────────────────────────
  console.log('\n[2/5] Getting Google Cloud projects...');
  const projRes = await gcpApi('GET',
    'https://cloudresourcemanager.googleapis.com/v1/projects?filter=lifecycleState%3AACTIVE',
    authToken);
  console.log('  Status:', projRes.status);

  let projectId;
  if (projRes.status === 200 && projRes.data.projects && projRes.data.projects.length > 0) {
    const project = projRes.data.projects[0];
    projectId = project.projectId;
    console.log(`  Using project: ${project.name} (${projectId})`);
  } else if (projRes.status === 200) {
    console.log('  No projects found — creating one...');
    const pid = 'threelakes-' + Date.now().toString().slice(-8);
    const cr  = await gcpApi('POST',
      'https://cloudresourcemanager.googleapis.com/v1/projects',
      authToken, { projectId: pid, name: '3 Lakes Logistics' });
    console.log('  Create status:', cr.status);
    if (cr.status !== 200 && cr.status !== 201) {
      console.error('  Failed to create project:', JSON.stringify(cr.data).slice(0, 400));
      process.exit(1);
    }
    console.log('  Waiting 30s for project to be ready...');
    await sleep(30000);
    const pr2 = await gcpApi('GET',
      'https://cloudresourcemanager.googleapis.com/v1/projects?filter=lifecycleState%3AACTIVE',
      authToken);
    projectId = (pr2.data.projects && pr2.data.projects.length > 0)
      ? pr2.data.projects[0].projectId : pid;
    console.log('  Project:', projectId);
  } else {
    console.error('  GCP error:', JSON.stringify(projRes.data).slice(0, 400));
    process.exit(1);
  }

  // ── Step 3: Enable required APIs ─────────────────────────────────────────
  console.log('\n[3/5] Enabling IAM API...');
  const enableRes = await gcpApi('POST',
    `https://serviceusage.googleapis.com/v1/projects/${projectId}/services/iam.googleapis.com:enable`,
    authToken, {});
  console.log('  Enable IAM status:', enableRes.status);
  await sleep(8000);

  // ── Step 4: List or create service account ────────────────────────────────
  console.log('[4/5] Getting service accounts...');
  const saRes = await gcpApi('GET',
    `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`, authToken);
  console.log('  Status:', saRes.status);

  let saEmail;
  if (saRes.status === 200 && saRes.data.accounts && saRes.data.accounts.length > 0) {
    saEmail = saRes.data.accounts[0].email;
    console.log('  Using:', saEmail);
  } else {
    console.log('  None found — creating service account...');
    const cr = await gcpApi('POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts`,
      authToken,
      { accountId: 'threelakes-play', serviceAccount: { displayName: '3 Lakes Play Store' } });
    console.log('  Create SA status:', cr.status);
    if (!cr.data.email) {
      console.error('  Failed to create service account:', JSON.stringify(cr.data).slice(0, 400));
      process.exit(1);
    }
    saEmail = cr.data.email;
    console.log('  Created:', saEmail);
  }

  // ── Step 5: Create JSON key ───────────────────────────────────────────────
  console.log('[5/5] Creating service account JSON key...');
  let keyRes = await gcpApi('POST',
    `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
    authToken,
    { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' });
  console.log('  Key create status:', keyRes.status);

  if (!keyRes.data.privateKeyData) {
    console.log('  Retrying after enabling IAM API...');
    await gcpApi('POST',
      `https://serviceusage.googleapis.com/v1/projects/${projectId}/services/iam.googleapis.com:enable`,
      authToken, {});
    await sleep(10000);
    keyRes = await gcpApi('POST',
      `https://iam.googleapis.com/v1/projects/${projectId}/serviceAccounts/${saEmail}/keys`,
      authToken,
      { privateKeyType: 'TYPE_GOOGLE_CREDENTIALS_FILE', keyAlgorithm: 'KEY_ALG_RSA_2048' });
    console.log('  Retry status:', keyRes.status);
    if (!keyRes.data.privateKeyData) {
      console.error('  Key creation failed:', JSON.stringify(keyRes.data).slice(0, 400));
      process.exit(1);
    }
  }

  const keyJson = Buffer.from(keyRes.data.privateKeyData, 'base64').toString('utf8');
  const b64     = Buffer.from(keyJson).toString('base64');
  fs.writeFileSync(path.join(repoRoot, 'google-play-key.json'), keyJson);
  console.log('  Key saved to google-play-key.json');

  // ── Upload to GitHub ──────────────────────────────────────────────────────
  if (GITHUB_TOKEN === 'NEEDS_TOKEN') {
    console.log('\nNo GITHUB_TOKEN — key is in google-play-key.json only.');
    console.log('Set token and re-run: $env:GITHUB_TOKEN = "YOUR_TOKEN"');
    process.exit(0);
  }

  console.log('\nAdding GOOGLE_PLAY_KEY_BASE64 to GitHub secrets...');
  const ok = await addGithubSecret('GOOGLE_PLAY_KEY_BASE64', b64);
  console.log(ok ? '  Secret added' : '  FAILED — check GITHUB_TOKEN');
  if (!ok) process.exit(1);

  // ── Trigger build ─────────────────────────────────────────────────────────
  console.log('\nTriggering Android build...');
  const trigRes = await ghApi('POST',
    `/repos/${OWNER}/${REPO}/actions/workflows/android-build.yml/dispatches`,
    { ref: 'main', inputs: { version_code: '1', version_name: '1.0.0' } });
  console.log('  Trigger status:', trigRes.status, trigRes.status === 204 ? '(success)' : '');

  console.log('\nDONE — service account created, secret added, build triggered.');
  console.log('Watch: https://github.com/modom123/3-lakes-logistics/actions');

})().catch(err => {
  console.error('\nBond error:', err.message);
  process.exit(1);
});
