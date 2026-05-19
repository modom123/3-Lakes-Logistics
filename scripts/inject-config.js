// Build-time script: injects API_BASE_URL and API_BEARER_TOKEN env vars into public/shared/config.js
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '..', 'public', 'shared', 'config.js');
const apiBase  = process.env.API_BASE_URL      || 'http://localhost:8080';
const apiToken = process.env.API_BEARER_TOKEN  || '';

let content = fs.readFileSync(configPath, 'utf8');
content = content.replace("'http://localhost:8080'", `'${apiBase}'`);
content = content.replace("'change-me-in-prod'",     `'${apiToken}'`);
fs.writeFileSync(configPath, content);

console.log('config.js injected — API_BASE_URL:', apiBase, '| token set:', !!apiToken);
