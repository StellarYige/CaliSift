// @vitest-environment jsdom
// All schedules and bridge responses here are synthetic; no native-client claim.
import { afterEach, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import DraftList from "../src/components/DraftList.vue";
import ImportPane from "../src/components/ImportPane.vue";
import ExportPane from "../src/components/ExportPane.vue";
import EventForm from "../src/components/EventForm.vue";
import ChangePreview from "../src/components/ChangePreview.vue";
import { call } from "../src/bridge";
import { defaultCategories, type DraftEvent } from "../src/types";

vi.mock("../src/bridge", () => ({ call: vi.fn() }));
const notify = vi.fn(),
  wrappers: any[] = [];
const workspace = {
  id: "one",
  name: "星辰奕歌",
  version: 1,
  sources: [],
  settings: { categories: defaultCategories },
};
function render(component: any, props: any) {
  const w = mount(component, {
    props,
    attachTo: document.body,
    global: { provide: { notify } },
  });
  wrappers.push(w);
  return w;
}
function entry(id: string, values: Partial<DraftEvent> = {}): DraftEvent {
  return {
    id,
    title: id,
    date: "2026-09-08",
    start: "08:00",
    end: "10:00",
    end_date: "2026-09-08",
    shift: "",
    precision: "interval",
    status: "confirmed",
    location: "一号站",
    warnings: [],
    notes: [],
    sources: [
      {
        file_id: "hash-second",
        filename: "排班.csv",
        sheet: "第二页",
        name_cell: "A3",
        evidence: { value: "AA63", date: "AA1" },
        excerpt: "星辰奕歌 | 夜班 22:00-次日06:00",
        hidden: false,
      },
    ],
    ...values,
  };
}
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = "";
  vi.resetAllMocks();
});

it("shows both original excerpts when a new import overlaps an already saved event", async () => {
  const events = [entry("原有值班"), entry("新增培训")];
  render(ChangePreview, {
    preview: {
      summary: {
        added: [events[1]],
        changed: [],
        cancelled: [],
        duplicates: 0,
        unresolved: [],
        warnings: [],
        schedule_conflicts: [
          {
            kind: "definite",
            message: "时间冲突",
            event_ids: events.map((e) => e.id),
          },
        ],
        schedule_conflict_events: Object.fromEntries(
          events.map((e) => [e.id, e]),
        ),
      },
    },
  });
  const section = document.querySelector(".preview-conflicts")!;
  expect(section.textContent).toContain("含已保存安排");
  expect(section.textContent).toContain("原有值班");
  expect(section.textContent).toContain("新增培训");
  expect(section.querySelectorAll("blockquote")).toHaveLength(2);
  expect(section.querySelector("summary")!.textContent).toBe(
    "查看双方原文摘录",
  );
});

it("surfaces confirmed conflicts and missing information while retaining edit and source identity", async () => {
  const entries = [
    entry("完整"),
    entry("缺少日期", { status: "pending", date: null }),
    entry("夜班", { date: "2026-09-07", start: "22:00", end: "06:00" }),
    entry("培训"),
    entry("单点", {
      end: null,
      end_date: null,
      precision: "point",
      warnings: ["年份按补全年份 2026 填入"],
    }),
  ];
  const w = render(DraftList, {
    entries,
    checked: [],
    conflicts: [
      { event_ids: ["夜班", "培训"], kind: "definite", message: "时间冲突" },
    ],
  });
  expect(w.find(".review-counts").text()).toContain("2 项涉及冲突");
  expect(w.findAll("h3")[0].text()).toBe("缺少日期");
  await w.find('select[aria-label="核对范围"]').setValue("conflicts");
  expect(w.findAll("h3").map((h) => h.text())).toEqual(["夜班", "培训"]);
  await w
    .findAll("button")
    .find((b) => b.text() === "修正")!
    .trigger("click");
  expect(w.emitted("edit")![0]).toEqual([2]);
  await w.find(".draft-conflict button").trigger("click");
  expect(w.emitted("evidence")![0][0]).toEqual(entries[3]);
  expect(w.text()).toContain("结束于 2026-09-08");
  await w.find("select").setValue("missing");
  expect(w.findAll("h3").map((h) => h.text())).toEqual(["缺少日期", "单点"]);
  expect(w.text()).toContain("可导出，不补写结束时长");
  expect(w.text()).toContain("年份按补全年份 2026 填入");
});

