const store = require('../../utils/calendar-store');
const api = require('../../utils/api');
Page({
  data: { name: '', error: '', busy: false, hidden: [], sources: [], sourceIndex: 0, alarms: ['不提醒', '提前十五分钟', '提前三十分钟', '提前一小时', '提前一天'], alarmIndex: 0,
    from: '', to: '', category: '', large: false, hideRest: false, colorCategory: '工作', color: '#6a59d7', colors: ['#6a59d7', '#207968', '#a26823', '#bb4d6a'], colorIndex: 0 },
  onShow() {
    const state = getApp().globalData, c = state.calendar;
    this.setData({ name: state.personName, savedAt: state.savedAt, error: state.persistenceError || '', hasCalendar: !!c,
      hidden: c ? c.events.filter(e => e.hidden).map(e => ({ id: e.id, title: e.overrides.title || e.base.title, date: e.overrides.date || e.base.date })) : [],
      sources: [{ id: '', name: '全部来源' }, ...(c ? c.sources.map(s => ({ id: s.id, name: s.name })) : [])],
      large: !!(c && c.settings.large), hideRest: !!(c && c.settings.hideRest), canUndo: !!(c && c.undo) });
  },
  field(event) { this.setData({ [event.currentTarget.dataset.field]: event.detail.value }); },
  rules() { wx.navigateTo({ url: '/pages/rules/rules' }); },
  async operation(operation) {
    const state = getApp().globalData;
    if (!state.calendar || this.data.busy) return;
    this.setData({ busy: true, error: '' });
    try { const result = await api.transform(state.calendar, operation); store.commit(state, result, state.referenceYear); this.onShow(); }
    catch (error) { this.setData({ error: error.message }); }
    finally { this.setData({ busy: false }); }
  },
  settings() {
    const c = getApp().globalData.calendar;
    if (!c) return;
    this.operation({ type: 'settings', settings: { ...c.settings, large: this.data.large, hideRest: this.data.hideRest,
      colors: { ...(c.settings.colors || {}), [this.data.colorCategory || '工作']: this.data.colors[this.data.colorIndex] } } });
  },
  restoreHidden(event) { this.operation({ type: 'restore', event_id: event.currentTarget.dataset.id }); },
  undo() { wx.showModal({ title: '撤销最近一次来源更新？', content: '将恢复该次更新前的安排，日历修订序号继续递增。', success: r => { if (r.confirm) this.operation({ type: 'undo' }); } }); },
  share(path) {
    wx.shareFileMessage({ filePath: path, fail: error => { if (!/cancel/i.test(error.errMsg || '')) this.setData({ error: '文件已保存到本机，请重试分享' }); } });
  },
  backup() { try { const path = store.backup(getApp().globalData); this.share(path); } catch (error) { this.setData({ error: error.message }); } },
  restoreBackup() {
    wx.chooseMessageFile({ count: 1, type: 'file', extension: ['json'], success: result => {
      try {
        if (result.tempFiles[0].size > 40 * 1024 * 1024) throw Error('备份文件超过 40 MiB');
        const snapshot = store.unpack(wx.getFileSystemManager().readFileSync(result.tempFiles[0].path, 'utf8'));
        const state = getApp().globalData, version = state.calendar && state.calendar.version;
        wx.showModal({ title: '恢复此备份？', content: `${snapshot.calendar.personName} · ${snapshot.calendar.events.length} 条安排 · ${snapshot.calendar.sources.length} 个来源。会替换当前日历，上一份本机快照仍保留。`,
          success: r => {
            if (!r.confirm) return;
            try {
              if ((state.calendar && state.calendar.version) !== version) throw Error('当前日历已变化，请重新选择备份');
              snapshot.calendar.version = Math.max(version || 0, snapshot.calendar.version) + 1;
              const sequences = new Map(state.calendar ? state.calendar.events.map(e => [e.id,e.sequence]) : []);
              for (const e of snapshot.calendar.events) if (sequences.has(e.id)) e.sequence = Math.max(e.sequence,sequences.get(e.id)) + 1;
              const restoredSequences = new Map(snapshot.calendar.events.map(e => [e.id,e.sequence]));
              for (const e of [...snapshot.report.events,...snapshot.report.pending]) e.sequence = restoredSequences.get(e.id);
              snapshot.calendar.undo = null;
              store.write(state, snapshot); this.onShow();
            } catch (error) { this.setData({ error: error.message }); }
          } });
      } catch (error) { this.setData({ error: error.message || '备份无法读取' }); }
    } });
  },
  async export() {
    const state = getApp().globalData;
    if (!state.calendar || this.data.busy) return;
    this.setData({ busy: true, error: '' });
    try {
      const content = await api.request('/api/calendar/export', { calendar: state.calendar, options: { from: this.data.from, to: this.data.to,
        source_id: (this.data.sources[this.data.sourceIndex] || {}).id, category: this.data.category, alarm: [0, 15, 30, 60, 1440][this.data.alarmIndex] } });
      if (typeof content !== 'string' || !content.startsWith('BEGIN:VCALENDAR')) throw Error('日历文件生成失败');
      const path = `${wx.env.USER_DATA_PATH}/xingcheng-${Date.now()}.ics`;
      wx.getFileSystemManager().writeFileSync(path, content, 'utf8'); this.share(path);
    } catch (error) { this.setData({ error: error.message }); } finally { this.setData({ busy: false }); }
  },
  clear() { wx.showModal({ title: '清除当前日历？', content: '会清除当前安排、来源和修正历史。请先分享备份文件到你要保存的位置。', confirmText: '清除', success: r => {
    if (!r.confirm) return;
    try { store.clear(getApp().globalData); this.onShow(); } catch (error) { this.setData({ error: error.message }); }
  } }); },
  switchPerson() {
    const name = this.data.name.normalize('NFKC').trim(), state = getApp().globalData;
    if (!name || name.length > 80 || /[\s、,;；，/|]/.test(name)) return this.setData({ error: '请输入一个完整姓名' });
    if (name === state.personName && state.calendar) return;
    wx.showModal({ title: '切换个人日历？', content: `将建立“${name}”的空日历。旧姓名的日历请先导出备份，恢复备份可以切换回来。`, success: r => {
      if (!r.confirm) return;
      try { const calendar = store.empty(name); calendar.version = (state.calendar ? state.calendar.version : 0) + 1;
        store.write(state, { schema: 2, calendar, report: { events: [], pending: [], files: [], warnings: [], conflicts: [] }, referenceYear: new Date().getFullYear(), savedAt: new Date().toISOString() });
        state.draft = null; this.onShow();
      } catch (error) { this.setData({ error: error.message }); }
    } });
  }
});
