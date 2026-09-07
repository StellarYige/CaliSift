const api = require('../../utils/api');
const store = require('../../utils/calendar-store');
const { eventView } = require('../../utils/timeline');
Page({
  data: { mode: 0, sourceIndex: 0, sourceName: '', from: '', to: '', sources: [], modes: ['追加安排', '更新已有来源'], busy: false, error: '', preview: null,
    rows: [], pageIndex: 0, pageCount: 0, changeIndex: 0, changePages: 0, mappingLabels: [], choices: {}, batchDate: '', batchStart: '', batchEnd: '', batchLocation: '', batchCategory: '', nextDay: false },
  onLoad() {
    const state = getApp().globalData;
    if (!state.draft) return this.setData({ error: '导入预览已失效，请返回重新选择文件' });
    this._draft = JSON.parse(JSON.stringify(state.draft));
    this._originalReport = JSON.parse(JSON.stringify(state.draft.report));
    this._calendar = state.calendar || store.empty(state.draft.name);
    this._mappings = {}; this._cancel = []; this._choices = {};
    this._generation = 0;
    const all = this._draft.report.events.concat(this._draft.report.pending);
    const days = all.map(e => e.date).filter(Boolean).sort();
    this.setData({ sources: this._calendar.sources, sourceIndex: Math.max(0,this._calendar.sources.findIndex(s => s.id === this._draft.sourceId)), sourceName: this._draft.sourceName || '', from: days[0] || '', to: days[days.length - 1] || '',
      files: this._draft.report.files.map(f => ({filename:f.filename,error:f.error,sheetCount:f.sheets.length,sheets:f.sheets.slice(0,3)})), pendingCount: this._draft.report.pending.length });
    this.refreshMappings();
    this.refreshRows();
  },
  refreshRows() { const all = this._draft.report.events.concat(this._draft.report.pending);
    this.setData({pageCount:Math.ceil(all.length/50),rows:all.slice(this.data.pageIndex*50,(this.data.pageIndex+1)*50).map((e,i) => ({...eventView(e,[]),draftIndex:this.data.pageIndex*50+i,
      mappingLabel:this._mappings[this.data.pageIndex*50+i] ? this.data.mappingLabels[this._old.findIndex(e=>e.id===this._mappings[this.data.pageIndex*50+i])+1] : ''}))}); },
  page(event) { const index=this.data.pageIndex+Number(event.currentTarget.dataset.delta); if (index<0 || index>=this.data.pageCount) return; this.setData({pageIndex:index});this.refreshRows();wx.pageScrollTo({scrollTop:0}); },
  refreshMappings() {
    const source = this.data.sources[this.data.sourceIndex];
    this._old = source ? this._calendar.events.filter(e => e.contributions.some(c => c.source_id === source.id)) : [];
    this.setData({ mappingLabels: ['作为新增安排', ...this._old.map(e => { const c = e.contributions.find(c => c.source_id === source.id); return `${c.value.date || '日期待确认'} ${c.value.start || ''} ${c.value.title.slice(0,30)}`; })] });
  },
  field(event) { this._generation++; this.setData({ [event.currentTarget.dataset.field]: event.detail.value, preview: null, error: '' }); this._preview = null; },
  mode(event) { this._generation++; this.setData({ mode: Number(event.detail.value), preview: null }); this._preview = null; },
  source(event) { this._generation++; this.setData({ sourceIndex: Number(event.detail.value), preview: null }); this._mappings = {}; this._preview = null; this.refreshMappings(); this.refreshRows(); },
  map(event) { this._generation++; const index = event.currentTarget.dataset.index, selected = Number(event.detail.value); if (selected) this._mappings[index] = this._old[selected - 1].id; else delete this._mappings[index];
    const rows = this.data.rows.map(row => row.draftIndex === Number(index) ? { ...row, mappingLabel: this.data.mappingLabels[selected] } : row);
    this.setData({ rows, preview: null }); this._preview = null; },
  cancellations(event) { this._generation++; const visible = new Set(this.data.preview.cancelled.map(e=>e.id)); this._cancel = [...this._cancel.filter(id=>!visible.has(id)),...event.detail.value]; this._preview = null; this.setData({ acknowledged: false }); },
  correction(event) { this._generation++; this._choices[event.currentTarget.dataset.id] = event.detail.value; this._preview = null; this.setData({ acknowledged: false }); },
  batch() {
    this._generation++;
    const { batchDate, batchStart, batchEnd, batchLocation, batchCategory, nextDay } = this.data;
    const rows = this._draft.report.events.concat(this._draft.report.pending);
    for (const e of rows) {
      if (!e.reviews || !e.reviews.length) { const before = JSON.parse(JSON.stringify(e)); delete before.reviews; e.reviews = [{before,edited_at:new Date().toISOString()}]; }
      if (batchDate) e.date = batchDate;
      if (batchStart) { e.start = batchStart; e.end = batchEnd || null; e.precision = batchEnd ? 'interval' : 'point';
        if (batchEnd && e.date) { const d = new Date(`${e.date}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + (nextDay ? 1 : 0)); e.end_date = d.toISOString().slice(0, 10); } else e.end_date = null; }
      if (batchLocation) e.location = batchLocation;
      if (batchCategory) e.category = batchCategory;
      e.field_basis = { ...(e.field_basis || {}), ...Object.fromEntries([['date', batchDate], ['start', batchStart], ['location', batchLocation], ['category', batchCategory]].filter(v => v[1]).map(v => [v[0], '手动修正'])) };
    }
    this.refreshRows(); this.setData({ preview: null, error: '已更新草稿，请核对下方内容后重新预览。待确认项加入后仍需逐项确认。' }); this._preview = null;
  },
  async preview() {
    if (this.data.busy || !this._draft) return;
    this.setData({ busy: true, error: '' });
    const generation = this._generation;
    try {
      const source = this.data.sources[this.data.sourceIndex];
      if (this.data.mode && !source) throw Error('请先建立来源，再使用更新模式');
      const operation = { type: this.data.mode ? 'update' : 'append', report: this._draft.report,
        rules: this._draft.rules || {},
        source_name: this.data.sourceName || '个人安排', source_id: this.data.mode ? source.id : this._draft.sourceId || undefined,
        coverage: this.data.mode ? [this.data.from, this.data.to] : undefined, mappings: this.data.mode ? this._mappings : {},
        cancel_ids: this._cancel, correction_choices: this._choices };
      const result = await api.transform(this._calendar, operation);
      if (generation !== this._generation) throw Error('预览期间草稿已变化，请重新计算');
      this._preview = result;
      this._summary = result.summary;
      this.setData({changeIndex:0,acknowledged:!result.summary.unresolved.length});this.showChanges();
    } catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: false }); }
  },
  showChanges() {
    const s=this._summary,start=this.data.changeIndex*50,end=start+50;
    const visible = e=>({id:e.id,date:e.date,start:e.start,end:e.end,title:e.title,location:e.location});
    this.setData({changePages:Math.ceil(Math.max(s.cancelled.length,s.changed.length,s.correction_conflicts.length)/50),preview:{added:s.added.length,pending:this._draft.report.pending.length,duplicates:s.duplicates,
      cancelled:s.cancelled.slice(start,end).map(e=>({...visible(e),checked:this._cancel.includes(e.id)})),changed:s.changed.slice(start,end).map(c=>({id:c.id,before:visible(c.before),after:visible(c.after),label:(c.kinds||[]).join('、')})),
      warnings:s.warnings,unresolvedCount:s.unresolved.length,corrections:s.correction_conflicts.slice(start,end).map(c=>({...c,choice:this._choices[c.id]}))}});
  },
  changePage(event) { const index=this.data.changeIndex+Number(event.currentTarget.dataset.delta);if(index<0 || index>=this.data.changePages)return;this.setData({changeIndex:index});this.showChanges(); },
  save() {
    if (!this._preview || this.data.busy) return this.setData({ error: '请先重新预览' });
    try {
      store.commit(getApp().globalData, this._preview, this._draft.year);
      getApp().globalData.draft = null;
      wx.switchTab({ url: '/pages/timeline/timeline' });
    } catch (error) { this.setData({ error: error.message }); }
  }
});
