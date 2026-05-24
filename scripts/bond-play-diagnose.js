/**
 * Bond — Diagnose what Play Console is showing
 * Run: node scripts/bond-play-diagnose.js
 */
const { execSync, spawnSync } = require('child_process');
const path = require('path');
function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('playwright')) {
  execSync('npm install', { cwd: path.join(__dirname,'..'), stdio: 'inherit' });
  execSync('npx playwright install chromium', { cwd: path.join(__dirname,'..'), stdio: 'inherit' });
  spawnSync(process.execPath, [__filename, ...process.argv.slice(2)], { stdio: 'inherit', env: process.env });
  process.exit(0);
}
const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
    browser = await chromium.connectOverCDP('http://localhost:9222');
    console.log('Connected to Chrome');
  } catch {
    browser = await chromium.launch({ headless: false });
  }
  const context = browser.contexts()[0] || await browser.newContext();
  const page    = context.pages()[0]    || await context.newPage();

  console.log('\nNavigating to Play Console...');
  await page.goto('https://play.google.com/console', { waitUntil: 'domcontentloaded', timeout: 60000 });

  // Wait longer for redirects and JS to run
  await new Promise(r => setTimeout(r, 10000));

  console.log('URL after 10s:', page.url());

  // Full page text (first 2000 chars)
  const text = await page.evaluate(() => document.body.innerText).catch(() => '');
  console.log('\n=== PAGE TEXT ===');
  console.log(text.slice(0, 2000));
  console.log('=================');

  // All buttons
  const btns = await page.evaluate(() =>
    [...document.querySelectorAll('button, a, [role="button"], [role="link"]')]
      .map(e => e.innerText?.trim() || e.getAttribute('aria-label') || '')
      .filter(t => t.length > 0 && t.length < 80)
  ).catch(() => []);
  console.log('\nAll clickable elements:', btns.slice(0, 40).join(' | '));

  // Any iframes?
  const frames = page.frames();
  console.log('\nFrames on page:', frames.length);
  for (const f of frames.slice(0, 5)) {
    console.log(' ', f.url().slice(0, 80));
  }

  await page.screenshot({ path: path.join(__dirname, 'play-diagnose.png'), fullPage: true });
  console.log('\nFull-page screenshot: scripts/play-diagnose.png');

  await browser.close();
})().catch(e => { console.error('Error:', e.message); process.exit(1); });
