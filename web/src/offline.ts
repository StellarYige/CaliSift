import { reactive } from "vue";
import { siteBase } from "./database";
export const offline = reactive({
  ready: false,
  busy: false,
  total: 0,
  loaded: 0,
  message: "尚未准备离线使用",
  update: false,
});
let registration: ServiceWorkerRegistration | undefined;
export async function registerOffline() {
  if (!isSecureContext || !("serviceWorker" in navigator)) {
    offline.message = "完整离线使用需要 HTTPS 或 localhost";
    return;
  }
  try {
    const r = (registration = await navigator.serviceWorker.register(
      new URL("sw.js", siteBase),
      { scope: siteBase.pathname, updateViaCache: "none" },
    ));
    const update = () => {
      offline.update = !!r.waiting;
    };
    update();
    r.addEventListener("updatefound", () =>
      r.installing?.addEventListener("statechange", update),
    );
    const manifest = await (
      await fetch(new URL("offline-manifest.json", siteBase))
    ).json();
    offline.total = manifest.total;
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller)
      await new Promise<void>((resolve) =>
        navigator.serviceWorker.addEventListener(
          "controllerchange",
          () => resolve(),
          { once: true },
        ),
      );
    await offlineTask("CHECK");
  } catch (e: any) {
    offline.message = "离线资源检查失败：" + e.message;
    offline.ready = false;
  }
}
export async function offlineTask(type = "PREPARE") {
  if (offline.busy) return;
  if (!navigator.serviceWorker?.controller) {
    offline.message = "离线服务尚未启动，请重新打开页面后重试";
    return;
  }
  offline.busy = true;
  offline.ready = false;
  offline.loaded = 0;
  try {
    await new Promise<void>((resolve, reject) => {
      const channel = new MessageChannel();
      const timer = setTimeout(() => {
        channel.port1.close();
        reject(new Error("资源准备超时，可重试以继续校验"));
      }, 300000);
      channel.port1.onmessage = ({ data }) => {
        Object.assign(offline, {
          loaded: data.loaded || 0,
          total: data.total || offline.total,
          message: data.message || offline.message,
        });
        if (data.done) {
          clearTimeout(timer);
          channel.port1.close();
          offline.ready = data.ready;
          if (data.error) reject(new Error(data.error));
          else resolve();
        }
      };
      navigator.serviceWorker.controller!.postMessage({ type }, [
        channel.port2,
      ]);
    });
  } catch (e: any) {
    offline.message = e.message;
    offline.ready = false;
  } finally {
    offline.busy = false;
  }
}
export async function checkUpdate() {
  await registration?.update();
  offline.update = !!registration?.waiting;
}
