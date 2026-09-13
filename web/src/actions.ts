import { inject, ref } from "vue";
export function useActions() {
  const notify = inject<(message: string, error?: boolean) => void>(
    "notify",
    () => {},
  );
  const busy = ref(false);
  async function run<T>(operation: () => Promise<T>): Promise<T | undefined> {
    busy.value = true;
    try {
      return await operation();
    } catch (error: any) {
      notify(error.message || "操作失败，请重试", true);
    } finally {
      busy.value = false;
    }
  }
  return { run, busy, notify };
}
