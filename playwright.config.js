// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  retries: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.APP_BASE_URL || 'http://localhost:8080',
    headless: true,
    viewport: { width: 390, height: 844 }, // iPhone 14 Pro
    userAgent: '3LakesDriver/1.0 Mozilla/5.0',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 7'] },
    },
  ],
  // Serve the static driver surfaces (driver-pwa/, light-fleet.html, …) so
  // `npx playwright test` is self-contained — no manual server step. The E2E
  // specs mock the backend via page.route(), so a static file server is enough.
  // Skipped when APP_BASE_URL points at an already-running server.
  webServer: process.env.APP_BASE_URL ? undefined : {
    command: 'python3 -m http.server 8080',
    url: 'http://localhost:8080/driver-pwa/login.html',
    timeout: 30000,
    reuseExistingServer: true,
  },
});
