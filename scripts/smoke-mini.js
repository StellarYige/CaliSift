// Real HTTP + actual mini-program page methods. This does not emulate rendering
// or claim to test WeChat's file picker. Use devtools-smoke.js for simulator QA.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const fixtureRoot = path.resolve(__dirname, '../tests/fixtures');
  const output = path.resolve(__dirname, '../artifacts');
  fs.mkdirSync(output, { recursive: true });
  const state = { globalData: {} };
  const saved = new Map();
  let pageDefinition, navigatedTo;
  global.Page = definition => { pageDefinition = definition; };
  global.getApp = () => state;
  global.wx = {
    env: { USER_DATA_PATH: path.join(output, 'wx-local') },
    getFileSystemManager() { return { accessSync: fs.accessSync, mkdirSync: (p) => fs.mkdirSync(p,{recursive:true}),
      writeFileSync: (p,v,encoding) => fs.writeFileSync(p,v,encoding), readFileSync: (p,encoding) => fs.readFileSync(p,encoding),
      readdirSync: fs.readdirSync, unlinkSync: fs.unlinkSync }; },
    switchTab({ url }) { navigatedTo = url; },
    setStorageSync(key, value) { saved.set(key, structuredClone(value)); },
    getStorageSync(key) { return structuredClone(saved.get(key)); },
    removeStorageSync(key) { saved.delete(key); },
    navigateBack() { navigatedTo = '/pages/timeline/timeline'; },
    uploadFile(options) {
      const form = new FormData();
      form.append(options.name, new Blob([fs.readFileSync(options.filePath)]), path.basename(options.filePath));
      for (const [key, value] of Object.entries(options.formData)) form.append(key, value);
      fetch(options.url, { method: 'POST', body: form }).then(async response => {
        options.success({ statusCode: response.status, data: await response.text() });
      }).catch(options.fail);
      return { onProgressUpdate(callback) { callback({ progress: 100 }); } };
    },
    request(options) {
      fetch(options.url, { method: options.method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options.data) })
        .then(async response => options.success({ statusCode: response.status, data: await response.json() })).catch(options.fail);
    },
    navigateTo({ url }) { navigatedTo = url; },
    redirectTo() { throw new Error('Unexpected redirect'); }
  };
  require('../miniprogram/pages/upload/upload');
  const files = ['9月排班表.xlsx', '培训安排.xlsx', '国庆值班表.xlsx', '冲突与重复.xlsx'].map((name, id) => {
    const filePath = path.join(fixtureRoot, name);
    return { id: String(id), name, path: filePath, size: fs.statSync(filePath).size, status: 'ready' };
  });
  const page = { ...pageDefinition, data: { ...pageDefinition.data, name: '星辰奕歌', year: 2026, files },
    setData(data) { Object.assign(this.data, data); } };
  await page.start();
  assert.equal(page.data.error, '', page.data.error);
  assert.equal(navigatedTo, '/pages/confirm/confirm');
  assert.equal(state.globalData.report, undefined, 'preview must not mutate saved calendar');
  require('../miniprogram/pages/confirm/confirm');
  const confirmation = { ...pageDefinition, data: structuredClone(pageDefinition.data), setData(data) { Object.assign(this.data,data); } };
  confirmation.onLoad(); await confirmation.preview();
  assert.equal(confirmation.data.error, '', confirmation.data.error);
  confirmation.save();
  assert.equal(confirmation.data.error, '', confirmation.data.error);
  assert.equal(navigatedTo, '/pages/timeline/timeline');
  assert.equal(state.globalData.report.events.length, 5);
  assert.equal(state.globalData.report.conflicts.length, 1);
  assert.equal(state.globalData.report.events[0].sources.length, 2);
  require('../miniprogram/pages/timeline/timeline');
  const timeline = { ...pageDefinition, data: { ...pageDefinition.data }, setData(data) { Object.assign(this.data, data); } };
  timeline.onLoad();
  assert.equal(timeline.data.groups[0].events[0].timeLabel, '08:00–16:00');
  assert.equal(timeline.data.groups[0].events[0].conflictLabel, '时间冲突');
  assert.equal(timeline.data.groups[2].events[0].title, '消防培训');
  timeline.toggleEvent({ currentTarget: { dataset: { id: timeline.data.groups[0].events[0].id } } });
  assert.equal(timeline.data.groups[0].events[0].expanded, true);
  fs.writeFileSync(path.join(output, 'http-smoke-report.json'), JSON.stringify(state.globalData.report, null, 2));
  assert.ok(state.globalData.savedAt);
  const original = structuredClone(state.globalData.report);
  // Correct an overlapping interval through the actual edit page and API.
  require('../miniprogram/pages/review/review');
  const review = { ...pageDefinition, data: structuredClone(pageDefinition.data), setData(data) { Object.assign(this.data, data); } };
  review.onLoad({ id: original.events[0].id });
  review.fieldChange({ currentTarget: { dataset: { field: 'date' } }, detail: { value: '2026-09-09' } });
  await review.save();
  assert.equal(review.data.error, '', review.data.error);
  timeline.onShow();
  assert.equal(timeline.data.conflictCount, 0);
  const edited = state.globalData.report.events.find(event => event.reviews.length);
  assert.equal(edited.date, '2026-09-09');
  assert.equal(edited.sources.length, 2);
  assert.equal(edited.reviews[0].before.date, '2026-09-07');
  fs.writeFileSync(path.join(output, 'reviewed-smoke-report.json'), JSON.stringify(state.globalData.report, null, 2));
  // Simulate a fresh application instance; only wx storage bridges the launches.
  global.App = definition => { Object.assign(state, definition); };
  require('../miniprogram/app');
  state.onLaunch();
  assert.equal(state.globalData.personName, '星辰奕歌');
  assert.equal(state.globalData.report.events.find(event => event.reviews.length).date, '2026-09-09');
  timeline.onShow();
  assert.equal(timeline.data.count, 5);
  const api = require('../miniprogram/utils/api');
  const pendingName = '周期课表待确认.xlsx';
  const pendingReport = await api.upload({ path: path.join(fixtureRoot, pendingName), name: pendingName }, '星辰奕歌', 2026, () => {});
  assert.ok(pendingReport.pending.length);
  fs.writeFileSync(path.join(output, 'pending-smoke-report.json'), JSON.stringify(pendingReport, null, 2));
  const pendingId = pendingReport.pending[0].id;
  const confirmed = await api.review(pendingReport, [{ event_id: pendingId, values: { date: '2026-09-10', title: '确认课程', start: '14:00' } }]);
  assert.equal(confirmed.pending.length, pendingReport.pending.length - 1);
  assert.ok(confirmed.events.some(event => event.title === '确认课程' && event.reviews.length));
  console.log(JSON.stringify({ status: 'passed', layer: 'actual page methods + real HTTP (wx transport bridge)', events: timeline.data.count,
    initialConflicts: original.conflicts.length, correctedConflicts: timeline.data.conflictCount,
    correctedSources: edited.sources.length, restoredAfterRelaunch: true, confirmedPending: true }, null, 2));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
