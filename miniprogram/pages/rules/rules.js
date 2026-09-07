const api = require('../../utils/api');
const store = require('../../utils/calendar-store');
Page({
  data: { sources: [], index: 0, error: '', busy: false, name: '', aliases: '', shiftName: '', start: '', end: '', nextDay: false, shifts: [],
    monday: '', weeks: 20, periodsText: '', courseTitle: '', location: '', weekday: 1, periodFrom: 1, periodTo: 2, weekFrom: 1, weekTo: 20,
    parity: 0, parityLabels: ['全部周', '单周', '双周'], specificWeeks: '', templateLayout: 0, layouts: ['逐行明细表', '姓名在行、日期在列', '姓名在列、日期在行'], headerRow: 1,
    nameColumn: 1, dateColumn: 2, titleColumn: 3, timeColumn: 4, templateSheet: '', preview: null },
  onLoad(options) {
    const c = getApp().globalData.calendar;
    if (!c) return this.setData({ error: '请先建立个人日历' });
    this._calendar = c;
    const sources = c.sources.map(s => ({ id: s.id, name: s.name }));
    this.setData({ sources, index: Math.max(0, sources.findIndex(s => s.id === options.id)) }); this.loadSource();
  },
  loadSource() {
    const s = this._calendar.sources[this.data.index];
    if (!s) return;
    const rules = s.rules || {}, semester = rules.semester || {};
    this._rules = JSON.parse(JSON.stringify(rules));
    this.setData({ name: s.name, shifts: rules.shifts || [], monday: semester.monday || '', weeks: semester.weeks || 20,
      periodsText: (semester.periods || []).map(p => `${p.start}-${p.end}`).join('\n'), templateSaved: !!rules.template, preview: null,
      revisions:s.revisions.map(r=>({id:r.id,importedAt:r.imported_at,coverage:r.coverage ? r.coverage.join(' 至 ') : '追加导入',files:r.report.files.map(f=>f.filename).join('、')})) });
    this._sheets = s.revisions.flatMap(r => r.report.files.flatMap(f => f.sheets)).filter(s => s.preview && s.preview.length);
    this.setData({ tableSheets: this._sheets.map((s, i) => ({ label: `${i + 1}. ${s.sheet}` })), tablePreview: this._sheets[0] ? this._sheets[0].preview : [], sheetIndex: 0 });
  },
  source(event) { this.setData({ index: Number(event.detail.value) }); this.loadSource(); },
  field(event) { this.setData({ [event.currentTarget.dataset.field]: event.detail.value, preview: null }); if(event.currentTarget.dataset.field==='sheetIndex') this.setData({tablePreview:this._sheets[Number(event.detail.value)].preview}); this._preview = null; },
  addShift() {
    const s = { name: this.data.shiftName.trim(), aliases: this.data.aliases.split(/[、,，/]/).map(s => s.trim()).filter(Boolean), start: this.data.start, end: this.data.end, next_day: this.data.nextDay };
    if (!s.name || !s.aliases.length || !s.start || !s.end) return this.setData({ error: '请填写班次名称、符号和起止时间' });
    this.setData({ shifts: [...this.data.shifts, s], preview: null, error: '' }); this._preview = null;
  },
  removeShift(event) { this.setData({ shifts: this.data.shifts.filter((_, i) => i !== Number(event.currentTarget.dataset.index)), preview: null }); this._preview = null; },
  config() {
    const rules = { ...(this._rules || {}), shifts: this.data.shifts };
    if (this.data.monday) {
      const periods = this.data.periodsText.trim().split('\n').filter(Boolean).map(line => { const p = line.trim().split(/[-–]/); return { start: (p[0] || '').trim(), end: (p[1] || '').trim() }; });
      rules.semester = { monday: this.data.monday, weeks: Number(this.data.weeks), periods };
    }
    return rules;
  },
  template() {
    const sheet = (this._sheets || [])[Number(this.data.sheetIndex)];
    const header = sheet && sheet.preview[Number(this.data.headerRow) - 1];
    if (!header) return this.setData({ error: '请选择包含表头的来源版本和表头行（局部预览前 20 行）' });
    this._rules = { ...(this._rules || {}), template: { sheet: sheet.sheet, header_row: Number(this.data.headerRow) - 1,
      headers: header.map(c => c.text), layout: ['records', 'names_rows', 'names_columns'][this.data.templateLayout],
      mapping: { name: Number(this.data.nameColumn) - 1, date: Number(this.data.dateColumn) - 1, title: Number(this.data.titleColumn) - 1, time: Number(this.data.timeColumn) - 1 } } };
    this.setData({ templateSaved: true, preview: null, error: '模板已加入草稿，请预览后保存' }); this._preview = null;
  },
  async preview() {
    if (this.data.busy || !this._calendar) return;
    const source = this._calendar.sources[this.data.index];
    if (!source) return this.setData({ error: '请先导入一个来源，再为它配置规则' });
    this.setData({ busy: true, error: '' });
    const fingerprint = JSON.stringify([this.data.index,this.data.name,this.config()]);
    try { const result = await api.transform(this._calendar, { type: 'source_config', source_id: source.id, name: this.data.name, rules: this.config(), apply: true });
      if (fingerprint !== JSON.stringify([this.data.index,this.data.name,this.config()])) throw Error('规则已变化，请重新预览');
      this._preview = result; this.setData({ preview: result.summary.changed.map(c => ({ id: c.id, before: `${c.before.date} ${c.before.start || '时间未注明'} ${c.before.title}`, after: `${c.after.date} ${c.after.start || '时间未注明'}–${c.after.end || ''} ${c.after.title}` })) });
    } catch (error) { this.setData({ error: error.message }); } finally { this.setData({ busy: false }); }
  },
  save() {
    if (!this._preview) return;
    try { store.commit(getApp().globalData, this._preview, getApp().globalData.referenceYear); this._calendar = getApp().globalData.calendar; this.loadSource(); this.setData({ error: '规则已保存' }); }
    catch (error) { this.setData({ error: error.message }); }
  },
  async course() {
    if (!this._calendar || this.data.busy) return;
    this.setData({ busy: true, error: '' });
    try {
      const rules = this.config();
      if (!rules.semester) throw Error('请设置第一教学周周一和节次时间');
      const a = Number(this.data.periodFrom), b = Number(this.data.periodTo);
      if (!Number.isInteger(a) || !Number.isInteger(b) || b < a || b - a > 30) throw Error('连续节次范围无效');
      const course = { title: this.data.courseTitle, location: this.data.location, weekday: Number(this.data.weekday), periods: Array.from({length: b - a + 1}, (_, i) => a + i),
        week_from: Number(this.data.weekFrom), week_to: Number(this.data.weekTo), parity: ['all', 'odd', 'even'][this.data.parity],
        weeks: this.data.specificWeeks ? this.data.specificWeeks.split(/[,，、\s]+/).filter(Boolean).map(Number) : undefined };
      const report = await api.request('/api/calendar/course', { course, semester: rules.semester });
      getApp().globalData.draft = { report, rules, name: this._calendar.personName, year: new Date().getFullYear(), sourceName: `${this.data.courseTitle}课程` };
      wx.navigateTo({ url: '/pages/confirm/confirm' });
    } catch (error) { this.setData({ error: error.message }); } finally { this.setData({ busy: false }); }
  }
});
