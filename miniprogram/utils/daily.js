const REST = new Set(['休', '休息', '轮休', '调休', '公休', '休假', '请假', '年假']);
function localDay(d = new Date()) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function select(report, calendar, filters = {}, now = new Date()) {
  const today = localDay(now), nextWeek = new Date(now); nextWeek.setDate(nextWeek.getDate() + 7);
  const last = localDay(nextWeek);
  const source = filters.source;
  const ids = source && calendar ? new Set(calendar.events.filter(e => e.contributions.some(c => c.source_id === source)).map(e => e.id)) : null;
  const query = (filters.query || '').trim().toLowerCase();
  const sourceNames = new Map(calendar ? calendar.events.map(e => [e.id, e.contributions.map(c => (calendar.sources.find(s => s.id === c.source_id) || {}).name || '').join(' ')]) : []);
  function matches(e) {
    if (ids && !ids.has(e.id)) return false;
    if (filters.hideRest && (REST.has(e.shift) || REST.has(e.title))) return false;
    if (filters.date && !(e.date <= filters.date && (e.end_date || e.date) >= filters.date)) return false;
    return !query || [e.date, e.title, e.location, sourceNames.get(e.id), ...e.sources.map(s => s.filename)].join(' ').toLowerCase().includes(query);
  }
  const events = report.events.filter(matches);
  const todayEvents = events.filter(e => e.date === today || (e.date < today && e.end_date >= today && e.end && new Date(`${e.end_date}T${e.end}:00`) > now));
  const upcoming = events.filter(e => e.date >= today && e.date < last);
  const next = events.find(e => e.start && new Date(`${e.date}T${e.start}:00`) > now);
  return { report: { ...report, events, pending: report.pending.filter(matches) }, today, todayEvents, upcoming, next };
}
function monthCells(month, events) {
  const [year, number] = month.split('-').map(Number);
  const first = new Date(year, number - 1, 1), count = new Date(year, number, 0).getDate();
  const cells = Array.from({ length: (first.getDay() + 6) % 7 }, (_, i) => ({ key: `blank-${i}`, day: '', date: '', count: 0 }));
  for (let day = 1; day <= count; day++) {
    const date = `${month}-${String(day).padStart(2, '0')}`;
    cells.push({ key: date, date, day, count: events.filter(e => e.date <= date && (e.end_date || e.date) >= date).length });
  }
  return cells;
}
module.exports = { localDay, select, monthCells };
