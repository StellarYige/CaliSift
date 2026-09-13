// Exercise the deployed bytes with synthetic inputs in a fresh browser profile.
import {
  chromium,
  expect,
} from "../web/node_modules/@playwright/test/index.mjs";
import fs from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const url = process.argv[2] || "https://stellaryige.github.io/CaliSift/";
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(180000);
const requests = [];
const errors = [];
context.on("request", (request) =>
  requests.push({ url: request.url(), method: request.method() }),
);
page.on("pageerror", (error) => errors.push(error.message));
const record = {
  url,
  browser: browser.version(),
  timestamp: new Date().toISOString(),
};
async function identifyAndSave() {
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  const preview = page.getByRole("button", {
    name: "预览并加入日历",
    exact: true,
  });
  await expect(preview).toBeEnabled({ timeout: 180000 });
  await preview.click();
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "继续导出日历" }),
  ).toBeVisible();
}
try {
  await page.goto(url);
  await page.getByRole("button", { name: "先用示例体验" }).click();
  await identifyAndSave();
  record.spreadsheets = true;
  console.log("Published spreadsheet parsing and calendar save passed.");
  await page.getByRole("button", { name: /设置$/ }).click();
  await page.getByRole("button", { name: "准备 / 修复离线资源" }).click();
  await expect(page.getByText("离线就绪", { exact: true })).toBeVisible({
    timeout: 300000,
  });
  record.offlinePrepared = true;
  console.log("Published offline resources verified.");
  await context.setOffline(true);
  await page.reload();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "选择文件", exact: true }).click();
  await (
    await chooser
  ).setFiles(path.join(root, "tests/fixtures/ocr/clean.png"));
  await identifyAndSave();
  record.offlineOCR = true;
  await page.getByRole("button", { name: "继续导出日历" }).click();
  await page
    .getByRole("combobox", { name: "来源", exact: true })
    .selectOption({ label: "clean" });
  await page.getByRole("button", { name: "查看导出预览" }).click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "保存 ICS 文件", exact: true })
    .click();
  const file = await download;
  const ics = await fs.readFile(await file.path(), "utf8");
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain("消防培训");
  expect(ics).toContain("DTSTART;TZID=Asia/Shanghai:20260907T080000");
  record.offlineICS = true;
  expect(
    requests.every(
      (r) =>
        r.method === "GET" && new URL(r.url).origin === new URL(url).origin,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  record.sameOriginGetOnly = true;
  await page.screenshot({
    path: path.join(root, "artifacts/web-production.png"),
    fullPage: true,
  });
  console.log("Published offline OCR, ICS and request inspection passed.");
} finally {
  await fs.mkdir(path.join(root, "artifacts"), { recursive: true });
  await fs.writeFile(
    path.join(root, "artifacts/web-production.json"),
    JSON.stringify({ ...record, requests, errors }, null, 2),
  );
  await browser.close();
}
