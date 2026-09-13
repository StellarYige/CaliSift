// Same-origin module Worker. Python receives only explicitly supplied file bytes.
let python;
let initializing;
let imagePackages;
const base = new URL("./", self.location.href);
const resourceFetch = self.fetch.bind(self);
self.fetch = (input, init) => {
  const url = new URL(
    input instanceof Request ? input.url : String(input),
    base,
  );
  const method = (
    init?.method || (input instanceof Request ? input.method : "GET")
  ).toUpperCase();
  if (
    url.origin !== base.origin ||
    !url.pathname.startsWith(base.pathname) ||
    method !== "GET"
  )
    return Promise.reject(new Error("计算进程仅允许读取本站静态资源"));
  return resourceFetch(input, init);
};
const sessions = new Map();
let ort;
async function ready() {
  if (!initializing)
    initializing = (async () => {
      const { loadPyodide } = await import(
        new URL("runtime/pyodide.mjs", base).href
      );
      python = await loadPyodide({
        indexURL: new URL("runtime/", base).href,
        checkAPIVersion: true,
      });
      await python.loadPackage(["pydantic", "pillow"], {
        checkIntegrity: true,
      });
      const response = await fetch(new URL("python-app.zip", base));
      if (!response.ok) throw new Error("Python 应用资源缺失");
      python.unpackArchive(await response.arrayBuffer(), "zip");
      await python.runPythonAsync(
        "from xingcheng.browser import dispatch_json, process_json",
      );
    })();
  await initializing;
}
self.ortInfer = async (role, data, dims) => {
  if (!ort) {
    ort = await import(new URL("ort/ort.wasm.min.mjs", base).href);
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.proxy = false;
    ort.env.wasm.wasmPaths = new URL("ort/", base).href;
  }
  if (!sessions.has(role)) {
    const names = {
      Det: "ch_PP-OCRv5_mobile_det.onnx",
      Rec: "ch_PP-OCRv5_rec_mobile_infer.onnx",
      Cls: "ch_ppocr_mobile_v2.0_cls_infer.onnx",
    };
    sessions.set(
      role,
      await ort.InferenceSession.create(
        new URL("models/" + names[role], base).href,
        { executionProviders: ["wasm"], graphOptimizationLevel: "all" },
      ),
    );
  }
  const session = sessions.get(role);
  const output = await session.run({
    [session.inputNames[0]]: new ort.Tensor("float32", data, Array.from(dims)),
  });
  const value = output[session.outputNames[0]];
  return { data: value.data, dims: Array.from(value.dims) };
};
self.onmessage = async ({ data }) => {
  try {
    await ready();
    if (data.mode === "process" && JSON.parse(data.raw).kind === "ocr") {
      if (!imagePackages)
        imagePackages = python.loadPackage(
          ["numpy", "opencv-python", "pyclipper", "shapely"],
          { checkIntegrity: true },
        );
      await imagePackages;
    }
    python.globals.set("_request", data.raw);
    const output = await python.runPythonAsync(
      data.mode === "process"
        ? "await process_json(_request)"
        : "dispatch_json(_request)",
    );
    python.globals.delete("_request");
    self.postMessage({ id: data.id, output: JSON.parse(output) });
  } catch (error) {
    self.postMessage({ id: data.id, error: String(error.message || error) });
  }
};
