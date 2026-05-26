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
  { name: 'ANDROID_STORE_PASSWORD',  value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
  { name: 'ANDROID_KEY_PASSWORD',    value: 'Z!%8a7lx5$ANlUNwdVcwKFZe' },
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
    console.log('\n✅ All 4 secrets added successfully!');
    console.log('Next: github.com/modom123/3-lakes-logistics/actions');
    console.log('      → "Build Android AAB (Google Play)" → Run workflow');
  } else {
    console.log('\n⚠️  Some secrets failed. Check errors above.');
  }
  process.exit(0);
})();
