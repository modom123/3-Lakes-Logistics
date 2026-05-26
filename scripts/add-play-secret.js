/**
 * Bond — Add GOOGLE_PLAY_KEY_BASE64 secret to GitHub
 * Run after get-play-service-account.js downloads the JSON key.
 *
 * Usage:
 *   node scripts/add-play-secret.js
 *   (reads from scripts/play-key-b64.txt automatically)
 */

const https  = require('https');
const sodium = require('libsodium-wrappers');
const fs     = require('fs');
const path   = require('path');

const OWNER = 'modom123';
const REPO  = '3-lakes-logistics';
const TOKEN = process.env.GITHUB_TOKEN;

function api(method, apiPath, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req  = https.request({
      hostname: 'api.github.com',
      path:     apiPath,
      method,
      headers: {
        'Authorization':        `Bearer ${TOKEN}`,
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
  const sealed = sodium.crypto_box_seal(sodium.from_string(value), sodium.from_base64(publicKeyB64, sodium.base64_variants.ORIGINAL));
  return sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
}

(async () => {
  // Read the base64 key
  const b64File = path.join(__dirname, 'play-key-b64.txt');
  let b64;
  if (fs.existsSync(b64File)) {
    b64 = fs.readFileSync(b64File, 'utf8').trim();
    console.log('Read key from scripts/play-key-b64.txt');
  } else {
    // Try to find the JSON directly in Downloads
    const downloadsDir = path.join(process.env.USERPROFILE || process.env.HOME, 'Downloads');
    const files = fs.readdirSync(downloadsDir)
      .filter(f => f.endsWith('.json'))
      .sort((a, b) => fs.statSync(path.join(downloadsDir, b)).mtimeMs - fs.statSync(path.join(downloadsDir, a)).mtimeMs);
    if (files.length === 0) {
      console.error('No key file found. Download the service account JSON from Google Cloud Console first.');
      process.exit(1);
    }
    const keyJson = fs.readFileSync(path.join(downloadsDir, files[0]), 'utf8');
    b64 = Buffer.from(keyJson).toString('base64');
    console.log(`Read key from Downloads/${files[0]}`);
  }

  const pkRes = await api('GET', `/repos/${OWNER}/${REPO}/actions/secrets/public-key`);
  const { key, key_id } = pkRes.body;
  const encrypted = await encryptSecret(key, b64);

  process.stdout.write('Adding GOOGLE_PLAY_KEY_BASE64 secret... ');
  const res = await api('PUT', `/repos/${OWNER}/${REPO}/actions/secrets/GOOGLE_PLAY_KEY_BASE64`, { encrypted_value: encrypted, key_id });
  if (res.status === 201 || res.status === 204) {
    console.log('✓');
    console.log('\n✅ Google Play secret added! The next build will auto-upload to Play Store.');
  } else {
    console.log('✗', res.status, JSON.stringify(res.body));
  }
})();
