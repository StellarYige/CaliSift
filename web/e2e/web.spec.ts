import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root = path.resolve(import.meta.dirname, "../..");
const name = "星辰奕歌";
async function rpc(page: Page, raw: any, mode = "command"): Promise<any> {
  return page.evaluate(
    async ({ raw, mode }) => {
      const win = window as any;
      if (!win.probe) {
        win.probe = new Worker(new URL("runtime-worker.js", location.href), {
          type: "module",
        });
        win.probeId = 0;
      }
      const id = ++win.probeId;
      return new Promise((resolve, reject) => {
        const listener = ({ data }: MessageEvent) => {
          if (data.id !== id) return;
          win.probe.removeEventListener("message", listener);
          if (data.error) reject(new Error(data.error));
          else resolve(data.output);
        };
        win.probe.addEventListener("message", listener);
        win.probe.postMessage({ id, mode, raw: JSON.stringify(raw) });
      });
    },
    { raw, mode },
  );
}
async function choose(page: Page, file: string) {
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "选择文件", exact: true }).click();
  await (await chooser).setFiles(path.join(root, file));
  await expect(
    page.getByRole("button", { name: "开始识别", exact: true }),
  ).toBeVisible();
}
async function identify(page: Page) {
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "预览并加入日历", exact: true }),
  ).toBeEnabled();
}
async function save(page: Page) {
  await page
    .getByRole("button", { name: "预览并加入日历", exact: true })
    .click();
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "继续导出日历" }),
  ).toBeVisible();
}
async function snapshot(page: Page): Promise<any> {
  return page.evaluate(
    () =>
      new Promise((resolve, reject) => {
        const r = indexedDB.open("calisift:/CaliSift/", 1);
        r.onerror = () => reject(r.error);
        r.onsuccess = () => {
          const db = r.result;
          const tx = db.transaction("state");
          const q = tx.objectStore("state").get("root");
          tx.oncomplete = () => {
            db.close();
            resolve(q.result);
          };
        };
      }),
  );
}
test("15 existing synthetic spreadsheets match native domain results in a real browser", async ({
  page,
  browser,
}, info) => {
  await page.goto("./");
  const cases = JSON.parse(
    await fs.readFile(
      path.join(root, "tests/fixtures/browser-expected.json"),
      "utf8",
    ),
  );
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  for (const item of cases) {
    const data = (await fs.readFile(path.join(root, item.file))).toString(
      "base64",
    );
    const result = await rpc(
      page,
      {
        kind: "parse",
        filename: path.basename(item.file),
        data,
        name,
        year: 2026,
      },
      "process",
    );
    expect(result.report, item.file).toEqual(item.report);
  }
  expect(
    requests.every((u) => new URL(u).origin === "http://127.0.0.1:8766"),
  ).toBe(true);
  await info.attach("runtime", {
    body: JSON.stringify({
      browser: browser.version(),
      files: cases.length,
      pyodide: "314.0.6",
      pydantic: "2.12.5",
      requests,
    }),
    contentType: "application/json",
  });
});
test("six real WASM OCR regressions retain matching, layout, confidence and evidence", async ({
  page,
  browser,
}, info) => {
  await page.goto("./");
  const manifest = JSON.parse(
    await fs.readFile(
      path.join(root, "tests/fixtures/ocr/regression-manifest.json"),
      "utf8",
    ),
  );
  const results = [];
  for (const c of manifest.cases) {
    const data = (
      await fs.readFile(path.join(root, "tests/fixtures/ocr", c.file))
    ).toString("base64");
    const start = Date.now();
    const { report } = await rpc(
      page,
      {
        kind: "ocr",
        filename: c.file,
        data,
        name,
        year: 2026,
        options: {},
        rules: {},
      },
      "process",
    );
    const events = [...report.events, ...report.pending];
    expect(events, c.file).toHaveLength(1);
    for (const field of [
      "date",
      "title",
      "start",
      "end",
      "end_date",
      "location",
    ])
      expect(events[0][field], c.file + ":" + field).toEqual(
        c.expected[0][field],
      );
    expect(events[0].sources[0].name_cell).toEqual(c.identity_cells[0].cell);
    expect(
      events[0].sources.every((s: any) => !s.excerpt.includes(name + "甲")),
    ).toBe(true);
    expect(Object.keys(report.files[0].ocr.crops).length).toBeGreaterThan(0);
    results.push({
      file: c.file,
      seconds: (Date.now() - start) / 1000,
      status: events[0].status,
    });
    if (c.id === "clean") {
      const block = report.files[0].ocr.blocks.find(
        (b: any) => b.text === name,
      );
      const fixed = await rpc(
        page,
        {
          kind: "ocr",
          filename: c.file,
          data,
          name: name + "乙",
          year: 2026,
          options: { corrections: { [block.id]: name + "乙" } },
        },
        "process",
      );
      const edited = fixed.report.files[0].ocr.blocks.find(
        (b: any) => b.id === block.id,
      );
      expect(edited.original_text).toBe(name);
      expect(edited.corrected).toBe(true);
      expect([...fixed.report.events, ...fixed.report.pending]).toHaveLength(1);
    }
  }
  await info.attach("real-ocr", {
    body: JSON.stringify({
      browser: browser.version(),
      results,
      provenance: "synthetic",
      independentReview: false,
    }),
    contentType: "application/json",
  });
});
test("source review, browser persistence, backup, ICS downloads and full offline table/image flow", async ({
  page,
  context,
  browser,
}, info) => {
  const requests: { url: string; method: string }[] = [];
  context.on("request", (r) =>
    requests.push({ url: r.url(), method: r.method() }),
  );
  await page.goto("./");
  await page.getByRole("button", { name: "先用示例体验" }).click();
  await expect(
    page.getByRole("button", { name: "开始识别", exact: true }),
  ).toBeVisible();
  await identify(page);
  await expect(page.locator("body")).toContainText("次日08:00");
  await page.screenshot({
    path: path.join(root, `artifacts/web-${info.project.name}-review.png`),
    fullPage: true,
  });
  const before = await snapshot(page);
  const jobId = Object.values(before.state.documents).find(
    (v: any) => v.kind === "job",
  ) as any;
  expect(jobId.body.report.events.length).toBeGreaterThan(0);
  await page.reload();
  await page
    .getByRole("button", { name: /九月排班.csv、培训通知.csv/ })
    .click();
  await expect(
    page.getByRole("button", { name: "预览并加入日历" }),
  ).toBeEnabled();
  await save(page);
  const state = await snapshot(page);
  const job: any = state.state.documents["job:" + jobId.body.id].body;
  expect(job.files.every((f: any) => !f.data && !f.report)).toBe(true);
  await page.getByRole("button", { name: "继续导出日历" }).click();
  await page.getByRole("button", { name: "查看导出预览" }).click();
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "保存 ICS 文件", exact: true })
    .click();
  const file = await downloaded;
  const filePath = await file.path();
  const ics = await fs.readFile(filePath!, "utf8");
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain("DTEND;TZID=Asia/Shanghai:20260911T080000");
  expect(ics).toContain("TRIGGER:-PT15M");
  expect(ics).not.toContain("示例同事");
  await page.getByRole("button", { name: /设置$/ }).click();
  const backupDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "备份当前工作区" }).click();
  const backup = await backupDownload;
  expect(await backup.failure()).toBeNull();
  await page.getByRole("button", { name: "准备 / 修复离线资源" }).click();
  await expect(page.getByText("离线就绪", { exact: true })).toBeVisible();
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "选择文件", exact: true }),
  ).toBeVisible();
  await choose(page, "tests/fixtures/纵向排班.xls");
  await identify(page);
  await save(page);
  await choose(page, "tests/fixtures/ocr/clean.png");
  await identify(page);
  await expect(page.locator("body")).toContainText("消防培训");
  await save(page);
  await page.getByRole("button", { name: "继续导出日历" }).click();
  await page
    .getByRole("combobox", { name: "来源", exact: true })
    .selectOption({ label: "clean" });
  await page.getByRole("button", { name: "查看导出预览" }).click();
  const offlineDownload = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "保存 ICS 文件", exact: true })
    .click();
  expect(await (await offlineDownload).failure()).toBeNull();
  await context.setOffline(false);
  // Edge also exposes its own edge://downloads-hub UI to context events.
  // It is local browser chrome, not a network request made by the website.
  const network = requests.filter((r) => /^https?:/.test(r.url));
  expect(
    network.filter(
      (r) =>
        r.method !== "GET" || new URL(r.url).origin !== "http://127.0.0.1:8766",
    ),
    "Every observed HTTP(S) request must read a same-origin static asset",
  ).toEqual([]);
  await info.attach("offline-and-network", {
    body: JSON.stringify({
      browser: browser.version(),
      offlineTable: true,
      offlineOCR: true,
      offlineICS: true,
      requests,
    }),
    contentType: "application/json",
  });
});
test("two tabs cannot commit stale previews and separate browser profiles isolate data", async ({
  page,
  context,
  browser,
}) => {
  await page.goto("./");
  await page.getByRole("button", { name: "先用示例体验" }).click();
  await identify(page);
  const second = await context.newPage();
  await second.goto("./");
  await second
    .getByRole("button", { name: /九月排班.csv、培训通知.csv/ })
    .click();
  await page.getByRole("button", { name: "预览并加入日历" }).click();
  await second.getByRole("button", { name: "预览并加入日历" }).click();
  await expect(
    second.getByRole("button", { name: "确认保存", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "继续导出日历" }),
  ).toBeVisible();
  await second.getByRole("button", { name: "确认保存", exact: true }).click();
  await expect(second.getByRole("alert")).toContainText("日历已变化");
  const value = await snapshot(page);
  const calendars = Object.values(value.state.workspaces) as any[];
  expect(calendars[0].calendar.events).toHaveLength(4);
  expect(calendars[0].version).toBe(1);
  const separate = await browser.newContext();
  const isolated = await separate.newPage();
  await isolated.goto("http://127.0.0.1:8766/CaliSift/");
  await expect(
    isolated.getByRole("button", { name: "建立个人工作区 →" }),
  ).toBeVisible();
  expect(Object.keys((await snapshot(isolated)).state.workspaces)).toHaveLength(
    0,
  );
  await separate.close();
  const atRoot = await context.newPage();
  await atRoot.goto("http://127.0.0.1:8766/");
  await expect(
    atRoot.getByRole("button", { name: "建立个人工作区 →" }),
  ).toBeVisible();
});
test("storage failure is not success; old Windows ZIP and v1 JSON restore; download failure is visible", async ({
  page,
}) => {
  await page.goto("./");
  await expect(
    page.getByRole("button", { name: "先用示例体验" }),
  ).toBeVisible();
  await page.evaluate(() => {
    (window as any).originalPut = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function () {
      throw new DOMException("test", "QuotaExceededError");
    };
  });
  await page.getByLabel("你的完整姓名").fill(name);
  await page.getByRole("button", { name: "建立个人工作区 →" }).click();
  await expect(page.getByRole("alert")).toContainText("未保存");
  expect(Object.keys((await snapshot(page)).state.workspaces)).toHaveLength(0);
  await page.evaluate(() => {
    IDBObjectStore.prototype.put = (window as any).originalPut;
  });
  await page.getByRole("button", { name: "建立个人工作区 →" }).click();
  await page.getByRole("button", { name: /设置$/ }).click();
  let chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "恢复 / 迁移备份" }).click();
  await (
    await chooser
  ).setFiles(path.join(root, "tests/fixtures/portable/windows-v2.zip"));
  await page.getByRole("button", { name: "确认恢复", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "确认恢复", exact: true }),
  ).not.toBeVisible();
  await expect(page.getByRole("alert")).toContainText("备份已恢复");
  let saved = await snapshot(page);
  const values = Object.values(saved.state.workspaces) as any[];
  expect(values.some((w) => w.calendar.events.length === 1)).toBe(true);
  // Restore a historical v1 JSON containing an event's original report.
  const legacy = {
    version: 1,
    personName: name,
    report: JSON.parse(
      await fs.readFile(
        path.join(root, "tests/fixtures/browser-expected.json"),
        "utf8",
      ),
    )[0].report,
    savedAt: "2026-09-13T00:00:00Z",
  };
  await page.getByRole("button", { name: /设置$/ }).click();
  chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "恢复 / 迁移备份" }).click();
  await (
    await chooser
  ).setFiles({
    name: "legacy-v1.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(legacy)),
  });
  await page.getByRole("button", { name: "确认恢复", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "确认恢复", exact: true }),
  ).not.toBeVisible();
  await expect(page.getByRole("alert")).toContainText("备份已恢复");
  saved = await snapshot(page);
  expect(Object.keys(saved.state.workspaces)).toHaveLength(3);
  await page.getByRole("button", { name: /安排$/ }).click();
  await page.getByRole("button", { name: /导出/ }).first().click();
  await page.getByRole("button", { name: "查看导出预览" }).click();
  await page.evaluate(() => {
    URL.createObjectURL = () => {
      throw new Error("下载无法启动");
    };
  });
  await page
    .getByRole("button", { name: "保存 ICS 文件", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("下载无法启动");
  const after = await snapshot(page);
  expect(
    Object.values(after.state.documents).filter((d: any) => d.kind === "export")
      .length,
  ).toBe(
    Object.values(saved.state.documents).filter((d: any) => d.kind === "export")
      .length,
  );
});
test("cancel, refresh and retry retain drafts; cache corruption and version upgrade preserve saved data", async ({
  page,
  context,
}, info) => {
  await page.goto("./");
  await page.getByLabel("你的完整姓名").fill(name);
  await page.getByRole("button", { name: "建立个人工作区 →" }).click();
  await choose(page, "tests/fixtures/ocr/clean.png");
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await page.getByRole("button", { name: "取消识别", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "开始识别", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await page.getByRole("button", { name: /clean.png.*已取消/ }).click();
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await page.reload();
  await expect
    .poll(async () => {
      const state = await snapshot(page);
      return (
        Object.values(state.state.documents).find(
          (d: any) => d.kind === "job",
        ) as any
      )?.body.status;
    })
    .toBe("cancelled");
  await page.getByRole("button", { name: /clean.png/ }).click();
  await page.getByRole("button", { name: "开始识别", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "预览并加入日历" }),
  ).toBeEnabled();
  await save(page);
  await page.getByRole("button", { name: /设置$/ }).click();
  await page.getByRole("button", { name: "准备 / 修复离线资源" }).click();
  await expect(page.getByText("离线就绪", { exact: true })).toBeVisible();
  const before = await snapshot(page);
  await page.evaluate(async () => {
    const key = (await caches.keys()).find((k) =>
      k.startsWith("calisift:/CaliSift/"),
    )!;
    const cache = await caches.open(key);
    await cache.put(
      new URL("models/ch_PP-OCRv5_mobile_det.onnx", location.href).href,
      new Response("corrupt"),
    );
  });
  await context.setOffline(true);
  await page.getByRole("button", { name: "重新校验", exact: true }).click();
  await expect(page.getByRole("status")).toContainText(
    "资源未完整缓存或校验失败",
  );
  expect((await snapshot(page)).state.workspaces).toEqual(
    before.state.workspaces,
  );
  await context.setOffline(false);
  await page.getByRole("button", { name: "准备 / 修复离线资源" }).click();
  await expect(page.getByText("离线就绪", { exact: true })).toBeVisible();
  const next = path.join(root, "web/dist/sw-next.js");
  await fs.writeFile(
    next,
    (await fs.readFile(path.join(root, "web/dist/sw.js"), "utf8")).replace(
      /"build":"[^"]+"/,
      '"build":"upgrade-test"',
    ),
  );
  try {
    await page.evaluate(async () => {
      const r = await navigator.serviceWorker.register(
        new URL("sw-next.js", location.href),
        { scope: "/CaliSift/" },
      );
      if (!r.waiting)
        await new Promise<void>((resolve) => {
          const worker = r.installing;
          worker?.addEventListener("statechange", () => {
            if (worker.state === "installed") resolve();
          });
        });
    });
    expect(
      await page.evaluate(() => navigator.serviceWorker.controller!.scriptURL),
    ).toContain("/sw.js");
    expect((await snapshot(page)).state.workspaces).toEqual(
      before.state.workspaces,
    );
    await page.close();
    const reopened = await context.newPage();
    await reopened.goto("./");
    await expect(
      reopened.getByRole("button", { name: "选择文件", exact: true }),
    ).toBeVisible();
    await expect
      .poll(() =>
        reopened.evaluate(
          () => navigator.serviceWorker.controller?.scriptURL || "",
        ),
      )
      .toContain("/sw-next.js");
    expect((await snapshot(reopened)).state.workspaces).toEqual(
      before.state.workspaces,
    );
    await info.attach("upgrade", {
      body: JSON.stringify({ waitingDidNotReload: true, dataPreserved: true }),
      contentType: "application/json",
    });
  } finally {
    await fs.unlink(next);
  }
});
test("browser drop and image paste create local import jobs", async ({
  page,
}) => {
  await page.goto("./");
  await page.getByLabel("你的完整姓名").fill(name);
  await page.getByRole("button", { name: "建立个人工作区 →" }).click();
  await expect(
    page.getByRole("button", { name: "选择文件", exact: true }),
  ).toBeVisible();
  for (const [file, event] of [
    ["samples/九月排班.csv", "drop"],
    ["tests/fixtures/ocr/clean.png", "paste"],
  ]) {
    const data = (await fs.readFile(path.join(root, file!))).toString("base64");
    await page.evaluate(
      ({ data, event }) => {
        const transfer = new DataTransfer();
        const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
        transfer.items.add(
          new File([bytes], event === "paste" ? "粘贴截图.png" : "拖入.csv", {
            type: event === "paste" ? "image/png" : "text/csv",
          }),
        );
        const inputEvent =
          event === "paste"
            ? new ClipboardEvent("paste", { clipboardData: transfer })
            : new DragEvent("drop", { dataTransfer: transfer });
        // Firefox strips files from a constructed ClipboardEvent. Supply the
        // synthetic event payload explicitly; file reading/OCR/storage stay real.
        if (
          event === "paste" &&
          !(inputEvent as ClipboardEvent).clipboardData?.files.length
        )
          Object.defineProperty(inputEvent, "clipboardData", {
            value: transfer,
          });
        window.dispatchEvent(inputEvent);
      },
      { data, event: event! },
    );
    await identify(page);
    await save(page);
  }
  const saved = await snapshot(page);
  const workspace = Object.values(saved.state.workspaces)[0] as any;
  expect(workspace.calendar.events).toHaveLength(3);
});
