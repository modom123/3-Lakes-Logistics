// Build-time script: injects API_BASE_URL and API_BEARER_TOKEN env vars into public/shared/config.js
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '..', 'public', 'shared', 'config.js');
const apiBase  = process.env.API_BASE_URL     || 'https://three-lakes-logistics-api.onrender.com';
const apiToken = process.env.API_BEARER_TOKEN || 'taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE';

let content = fs.readFileSync(configPath, 'utf8');
content = content.replace("'https://three-lakes-logistics-api.onrender.com'", `'${apiBase}'`);
content = content.replace("'taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE'",  `'${apiToken}'`);
fs.writeFileSync(configPath, content);

console.log('config.js injected — API_BASE_URL:', apiBase, '| token set:', !!apiToken);
