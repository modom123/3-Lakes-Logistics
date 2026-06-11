// Build-time script: injects API_BASE_URL, SENTRY_DSN, and BOND_API_KEY into shared/config.js
const fs = require('fs');
const path = require('path');

const configPath  = path.join(__dirname, '..', 'shared', 'config.js');
const apiBase     = process.env.API_BASE_URL  || 'https://three-lakes-logistics-api.onrender.com';
const sentryDsn   = process.env.SENTRY_DSN    || '';
const bondApiKey  = process.env.BOND_API_KEY   || '';

let content = fs.readFileSync(configPath, 'utf8');
content = content.replace("'https://three-lakes-logistics-api.onrender.com'", `'${apiBase}'`);
if (sentryDsn) {
  content = content.replace("window.__3LL_SENTRY_DSN || ''", `'${sentryDsn}'`);
}
if (bondApiKey) {
  content = content.replace(
    "window.__3LL_BOND_API_KEY || 'xUvzgCnQZ-j-0HYTh749E1t6AKX3RNYFqNfoNVcnH1Z0KFCQUy693Q'",
    `'${bondApiKey}'`
  );
}
fs.writeFileSync(configPath, content);

console.log('config.js injected — API_BASE_URL:', apiBase, '| SENTRY_DSN set:', !!sentryDsn, '| BOND_API_KEY set:', !!bondApiKey);
