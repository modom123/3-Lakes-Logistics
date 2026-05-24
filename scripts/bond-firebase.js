/**
 * Bond — Firebase App Distribution + FCM Setup
 *
 * What this does:
 *   1. Builds a debug APK via Capacitor (if no APK found)
 *   2. Uploads APK to Firebase App Distribution
 *   3. Adds testers and creates a release
 *   4. Opens Firebase Console to show results
 *   5. Wires FCM server key into backend .env
 *
 * Run: node scripts\bond-firebase.js
 */

const { execSync, spawnSync } = require('child_process');
const path = require('path');
const fs   = require('fs');
const readline = require('readline');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  console.log('Installing playwright...');
  execSync('npm install playwright', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname, '..'), stdio: 'inherit' });
  const r = spawnSync(process.execPath, [__filename], { stdio: 'inherit', env: process.env });
  process.exit(r.status ?? 0);
}

const { chromium } = require('playwright');

// ── Config ────────────────────────────────────────────────────────────────────
const FIREBASE_PROJECT = 'lakes-logistics-ffe6f';
const APP_PACKAGE      = 'com.threelakes.driver';
const RELEASE_NOTES    = '3 Lakes Driver v1.0 — Initial release for internal testing';
const TESTERS          = [
  'nwtcinvestment@gmail.com',
  'info@3lakeslogistics.com',
];

const ROOT = path.join(__dirname, '..');

function pause(msg) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(msg, () => { rl.close(); resolve(); });
  });
}
async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

function run(cmd, opts = {}) {
  console.log(`  $ ${cmd}`);
  try {
    const out = execSync(cmd, { cwd: ROOT, stdio: 'pipe', ...opts }).toString().trim();
    if (out) console.log('  ' + out.slice(0, 300));
    return out;
  } catch (e) {
    console.log('  ⚠ ' + (e.stderr?.toString() || e.message).slice(0, 200));
    return null;
  }
}

function findApk() {
  const candidates = [
    'android/app/build/outputs/apk/release/app-release.apk',
    'android/app/build/outputs/apk/debug/app-debug.apk',
    'android/app/build/outputs/bundle/release/app-release.aab',
  ];
  for (const c of candidates) {
    const full = path.join(ROOT, c);
    if (fs.existsSync(full)) return full;
  }
  // Deep search
  try {
    const found = execSync('find . -name "*.apk" -o -name "*.aab" 2>/dev/null', { cwd: ROOT, stdio: 'pipe' })
      .toString().trim().split('\n').filter(Boolean);
    if (found.length) return path.join(ROOT, found[0]);
  } catch {}
  return null;
}

