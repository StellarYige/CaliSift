const api = require('../../utils/api');
const storage = require('../../utils/storage');
const { validateFiles, runQueue, queryKey } = require('../../utils/upload-queue');

Page({
  data: { name: '', year: new Date().getFullYear(), files: [], busy: false, error: '', hasSuccess: false, hasErrors: false },
  onShow() {
    const state = getApp().globalData;
    this.setData({ hasSaved: !!state.report, savedName: state.personName, savedCount: state.report ? state.report.events.length : 0,
      persistenceError: state.persistenceError || '', savedLocally: !!state.savedAt });
    if (!this.data.name && state.personName) this.setData({ name: state.personName, year: state.referenceYear || this.data.year });
    if (state.imageSelection) {
      const files = [...(this._files || this.data.files), state.imageSelection];
      const error = validateFiles(files);
      if (!error) this.updateFiles(files);
      this.setData({ error }); state.imageSelection = null;
    }
    this.setData({ sources: state.calendar ? state.calendar.sources.map(s => ({ id: s.id, name: s.name, count: s.revisions.length })) : [],
      templateSources: [{id:'',name:'不使用来源模板'}, ...(state.calendar ? state.calendar.sources.map(s => ({id:s.id,name:s.name})) : [])] });
  },
  resume() { wx.switchTab({ url: '/pages/timeline/timeline' }); },
  chooseImage(event) { wx.navigateTo({ url: `/pages/image/image?camera=${event.currentTarget.dataset.camera || ''}` }); },
  sourceRules(event) { wx.navigateTo({ url: `/pages/rules/rules?id=${event.currentTarget.dataset.id}` }); },
  templateSource(event) { this.setData({ templateIndex: Number(event.detail.value), hasSuccess: false, hasErrors: false }); this.updateFiles((this._files || this.data.files).map(f => ({ ...f, status: 'ready', report: null }))); },
  clearSaved() {
    if (this.data.busy) return;
    wx.showModal({ title: '清除本机结果？', content: '会清除最近一次日程和手动修正记录。再次查看需要重新上传表格。', confirmText: '清除',
      success: result => {
        if (!result.confirm) return;
        const error = storage.clear(getApp().globalData);
        if (!error) { this.updateFiles([]); this.setData({ hasSuccess: false, hasErrors: false }); }
        this.onShow();
        this.setData({ error });
      }
    });
  },
  onNameInput(event) { this.setData({ name: event.detail.value, error: '' }); },
  onYearInput(event) { this.setData({ year: event.detail.value, error: '' }); },
  updateFiles(files) {
    // Reports stay in JS memory, outside the renderer's limited setData channel.
    this._files = files;
    this.setData({ files: files.map(file => { const { report, ...visible } = file; return visible; }) });
  },
  chooseFiles() {
    if (this.data.busy) return;
    const remaining = 10 - this.data.files.length;
    if (remaining < 1) return this.setData({ error: '每批最多 10 个文件，请先移除部分文件' });
    wx.chooseMessageFile({
      count: remaining, type: 'file', extension: ['xlsx', 'xls', 'csv'],
      success: result => {
        const selected = result.tempFiles.map((file, index) => ({ ...file,
          id: `${Date.now()}-${index}`, sizeLabel: file.size < 1024 * 1024 ? `${Math.ceil(file.size / 1024)} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`,
          status: 'ready', progress: 0, error: '', report: null
        }));
        const files = [...(this._files || this.data.files), ...selected];
        const error = validateFiles(files);
        if (!error) this.updateFiles(files);
        this.setData({ error });
      },
      fail: error => { if (!/cancel/i.test(error.errMsg || '')) this.setData({ error: '未能选择文件，请从微信聊天中选择表格' }); }
    });
  },
  removeFile(event) {
    if (this.data.busy) return;
    const files = (this._files || this.data.files).filter(file => file.id !== event.currentTarget.dataset.id);
    this.updateFiles(files);
    this.setData({ error: '', hasSuccess: files.some(f => f.status === 'done'), hasErrors: files.some(f => f.status === 'error') });
  },
  async start() {
    if (this.data.busy) return;
    const name = this.data.name.normalize('NFKC').trim();
    const year = Number(this.data.year);
    let error = validateFiles(this.data.files);
    if (!name || name.length > 80 || /[\s、,;；，/|]/.test(name)) error = '请输入一个完整姓名（不含分隔符）';
    else if (!Number.isInteger(year) || year < 1900 || year > 2199) error = '补全年份应在 1900–2199 之间';
    if (error) return this.setData({ error });
    const key = queryKey(name, year);
    const files = (this._files || this.data.files).map(file => file.queryKey === key ? file : { ...file, queryKey: key, status: 'ready', report: null });
    this.setData({ busy: true, error: '', name });
    try {
      const c = getApp().globalData.calendar, source = c && c.sources.find(s => s.id === (this.data.templateSources[this.data.templateIndex || 0] || {}).id);
      const completed = await runQueue(files, (file, progress) => api.upload({ ...file, layout_hint: source && source.rules && source.rules.template }, name, year, progress),
        updated => this.updateFiles(updated));
      const hasSuccess = completed.some(f => f.status === 'done');
      const hasErrors = completed.some(f => f.status === 'error');
      this.updateFiles(completed);
      this.setData({ hasSuccess, hasErrors });
      if (hasSuccess && !hasErrors) await this.showResults();
      else this.setData({ error: hasSuccess ? '部分文件未完成，可以重试或先查看成功结果' : '文件未能完成解析，请查看各文件的提示后重试' });
    } catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: false }); }
  },
  async showResults() {
    const key = queryKey(this.data.name, Number(this.data.year));
    const completed = (this._files || this.data.files).filter(file => file.status === 'done' && file.report && file.queryKey === key);
    if (!completed.length) return this.setData({ error: '姓名或年份已变化，请重新整理' });
    const wasBusy = this.data.busy;
    this.setData({ busy: true, error: '' });
    try {
      const report = await api.merge(completed.map(file => file.report));
      const failures = this.data.files.filter(file => file.status === 'error');
      report.files.push(...failures.map(file => ({ filename: file.name, status: 'error', error: file.error, sheets: [] })));
      const state = getApp().globalData;
      if (state.calendar && state.calendar.personName !== this.data.name) throw Error('姓名已变化。请先在“我的”中备份并切换个人日历，避免混入他人安排');
      state.draft = { report, name: this.data.name, year: this.data.year, sourceId: (this.data.templateSources && this.data.templateSources[this.data.templateIndex || 0] || {}).id };
      wx.navigateTo({ url: '/pages/confirm/confirm' });
    } catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: wasBusy }); }
  }
});
