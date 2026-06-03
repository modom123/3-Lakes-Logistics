/**
 * Bond Master Installer — Full Google Play Store Setup
 *
 * What Bond does automatically:
 *   1. Adds all 6 Android signing GitHub Secrets via API (no browser needed)
 *   2. Sets up Play Console account as Organization (browser automation)
 *   3. Triggers both Android build workflows (Truck Driver + Light Fleet)
 *
 * Prerequisites:
 *   - GITHUB_TOKEN set (repo scope) — Bond will prompt if not set
 *   - Chrome open at play.google.com/console logged in as nwtcinvestment@gmail.com
 *     (for Play Console setup)
 *
 * Launch Chrome with debugging enabled first (Windows):
 *   PowerShell: .\scripts\launch-chrome.ps1
 *
 * Run: node scripts/bond-install-all.js
 */

const { execSync } = require('child_process');
const https        = require('https');
const path         = require('path');

const OWNER = 'modom123';
const REPO  = '3-lakes-logistics';

function run(script, env = {}) {
  console.log(`\n${'='.repeat(56)}`);
  console.log(`BOND › ${script}`);
  console.log('='.repeat(56));
  try {
    execSync(`node ${path.join(__dirname, script)}`, {
      stdio: 'inherit',
      env: { ...process.env, ...env },
    });
  } catch (e) {
    console.error(`  ✗ Script failed: ${e.message}`);
  }
}

function ghApi(method, p, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req = https.request({
      hostname: 'api.github.com', path: p, method,
      headers: {
        'Authorization': `Bearer ${token}`, 'User-Agent': 'Bond-3Lakes',
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
        ...(data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}),
      },
    }, res => { let b = ''; res.on('data', c => b += c); res.on('end', () => resolve({ status: res.statusCode, body: b ? JSON.parse(b) : {} })); });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

async function triggerBuild(token, workflow, versionCode, versionName) {
  const res = await ghApi('POST',
    `/repos/${OWNER}/${REPO}/actions/workflows/${workflow}/dispatches`,
    token,
    { ref: 'main', inputs: { version_code: String(versionCode), version_name: versionName } }
  );
  return res.status === 204;
}

function promptToken() {
  return new Promise(resolve => {
    process.stdout.write('\nPaste your GitHub Personal Access Token (repo scope): ');
    process.stdin.setEncoding('utf8');
    process.stdin.once('data', d => resolve(d.trim()));
  });
}

async function main() {
  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║  BOND MASTER INSTALLER — 3 LAKES LOGISTICS  ║');
  console.log('╠══════════════════════════════════════════════╣');
  console.log('║  Apps:   Truck Driver + Light Fleet          ║');
  console.log('║  Org:    3 Lakes Logistics                   ║');
  console.log('║  DUNS:   145025174                           ║');
  console.log('║  Email:  nwtcinvestment@gmail.com            ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  // ── Step 1: Add GitHub Secrets via API ─────────────────────────────────────
  console.log('\n[1/3] Adding Android signing secrets to GitHub...');
  run('add-secrets-api.js');

  // ── Step 2: Setup Play Console (browser automation) ────────────────────────
  console.log('\n[2/3] Setting up Google Play Console...');
  run('bond-play-console-setup.js');

  // ── Step 3: Trigger both Android builds ────────────────────────────────────
  console.log('\n[3/3] Triggering Android build workflows...');
  const token = process.env.GITHUB_TOKEN || await promptToken();

  process.stdout.write('  Triggering Truck Driver build... ');
  const ok1 = await triggerBuild(token, 'android-build.yml', 1, '1.0.0');
  console.log(ok1 ? '✓ triggered' : '✗ failed (run manually in Actions tab)');

  process.stdout.write('  Triggering Light Fleet build... ');
  const ok2 = await triggerBuild(token, 'android-build-lf.yml', 1, '1.0.0');
  console.log(ok2 ? '✓ triggered' : '✗ failed (run manually in Actions tab)');

  console.log('\n╔══════════════════════════════════════════════╗');
  console.log('║  BOND INSTALL COMPLETE                       ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log('\n📱 Monitor builds:');
  console.log('   https://github.com/modom123/3-lakes-logistics/actions');
  console.log('\n📦 After builds complete:');
  console.log('   1. Download AABs from Actions artifacts');
  console.log('   2. Create app listings in Play Console (if not already done)');
  console.log('   3. Upload AABs to internal track');
  console.log('   4. Complete store listing, content rating, data safety form');
  console.log('\n🔑 Still needed: GOOGLE_PLAY_KEY_BASE64');
  console.log('   After creating Play Console → Service Account:');
  console.log('   run: node scripts/encode-play-key.js');
}

main().catch(e => { console.error('\nBond error:', e.message); process.exit(1); });
