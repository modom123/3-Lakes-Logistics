// Build-time script: injects API_BASE_URL and SENTRY_DSN env vars into shared/config.js
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '..', 'shared', 'config.js');
const apiBase   = process.env.API_BASE_URL  || 'https://three-lakes-logistics-api.onrender.com';
const sentryDsn = process.env.SENTRY_DSN    || '';

let content = fs.readFileSync(configPath, 'utf8');
content = content.replace("'https://three-lakes-logistics-api.onrender.com'", `'${apiBase}'`);
if (sentryDsn) {
  content = content.replace("window.__3LL_SENTRY_DSN || ''", `'${sentryDsn}'`);
}
fs.writeFileSync(configPath, content);

console.log('config.js injected — API_BASE_URL:', apiBase, '| SENTRY_DSN set:', !!sentryDsn);
