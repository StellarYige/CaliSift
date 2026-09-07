// Native picker is replaced with generated test files; wx file storage,
// wx.uploadFile, wx.request, page rendering and interactions are real.
const automator = require('miniprogram-automator');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const out = path.resolve(__dirname, '../artifacts');
  fs.mkdirSync(out, { recursive: true });
  const mini = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9420' });
  const errors = [];
  mini.on('exception', error => { errors.push(String(error.message || error)); });
  try {
    let page = await mini.reLaunch('/pages/upload/upload');
    await page.waitFor('.name-input');
    await mini.screenshot({ path: path.join(out, 'upload.png') });
    const files = ['9月排班表.xlsx', '培训安排.xlsx', '国庆值班表.xlsx', '冲突与重复.xlsx'].map(name => {
      const bytes = fs.readFileSync(path.resolve(__dirname, '../tests/fixtures', name));
      return { name, data: bytes.toString('base64'), size: bytes.length };
    });
    const chosen = await mini.evaluate(items => {
      const manager = wx.getFileSystemManager();
      return items.map((item, index) => {
        const filePath = `${wx.env.USER_DATA_PATH}/xingcheng-${index}.xlsx`;
        manager.writeFileSync(filePath, item.data, 'base64');
        return { name: item.name, path: filePath, size: item.size, type: 'file' };
      });
    }, files);
    await mini.mockWxMethod('chooseMessageFile', { tempFiles: chosen });
    await (await page.$('.name-input')).input('星辰奕歌');
    await (await page.$('.year-input')).input('2026');
    await (await page.$('.upload-zone')).tap();
    assert.equal((await page.data('files')).length, 4);
    await (await page.$('.submit')).tap();
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      page = await mini.currentPage();
      if (page.path === 'pages/confirm/confirm') break;
      const error = await page.data('error');
      if (error && !(await page.data('busy'))) throw new Error(error + ': ' + JSON.stringify(await page.data('files')));
      await page.waitFor(500);
    }
    assert.equal(page.path, 'pages/confirm/confirm', 'Import preview navigation timed out');
    await page.callMethod('preview');
    await page.waitFor(1000);
    const previewDeadline = Date.now() + 20000;
    while (!(await page.data('preview')) && Date.now() < previewDeadline) await page.waitFor(300);
    assert.equal(await page.data('error'), '');
    await mini.screenshot({path:path.join(out,'confirm-v02.png')});
    await page.callMethod('save');
    await page.waitFor(800);
    page = await mini.currentPage();
    assert.equal(page.path,'pages/timeline/timeline');
    await page.callMethod('view',{currentTarget:{dataset:{view:'timeline'}}});
    await page.waitFor('.event');
    const data = await page.data();
    assert.equal(data.count, 5);
    assert.equal(data.conflictCount, 1);
    assert.equal(data.groups[0].events[0].sourceCount, 2);
    await mini.screenshot({ path: path.join(out, 'timeline.png') });
    await (await page.$('.event')).tap();
    assert.equal((await page.data('groups'))[0].events[0].expanded, true);
    await mini.pageScrollTo(210);
    await page.waitFor(300);
    await mini.screenshot({ path: path.join(out, 'sources.png') });
    await (await page.$('.diagnostic-toggle')).tap();
    assert.equal(await page.data('showDiagnostics'), true);
    await mini.pageScrollTo(0);
    await (await page.$('.edit-button')).tap();
    page = await mini.currentPage();
    await page.waitFor('.save-button');
    assert.equal(page.path, 'pages/review/review');
    await mini.screenshot({ path: path.join(out, 'review.png') });
    // Supply a date-picker result; the handler, request and subsequent UI are real.
    await page.callMethod('fieldChange', { currentTarget: { dataset: { field: 'date' } }, detail: { value: '2026-09-09' } });
    await (await page.$('.save-button')).tap();
    const reviewDeadline = Date.now() + 15000;
    while (Date.now() < reviewDeadline) {
      page = await mini.currentPage();
      if (page.path === 'pages/timeline/timeline') break;
      if (await page.data('error')) throw new Error(await page.data('error'));
      await page.waitFor(250);
    }
    assert.equal(page.path, 'pages/timeline/timeline');
    assert.equal(await page.data('conflictCount'), 0);
    assert.equal(await page.data('savedLocally'), true);
    await mini.screenshot({ path: path.join(out, 'timeline-reviewed.png') });
    // Re-run application initialization over real wx storage, then use resume.
    await mini.evaluate(() => { const app = getApp(); app.globalData = { report: null, personName: '' }; app.onLaunch(); });
    page = await mini.reLaunch('/pages/upload/upload');
    await page.waitFor('.resume-button');
    await mini.screenshot({ path: path.join(out, 'upload-saved.png') });
    await (await page.$('.resume-button')).tap();
    page = await mini.currentPage();
    assert.equal(await page.data('count'), 5);
    assert.equal(await page.data('conflictCount'), 0);
    assert.deepEqual(errors, []);
    const result = { status: 'passed', layer: 'WeChat developer-tools simulator', picker: 'synthetic fixtures injected',
      transport: 'real wx.uploadFile + wx.request', events: data.count, conflicts: data.conflictCount,
      sources: data.groups[0].events[0].sourceCount, correctedConflicts: 0, restoredFromWxStorage: true,
      datePicker: 'change result injected', runtimeErrors: errors };
    fs.writeFileSync(path.join(out, 'devtools-smoke.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await mini.restoreWxMethod('chooseMessageFile').catch(() => {});
    mini.disconnect();
  }
}
const watchdog = setTimeout(() => { console.error('Developer tools did not become ready within 70 seconds. Check its AppID/login dialog.'); process.exit(1); }, 70000);
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => clearTimeout(watchdog));
