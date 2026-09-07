const api = require('../../utils/api');
const storage = require('../../utils/storage');
const { formFor, validate, historyFor } = require('../../utils/review');
const { eventView } = require('../../utils/timeline');

Page({
  data: { form: { date: '', start: '', end: '', title: '', shift: '', location: '', notes: '', next_day: false },
    errors: {}, error: '', busy: false, sources: [], warnings: [], history: [], showEvidence: false, isPending: false },
  onLoad(options) {
    const state = getApp().globalData;
    this._calendar = state.calendar;
    if (options.manual) { this._manual = true; this.setData({ manual: true, form: { ...this.data.form, category: '其他', all_day: false } }); return; }
    const report = state.report;
    const record = report && [...report.events, ...report.pending].find(item => item.id === options.id);
    if (!record) { this.setData({ error: '这条记录已变化，请返回时间线重新选择', unavailable: true }); return; }
    this._report = report;
    this._eventId = record.id;
    this.setData({ form: { ...formFor(record), category: record.category || '其他', all_day: record.all_day || false }, sources: eventView(record, []).sources, warnings: record.warnings,
      history: historyFor(record), isPending: record.status === 'pending' });
    if (state.calendar) this.setData({ basis: Object.entries(record.field_basis || {}).map(([k,v]) => `${k}：${v}`).join(' · ') });
    const ids = [...new Set(record.sources.map(s => s.evidence && s.evidence.image).filter(id => /^[a-f0-9]{20}$/.test(id)))];
    if (wx.env) this.setData({ images: ids.map(id => `${wx.env.USER_DATA_PATH}/xingcheng/evidence-${id}.jpg`) });
  },
  fieldChange(event) {
    if (this.data.busy) return;
    const field = event.currentTarget.dataset.field;
    if (!(field in this.data.form)) return;
    this.setData({ form: { ...this.data.form, [field]: event.detail.value }, errors: { ...this.data.errors, [field]: '' }, error: '' });
  },
  clearTime(event) {
    if (this.data.busy) return;
    const field = event.currentTarget.dataset.field;
    const form = { ...this.data.form, [field]: '' };
    if (field === 'start') { form.end = ''; form.next_day = false; }
    if (field === 'end') form.next_day = false;
    this.setData({ form, errors: {}, error: '' });
  },
  toggleEvidence() { this.setData({ showEvidence: !this.data.showEvidence }); },
  async save() {
    if (this.data.busy || this.data.unavailable) return;
    const { errors, values } = validate(this.data.form);
    this.setData({ errors, error: '' });
    if (Object.keys(errors).length) return;
    const state = getApp().globalData;
    if (!this._manual && state.report !== this._report) return this.setData({ error: '时间线已变化，请返回后重新选择，避免覆盖新结果' });
    this.setData({ busy: true });
    try {
      if (this._calendar || this._manual) {
        const store = require('../../utils/calendar-store');
        if (!this._calendar) throw Error('请先导入安排建立具名个人日历');
        const day = values.end ? new Date(`${values.date}T00:00:00Z`) : null;
        if (day && values.next_day) day.setUTCDate(day.getUTCDate() + 1);
        const { next_day, ...fields } = values;
        Object.assign(fields, { end_date: day ? day.toISOString().slice(0, 10) : null, precision: values.end ? 'interval' : values.start ? 'point' : 'date',
          status: 'confirmed', category: this.data.form.category || '其他', all_day: this.data.form.all_day });
        const preview = await api.transform(this._calendar, { type: this._manual ? 'manual' : 'edit', event_id: this._eventId, values: fields });
        store.commit(state, preview, state.referenceYear);
        wx.navigateBack({ fail: () => wx.switchTab({ url: '/pages/timeline/timeline' }) });
        return;
      }
      const report = await api.review(this._report, [{ event_id: this._eventId, values }]);
      if (state.report !== this._report) throw new Error('时间线已变化，本次修正未覆盖新结果，请返回重试');
      storage.commit(state, report, state.personName, state.referenceYear);
      wx.navigateBack({ fail: () => wx.redirectTo({ url: '/pages/timeline/timeline' }) });
    } catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: false }); }
  },
  async hide() {
    if (!this._calendar || this.data.busy) return;
    this.setData({ busy: true, error: '' });
    try { const result = await api.transform(this._calendar, { type: 'hide', event_id: this._eventId });
      require('../../utils/calendar-store').commit(getApp().globalData, result, getApp().globalData.referenceYear);
      wx.navigateBack();
    } catch (error) { this.setData({ error: error.message }); } finally { this.setData({ busy: false }); }
  },
  cancel() { if (!this.data.busy) wx.navigateBack({ fail: () => wx.redirectTo({ url: '/pages/timeline/timeline' }) }); }
});
