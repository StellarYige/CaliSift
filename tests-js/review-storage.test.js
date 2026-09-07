const test = require('node:test');
const assert = require('node:assert/strict');
const storage = require('../miniprogram/utils/storage');
const { formFor, validate } = require('../miniprogram/utils/review');
const { buildTimeline } = require('../miniprogram/utils/timeline');
const report = { events: [{ id: 'one', date: '2026-09-07', title: '早班', start: '08:00', end: '16:00',
  end_date: '2026-09-07', sources: [{ filename: '排班.xlsx', sheet: '九月', name_cell: 'B2', excerpt: '原表', evidence: {} }],
  notes: [], warnings: [], reviews: [], status: 'confirmed' }], pending: [], files: [], warnings: [], conflicts: [] };

function memory() {
  const values = new Map();
  return { values, getStorageSync: key => structuredClone(values.get(key)),
    setStorageSync: (key, value) => values.set(key, structuredClone(value)), removeStorageSync: key => values.delete(key) };
}
function pageAt(path) {
  let definition;
  global.Page = value => { definition = value; };
  delete require.cache[require.resolve(path)];
  require(path);
  return { ...definition, data: structuredClone(definition.data), setData(data) { Object.assign(this.data, data); } };
}

test('latest snapshot survives new app launch, replaces prior result, stores no temporary paths', () => {
  const wxApi = memory(), state = {};
  storage.commit(state, report, '星辰奕歌', 2026, wxApi);
  assert.equal(state.persistenceError, '');
  assert.ok(state.savedAt);
  global.wx = wxApi;
  let app;
  global.App = value => { app = value; };
  require('../miniprogram/app');
  app.onLaunch();
  assert.deepEqual(app.globalData.report, report);
  assert.equal(app.globalData.personName, '星辰奕歌');
  storage.commit(state, { ...report, events: [] }, '林知夏', 2027, wxApi);
  assert.equal(storage.restore(wxApi).snapshot.personName, '林知夏');
  assert.equal(wxApi.values.size, 1);
  assert.ok(!JSON.stringify([...wxApi.values]).includes('filePath'));
  assert.equal(storage.clear(state, wxApi), '');
  assert.equal(storage.restore(wxApi).snapshot, null);
  assert.equal(state.report, null);
});

test('corrupt and future-version storage is ignored with visible error', () => {
  for (const value of [{ version: 9 }, { version: 1, personName: '星辰奕歌', report: {} },
    { version: 1, personName: '星辰奕歌', report: { ...report, events: [{ id: 'a', date: null }] } }]) {
    const result = storage.restore({ getStorageSync: () => value });
    assert.equal(result.snapshot, null); assert.ok(result.error);
  }
  assert.ok(storage.restore({ getStorageSync() { throw Error(); } }).error);
});

test('failed or oversized save preserves old snapshot and current report; failed clear preserves memory', () => {
  const wxApi = memory(), state = {};
  storage.commit(state, report, '星辰奕歌', 2026, wxApi);
  const old = structuredClone(wxApi.values.get(storage.KEY));
  const next = { ...report, events: [] };
  assert.ok(storage.commit(state, next, '星辰奕歌', 2026, { setStorageSync() { throw Error('quota'); } }));
  assert.equal(state.report, next);
  assert.equal(state.savedAt, '');
  assert.deepEqual(wxApi.values.get(storage.KEY), old);
  const large = { ...report, warnings: ['文'.repeat(storage.MAX_BYTES)] };
  assert.ok(storage.commit(state, large, '星辰奕歌', 2026, wxApi));
  assert.deepEqual(wxApi.values.get(storage.KEY), old);
  assert.ok(storage.clear(state, { removeStorageSync() { throw Error(); } }));
  assert.equal(state.report, large);
});

