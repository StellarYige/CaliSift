import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  timeout: 240000,
  expect: { timeout: 60000 },
  workers: 1,
  maxFailures: process.env.CI ? 1 : 0,
  fullyParallel: false,
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          process.env.CALISIFT_BROWSER_RESULTS ||
          "../artifacts/web-browser-results.json",
      },
    ],
  ],
  use: {
    baseURL: "http://127.0.0.1:8766/CaliSift/",
    headless: true,
    actionTimeout: 60000,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python ../scripts/serve-web.py",
    url: "http://127.0.0.1:8766/CaliSift/",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
  projects: [
    { name: "Chrome", use: { browserName: "chromium", channel: "chrome" } },
    { name: "Edge", use: { browserName: "chromium", channel: "msedge" } },
    { name: "Firefox", use: { browserName: "firefox" } },
  ],
});
