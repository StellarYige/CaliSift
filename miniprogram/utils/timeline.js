const { historyFor } = require('./review');
function eventView(event, conflicts) {
  const related = conflicts.filter(c => c.event_ids.includes(event.id));
  const crossDay = event.end_date && event.end_date !== event.date;
  const timeLabel = event.start
    ? `${event.start}${event.end ? `–${crossDay ? '次日 ' : ''}${event.end}` : ''}`
    : '时间未注明';
  const sources = (event.sources || []).map((source, index) => ({ ...source, sourceKey: String(index),
    evidenceText: Object.entries(source.evidence || {}).map(([key, value]) => {
      const labels = { date: '日期', time: '时间', start: '开始', end: '结束', title: '事项', shift: '班次', value: '安排', location: '地点', notes: '备注' };
      return `${labels[key] || key}：${value}`;
    }).join(' · ')
  }));
  const { reviews, ...visible } = event;
  return { ...visible, timeLabel, sources, expanded: false, edited: !!(reviews && reviews.length), history: historyFor(event),
    filenameLabel: [...new Set(sources.map(s => s.filename))].join('、'),
    sourceCount: sources.length,
    conflictLabel: related.some(c => c.kind === 'definite') ? '时间冲突' : related.length ? '可能重叠' : '',
    conflictKind: related.some(c => c.kind === 'definite') ? 'definite' : related.length ? 'possible' : '',
    relatedIds: [...new Set(related.flatMap(c => c.event_ids).filter(id => id !== event.id))]
  };
}

const PAGE_SIZE = 50;
function buildTimeline(report, pageIndex = 0, pendingPageIndex = 0) {
  const allEvents = report.events || [];
  const events = allEvents.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE).map(event => eventView(event, report.conflicts || []));
  const titles = new Map(allEvents.map(e => [e.id, `${e.date} ${e.start || '时间未注明'} ${e.title}`]));
  const groups = [];
  for (const event of events) {
    event.relatedLabels = event.relatedIds.map(id => titles.get(id)).filter(Boolean);
    let group = groups.find(group => group.date === event.date);
    if (!group) {
      const parts = event.date.split('-').map(Number);
      const weekday = ['日', '一', '二', '三', '四', '五', '六'][new Date(Date.UTC(parts[0], parts[1] - 1, parts[2])).getUTCDay()];
      group = { date: event.date, label: `${parts[1]}月${parts[2]}日`, weekday: `星期${weekday}`, year: parts[0], events: [] };
      groups.push(group);
    }
    group.events.push(event);
  }
  return { groups, pending: (report.pending || []).slice(pendingPageIndex * PAGE_SIZE, (pendingPageIndex + 1) * PAGE_SIZE).map(e => eventView(e, [])),
    count: allEvents.length, pendingCount: (report.pending || []).length,
    pageIndex, pageCount: Math.ceil(allEvents.length / PAGE_SIZE),
    pendingPageIndex, pendingPageCount: Math.ceil((report.pending || []).length / PAGE_SIZE),
    fileCount: (report.files || []).length, conflictCount: (report.conflicts || []).length,
    files: (report.files || []).map(file => ({ filename: file.filename, status: file.status, error: file.error,
      sheets: (file.sheets || []).map(s => ({ sheet:s.sheet,status:s.status,events:s.events,pending:s.pending,hidden:s.hidden })) })), warnings: report.warnings || [] };
}

module.exports = { eventView, buildTimeline };
