import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
const root = path.resolve(import.meta.dirname, "..");
const dist = path.join(root, "web/dist");
const hash = (data) => crypto.createHash("sha256").update(data).digest("hex");
async function walk(dir) {
  const files = [];
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(p)));
    else files.push(p);
  }
  return files;
}
// Build output is isolated; Vite creates it from the source tree on each build.
const files = [];
for (const file of (await walk(dist)).sort()) {
  const relative = path.relative(dist, file).replaceAll("\\", "/");
  if (["sw.js", "offline-manifest.json", "SHA256SUMS"].includes(relative))
    continue;
  const data = await fs.readFile(file);
  files.push({
    path: relative,
    size: data.length,
    sha256: hash(data),
    shell: relative === "index.html" || relative.startsWith("assets/"),
  });
}
const version = JSON.parse(
  await fs.readFile(path.join(root, "web/package.json"), "utf8"),
).version;
const manifest = {
  version,
  build: hash(JSON.stringify(files)).slice(0, 20),
  total: files.reduce((s, f) => s + f.size, 0),
  files,
};
await fs.writeFile(
  path.join(dist, "offline-manifest.json"),
  JSON.stringify(manifest, null, 2),
);
const template = await fs.readFile(
  path.join(root, "web/service-worker.js"),
  "utf8",
);
await fs.writeFile(
  path.join(dist, "sw.js"),
  "const MANIFEST = " + JSON.stringify(manifest) + ";\n" + template,
);
const sums = [];
for (const file of (await walk(dist)).sort()) {
  if (path.basename(file) === "SHA256SUMS") continue;
  sums.push(
    hash(await fs.readFile(file)) +
      "  " +
      path.relative(dist, file).replaceAll("\\", "/"),
  );
}
await fs.writeFile(path.join(dist, "SHA256SUMS"), sums.join("\n") + "\n");
console.log(
  `Static web ${version}: ${files.length} resources, ${(manifest.total / 1048576).toFixed(1)} MiB; build ${manifest.build}`,
);
