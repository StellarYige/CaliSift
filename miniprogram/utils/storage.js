const KEY = 'xingcheng.latest.v1';
const MAX_BYTES = 900 * 1024;

const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string');
function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
function validRecord(event) {
  return event && typeof event.id === 'string' && typeof event.title === 'string' &&
    (event.date === null || validDate(event.date)) && strings(event.notes) && strings(event.warnings) &&
    Array.isArray(event.sources) && event.sources.every(source => source && typeof source.filename === 'string' &&
      typeof source.sheet === 'string' && typeof source.name_cell === 'string' &&
      (!source.evidence || typeof source.evidence === 'object'));
}

function validReport(report) {
  if (!report || !['events', 'pending', 'files', 'warnings', 'conflicts'].every(key => Array.isArray(report[key]))) return false;
  return [...report.events, ...report.pending].every(e => validRecord(e) &&
    (e.reviews === undefined || (Array.isArray(e.reviews) && e.reviews.every(r => r && validRecord(r.before))))) &&
    report.events.every(e => validDate(e.date)) && strings(report.warnings) &&
    report.files.every(f => f && typeof f.filename === 'string' && Array.isArray(f.sheets) && f.sheets.every(s => s && typeof s.sheet === 'string')) &&
    report.conflicts.every(c => c && strings(c.event_ids));
}

function restore(wxApi = wx) {
  try {
    const snapshot = wxApi.getStorageSync(KEY);
    if (!snapshot) return { snapshot: null, error: '' };
    if (snapshot.version !== 1 || typeof snapshot.personName !== 'string' || !validReport(snapshot.report)) {
      return { snapshot: null, error: '本机保存的结果无法读取，请清除后重新整理' };
    }
    return { snapshot, error: '' };
  } catch (_) { return { snapshot: null, error: '暂时无法读取本机结果，请检查存储空间' }; }
}

function commit(state, report, personName, referenceYear, wxApi = wx) {
  const snapshot = { version: 1, savedAt: new Date().toISOString(), personName, referenceYear: Number(referenceYear), report };
  // Selected files and temporary upload paths never enter this snapshot.
  let error = '';
  try {
    const serialized = JSON.stringify(snapshot);
    const bytes = encodeURIComponent(serialized).replace(/%[A-F\d]{2}/g, 'x').length;
    if (bytes > MAX_BYTES) throw new Error('too large');
    wxApi.setStorageSync(KEY, snapshot);
  } catch (_) { error = '本次结果未能保存到本机，请勿关闭；上次保存的结果仍保留。可清理存储空间后重试保存。'; }
  Object.assign(state, { report, personName, referenceYear: Number(referenceYear), savedAt: error ? '' : snapshot.savedAt, persistenceError: error });
  return error;
}

function clear(state, wxApi = wx) {
  try { wxApi.removeStorageSync(KEY); }
  catch (_) { return '清除失败，本机结果仍保留，请重试'; }
  Object.assign(state, { report: null, personName: '', referenceYear: null, savedAt: '', persistenceError: '' });
  return '';
}

module.exports = { KEY, MAX_BYTES, validReport, restore, commit, clear };
