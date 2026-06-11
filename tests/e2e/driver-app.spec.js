// @ts-check
const { test, expect } = require('@playwright/test');

const BASE = process.env.APP_BASE_URL || 'http://localhost:8080';

// Helper: inject a mock authenticated session
async function injectSession(page, overrides = {}) {
  await page.evaluate((data) => {
    sessionStorage.setItem('3ll_token',      data.token);
    sessionStorage.setItem('3ll_api_token',  data.token);
    sessionStorage.setItem('3ll_expires_at', data.expiresAt);
    localStorage.setItem('3ll_driver_id',   data.driverId);
    localStorage.setItem('3ll_driver_name', data.driverName);
    localStorage.setItem('3ll_driver_code', data.driverCode);
    localStorage.setItem('3ll_driver_mode', 'truck');
    localStorage.setItem('3ll_phone',       data.phone);
  }, {
    token:      overrides.token      || 'mock-session-token-abc123',
    expiresAt:  overrides.expiresAt  || new Date(Date.now() + 86400000 * 7).toISOString(),
    driverId:   overrides.driverId   || 'drv-test-001',
    driverName: overrides.driverName || 'Test Driver',
    driverCode: overrides.driverCode || 'D001',
    phone:      overrides.phone      || '+13125550100',
  });
}

test.describe('Driver App — Navigation', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await injectSession(page);
  });

  test('loads main app with valid session', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await expect(page.locator('#header')).toBeVisible();
    await expect(page.locator('#nav-bar')).toBeVisible();
  });

  test('bottom nav has expected tabs', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await expect(page.locator('#nav-home')).toBeVisible();
    await expect(page.locator('#nav-loads')).toBeVisible();
    await expect(page.locator('#nav-messages')).toBeVisible();
    await expect(page.locator('#nav-profile')).toBeVisible();
  });

  test('tapping loads tab shows load board view', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await page.click('#nav-loads');
    await expect(page.locator('#view-loads')).toHaveClass(/active/);
  });

  test('tapping messages tab shows messages view', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await page.click('#nav-messages');
    await expect(page.locator('#view-messages')).toHaveClass(/active/);
  });

  test('tapping profile tab shows profile view', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await page.click('#nav-profile');
    await expect(page.locator('#view-profile')).toHaveClass(/active/);
  });

  test('driver name displayed in header', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/index.html`);
    const nameEl = page.locator('#driver-name');
    await expect(nameEl).toContainText('Test Driver');
  });

});

test.describe('Driver App — Load Board', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await injectSession(page);
  });

  test('load board renders without crashing on API error', async ({ page }) => {
    await page.route('**/api/loads**', route => route.fulfill({
      status: 500,
      body: 'Internal Server Error',
    }));
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await page.click('#nav-loads');
    // Should show error state, not crash
    await page.waitForTimeout(1000);
    const crashed = await page.evaluate(() => document.body.innerHTML === '');
    expect(crashed).toBe(false);
  });

  test('load board shows loads returned from API', async ({ page }) => {
    await page.route('**/api/loads**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 'ld-001', load_number: 'L-1001', origin: 'Chicago, IL', destination: 'Milwaukee, WI', rate: 850, miles: 90, equipment_type: 'Dry Van', pickup_at: new Date().toISOString() },
        { id: 'ld-002', load_number: 'L-1002', origin: 'Detroit, MI', destination: 'Cleveland, OH', rate: 1200, miles: 170, equipment_type: 'Reefer', pickup_at: new Date().toISOString() },
      ]),
    }));
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await page.click('#nav-loads');
    await page.waitForTimeout(800);
    const loadList = page.locator('#load-list');
    await expect(loadList).toBeVisible();
  });

});

test.describe('Driver App — Logout', () => {

  test('logout clears sessionStorage and redirects to login', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await injectSession(page);
    await page.goto(`${BASE}/driver-pwa/index.html`);

    // Confirm app loaded
    await expect(page.locator('#header')).toBeVisible();

    // Trigger logout (confirm dialog)
    page.on('dialog', dialog => dialog.accept());
    await page.evaluate(() => {
      if (typeof logout === 'function') logout();
    });

    await page.waitForURL(/login\.html/, { timeout: 3000 });

    const ssToken = await page.evaluate(() => sessionStorage.getItem('3ll_token'));
    expect(ssToken).toBeNull();
  });

});

test.describe('Driver App — Expired Session', () => {

  test('expired session redirects to login', async ({ page }) => {
    await page.goto(`${BASE}/driver-pwa/login.html`);
    await injectSession(page, {
      expiresAt: new Date(Date.now() - 1000).toISOString(), // already expired
    });
    await page.goto(`${BASE}/driver-pwa/index.html`);
    await expect(page).toHaveURL(/login\.html/);
  });

});
