import type { WebRequests } from "./types";
import { command, startJob, cancelJob, recoverJobs } from "./runtime";
import { siteBase } from "./database";
declare global {
  interface Window {
    calisiftWorkspace?: string;
  }
}
export async function request<M extends keyof WebRequests>(
  method: M,
  payload: WebRequests[M][0],
): Promise<WebRequests[M][1]> {
  return call<WebRequests[M][1]>(method, payload);
}
export async function call<T = any>(
  method: string,
  payload: any = {},
): Promise<T> {
  if (method === "select_files")
    return (await stageFiles(
      await selectFiles(".xlsx,.xls,.csv,.png,.jpg,.jpeg", true),
      payload.workspace_id,
    )) as T;
  if (method === "paste_image") {
    if (!navigator.clipboard?.read)
      throw new Error("请复制截图后在页面按 Ctrl+V 粘贴，或使用选择文件。");
    try {
      const items = await navigator.clipboard.read();
      const files: File[] = [];
      for (const item of items)
        for (const type of item.types.filter((t) =>
          ["image/png", "image/jpeg"].includes(t),
        ))
          files.push(
            new File(
              [await item.getType(type)],
              "剪贴板截图." + (type === "image/png" ? "png" : "jpg"),
              { type },
            ),
          );
      if (!files.length) throw new Error("empty");
      return (await stageFiles(files, payload.workspace_id)) as T;
    } catch {
      throw new Error(
        "未能读取剪贴板图片。请在页面按 Ctrl+V 粘贴，或选择图片文件。",
      );
    }
  }
  if (method === "sample") {
    const response = await fetch(new URL("samples/index.json", siteBase));
    if (!response.ok) throw new Error("示例资源缺失");
    const names: string[] = await response.json();
    const files = await Promise.all(
      names.slice(0, 2).map(async (filename) => {
        const r = await fetch(new URL("samples/" + filename, siteBase));
        if (!r.ok) throw new Error("示例文件缺失");
        return new File([await r.blob()], filename);
      }),
    );
    return (await stageFiles(files, payload.workspace_id)) as T;
  }
  if (method === "start_job") return startJob(payload);
  if (method === "cancel_job" || method === "discard_job")
    return cancelJob(payload.job_id, method === "discard_job");
  if (method === "prepare_restore" || method === "import_template") {
    const [file] = await selectFiles(
      method === "prepare_restore" ? ".zip,.json" : ".json",
    );
    if (!file) return null as T;
    const limit = method === "prepare_restore" ? 300 * 1024 * 1024 : 256 * 1024;
    if (file.size > limit) throw new Error("所选文件超过允许大小");
    return command(method, {
      data:
        method === "prepare_restore"
          ? await fileBase64(file)
          : (await file.text()).replace(/^\uFEFF/, ""),
    });
  }
  if (method === "copy_diagnostics") {
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          version: "0.4.0-alpha.1",
          runtime: "Pyodide 314.0.6 / ORT Web 1.23.2",
          browser: navigator.userAgent,
          secureContext: isSecureContext,
        },
        null,
        2,
      ),
    );
    return true as T;
  }
  return command(method, payload);
}
export function whenReady(callback: () => void) {
  callback();
  recoverJobs().catch((e) =>
    window.dispatchEvent(
      new CustomEvent("calisift-error", { detail: e.message }),
    ),
  );
}
export function selectFiles(accept: string, multiple = false): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.multiple = multiple;
    input.hidden = true;
    const finish = (files: File[]) => {
      input.remove();
      resolve(files);
    };
    input.onchange = () => finish(Array.from(input.files || []));
    input.oncancel = () => finish([]);
    document.body.append(input);
    input.click();
  });
}
export async function fileBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(new Error("未能读取文件"));
    r.onload = () => resolve(String(r.result).split(",")[1]!);
    r.readAsDataURL(file);
  });
}
export async function stageFiles(files: File[], workspace_id: string) {
  if (!files.length) return null;
  if (
    files.length > 10 ||
    files.some((f) => f.size > 10 * 1024 * 1024) ||
    files.reduce((n, f) => n + f.size, 0) > 30 * 1024 * 1024
  )
    throw new Error("每批最多 10 个文件、30 MiB，单文件最多 10 MiB");
  return command("stage_files", {
    workspace_id,
    files: await Promise.all(
      files.map(async (f) => ({ filename: f.name, data: await fileBase64(f) })),
    ),
  });
}
async function acceptDropped(files: File[]) {
  try {
    if (!window.calisiftWorkspace) throw new Error("请先建立个人工作区");
    const job = await stageFiles(files, window.calisiftWorkspace);
    window.dispatchEvent(new CustomEvent("calisift-drop", { detail: { job } }));
  } catch (e: any) {
    window.dispatchEvent(
      new CustomEvent("calisift-error", { detail: e.message }),
    );
  }
}
window.addEventListener("dragover", (e) => {
  if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
});
window.addEventListener("drop", (e) => {
  if (e.dataTransfer?.files.length) {
    e.preventDefault();
    void acceptDropped(Array.from(e.dataTransfer.files));
  }
});
window.addEventListener("paste", (e) => {
  const files = Array.from(e.clipboardData?.files || []).filter((f) =>
    f.type.startsWith("image/"),
  );
  if (files.length) {
    e.preventDefault();
    void acceptDropped(files);
  }
});