test('edit form validates missing date, invalid dates, end without start and explicit cross-midnight', () => {
  const form = formFor(report.events[0]);
  assert.deepEqual(validate(form).errors, {});
  assert.ok(validate({ ...form, date: '' }).errors.date);
  assert.ok(validate({ ...form, date: '2026-02-30' }).errors.date);
  assert.ok(validate({ ...form, title: '  ' }).errors.title);
  assert.ok(validate({ ...form, start: '' }).errors.start);
  assert.ok(validate({ ...form, end: '06:00' }).errors.end);
  assert.deepEqual(validate({ ...form, start: '22:00', end: '06:00', next_day: true }).errors, {});
  assert.equal(validate({ ...form, start: '', end: '' }).values.start, null);
  assert.deepEqual(validate({ ...form, notes: ' 带证件\n\n 提前到场 ' }).values.notes, ['带证件', '提前到场']);
});

test('review page rejects stale data, keeps draft on network failure, commits only successful responses', async () => {
  const state = { report: structuredClone(report), personName: '星辰奕歌', referenceYear: 2026 };
  global.getApp = () => ({ globalData: state });
  let requests = 0, backs = 0;
  const wxApi = memory();
  global.wx = { ...wxApi, request(options) { requests++; options.fail(); }, navigateBack() { backs++; } };
  const page = pageAt('../miniprogram/pages/review/review');
  page.onLoad({ id: 'one' });
  page.fieldChange({ currentTarget: { dataset: { field: 'title' } }, detail: { value: '修正后的早班' } });
  await page.save();
  assert.match(page.data.error, /修正未保存/);
  assert.equal(page.data.form.title, '修正后的早班');
  assert.equal(state.report.events[0].title, '早班');
  assert.equal(backs, 0);
  const updated = structuredClone(report); updated.events[0].title = '修正后的早班';
  global.wx.request = options => { requests++; options.success({ statusCode: 200, data: updated }); };
  await page.save();
  assert.equal(state.report.events[0].title, '修正后的早班');
  assert.equal(storage.restore(wxApi).snapshot.report.events[0].title, '修正后的早班');
  assert.equal(backs, 1);
  await page.save();
  assert.match(page.data.error, /时间线已变化/);
  assert.equal(requests, 2);
});

test('review page invalid fields stay local; cancel and clear do not edit the report', async () => {
  const state = { report: structuredClone(report) };
  global.getApp = () => ({ globalData: state });
  let backs = 0;
  global.wx = { request() { throw Error('must not request'); }, navigateBack() { backs++; } };
  const page = pageAt('../miniprogram/pages/review/review');
  page.onLoad({ id: 'one' });
  page.clearTime({ currentTarget: { dataset: { field: 'start' } } });
  assert.equal(page.data.form.end, '');
  page.fieldChange({ currentTarget: { dataset: { field: 'date' } }, detail: { value: '' } });
  await page.save();
  assert.ok(page.data.errors.date);
  page.cancel();
  assert.equal(backs, 1);
  assert.deepEqual(state.report, report);
});

test('history is readable without passing nested source snapshots to the renderer', () => {
  const revised = structuredClone(report);
  revised.events[0].reviews = [{ before: structuredClone(report.events[0]) }];
  const event = buildTimeline(revised).groups[0].events[0];
  assert.equal(event.edited, true);
  assert.equal(event.reviews, undefined);
  assert.equal(event.history[0].title, '早班');
  assert.equal(event.history[0].sources, undefined);
  assert.equal(event.sources[0].sourceKey, '0');
});

test('all failed uploads preserve the saved report', async () => {
  const wxApi = memory(), state = {};
  storage.commit(state, report, '星辰奕歌', 2026, wxApi);
  global.getApp = () => ({ globalData: state });
  global.wx = { ...wxApi, uploadFile(options) { options.fail(); return {}; } };
  const page = pageAt('../miniprogram/pages/upload/upload');
  page.setData({ name: '星辰奕歌', files: [{ id: 'file', name: '失败.xlsx', path: '/tmp/file', size: 100 }] });
  await page.start();
  assert.match(page.data.error, /未能完成/);
  assert.deepEqual(state.report, report);
  assert.deepEqual(storage.restore(wxApi).snapshot.report, report);
});
