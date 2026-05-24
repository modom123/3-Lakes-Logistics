/**
 * Bond — Firebase App Distribution setup under new56money@gmail.com
 *
 * Run: node scripts\firebase-full.js
 *
 * 1. Opens Firebase Console (logged in as new56money@gmail.com)
 * 2. Creates "3 Lakes Driver" project if needed
 * 3. Enables App Distribution, uploads APK, adds all testers
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

const APK_PATH      = 'C:\\Users\\12068\\AndroidStudioProjects\\3lakesDriver\\app\\release\\app-release.apk';
const PACKAGE_NAME  = 'com.threelakes.driver';
const TESTERS       = [
  'nwtcinvestment@gmail.com',
  'info@3lakeslogistics.com',
  'raycece@yahoo.com',
  'goldiethemac@yahoo.com',
  'Savior45@yahoo.com',
  'talormoe14@yahoo.com',
  'new56money@gmail.com',
];
const RELEASE_NOTES = '3 Lakes Driver v1.0 — Internal test build';
const CONSOLE_URL   = 'https://console.firebase.google.com/';

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}

(async () => {
  console.log('=== Bond: Firebase App Distribution — new56money@gmail.com ===\n');

  if (!fs.existsSync(APK_PATH)) {
    console.log(`✗ APK not found: ${APK_PATH}`);
    process.exit(1);
  }
  const sizeMB = (fs.statSync(APK_PATH).size / 1024 / 1024).toFixed(1);
  console.log(`✓ APK found: ${APK_PATH} (${sizeMB} MB)\n`);

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('✓ Connected to your existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 60, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // ── Step 1: Open Firebase Console ─────────────────────────────────────────
  console.log('\n[1] Opening Firebase Console...');
  await page.goto(CONSOLE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(5000);

  const url1 = page.url();
  console.log('  URL:', url1.slice(0, 80));

  // Check if we need to sign in
  if (url1.includes('accounts.google') || url1.includes('signin')) {
    console.log('\n  Please sign in with new56money@gmail.com in Chrome.');
    await pause('  Press Enter once signed in... ');
    await page.goto(CONSOLE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await wait(5000);
  }

  // Check which account is active
  const accountInfo = await page.evaluate(() => {
    const header = document.body.innerText;
    return header.slice(0, 300);
  });
  console.log('  Console loaded. Page preview:', accountInfo.replace(/\n/g,' ').slice(0, 150));

  // ── Step 2: Find or create the 3 Lakes project ────────────────────────────
  console.log('\n[2] Looking for 3 Lakes project in your account...');
  const projectFound = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('[class*="project"], mat-card, a')];
    const p = cards.find(c => /(3.?lakes|lakes.?logistics|driver)/i.test(c.innerText || c.textContent || ''));
    if (p) { p.click(); return (p.innerText || p.textContent || '').trim().slice(0, 60); }
    return null;
  });

  if (projectFound) {
    console.log(`  ✓ Found project: ${projectFound}`);
    await wait(4000);
  } else {
    console.log('  No 3 Lakes project found — need to create one or use Firebase CLI.');
    console.log('\n╔══════════════════════════════════════════════════════════╗');
    console.log('║  ACTION: Log Firebase CLI into new56money@gmail.com      ║');
    console.log('╚══════════════════════════════════════════════════════════╝\n');

    // Re-login Firebase CLI as new56money@gmail.com
    console.log('  Running: firebase login --reauth');
    try {
      execSync('firebase login --reauth', { stdio: 'inherit', timeout: 120000 });
    } catch {}

    // List projects available to this account
    console.log('\n  Projects available after login:');
    try {
      execSync('firebase projects:list', { stdio: 'inherit', timeout: 15000 });
    } catch (e) {
      console.log('  ' + (e.stderr?.toString() || e.message || '').slice(0, 200));
    }

    await pause('\n  If you see a 3 Lakes project above, enter its ID here (or press Enter to create new): ');
  }

  // ── Step 3: Upload APK via Firebase CLI ───────────────────────────────────
  console.log('\n[3] Uploading APK to Firebase App Distribution...');
  console.log('  First, listing available Firebase projects...\n');

  let projectId = '';
  let appId = '';

  try {
    const projectsJson = execSync('firebase projects:list --json', { stdio: 'pipe', timeout: 15000 }).toString();
    const projects = JSON.parse(projectsJson);
    const list = projects.result || [];
    console.log('  Your Firebase projects:');
    list.forEach(p => console.log(`    ${p.projectId} — ${p.displayName}`));

    // Pick the 3 Lakes one or first available
    const match = list.find(p => /(3.?lakes|lakes.?logistics|driver)/i.test(p.displayName || p.projectId));
    const picked = match || list[0];
    if (picked) {
      projectId = picked.projectId;
      console.log(`\n  ✓ Using project: ${projectId} (${picked.displayName})`);
    }
  } catch (e) {
    console.log('  Could not list projects:', (e.stderr?.toString() || e.message || '').slice(0, 150));
    await pause('  Enter your Firebase Project ID manually: ');
  }

  if (projectId) {
    // Get Android app ID for this project
    try {
      const appsJson = execSync(`firebase apps:list --project ${projectId} --json`, { stdio: 'pipe', timeout: 15000 }).toString();
      const apps = JSON.parse(appsJson);
      const androidApp = (apps.result || []).find(a => a.platform === 'ANDROID');
      if (androidApp) {
        appId = androidApp.appId;
        console.log(`  ✓ Android App ID: ${appId}`);
      } else {
        console.log('  No Android app registered — creating one...');
        try {
          const createJson = execSync(
            `firebase apps:create ANDROID "${PACKAGE_NAME}" --project ${projectId} --json`,
            { stdio: 'pipe', timeout: 30000 }
          ).toString();
          const created = JSON.parse(createJson);
          appId = created.result?.appId || '';
          console.log(`  ✓ Created Android app: ${appId}`);
        } catch (e2) {
          console.log('  Create error:', (e2.stderr?.toString() || e2.message || '').slice(0, 150));
        }
      }
    } catch (e) {
      console.log('  Apps list error:', (e.stderr?.toString() || e.message || '').slice(0, 150));
    }
  }

  if (projectId && appId) {
    const uploadCmd = [
      `firebase appdistribution:distribute "${APK_PATH}"`,
      `--app "${appId}"`,
      `--project ${projectId}`,
      `--testers "${TESTERS.join(',')}"`,
      `--release-notes "${RELEASE_NOTES}"`,
    ].join(' ');

    console.log(`\n  $ ${uploadCmd}\n`);
    try {
      execSync(uploadCmd, { stdio: 'inherit', timeout: 180000 });
      console.log('\n  ✓ Upload complete! All testers notified.');

      // Open the App Distribution page
      const distUrl = `https://console.firebase.google.com/project/${projectId}/appdistribution`;
      await page.goto(distUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await wait(3000);
      console.log(`\n  ✓ Firebase App Distribution open: ${distUrl}`);
    } catch (e) {
      console.log('  Upload error:', (e.stderr?.toString() || e.message || '').slice(0, 300));
    }
  } else {
    console.log('\n  Could not determine project/app ID.');
    console.log('  Opening Firebase Console — you can upload manually:');
    console.log(`  1. Go to App Distribution in Firebase Console`);
    console.log(`  2. Get started → Android → Upload APK`);
    console.log(`  3. APK is at: ${APK_PATH}`);
  }

  console.log('\n=== Done ===');
  console.log('  Browser is open on Firebase Console.');

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
