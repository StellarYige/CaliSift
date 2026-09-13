// MANIFEST is injected at build time. No skipWaiting, database deletion, or remote APIs.
const BASE = new URL("./", self.location.href);
const CACHE = "calisift:" + BASE.pathname + ":" + MANIFEST.build;
const entries = new Map(
  MANIFEST.files.map((f) => [new URL(f.path, BASE).href, f]),
);
async function checksum(bytes) {
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
}
async function valid(response, entry) {
  if (!response?.ok) return false;
  const bytes = await response.clone().arrayBuffer();
  return (
    bytes.byteLength === entry.size && (await checksum(bytes)) === entry.sha256
  );
}
async function acquire(entry, cache, progress) {
  const url = new URL(entry.path, BASE).href;
  const cached = await cache.match(url);
  if (await valid(cached, entry)) {
    progress?.(entry.size);
    return cached;
  }
  if (cached) await cache.delete(url);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("资源下载失败：" + entry.path);
  let bytes;
  if (response.body && progress) {
    const reader = response.body.getReader(),
      chunks = [];
    let length = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      length += value.length;
      progress(value.length);
    }
    bytes = new Uint8Array(length);
    let offset = 0;
    for (const c of chunks) {
      bytes.set(c, offset);
      offset += c.length;
    }
  } else {
    bytes = new Uint8Array(await response.arrayBuffer());
    progress?.(bytes.length);
  }
  if (bytes.length !== entry.size || (await checksum(bytes)) !== entry.sha256)
    throw new Error("资源校验失败：" + entry.path + "；请重新准备资源");
  const saved = new Response(bytes, { status: 200, headers: response.headers });
  await cache.put(url, saved.clone());
  return saved;
}
self.addEventListener("install", (event) =>
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      for (const entry of MANIFEST.files.filter((f) => f.shell))
        await acquire(entry, cache);
    })(),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);
// Older version caches are retained so an in-progress page can keep working.
// Browser storage settings can clear resources; personal data is never touched here.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  let url = new URL(event.request.url);
  if (url.href === new URL("offline-manifest.json", BASE).href) {
    event.respondWith(
      Promise.resolve(
        new Response(JSON.stringify(MANIFEST), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    return;
  }
  if (url.href === BASE.href) url = new URL("index.html", BASE);
  const entry = entries.get(url.href);
  if (entry)
    event.respondWith(
      caches
        .open(CACHE)
        .then((cache) => acquire(entry, cache))
        .catch(
          () =>
            new Response("本站资源缺失或校验失败，请联网准备离线资源", {
              status: 503,
            }),
        ),
    );
});
let preparing = false;
self.addEventListener("message", (event) => {
  if (!["CHECK", "PREPARE"].includes(event.data?.type) || !event.ports[0])
    return;
  const port = event.ports[0];
  event.waitUntil(
    (async () => {
      let loaded = 0;
      const post = (data) =>
        port.postMessage({ total: MANIFEST.total, loaded, ...data });
      if (preparing) {
        post({
          done: true,
          ready: false,
          error: "另一个标签页正在准备离线资源，请稍后重新校验",
        });
        return;
      }
      preparing = true;
      try {
        const cache = await caches.open(CACHE);
        for (const entry of MANIFEST.files) {
          const url = new URL(entry.path, BASE).href;
          if (event.data.type === "PREPARE")
            await acquire(entry, cache, (n) => {
              loaded += n;
              post({ message: "正在下载并校验：" + entry.path });
            });
          else {
            if (!(await valid(await cache.match(url), entry))) {
              post({
                done: true,
                ready: false,
                message: "资源未完整缓存或校验失败，请准备 / 修复离线资源",
              });
              return;
            }
            loaded += entry.size;
            post({ message: "正在校验：" + entry.path });
          }
        }
        post({
          done: true,
          ready: true,
          message: "全部资源 SHA-256 校验通过，离线就绪",
        });
      } catch (e) {
        post({
          done: true,
          ready: false,
          error:
            e.name === "QuotaExceededError"
              ? "浏览器空间不足，离线准备未完成"
              : e.message,
        });
      } finally {
        preparing = false;
      }
    })(),
  );
});
