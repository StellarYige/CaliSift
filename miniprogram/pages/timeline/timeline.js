const { buildTimeline } = require('../../utils/timeline');
const storage = require('../../utils/storage');
const daily = require('../../utils/daily');
const { eventView } = require('../../utils/timeline');

Page({
  data: { name: '', groups: [], pending: [], files: [], warnings: [], count: 0, pendingCount: 0, fileCount: 0, conflictCount: 0, showDiagnostics: false,
    query: '', dateFilter: '', sourceIndex: 0, view: 'daily', month: daily.localDay().slice(0, 7), sources: [] },
  onLoad() {
    this.onShow();
  },
  onShow() {
    const state = getApp().globalData;
    if (!state.report) { this.setData({ firstUse: true, persistenceError: state.persistenceError || '' }); return; }
    const settings = state.calendar ? state.calendar.settings : {};
    const sources = [{ id: '', name: '全部来源' }, ...(state.calendar ? state.calendar.sources : [])];
    const selected = daily.select(state.report, state.calendar, { query: this.data.query, date: this.data.dateFilter,
      source: (sources[this.data.sourceIndex] || {}).id, hideRest: settings.hideRest });
    this._filtered = selected.report;
    this.setData({ name: state.personName, persistenceError: state.persistenceError || '', savedLocally: !!state.savedAt,
      ...buildTimeline(selected.report, Math.min(this.data.pageIndex || 0, Math.max(0, Math.ceil(selected.report.events.length / 50) - 1))),
      firstUse: false, large: settings.large, sources: sources.map(s => ({ id: s.id, name: s.name })), today: selected.today,
      todayEvents: selected.todayEvents.slice(0, 50).map(e => eventView(e, state.report.conflicts)),
      nextEvent: selected.next ? eventView(selected.next, state.report.conflicts) : null,
      weekEvents: selected.upcoming.slice(0, 50).map(e => eventView(e, state.report.conflicts)),
      monthCells: daily.monthCells(this.data.month, selected.report.events), hasUpdate: !!(state.calendar && state.calendar.undo) });
    if (settings.colors) this.setData({ groups: this.data.groups.map(g => ({ ...g, events: g.events.map(e => ({ ...e, color: settings.colors[e.category] || '#6a59d7' })) })) });
  },
  filter(event) { this.setData({ [event.currentTarget.dataset.field]: event.detail.value, pageIndex: 0 }); this.onShow(); },
  clearFilters() { this.setData({ query: '', dateFilter: '', sourceIndex: 0, pageIndex: 0 }); this.onShow(); },
  toggleFilters() { this.setData({ showFilters: !this.data.showFilters }); },
  view(event) { this.setData({ view: event.currentTarget.dataset.view }); this.onShow(); },
  month(event) { const d = new Date(`${this.data.month}-01T12:00:00`); d.setMonth(d.getMonth() + Number(event.currentTarget.dataset.delta)); this.setData({ month: daily.localDay(d).slice(0, 7) }); this.onShow(); },
  day(event) { if (!event.currentTarget.dataset.date) return; this.setData({ dateFilter: event.currentTarget.dataset.date, view: 'timeline', pageIndex: 0 }); this.onShow(); },
  add() { wx.navigateTo({ url: '/pages/review/review?manual=yes' }); },
  importFiles() { wx.switchTab({ url: '/pages/upload/upload' }); },
  editEvent(event) { wx.navigateTo({ url: `/pages/review/review?id=${encodeURIComponent(event.currentTarget.dataset.id)}` }); },
  retrySave() {
    const state = getApp().globalData;
    storage.commit(state, state.report, state.personName, state.referenceYear);
    this.onShow();
  },
  toggleEvent(event) {
    const id = event.currentTarget.dataset.id;
    this.setData({ groups: this.data.groups.map(group => ({ ...group,
      events: group.events.map(item => item.id === id ? { ...item, expanded: !item.expanded } : item) })) });
  },
  toggleDiagnostics() { this.setData({ showDiagnostics: !this.data.showDiagnostics }); },
  changePage(event) {
    const pending = event.currentTarget.dataset.section === 'pending';
    const delta = Number(event.currentTarget.dataset.delta);
    const pageIndex = pending ? this.data.pageIndex : this.data.pageIndex + delta;
    const pendingIndex = pending ? this.data.pendingPageIndex + delta : this.data.pendingPageIndex;
    if (pageIndex < 0 || pageIndex >= Math.max(1, this.data.pageCount) || pendingIndex < 0 || pendingIndex >= Math.max(1, this.data.pendingPageCount)) return;
    this.setData(buildTimeline(this._filtered || getApp().globalData.report, pageIndex, pendingIndex));
    wx.pageScrollTo({ scrollTop: 0, duration: 0 });
  },
  goBack() { wx.switchTab({ url: '/pages/upload/upload' }); }
});
