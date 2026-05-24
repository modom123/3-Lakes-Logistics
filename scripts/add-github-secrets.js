/**
 * Bond Browser Automation — Add GitHub Secrets
 *
 * Navigates to github.com and adds the 4 Android signing secrets
 * using the browser already logged into GitHub.
 *
 * How to run (outside Bond runs this):
 *   node scripts/add-github-secrets.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const REPO_URL = 'https://github.com/modom123/3-lakes-logistics';
const SECRETS_URL = `${REPO_URL}/settings/secrets/actions`;

// Load keystore base64 from credentials file
const credsFile = path.join(__dirname, '..', 'KEYSTORE_CREDENTIALS.txt');
let keystoreB64 = '';
if (fs.existsSync(credsFile)) {
  const content = fs.readFileSync(credsFile, 'utf8');
  const match = content.match(/ANDROID_KEYSTORE_BASE64=([A-Za-z0-9+/=]+)/);
  if (match) keystoreB64 = match[1];
}

const SECRETS = [
  { name: 'ANDROID_KEY_ALIAS',      value: 'threelakes' },
  { name: 'ANDROID_STORE_PASSWORD', value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_KEY_PASSWORD',   value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_KEYSTORE_BASE64', value: keystoreB64 },
];

async function addSecret(page, name, value) {
  console.log(`  Adding secret: ${name}`);

  await page.goto(`${SECRETS_URL}/new`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);

  // Fill secret name
  const nameField = page.locator('input#secret-name, input[name="secret-name"], input[placeholder*="name" i]').first();
  await nameField.waitFor({ state: 'visible', timeout: 10000 });
  await nameField.fill(name);

  // Fill secret value
  const valueField = page.locator('textarea#secret-value, textarea[name="secret-value"], textarea[placeholder*="value" i]').first();
  await valueField.waitFor({ state: 'visible', timeout: 10000 });
  await valueField.fill(value);

  // Click Add secret
  const addBtn = page.locator('button:has-text("Add secret"), button[type="submit"]').first();
  await addBtn.click();
  await page.waitForTimeout(2000);

  console.log(`  ✓ ${name} added`);
}

(async () => {
  console.log('=== Bond GitHub Secrets Setup ===');

  if (!keystoreB64) {
    console.error('ERROR: Could not read keystore base64 from KEYSTORE_CREDENTIALS.txt');
    console.error('Make sure KEYSTORE_CREDENTIALS.txt exists in the repo root.');
    process.exit(1);
  }

  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to existing Chrome session.');
  } catch (e) {
    console.log('Launching new browser — log into github.com first, then Bond will proceed.');
    browser = await chromium.launch({ headless: false, slowMo: 300 });
  }

  const context = browser.contexts()[0] || await browser.newContext();
  const page = context.pages()[0] || await context.newPage();

  // Navigate to secrets page
  await page.goto(SECRETS_URL, { waitUntil: 'networkidle' });
  console.log('Opened GitHub secrets page.');
  await page.waitForTimeout(2000);

  // Check we're on the right page
  const url = page.url();
  if (url.includes('login')) {
    console.log('GitHub login required. Please log in as the repo owner, then press Enter...');
    await new Promise(r => process.stdin.once('data', r));
  }

  // Add each secret
  for (const secret of SECRETS) {
    await addSecret(page, secret.name, secret.value);
  }

  await page.screenshot({ path: 'scripts/github-secrets-done.png' });
  console.log('\n✅ All 4 GitHub Secrets added!');
  console.log('Screenshot: scripts/github-secrets-done.png');
  console.log('\nNext step: Go to GitHub Actions and run "Build Android AAB (Google Play)"');

  await browser.close();
})().catch(err => {
  console.error('Bond error:', err.message);
  process.exit(1);
});
