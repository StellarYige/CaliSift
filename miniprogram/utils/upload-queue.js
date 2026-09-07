const MAX_FILE = 10 * 1024 * 1024;
const MAX_BATCH = 30 * 1024 * 1024;

function validateFiles(files) {
  if (!files.length || files.length > 10) return '每次请选择 1–10 个文件';
  if (files.some(file => !/\.(xlsx|xls|csv|png|jpe?g)$/i.test(file.name))) return '仅支持 xlsx、xls、csv、png、jpg、jpeg 文件';
  if (files.filter(file => /\.(png|jpe?g)$/i.test(file.name)).length > 5) return '每批图片最多 5 张';
  if (files.some(file => !Number.isFinite(file.size) || file.size <= 0)) return '不能上传空文件';
  if (files.some(file => file.size > MAX_FILE)) return '单个文件不能超过 10 MiB';
  if (files.reduce((total, file) => total + file.size, 0) > MAX_BATCH) return '文件合计不能超过 30 MiB';
  return '';
}

function queryKey(name, year) { return `${name.normalize('NFKC').trim()}\n${year}`; }

async function runQueue(files, upload, onUpdate, concurrency = 2) {
  const results = files.map(file => ({ ...file }));
  let cursor = 0;
  async function worker() {
    while (cursor < results.length) {
      const index = cursor++;
      if (results[index].status === 'done' && results[index].report) continue;
      results[index] = { ...results[index], status: 'uploading', progress: 0, error: '' };
      onUpdate(results.slice());
      try {
        const report = await upload(results[index], progress => {
          results[index] = { ...results[index], progress, status: progress === 100 ? 'parsing' : 'uploading' };
          onUpdate(results.slice());
        });
        results[index] = { ...results[index], status: 'done', progress: 100, report };
      } catch (error) {
        results[index] = { ...results[index], status: 'error', error: error.message || '上传失败', report: null };
      }
      onUpdate(results.slice());
    }
  }
  await Promise.all(Array.from({ length: Math.min(files.some(f => f.image) ? 1 : concurrency, files.length) }, worker));
  return results;
}

module.exports = { validateFiles, runQueue, queryKey };
