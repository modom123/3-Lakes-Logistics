// @ts-check
const { test, expect } = require('@playwright/test');

const BASE = process.env.APP_BASE_URL || 'http://localhost:8080';

test.describe('Light Fleet Login Flow', () => {

  test('login page loads correctly', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login-lf.html`);
    await expect(page.locator('#phone')).toBeVisible();
    await expect(page.locator('#pin')).toBeVisible();
    await expect(page.locator('#login-btn')).toBeVisible();
  });

  test('rejects short phone number', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login-lf.html`);
    await page.fill('#phone', '312');
    await page.fill('#pin', '1234');
    await page.click('#login-btn');
    await expect(page.locator('#error')).toContainText('valid 10-digit');
  });

  test('auth token stored in sessionStorage after LF login', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login-lf.html`);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });

    // login-lf.html authenticates via the Supabase RPC lf_driver_login
    // (sb.rpc), which POSTs to /rest/v1/rpc/lf_driver_login — not a REST
    // /api/driver-auth endpoint. Mock the RPC the page actually calls.
    await page.route('**/rpc/lf_driver_login', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'lf-001', name: 'LF Driver' }),
    }));

    await page.fill('#phone', '(312) 555-0100');
    await page.fill('#pin', '1234');
    await page.click('#login-btn');
    await page.waitForTimeout(500);

    const ssToken = await page.evaluate(() => sessionStorage.getItem('3ll_token'));
    const lsToken = await page.evaluate(() => localStorage.getItem('3ll_token'));
    const lsMode  = await page.evaluate(() => localStorage.getItem('3ll_driver_mode'));
    expect(ssToken).toBeTruthy();
    expect(lsToken).toBeNull();
    expect(lsMode).toBe('light');
  });

  test('logout clears sessionStorage', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login-lf.html`);
    await page.evaluate(() => {
      sessionStorage.setItem('3ll_token',      'mock-lf-token');
      sessionStorage.setItem('3ll_api_token',  'mock-lf-token');
      sessionStorage.setItem('3ll_expires_at', new Date(Date.now() + 86400000).toISOString());
      localStorage.setItem('3ll_lf_driver_id', 'lf-001');
      localStorage.setItem('3ll_driver_mode',  'light');
    });
    await page.goto(`${BASE}/driver-pwa/lf.html`);

    page.on('dialog', dialog => dialog.accept());
    await page.evaluate(() => { if (typeof logout === 'function') logout(); });

    await page.waitForURL(/login-lf\.html/, { timeout: 3000 });

    const ssToken = await page.evaluate(() => sessionStorage.getItem('3ll_token'));
    expect(ssToken).toBeNull();
  });

});
