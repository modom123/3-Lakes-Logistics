// Build-time script: injects API_BASE_URL env var into public/shared/config.js
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, '..', 'public', 'shared', 'config.js');
const apiBase = process.env.API_BASE_URL || 'http://localhost:8080';

let content = fs.readFileSync(configPath, 'utf8');
content = content.replace("'http://localhost:8080'", `'${apiBase}'`);
fs.writeFileSync(configPath, content);

console.log('config.js injected with API_BASE_URL:', apiBase);
