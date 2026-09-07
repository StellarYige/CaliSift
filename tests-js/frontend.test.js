const test = require('node:test');
const assert = require('node:assert/strict');
const { runQueue, validateFiles, queryKey } = require('../miniprogram/utils/upload-queue');
const { buildTimeline } = require('../miniprogram/utils/timeline');
const { parseResponse, upload, merge } = require('../miniprogram/utils/api');

const file = (id, size = 100) => ({ id, name: `${id}.xlsx`, path: `/tmp/${id}.xlsx`, size, status: 'ready' });
const report = { events: [], pending: [], files: [], warnings: [], conflicts: [] };

test('upload concurrency is limited and errors preserve successes', async () => {
  let active = 0, highest = 0;
  const result = await runQueue([file('a'), file('b'), file('c')], async item => {
    active++; highest = Math.max(active, highest);
    await new Promise(resolve => setTimeout(resolve, 10));
    active--;
    if (item.id === 'b') throw new Error('断网');
    return report;
  }, () => {});
  assert.equal(highest, 2);
  assert.deepEqual(result.map(f => f.status), ['done', 'error', 'done']);
  let calls = 0;
  const retried = await runQueue(result, async () => { calls++; return report; }, () => {});
  assert.equal(calls, 1);
  assert.ok(retried.every(f => f.status === 'done'));
});

test('query key changes when person or year changes', () => {
  assert.equal(queryKey(' 星辰奕歌 ', 2026), queryKey('星辰奕歌', 2026));
  assert.notEqual(queryKey('林知夏', 2026), queryKey('星辰奕歌', 2026));
  assert.notEqual(queryKey('星辰奕歌', 2027), queryKey('星辰奕歌', 2026));
});

test('file limits and supported types', () => {
  assert.equal(validateFiles([file('a')]), '');
  assert.ok(validateFiles([]));
  assert.ok(validateFiles(Array.from({ length: 11 }, (_, i) => file(i))));
  assert.ok(validateFiles([{ ...file('a'), name: 'a.pdf' }]));
  assert.ok(validateFiles([file('a', 0)]));
  assert.ok(validateFiles([file('a', 11 * 1024 * 1024)]));
  assert.ok(validateFiles(Array.from({ length: 4 }, (_, i) => file(i, 9 * 1024 * 1024))));
});

test('upload uses original filename and handles HTTP errors', async () => {
  let options;
  const fakeWx = { uploadFile(o) { options = o; queueMicrotask(() => o.success({ statusCode: 200, data: JSON.stringify(report) })); return { onProgressUpdate(fn) { fn({ progress: 100 }); } }; } };
  let progress;
  assert.deepEqual(await upload(file('a'), '星辰奕歌', 2026, p => { progress = p; }, fakeWx), report);
  assert.equal(options.name, 'files');
  assert.equal(options.formData.original_filename, 'a.xlsx');
  assert.equal(progress, 100);
  await assert.rejects(upload(file('a'), '星辰奕歌', 2026, () => {}, { uploadFile(o) { o.success({ statusCode: 413, data: '{"detail":"太大"}' }); } }), /太大/);
  await assert.rejects(upload(file('a'), '星辰奕歌', 2026, () => {}, { uploadFile(o) { o.fail(); } }), /连接失败/);
});

test('file parser errors are not counted as successful uploads', async () => {
  const failed = { ...report, files: [{ status: 'error', error: '损坏文件' }] };
  await assert.rejects(upload(file('a'), '星辰奕歌', 2026, () => {}, { uploadFile(o) { o.success({ statusCode: 200, data: JSON.stringify(failed) }); } }), /损坏文件/);
});

test('response validation and merge failure', async () => {
  assert.throws(() => parseResponse({ statusCode: 200, data: 'html' }), /无法识别/);
  assert.throws(() => parseResponse({ statusCode: 200, data: {} }), /不完整/);
  assert.throws(() => parseResponse({ statusCode: 422, data: { detail: [] } }), /格式/);
  await assert.rejects(merge([report], { request(o) { o.fail(); } }), /已上传的结果仍保留/);
});

test('timeline displays crossing midnight, source evidence and conflicts', () => {
  const source = { filename: '夜班.xlsx', sheet: '九月', name_cell: 'B2', evidence: { date: 'A2' } };
  const events = [
    { id: 'a', date: '2026-09-07', start: '22:00', end: '06:00', end_date: '2026-09-08', title: '夜班', sources: [source] },
    { id: 'b', date: '2026-09-08', start: null, title: '培训', sources: [source] }
  ];
  const view = buildTimeline({ ...report, events, conflicts: [{ event_ids: ['a', 'b'], kind: 'possible' }] });
  assert.equal(view.groups[0].weekday, '星期一');
  assert.equal(view.groups[0].events[0].timeLabel, '22:00–次日 06:00');
  assert.equal(view.groups[1].events[0].timeLabel, '时间未注明');
  assert.equal(view.groups[0].events[0].conflictLabel, '可能重叠');
  assert.match(view.groups[0].events[0].relatedLabels[0], /培训/);
  assert.equal(view.groups[0].events[0].sources[0].evidenceText, '日期：A2');
});

test('upload page clears stale reports after changing year', async () => {
  let definition;
  global.Page = value => { definition = value; };
  global.wx = {
    uploadFile(o) { queueMicrotask(() => o.success({ statusCode: 200, data: JSON.stringify(report) })); return {}; },
    request(o) { o.success({ statusCode: 200, data: report }); }, navigateTo() {}
  };
  global.getApp = () => ({ globalData: {} });
  require('../miniprogram/pages/upload/upload');
  let calls = 0;
  const original = global.wx.uploadFile;
  global.wx.uploadFile = o => { calls++; return original(o); };
  const page = { ...definition, data: { ...definition.data, name: '星辰奕歌', year: 2027,
    files: [{ ...file('a'), status: 'done', report, queryKey: queryKey('星辰奕歌', 2026) }] },
    setData(value) { this.data = { ...this.data, ...value }; }
  };
  await page.start();
  assert.equal(calls, 1);
  assert.equal(page.data.files[0].queryKey, queryKey('星辰奕歌', 2027));
  assert.equal(page.data.busy, false);
  assert.equal(page.data.files[0].report, undefined);
  assert.ok(page._files[0].report);
});

test('large timelines paginate without losing the total or cross-page conflicts', () => {
  const events = Array.from({ length: 125 }, (_, i) => ({ id: String(i), date: '2026-09-07', title: `活动${i}`, start: null, sources: [] }));
  const result = { ...report, events, pending: events, conflicts: [{ event_ids: ['0', '124'], kind: 'possible' }] };
  const first = buildTimeline(result);
  assert.equal(first.count, 125);
  assert.equal(first.groups[0].events.length, 50);
  assert.equal(first.pageCount, 3);
  assert.match(first.groups[0].events[0].relatedLabels[0], /活动124/);
  const last = buildTimeline(result, 2, 2);
  assert.equal(last.groups[0].events.length, 25);
  assert.equal(last.pending.length, 25);
});
