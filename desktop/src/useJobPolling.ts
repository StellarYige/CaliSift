import { onUnmounted, type Ref } from "vue";
import { call } from "./bridge";
export function useJobPolling(
  job: Ref<any>,
  completed: () => Promise<void>,
  notify: (message: string, error: boolean) => void,
) {
  let polling = false,
    closed = false;
  const timer = setInterval(async () => {
    if (closed || polling || !["queued", "running"].includes(job.value?.status))
      return;
    polling = true;
    const id = job.value.id;
    try {
      const next = await call("get_job", { job_id: id });
      if (closed || job.value?.id !== id) return;
      job.value = next;
      if (!["queued", "running"].includes(next.status)) await completed();
    } catch (error) {
      if (!closed) notify((error as Error).message, true);
    } finally {
      polling = false;
    }
  }, 900);
  onUnmounted(() => {
    closed = true;
    clearInterval(timer);
  });
}
