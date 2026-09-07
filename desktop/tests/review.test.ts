// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import ChangePreview from "../src/components/ChangePreview.vue";
import EventForm from "../src/components/EventForm.vue";
import RulesPane from "../src/components/RulesPane.vue";
import ExportPane from "../src/components/ExportPane.vue";
import Modal from "../src/components/Modal.vue";
import { call } from "../src/bridge";

vi.mock("../src/bridge", () => ({ call: vi.fn() }));
const notify = vi.fn();
const wrappers: any[] = [];
const render = (component: any, props: any) => {
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: { provide: { notify } },
  });
  wrappers.push(wrapper);
  return wrapper;
};
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = "";
  vi.clearAllMocks();
});
const workspace = {
  id: "one",
  version: 1,
  name: "星辰奕歌",
  settings: {},
  sources: [],
};

describe("review and export decisions", () => {
  it("prevents confirmation until unmatched changes are resolved", async () => {
    const summary = {
      added: [],
      changed: [],
      cancelled: [],
      duplicates: 0,
      warnings: [],
      unresolved: [{ id: "old" }],
    };
    const wrapper = render(ChangePreview, { preview: { summary } });
    const confirm = () =>
      [...document.querySelectorAll("button")].find(
        (b) => b.textContent?.trim() === "确认保存",
      )!;
    expect(confirm().disabled).toBe(true);
    await wrapper.setProps({
      preview: { summary: { ...summary, unresolved: [] } },
    });
    expect(confirm().disabled).toBe(false);
    confirm().click();
    await nextTick();
    expect(wrapper.emitted("commit")).toHaveLength(1);
  });

  it("preserves a start-only event without inventing an end time", async () => {
    const wrapper = render(EventForm, {
      event: {
        date: "2026-09-08",
        title: "考试",
        start: "08:00",
        end: null,
        status: "confirmed",
        sources: [],
        notes: [],
      },
    });
    await wrapper.find("form").trigger("submit");
    const event = wrapper.emitted("save")![0][0] as any;
    expect(event.start).toBe("08:00");
    expect(event.end).toBeNull();
    expect(event.all_day).toBe(false);
  });

  it("loads a reusable template after changing away from source rules", async () => {
    vi.mocked(call).mockResolvedValue([
      {
        id: "template",
        name: "学校规则",
        description: "",
        rules: {
          shifts: [
            { name: "晚", aliases: ["晚"], start: "16:00", end: "23:00" },
          ],
        },
      },
    ]);
    const wrapper = render(RulesPane, {
      workspace: {
        ...workspace,
        sources: [{ id: "source", name: "单位", rules: {} }],
      },
      sourceId: "source",
    });
    await flushPromises();
    const load = wrapper
      .findAll("button")
      .find((b) => b.text() === "载入编辑")!;
    await load.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("16:00–23:00");
    expect(
      wrapper
        .findAll("input")
        .some((i) => (i.element as HTMLInputElement).value === "学校规则"),
    ).toBe(true);
    expect(notify).not.toHaveBeenCalled();
  });

  it("invalidates an export preview when the reminder changes", async () => {
    vi.mocked(call).mockImplementation(async (method: string) =>
      method === "export_preview"
        ? { version: 1, count: 1, excluded: [], blocked: false }
        : [],
    );
    const wrapper = render(ExportPane, { workspace });
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "查看导出预览")!
      .trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("本次可导出 1 项");
    await wrapper
      .findAll("select")
      .find((s) => s.text().includes("提前 15 分钟"))!
      .setValue("30");
    expect(wrapper.text()).not.toContain("本次可导出");
  });

  it("shows a failed save as an error and retains the review form", async () => {
    vi.mocked(call).mockImplementation(async (method: string) => {
      if (method === "export_preview") throw Error("日历已变化，请重新预览");
      return [];
    });
    const wrapper = render(ExportPane, { workspace });
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "查看导出预览")!
      .trigger("click");
    await flushPromises();
    expect(notify).toHaveBeenCalledWith("日历已变化，请重新预览", true);
    expect(wrapper.text()).not.toContain("本次可导出");
  });

  it("restores keyboard focus and closes the dialog with Escape", async () => {
    const opener = document.createElement("button");
    document.body.append(opener);
    opener.focus();
    const wrapper = render(Modal, { title: "核对" });
    await nextTick();
    expect(document.activeElement).not.toBe(opener);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    expect(wrapper.emitted("close")).toHaveLength(1);
    wrapper.unmount();
    expect(document.activeElement).toBe(opener);
  });
});