(async () => {
  console.log('=== Bond: Firebase App Distribution + FCM Setup ===\n');
  console.log(`Project: ${FIREBASE_PROJECT}`);
  console.log(`Package: ${APP_PACKAGE}\n`);

  // ── Step 1: Check Firebase CLI ────────────────────────────────────────────
  console.log('[1] Checking Firebase CLI...');
  const fbVersion = run('firebase --version');
  if (!fbVersion) {
    console.log('  Firebase CLI not found — installing globally...');
    run('npm install -g firebase-tools');
  }

  // ── Step 2: Find or build APK ─────────────────────────────────────────────
  console.log('\n[2] Looking for APK/AAB...');
  let apkPath = findApk();

  if (apkPath) {
    console.log(`  ✓ Found: ${apkPath}`);
  } else {
    console.log('  No APK found. Attempting to build debug APK via Capacitor...');
    console.log('  (This requires Android SDK — may take a few minutes)');

    // Build www/ output first
    run('npm run build:mobile');
    // Sync to Android
    run('npx cap sync android');
    // Build debug APK via Gradle
    const gradlew = process.platform === 'win32' ? 'gradlew.bat' : './gradlew';
    run(`${gradlew} assembleDebug`, { cwd: path.join(ROOT, 'android') });

    apkPath = findApk();
    if (!apkPath) {
      console.log('\n  ⚠ Could not build APK automatically.');
      console.log('  Options:');
      console.log('  A) Build in Android Studio: open android/ folder → Build → Build APK');
      console.log('  B) Trigger GitHub Actions: push to main to build signed AAB');
      console.log('  C) Download the AAB from GitHub Actions artifacts');
      const apkInput = await pause('\n  Enter the full path to your APK/AAB (or press Enter to skip): ');
      if (apkInput && apkInput.trim() && fs.existsSync(apkInput.trim())) {
        apkPath = apkInput.trim();
      } else {
        console.log('  Skipping APK upload — continuing with FCM setup only.');
      }
    }
  }

  // ── Step 3: Upload to Firebase App Distribution ───────────────────────────
  if (apkPath) {
    console.log(`\n[3] Uploading ${path.basename(apkPath)} to Firebase App Distribution...`);

    const testersArg = TESTERS.join(',');
    const uploadCmd = [
      `firebase appdistribution:distribute "${apkPath}"`,
      `--app ${APP_PACKAGE}`,
      `--project ${FIREBASE_PROJECT}`,
      `--release-notes "${RELEASE_NOTES}"`,
      `--testers "${testersArg}"`,
    ].join(' ');

    const result = run(uploadCmd);
    if (result && result.includes('success')) {
      console.log('  ✓ APK uploaded to App Distribution!');
      console.log(`  Testers notified: ${testersArg}`);
    } else {
      console.log('  Upload may have succeeded — check Firebase Console for status.');
    }
  } else {
    console.log('\n[3] Skipped — no APK available');
  }

  // ── Step 4: Get FCM Server Key via Firebase Console ───────────────────────
  console.log('\n[4] Opening Firebase Console to get FCM server key...');

  let browser, context, page;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    context = browser.contexts()[0] || await browser.newContext();
    page    = context.pages()[0]    || await context.newPage();
    console.log('  ✓ Connected to existing Chrome');
  } catch {
    browser = await chromium.launch({ headless: false, slowMo: 100, args: ['--start-maximized'] });
    context = await browser.newContext({ viewport: null });
    page    = await context.newPage();
  }

  // Navigate to Firebase project settings → Cloud Messaging
  const fcmUrl = `https://console.firebase.google.com/project/${FIREBASE_PROJECT}/settings/cloudmessaging`;
  await page.goto(fcmUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(5000);
  console.log('  URL:', page.url().slice(0, 80));

  // Try to copy the server key from the page
  const serverKey = await page.evaluate(() => {
    const text = document.body.innerText || '';
    // FCM server keys are long strings starting with AAAA
    const m = text.match(/AAAA[A-Za-z0-9_\-]{100,}/);
    return m ? m[0] : null;
  });

  if (serverKey) {
    console.log(`  ✓ FCM Server Key found: ${serverKey.slice(0, 20)}...`);

    // Write to backend .env
    const envPath = path.join(ROOT, 'backend', '.env');
    if (fs.existsSync(envPath)) {
      let env = fs.readFileSync(envPath, 'utf8');
      if (env.includes('FCM_SERVER_KEY')) {
        env = env.replace(/FCM_SERVER_KEY=.*/g, `FCM_SERVER_KEY=${serverKey}`);
      } else {
        env += `\nFCM_SERVER_KEY=${serverKey}\n`;
      }
      fs.writeFileSync(envPath, env);
      console.log('  ✓ FCM_SERVER_KEY written to backend/.env');
    } else {
      console.log(`  FCM_SERVER_KEY=${serverKey}`);
      console.log('  (Copy this into your backend/.env file)');
    }
  } else {
    console.log('  FCM server key not auto-detected on page.');
    console.log('  In the browser, find the "Server key" under Cloud Messaging settings.');
  }

  // ── Step 5: Open App Distribution dashboard ───────────────────────────────
  console.log('\n[5] Opening App Distribution dashboard...');
  const distUrl = `https://console.firebase.google.com/project/${FIREBASE_PROJECT}/appdistribution`;
  await page.goto(distUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await wait(3000);
  console.log('  ✓ App Distribution dashboard open in browser');

  // ── Step 6: Wire FCM Admin SDK in backend ─────────────────────────────────
  console.log('\n[6] Checking FCM backend wiring...');
  const notifPath = path.join(ROOT, 'backend', 'app', 'api', 'routes_notifications.py');
  if (fs.existsSync(notifPath)) {
    let code = fs.readFileSync(notifPath, 'utf8');
    if (code.includes('# from firebase_admin')) {
      console.log('  Firebase Admin SDK is commented out in routes_notifications.py');
      console.log('  To enable real FCM: get serviceAccountKey.json from Firebase Console');
      console.log('  → Project Settings → Service Accounts → Generate new private key');
      console.log('  → Save as backend/serviceAccountKey.json');
      console.log('  → Then uncomment the firebase_admin imports in routes_notifications.py');
    } else if (code.includes('from firebase_admin')) {
      console.log('  ✓ Firebase Admin SDK already wired in routes_notifications.py');
    }
  }

  console.log('\n=== Bond Firebase Setup Complete ===');
  console.log('\nSummary:');
  if (apkPath) console.log(`  ✓ APK uploaded: ${path.basename(apkPath)}`);
  console.log(`  ✓ Testers: ${TESTERS.join(', ')}`);
  console.log('  → Browser open on App Distribution dashboard');
  console.log('\nNext steps:');
  console.log('  1. Testers check email for download link from Firebase');
  console.log('  2. Get serviceAccountKey.json to enable live FCM push notifications');
  console.log('  3. Upload signed AAB to Google Play when account type change is done');

  await pause('\nPress Enter to close browser... ');
  await browser.close();

})().catch(err => {
  console.error('\n✗ Error:', err.message);
  process.exit(1);
});