it("range selection preserves items outside the current filter and includes later pages", async () => {
  const entries = [
    entry("完整"),
    ...Array.from({ length: 55 }, (_, i) =>
      entry(String(i), { status: "pending" }),
    ),
  ];
  const w = render(DraftList, { entries, checked: [0] });
  await w.find("select").setValue("pending");
  await w.find(".draft-summary input").setValue(true);
  expect(w.emitted("update:checked")!.at(-1)![0]).toEqual(
    Array.from({ length: 56 }, (_, i) => i),
  );
  await w.setProps({ checked: [0, 1, 2] });
  await w.find(".draft-summary input").setValue(false);
  expect(w.emitted("update:checked")!.at(-1)).toEqual([[0]]);
  await w
    .findAll("button")
    .find((b) => b.text() === "下一页")!
    .trigger("click");
  expect(w.findAll(".event-row")).toHaveLength(5);
  await w.find("select").setValue("conflicts");
  await w.find("select").setValue("pending");
  expect(w.findAll(".event-row")).toHaveLength(50);
});

it("can retain a pending date without crashing and explains overnight corrections", async () => {
  const w = render(EventForm, {
    event: entry("日期待定", { date: null, status: "pending", end_date: null }),
  });
  await w.find("form").trigger("submit");
  expect(w.emitted("save")![0][0]).toMatchObject({
    date: null,
    end_date: null,
    status: "pending",
  });
  const times = w.findAll('input[type="time"]');
  await times[0].setValue("22:00");
  await times[1].setValue("06:00");
  expect(w.find('[role="alert"]').text()).toContain("次日结束");
  expect(w.find('button[type="submit"]').attributes("disabled")).toBeDefined();
  await w.find('input[type="date"]').setValue("2026-12-31");
  await w.findAll('input[type="checkbox"]')[0].setValue(true);
  await w.find("form").trigger("submit");
  expect(w.emitted("save")!.at(-1)![0]).toMatchObject({
    start: "22:00",
    end: "06:00",
    end_date: "2027-01-01",
  });
});

function mockImport() {
  const files = ["first", "second"].map((id) => ({
    id,
    filename: "排班.csv",
    suffix: ".csv",
    status: "done",
    source_file_ids: ["hash-" + id],
  }));
  const job = {
    id: "job",
    workspace_id: "one",
    status: "review",
    year: 2026,
    rules: {},
    files,
    report: {
      events: [entry("夜班")],
      pending: [],
      warnings: [],
      conflicts: [],
    },
  };
  const table = (p: any) => ({
    sheet: p.sheet === 1 ? "第二页" : "第一页",
    row: p.row || 0,
    col: p.col || 0,
    sheets: [
      { name: "第一页", height: 1, width: 1 },
      { name: "第二页", height: 70, width: 30 },
    ],
    cells: [
      [
        {
          row: p.row || 0,
          col: p.col || 0,
          coordinate: p.row === 50 ? "AA63" : "A1",
          text: p.file_id,
        },
      ],
    ],
  });
  vi.mocked(call).mockImplementation(async (method: string, p: any) => {
    if (method === "device_preferences") return { panel_ratio: 50 };
    if (method === "get_job") return job;
    if (method === "table") return table(p);
    return [];
  });
  return { job, table };
}

it("opens the correct same-named file and jumps to the schedule beyond the first page", async () => {
  mockImport();
  const w = render(ImportPane, { workspace, jobId: "job" });
  await flushPromises();
  await w
    .findAll("button")
    .find((b) => b.text() === "查看原文")!
    .trigger("click");
  await flushPromises();
  expect(call).toHaveBeenLastCalledWith("table", {
    job_id: "job",
    file_id: "second",
    row: 50,
    col: 20,
    sheet: 1,
  });
  expect(w.find(".evidence-context").text()).toContain("星辰奕歌 | 夜班");
  expect(w.find(".file-tabs .selected").text()).toContain("排班.csv");
  expect(w.find("td.highlight").attributes("data-coordinate")).toBe("AA63");
  expect(document.activeElement).toBe(w.find(".evidence-panel").element);
  await w
    .findAll(".evidence-links button")
    .find((b) => b.text() === "姓名 A3")!
    .trigger("click");
  await flushPromises();
  expect(call).toHaveBeenLastCalledWith("table", {
    job_id: "job",
    file_id: "second",
    row: 0,
    col: 0,
    sheet: 1,
  });
});

