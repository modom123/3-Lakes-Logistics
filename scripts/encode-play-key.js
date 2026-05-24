/**
 * Bond — Encode Google Play service account JSON and add to GitHub
 *
 * Run AFTER downloading the service account JSON from Google Cloud Console.
 *
 * Steps to get the JSON:
 *   1. Go to console.cloud.google.com
 *   2. IAM & Admin → Service Accounts
 *   3. Click the service account linked to Play Store
 *   4. Keys tab → Add Key → Create new key → JSON → Create
 *   5. File downloads automatically to your Downloads folder
 *   6. Run this script: node scripts/encode-play-key.js
 */

const https  = require('https');
const sodium = require('libsodium-wrappers');
const fs     = require('fs');
const path   = require('path');
const readline = require('readline');

const OWNER = 'modom123';
const REPO  = '3-lakes-logistics';

function api(method, apiPath, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req  = https.request({
      hostname: 'api.github.com',
      path:     apiPath,
      method,
      headers: {
        'Authorization':        `Bearer ${token}`,
        'User-Agent':           'Bond-3Lakes',
        'Accept':               'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        ...(data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}),
      },
    }, res => {
      let buf = '';
      res.on('data', c => buf += c);
      res.on('end', () => resolve({ status: res.statusCode, body: buf ? JSON.parse(buf) : {} }));
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

async function encryptSecret(publicKeyB64, value) {
  await sodium.ready;
  const sealed = sodium.crypto_box_seal(
    sodium.from_string(value),
    sodium.from_base64(publicKeyB64, sodium.base64_variants.ORIGINAL)
  );
  return sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
}

function prompt(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => rl.question(question, ans => { rl.close(); resolve(ans.trim()); }));
}

// Find newest JSON file in Downloads
function findNewestJson() {
  const dirs = [
    path.join(process.env.USERPROFILE || '', 'Downloads'),
    path.join(process.env.HOME || '', 'Downloads'),
  ].filter(d => d && fs.existsSync(d));

  for (const dir of dirs) {
    const files = fs.readdirSync(dir)
      .filter(f => f.endsWith('.json'))
      .map(f => ({ name: f, mtime: fs.statSync(path.join(dir, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);

    if (files.length > 0) {
      const newest = path.join(dir, files[0].name);
      // Verify it looks like a service account key
      try {
        const parsed = JSON.parse(fs.readFileSync(newest, 'utf8'));
        if (parsed.type === 'service_account') return newest;
      } catch {}
      // Return it anyway and let user confirm
      return newest;
    }
  }
  return null;
}

(async () => {
  console.log('=== Bond — Add Google Play Service Account Secret ===\n');

  // Find the JSON key file
  let keyPath = findNewestJson();

  if (keyPath) {
    console.log(`Found JSON file: ${keyPath}`);
    const confirm = await prompt('Is this the correct service account key? (yes/no): ');
    if (confirm.toLowerCase() !== 'yes' && confirm.toLowerCase() !== 'y') {
      keyPath = await prompt('Enter the full path to the JSON key file: ');
    }
  } else {
    console.log('No JSON file found in Downloads folder.');
    keyPath = await prompt('Enter the full path to the downloaded JSON key file: ');
  }

  if (!fs.existsSync(keyPath)) {
    console.error('File not found:', keyPath);
    process.exit(1);
  }

  const keyJson = fs.readFileSync(keyPath, 'utf8');
  const b64     = Buffer.from(keyJson).toString('base64');
  console.log('\nKey file loaded and encoded.');

  // Get GitHub token
  const token = process.env.GITHUB_TOKEN || await prompt('\nPaste your GitHub token (repo scope): ');

  // Verify token
  const me = await api('GET', '/user', token);
  if (me.status !== 200) {
    console.error('Invalid GitHub token. Get one at github.com/settings/tokens/new (repo scope)');
    process.exit(1);
  }
  console.log(`GitHub: authenticated as ${me.body.login}`);

  // Get public key
  const pkRes = await api('GET', `/repos/${OWNER}/${REPO}/actions/secrets/public-key`, token);
  const { key, key_id } = pkRes.body;

  // Encrypt and upload
  process.stdout.write('Adding GOOGLE_PLAY_KEY_BASE64 to GitHub secrets... ');
  const encrypted = await encryptSecret(key, b64);
  const res = await api('PUT', `/repos/${OWNER}/${REPO}/actions/secrets/GOOGLE_PLAY_KEY_BASE64`, token, {
    encrypted_value: encrypted,
    key_id,
  });

  if (res.status === 201 || res.status === 204) {
    console.log('✓');
    console.log('\n✅ Done! All secrets are now set.');
    console.log('Go to github.com/modom123/3-lakes-logistics/actions');
    console.log('→ "Build Android AAB (Google Play)" → Run workflow');
    console.log('The build will compile, sign, and upload the app to Google Play automatically.');
  } else {
    console.log('✗ Status:', res.status, JSON.stringify(res.body));
  }
})();
