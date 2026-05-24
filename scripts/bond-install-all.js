/**
 * Bond Master Installer — Full Google Play Store Setup
 *
 * Outside Bond runs this script. It handles:
 *   1. Add all 4 GitHub Secrets to the repo
 *   2. Trigger the GitHub Actions Android build
 *   3. Set up Google Play Console account as Organization
 *   4. Create the app listing in Play Console
 *
 * Prerequisites:
 *   - Chrome is open and logged into both github.com and play.google.com/console
 *     with the nwtcinvestment@gmail.com account
 *   - OR: Launch Chrome with --remote-debugging-port=9222
 *     Example (Windows): chrome.exe --remote-debugging-port=9222
 *     Example (Mac):     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
 *
 * Run: node scripts/bond-install-all.js
 */

const { execSync, spawn } = require('child_process');
const path = require('path');

function run(script) {
  console.log(`\n${'='.repeat(50)}`);
  console.log(`BOND RUNNING: ${script}`);
  console.log('='.repeat(50));
  try {
    execSync(`node ${path.join(__dirname, script)}`, { stdio: 'inherit' });
  } catch (e) {
    console.error(`Script failed: ${script}`);
    console.error(e.message);
  }
}

async function main() {
  console.log('\n🤖 BOND MASTER INSTALLER — 3 LAKES DRIVER');
  console.log('Organization: 3 Lakes Logistics | DUNS: 145025174');
  console.log('Account: nwtcinvestment@gmail.com\n');

  // Step 1: Add GitHub Secrets
  run('add-github-secrets.js');

  // Step 2: Setup Play Console
  run('play-console-setup.js');

  console.log('\n✅ BOND INSTALL COMPLETE');
  console.log('\nRemaining automated steps (triggered by GitHub Actions):');
  console.log('  • Android AAB build (auto-triggers on next push to main)');
  console.log('  • AAB upload to Google Play internal track (via fastlane)');
  console.log('\nTo trigger the build now, Bond will push a version bump to main.');
  console.log('Or go to: github.com/modom123/3-lakes-logistics/actions');
  console.log('  → "Build Android AAB (Google Play)" → Run workflow');
}

main();