it("does not guess which same-named file supplied legacy evidence without content identity", async () => {
  const { job } = mockImport();
  job.files.forEach((f) => (f.source_file_ids = []));
  const w = render(ImportPane, { workspace, jobId: "job" });
  await flushPromises();
  vi.mocked(call).mockClear();
  await w
    .findAll("button")
    .find((b) => b.text() === "查看原文")!
    .trigger("click");
  await flushPromises();
  expect(call).not.toHaveBeenCalled();
  expect(w.find(".evidence-context").text()).toContain("星辰奕歌");
  expect(w.find(".source-table").exists()).toBe(false);
  expect(notify).toHaveBeenCalledWith(
    "无法唯一定位原文件，请先核对下方原文摘录",
    true,
  );
});

it("ignores a table page arriving after a file switch", async () => {
  const { table } = mockImport();
  const w = render(ImportPane, { workspace, jobId: "job" });
  await flushPromises();
  let resolve!: (v: any) => void;
  vi.mocked(call).mockImplementation(async (method: string, p: any) => {
    if (method === "table" && p.row === 50)
      return new Promise((r) => (resolve = r));
    if (method === "table") return table(p);
    return [];
  });
  // Simulate a slow page request; the subsequent file switch must win.
  w.findComponent({ name: "SourceTable" }).vm.$emit("page", 50, 0);
  await flushPromises();
  await w.findAll(".file-tabs button")[1].trigger("click");
  await flushPromises();
  resolve(table({ row: 50, file_id: "stale-first" }));
  await flushPromises();
  expect(w.find(".source-table").text()).toContain("second");
  expect(w.find(".source-table").text()).not.toContain("stale-first");
});

it.each([true, false])(
  "only reports source-page errors for the active request (switch file: %s)",
  async (switchFile) => {
    const { table } = mockImport();
    const w = render(ImportPane, { workspace, jobId: "job" });
    await flushPromises();
    let reject!: (reason: Error) => void;
    vi.mocked(call).mockImplementation(async (method: string, p: any) => {
      if (method === "table" && p.row === 50)
        return new Promise((_, r) => (reject = r));
      if (method === "table") return table(p);
      return [];
    });
    w.findComponent({ name: "SourceTable" }).vm.$emit("page", 50, 0);
    await flushPromises();
    if (switchFile) {
      await w.findAll(".file-tabs button")[1].trigger("click");
      await flushPromises();
    }
    reject(Error("原文件已清理"));
    await flushPromises();
    if (switchFile) expect(notify).not.toHaveBeenCalled();
    else expect(notify).toHaveBeenCalledWith("原文件已清理", true);
  },
);

it("keeps the snapshot warning beside save and rejects an obsolete export preview", async () => {
  let resolve!: (v: any) => void;
  vi.mocked(call).mockImplementation(async (method: string) =>
    method === "export_preview" ? new Promise((r) => (resolve = r)) : [],
  );
  const w = render(ExportPane, { workspace });
  await flushPromises();
  expect(w.find(".snapshot-notice").text()).toContain(
    "不保证重新导入后自动更新或删除旧事项",
  );
  expect(w.find(".export-help ol").text()).toContain("另一个空的专用日历");
  expect(w.text()).toContain("不代表外部日历已删除");
  await w
    .findAll("button")
    .find((b) => b.text() === "查看导出预览")!
    .trigger("click");
  await w
    .findAll("select")
    .find((s) => s.text().includes("提前 15 分钟"))!
    .setValue("30");
  resolve({ version: 1, count: 1, excluded: [], blocked: false });
  await flushPromises();
  expect(w.text()).not.toContain("本次可导出");
  await w
    .findAll("button")
    .find((b) => b.text() === "查看导出预览")!
    .trigger("click");
  resolve({ version: 1, count: 1, excluded: [], blocked: false });
  await flushPromises();
  expect(w.findAll(".snapshot-notice")).toHaveLength(2);
  expect(
    w
      .findAll("button")
      .find((b) => b.text() === "保存 ICS 文件")!
      .attributes("disabled"),
  ).toBeUndefined();
});
