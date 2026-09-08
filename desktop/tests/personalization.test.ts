// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, ref } from "vue";
import DraftList from "../src/components/DraftList.vue";
import EventsPane from "../src/components/EventsPane.vue";
import EventForm from "../src/components/EventForm.vue";
import PreferencesPane from "../src/components/PreferencesPane.vue";
import { call, request } from "../src/bridge";
import { defaultCategories } from "../src/types";
import { useJobPolling } from "../src/useJobPolling";
vi.mock("../src/bridge", () => ({ call: vi.fn(), request: vi.fn() }));
const wrappers: any[] = [];
const notify = vi.fn();
function render(component: any, props: any = {}) {
  const w = mount(component, {
    props,
    attachTo: document.body,
    global: { provide: { notify } },
  });
  wrappers.push(w);
  return w;
}
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = "";
  vi.clearAllMocks();
  vi.useRealTimers();
});
const workspace = {
  id: "one",
  version: 4,
  settings: { categories: defaultCategories },
  sources: [],
};

it("keeps original draft indices when pending results are sorted and filtered", async () => {
  const w = render(DraftList, {
    entries: [
      { title: "已确认", status: "confirmed", warnings: [] },
      { title: "需核对", status: "pending", warnings: [] },
    ],
    checked: [],
  });
  expect(w.findAll("h3")[0].text()).toBe("需核对");
  await w.findAll(".event-row button")[0].trigger("click");
  expect(w.emitted("edit")![0]).toEqual([1]);
  await w.findAll(".draft-summary input")[1].setValue(true);
  await w.findAll(".draft-summary input")[0].setValue(true);
  expect(w.emitted("update:checked")!.at(-1)).toEqual([[1]]);
});

it.each([true, false])(
  "direct save retains the form on failure (%s)",
  async (fails) => {
    vi.mocked(call).mockImplementation(async (method: string) => {
      if (method === "events") return { items: [], total: 0, page: 0 };
      if (method === "preview_change")
        return { preview_id: "candidate", base_version: 4 };
      if (method === "commit_change") {
        if (fails) throw Error("保存失败");
        return {};
      }
    });
    const w = render(EventsPane, { workspace });
    await flushPromises();
    await w
      .findAll("button")
      .find((b) => b.text().includes("手动新增"))!
      .trigger("click");
    const values = {
      date: "2026-09-08",
      title: "培训",
      start: "08:00",
      end: null,
    };
    w.findComponent(EventForm).vm.$emit("save", values);
    await flushPromises();
    expect(call).toHaveBeenCalledWith("commit_change", {
      preview_id: "candidate",
      expected_version: 4,
    });
    expect(w.findComponent(EventForm).exists()).toBe(fails);
    expect(document.body.textContent).not.toContain("确认保存");
    if (fails) expect(notify).toHaveBeenCalledWith("保存失败", true);
  },
);

it("keeps a stale preferences edit for review and sends its own revision", async () => {
  const prefs = {
    theme: "light",
    font_size: 14,
    density: "comfortable",
    week_start: 1,
    scenario: "general",
    hide_rest: false,
    categories: defaultCategories,
  };
  vi.mocked(request).mockImplementation(async (method: string) => {
    if (method === "save_preferences") throw Error("偏好已变化");
    return { revision: 7, values: prefs } as any;
  });
  const w = render(PreferencesPane, { workspaceId: "one" });
  await flushPromises();
  await w.findAll("select")[0].setValue("dark");
  await w
    .findAll("button")
    .find((b) => b.text() === "保存偏好")!
    .trigger("click");
  await flushPromises();
  expect(request).toHaveBeenCalledWith(
    "save_preferences",
    expect.objectContaining({
      expected_revision: 7,
      values: expect.objectContaining({ theme: "dark" }),
    }),
  );
  expect((w.findAll("select")[0].element as HTMLSelectElement).value).toBe(
    "dark",
  );
  expect(notify).toHaveBeenCalledWith("偏好已变化", true);
});

it("ignores a previous job response arriving after the user switched jobs", async () => {
  vi.useFakeTimers();
  let resolve!: (v: any) => void;
  vi.mocked(call).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const job = ref<any>({ id: "old", status: "running" }),
    completed = vi.fn();
  render(
    defineComponent({
      setup() {
        useJobPolling(job, completed, notify);
        return () => null;
      },
    }),
  );
  await vi.advanceTimersByTimeAsync(900);
  job.value = { id: "new", status: "review" };
  resolve({ id: "old", status: "review" });
  await flushPromises();
  expect(job.value.id).toBe("new");
  expect(completed).not.toHaveBeenCalled();
});
