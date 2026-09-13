import { commitSnapshot, readSnapshot, siteBase } from "./database";

class PythonWorker {
  worker?: Worker;
  sequence = 0;
  pending = new Map<
    number,
    {
      resolve: (v: any) => void;
      reject: (e: Error) => void;
      timer: ReturnType<typeof setTimeout>;
    }
  >();
  stop(message = "已取消识别，原文件和已完成结果保留，可继续重试。") {
    this.worker?.terminate();
    this.worker = undefined;
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.reject(new Error(message));
    }
    this.pending.clear();
  }
  async request(raw: any, mode = "command", timeout = 120000): Promise<any> {
    if (!this.worker) {
      this.worker = new Worker(new URL("runtime-worker.js", siteBase), {
        type: "module",
      });
      this.worker.onmessage = ({ data }) => {
        const item = this.pending.get(data.id);
        if (!item) return;
        clearTimeout(item.timer);
        this.pending.delete(data.id);
        if (data.error) {
          const lines = String(data.error).trim().split("\n");
          item.reject(
            new Error(
              lines.at(-1)?.replace(/^\w*(Error|Exception): /, "") ||
                data.error,
            ),
          );
        } else item.resolve(data.output);
      };
      this.worker.onerror = () =>
        this.stop("浏览器计算进程失败，未保存。请重试或检查本站运行资源。");
    }
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => this.stop("处理超时，未完成的结果未保存；可以裁剪图片后重试。"),
        timeout,
      );
      this.pending.set(id, { resolve, reject, timer });
      this.worker!.postMessage({ id, raw: JSON.stringify(raw), mode });
    });
  }
}
const commands = new PythonWorker();
const processor = new PythonWorker();
let chain: Promise<unknown> = Promise.resolve();
const active = new Map<string, { cancelled: boolean }>();
let processingJob = "";
let processChain: Promise<unknown> = Promise.resolve();
export function browserDownload(file: {
  filename: string;
  data: string;
  mime: string;
}) {
  const bytes = Uint8Array.from(atob(file.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: file.mime }));
  const a = document.createElement("a");
  try {
    a.href = url;
    a.download = file.filename.replace(/[\\/]/g, "_");
    a.hidden = true;
    document.body.append(a);
    a.click();
  } catch (e) {
    URL.revokeObjectURL(url);
    throw new Error("未能启动浏览器下载，请检查下载权限后重试。", { cause: e });
  } finally {
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
export function command(method: string, payload: any = {}): Promise<any> {
  const task = chain.then(async () => {
    const snapshot = await readSnapshot();
    const output = await commands.request({
      method,
      payload,
      state: snapshot.state,
    });
    if (output.value?.download) browserDownload(output.value.download);
    if (output.changed) await commitSnapshot(snapshot.revision, output.state);
    return output.value;
  });
  chain = task.catch(() => {});
  return task;
}
export async function startJob(payload: any) {
  if (!navigator.locks)
    throw new Error(
      "当前浏览器不支持任务锁，请使用受支持的 Chrome、Edge 或 Firefox。",
    );
  return new Promise<any>((resolve, reject) => {
    navigator.locks
      .request(
        "calisift-job:" + payload.job_id,
        { ifAvailable: true },
        async (lock) => {
          if (!lock)
            throw new Error(
              "另一个标签页正在识别此任务，请在该页面完成或取消。",
            );
          const result = await scheduleJob(payload);
          resolve(result.job);
          await result.finished;
        },
      )
      .catch(reject);
  });
}
async function scheduleJob(payload: any) {
  const job = await command("start_job", payload);
  const token = { cancelled: false };
  active.set(job.id, token);
  processChain = processChain
    .catch(() => {})
    .then(async () => {
      if (token.cancelled) {
        active.delete(job.id);
        return;
      }
      processingJob = job.id;
      for (const file of job.files.filter((f: any) => f.status === "queued")) {
        if (token.cancelled) break;
        try {
          const snapshot = await readSnapshot();
          const full = snapshot.state.documents["job:" + job.id].body;
          if (full.generation !== job.generation) break;
          const input = full.files.find((f: any) => f.id === file.id);
          const output = await processor.request(
            {
              kind: [".png", ".jpg", ".jpeg"].includes(file.suffix)
                ? "ocr"
                : "parse",
              data: input.data,
              filename: file.filename,
              name: snapshot.state.workspaces[job.workspace_id].name,
              year: job.year,
              rules: job.rules,
              layout_hint: job.rules?.template,
              options: { ...input.options, layout_hint: job.rules?.template },
            },
            "process",
            90000,
          );
          if (token.cancelled) break;
          await command("finish_file", {
            job_id: job.id,
            file_id: file.id,
            generation: job.generation,
            report: output.report,
          });
        } catch (e: any) {
          if (token.cancelled) break;
          try {
            await command("finish_file", {
              job_id: job.id,
              file_id: file.id,
              generation: job.generation,
              error: e.message,
            });
          } catch (failure: any) {
            window.dispatchEvent(
              new CustomEvent("calisift-error", { detail: failure.message }),
            );
            break;
          }
        }
      }
      active.delete(job.id);
      processingJob = "";
    });
  return { job, finished: processChain };
}
export async function cancelJob(job_id: string, discard = false) {
  const token = active.get(job_id);
  if (token) {
    token.cancelled = true;
    if (processingJob === job_id) processor.stop();
  }
  return command(discard ? "discard_job" : "cancel_job", { job_id });
}
export async function recoverJobs() {
  const snapshot = await readSnapshot();
  for (const d of Object.values(snapshot.state?.documents || {}) as any[]) {
    if (
      d.kind === "job" &&
      ["queued", "running"].includes(d.body.status) &&
      !active.has(d.body.id)
    ) {
      // A tab owns processing while holding this lock; refresh releases it.
      if (navigator.locks)
        await navigator.locks.request(
          "calisift-job:" + d.body.id,
          { ifAvailable: true },
          async (lock) => {
            if (lock) await command("cancel_job", { job_id: d.body.id });
          },
        );
    }
  }
}
