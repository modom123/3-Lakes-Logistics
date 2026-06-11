// @ts-check
const { test, expect } = require('@playwright/test');

const BASE = process.env.APP_BASE_URL || 'http://localhost:8080';
const TEST_PHONE = process.env.TEST_DRIVER_PHONE || '3125550100';
const TEST_PIN   = process.env.TEST_DRIVER_PIN   || '1234';

test.describe('Driver Login Flow', () => {

  test('login page loads with required fields', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await expect(page.locator('#phone')).toBeVisible();
    await expect(page.locator('#pin')).toBeVisible();
    await expect(page.locator('#login-btn')).toBeVisible();
    await expect(page.locator('#login-btn')).toHaveText(/Sign In/);
  });

  test('rejects empty form submission', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.click('#login-btn');
    // HTML5 required validation fires — phone field should be focused/invalid
    const phoneValidity = await page.$eval('#phone', el => el.validity.valid);
    expect(phoneValidity).toBe(false);
  });

  test('rejects short phone number', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.fill('#phone', '312');
    await page.fill('#pin', '1234');
    await page.click('#login-btn');
    const error = page.locator('#error');
    await expect(error).toBeVisible();
    await expect(error).toContainText('valid 10-digit');
  });

  test('rejects non-numeric PIN', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.fill('#phone', '(312) 555-0100');
    await page.fill('#pin', 'abcd');
    // PIN input strips non-digits — field should remain empty
    const pinValue = await page.$eval('#pin', el => el.value);
    expect(pinValue).toBe('');
  });

  test('PIN input only accepts digits', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.fill('#pin', 'abc1def2');
    const pinValue = await page.$eval('#pin', el => el.value);
    expect(pinValue).toBe('12');
  });

  test('PIN input caps at 4 digits', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.fill('#pin', '123456789');
    const pinValue = await page.$eval('#pin', el => el.value);
    expect(pinValue.length).toBeLessThanOrEqual(4);
  });

  test('phone input formats as user types', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.fill('#phone', '3125550100');
    const formatted = await page.$eval('#phone', el => el.value);
    expect(formatted).toMatch(/\(312\) 555-0100/);
  });

  test('setup PIN mode toggles correctly', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.click('#mode-toggle');
    await expect(page.locator('#confirm-pin-group')).toBeVisible();
    await expect(page.locator('#login-btn')).toContainText('Set PIN');
    // Toggle back
    await page.click('#mode-toggle');
    await expect(page.locator('#confirm-pin-group')).toBeHidden();
    await expect(page.locator('#login-btn')).toContainText('Sign In');
  });

  test('setup PIN rejects mismatched PINs', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.click('#mode-toggle');
    await page.fill('#phone', '(312) 555-0100');
    await page.fill('#pin', '1234');
    await page.fill('#confirm-pin', '5678');
    await page.click('#login-btn');
    await expect(page.locator('#error')).toContainText('do not match');
  });

  test('unauthenticated access to index.html redirects to login', async ({ page }) => {
    // Clear any stored session
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await expect(page).toHaveURL(/login\.html/);
  });

  test('unauthenticated access to lf.html redirects to login', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await page.goto(`${BASE}/driver-pwa/lf.html`);
    await expect(page).toHaveURL(/login-lf\.html/);
  });

  test('auth token stored in sessionStorage after login (not localStorage)', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });

    // Intercept the API login call and mock a successful response
    await page.route('**/api/driver-auth/login', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ token: 'test-jwt-token-abc123', driver_id: 'drv-001', carrier_id: 1 }),
    }));
    await page.route('**/rpc/driver_login', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'drv-001', driver_code: 'D001', first_name: 'Test', last_name: 'Driver' }),
    }));

    await page.fill('#phone', '(312) 555-0100');
    await page.fill('#pin', '1234');
    await page.click('#login-btn');
    await page.waitForTimeout(500);

    const ssToken = await page.evaluate(() => sessionStorage.getItem('3ll_token'));
    const lsToken = await page.evaluate(() => localStorage.getItem('3ll_token'));
    expect(ssToken).toBeTruthy();
    expect(lsToken).toBeNull();
  });

});
