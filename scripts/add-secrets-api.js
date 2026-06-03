/**
 * Bond — Add GitHub Secrets via API (no browser needed)
 *
 * Uses GitHub REST API directly. Much more reliable than browser automation.
 *
 * Setup (one time):
 *   1. Go to: github.com/settings/tokens/new
 *   2. Note: "Bond secrets installer"
 *   3. Expiration: 7 days
 *   4. Scope: check "repo" (full repo access)
 *   5. Click "Generate token" — copy the token
 *   6. Run: GITHUB_TOKEN=your_token node scripts/add-secrets-api.js
 *      OR just run: node scripts/add-secrets-api.js  (Bond will prompt you)
 */

const https   = require('https');
const sodium  = require('libsodium-wrappers');

const OWNER = 'modom123';
const REPO  = '3-lakes-logistics';

const SECRETS = [
  { name: 'ANDROID_KEY_ALIAS',       value: 'threelakes' },
  { name: 'ANDROID_LF_KEY_ALIAS',    value: 'threelakes-lf' },
  { name: 'ANDROID_STORE_PASSWORD',  value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_KEY_PASSWORD',    value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_LF_KEY_PASSWORD', value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_KEYSTORE_BASE64', value: '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' },
];

// ── GitHub API helper ─────────────────────────────────────────────────────────
function api(method, path, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const req  = https.request({
      hostname: 'api.github.com',
      path,
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

// ── Encrypt secret using libsodium sealed box (GitHub's required format) ─────
async function encryptSecret(publicKeyB64, secretValue) {
  await sodium.ready;
  const binKey  = sodium.from_base64(publicKeyB64, sodium.base64_variants.ORIGINAL);
  const binMsg  = sodium.from_string(secretValue);
  const sealed  = sodium.crypto_box_seal(binMsg, binKey);
  return sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL);
}

// ── Prompt for token ──────────────────────────────────────────────────────────
function promptToken() {
  return new Promise(resolve => {
    process.stdout.write('\nPaste your GitHub Personal Access Token (repo scope): ');
    process.stdin.setEncoding('utf8');
    process.stdin.once('data', d => resolve(d.trim()));
  });
}

// ── Main ──────────────────────────────────────────────────────────────────────
(async () => {
  console.log('=== Bond GitHub Secrets (API mode) ===');

  const token = process.env.GITHUB_TOKEN || await promptToken();

  // Verify token works
  const me = await api('GET', '/user', token);
  if (me.status !== 200) {
    console.error('Token invalid or no access. Status:', me.status);
    console.error('Create a token at: github.com/settings/tokens/new  (scope: repo)');
    process.exit(1);
  }
  console.log(`Authenticated as: ${me.body.login}`);

  // Get repo public key for encryption
  const pkRes = await api('GET', `/repos/${OWNER}/${REPO}/actions/secrets/public-key`, token);
  if (pkRes.status !== 200) {
    console.error('Cannot get repo public key. Make sure the token has "repo" scope.');
    process.exit(1);
  }
  const { key: publicKey, key_id } = pkRes.body;
  console.log('Got repo encryption key. Adding secrets...\n');

  let allOk = true;
  for (const secret of SECRETS) {
    process.stdout.write(`  ${secret.name} ... `);
    try {
      const encrypted = await encryptSecret(publicKey, secret.value);
      const res = await api('PUT', `/repos/${OWNER}/${REPO}/actions/secrets/${secret.name}`, token, {
        encrypted_value: encrypted,
        key_id,
      });
      if (res.status === 201 || res.status === 204) {
        console.log('✓');
      } else {
        console.log('✗ Status:', res.status, JSON.stringify(res.body));
        allOk = false;
      }
    } catch (e) {
      console.log('✗ Error:', e.message);
      allOk = false;
    }
  }

  if (allOk) {
    console.log('\n✅ All 6 secrets added successfully! (GOOGLE_PLAY_KEY_BASE64 is separate — run encode-play-key.js after getting the Play service account)');
    console.log('Next: github.com/modom123/3-lakes-logistics/actions');
    console.log('      → "Build Android AAB (Google Play)" → Run workflow');
  } else {
    console.log('\n⚠️  Some secrets failed. Check errors above.');
  }
  process.exit(0);
})();
