declare global {
  interface Window {
    pywebview?: {
      api: { call(method: string, payload: unknown): Promise<any> };
    };
    calisiftWorkspace?: string;
  }
}
export async function call<T = any>(
  method: string,
  payload: unknown = {},
): Promise<T> {
  if (!window.pywebview)
    throw new Error(
      "请从 CaliSift 桌面程序打开；浏览器开发预览尚未连接本机服务。",
    );
  const result = await window.pywebview.api.call(method, payload);
  if (!result.ok)
    throw Object.assign(new Error(result.error.message), {
      code: result.error.code,
    });
  return result.value as T;
}
export function whenReady(callback: () => void) {
  if (window.pywebview) callback();
  else window.addEventListener("pywebviewready", callback, { once: true });
}
