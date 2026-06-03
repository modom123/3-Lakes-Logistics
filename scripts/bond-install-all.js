/**
 * Bond Master Installer — Full Google Play Store Setup
 *
 * What Bond does automatically:
 *   1. Adds all 6 Android signing GitHub Secrets via API (no browser needed)
 *   2. Sets up Play Console account as Organization (browser automation)
 *   3. Triggers both Android build workflows (Truck Driver + Light Fleet)
 *   4. Emails a full report to Mark Odom, Cece, and the owner
 *
 * Prerequisites:
 *   - GITHUB_TOKEN set (repo scope) — Bond will prompt if not set
 *   - BOND_EMAIL_PASS set (info@3lakeslogistics.com password) — Bond will prompt
 *   - Chrome open at play.google.com/console logged in as nwtcinvestment@gmail.com
 *
 * Launch Chrome with debugging enabled first (Windows):
 *   PowerShell: .\scripts\launch-chrome.ps1
 *
 * Run: node scripts/bond-install-all.js
 */

const { execSync } = require('child_process');
const https        = require('https');
const path         = require('path');
const { sendBondReport } = require('./bond-notify');

const OWNER = 'modom123';
const REPO  = '3-lakes-logistics';

// Track every step result for the email report
const report = [];

function run(script, label, env = {}) {
  console.log(`\n${'='.repeat(56)}`);
  console.log(`BOND › ${label || script}`);
  console.log('='.repeat(56));
  try {
    execSync(`node ${path.join(__dirname, script)}`, {
      stdio: 'inherit',
      env: { ...process.env, ...env },
    });
    report.push({ name: label || script, status: 'ok' });
    return true;
  } catch (e) {
    console.error(`  ✗ Failed: ${e.message.split('\n')[0]}`);
    report.push({ name: label || script, status: 'fail', detail: e.message.split('\n')[0] });
    return false;
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

async function triggerBuild(token, workflow, label) {
  try {
    const res = await ghApi('POST',
      `/repos/${OWNER}/${REPO}/actions/workflows/${workflow}/dispatches`,
      token,
      { ref: 'main', inputs: { version_code: '1', version_name: '1.0.0' } }
    );
    const ok = res.status === 204;
    report.push({ name: label, status: ok ? 'ok' : 'fail', detail: ok ? 'Build triggered' : `HTTP ${res.status}` });
    return ok;
  } catch (e) {
    report.push({ name: label, status: 'fail', detail: e.message });
    return false;
  }
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
  console.log('║  Org:    3 Lakes Logistics  |  DUNS: 145025174 ║');
  console.log('║  Report: mark · cece · nwtcinvestment        ║');
  console.log('╚══════════════════════════════════════════════╝\n');

  // ── Step 1: Add GitHub Secrets via API ─────────────────────────────────────
  console.log('\n[1/3] Adding Android signing secrets to GitHub...');
  run('add-secrets-api.js', 'GitHub Secrets — Android signing keys (6 secrets)');

  // ── Step 2: Setup Play Console ─────────────────────────────────────────────
  console.log('\n[2/3] Setting up Google Play Console...');
  run('bond-play-console-setup.js', 'Google Play Console — org setup + app listing');

  // ── Step 3: Trigger Android builds ────────────────────────────────────────
  console.log('\n[3/3] Triggering Android build workflows...');
  const token = process.env.GITHUB_TOKEN || await promptToken();

  process.stdout.write('  Triggering Truck Driver AAB build... ');
  const ok1 = await triggerBuild(token, 'android-build.yml', 'GitHub Actions — Truck Driver AAB build');
  console.log(ok1 ? '✓ triggered' : '✗ failed (run manually in Actions tab)');

  process.stdout.write('  Triggering Light Fleet AAB build... ');
  const ok2 = await triggerBuild(token, 'android-build-lf.yml', 'GitHub Actions — Light Fleet AAB build');
  console.log(ok2 ? '✓ triggered' : '✗ failed (run manually in Actions tab)');

  // ── Send email report to all offices ──────────────────────────────────────
  console.log('\n[4/4] Sending report to Mark, Cece, and owner...');
  await sendBondReport(report);

  // ── Summary ───────────────────────────────────────────────────────────────
  const failed = report.filter(s => s.status === 'fail');
  console.log('\n╔══════════════════════════════════════════════╗');
  console.log(`║  BOND COMPLETE — ${failed.length === 0 ? 'ALL STEPS OK ✅' : `${failed.length} STEP(S) FAILED ⚠️`}          ║`);
  console.log('╚══════════════════════════════════════════════╝');

  if (failed.length > 0) {
    console.log('\n⚠️  Failed steps:');
    failed.forEach(s => console.log(`   • ${s.name}: ${s.detail}`));
  }

  console.log('\n📱 Monitor builds:');
  console.log('   https://github.com/modom123/3-lakes-logistics/actions');
  console.log('\n🔑 Still needed after Play Console approved:');
  console.log('   node scripts\\encode-play-key.js   (adds GOOGLE_PLAY_KEY_BASE64)');
}

main().catch(e => { console.error('\nBond error:', e.message); process.exit(1); });
