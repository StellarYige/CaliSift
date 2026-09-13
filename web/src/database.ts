export type Snapshot = { revision: number; state: any };
export const siteBase = new URL(import.meta.env.BASE_URL, location.href);
export const databaseName = `calisift:${siteBase.pathname}`;
const fail = (error: any) =>
  Object.assign(
    new Error(
      error?.name === "QuotaExceededError"
        ? "浏览器存储空间不足，未保存。请先导出备份、清理未完成任务后重试。"
        : "浏览器存储不可用，未保存。请检查站点存储权限或从备份恢复。",
    ),
    { code: "STORAGE_FAILED", cause: error },
  );
export async function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let request: IDBOpenDBRequest;
    try {
      request = indexedDB.open(databaseName, 1);
    } catch (e) {
      reject(fail(e));
      return;
    }
    request.onupgradeneeded = () => {
      request.result.createObjectStore("state");
    };
    request.onerror = () => reject(fail(request.error));
    request.onblocked = () =>
      reject(
        new Error(
          "其他页面阻止数据库升级，请关闭旧版页面后重试；原数据已保留。",
        ),
      );
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
  });
}
export async function readSnapshot(): Promise<Snapshot> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("state", "readonly");
    const req = tx.objectStore("state").get("root");
    tx.oncomplete = () => {
      db.close();
      resolve(req.result || { revision: 0, state: null });
    };
    tx.onabort = () => {
      db.close();
      reject(fail(tx.error));
    };
    tx.onerror = () => {};
  });
}
export async function commitSnapshot(
  expected: number,
  state: any,
): Promise<void> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    let error: Error | undefined;
    let tx: IDBTransaction;
    try {
      tx = db.transaction("state", "readwrite", { durability: "strict" });
    } catch (e) {
      db.close();
      reject(fail(e));
      return;
    }
    const store = tx.objectStore("state");
    const req = store.get("root");
    req.onsuccess = () => {
      if ((req.result?.revision || 0) !== expected) {
        error = Object.assign(
          new Error("另一个标签页已修改数据。本次未保存，请刷新后重新核对。"),
          { code: "VERSION_CONFLICT" },
        );
        tx.abort();
        return;
      }
      try {
        store.put({ revision: expected + 1, state }, "root");
      } catch (e) {
        error = fail(e);
        tx.abort();
      }
    };
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onabort = () => {
      db.close();
      reject(error || fail(tx.error));
    };
    tx.onerror = () => {};
  });
}
