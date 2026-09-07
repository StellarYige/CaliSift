const legacy = require('./storage');
const clone = value => JSON.parse(JSON.stringify(value));
const POINTER = 'xingcheng.calendar.pointer.v2';
const MAX_BYTES = 40 * 1024 * 1024;
const empty = name => ({ schema: 2, version: 0, personName: name, sources: [], events: [], settings: {}, undo: null });
const id = () => `local-${Date.now()}-${Math.random().toString(36).slice(2)}`;
function validEvent(e) {
  if (!e || typeof e.title !== 'string' || !e.title.trim() || !['confirmed','pending'].includes(e.status)) return false;
  if (e.date !== null) { const d = new Date(`${e.date}T00:00:00Z`); if (!Number.isFinite(d.getTime()) || d.toISOString().slice(0,10) !== e.date) return false; }
  if (e.status === 'confirmed' && !e.date) return false;
  for (const k of ['start','end']) if (e[k] && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(e[k])) return false;
  if (e.precision === 'interval' && (!e.start || !e.end || (e.date && `${e.end_date || e.date}T${e.end}` <= `${e.date}T${e.start}`))) return false;
  if (e.precision === 'point' && (!e.start || e.end || e.end_date)) return false;
  if (e.precision === 'date' && (e.start || e.end || e.end_date)) return false;
  return ['interval','point','date'].includes(e.precision) && Array.isArray(e.sources) && Array.isArray(e.notes) && Array.isArray(e.warnings);
}
function hash(text) { let value = 2166136261; for (let i = 0; i < text.length; i++) { value ^= text.charCodeAt(i); value = Math.imul(value, 16777619); } return (value >>> 0).toString(16); }
function valid(snapshot) {
  const c = snapshot && snapshot.calendar;
  return snapshot && snapshot.schema === 2 && c && c.schema === 2 && Number.isInteger(c.version) && c.version >= 0 &&
    typeof c.personName === 'string' && !!c.personName.trim() && c.personName.length <= 80 &&
    Array.isArray(c.sources) && c.sources.length <= 100 && Array.isArray(c.events) && c.events.length <= 5000 &&
    new Set(c.sources.map(s => s.id)).size === c.sources.length && new Set(c.events.map(e => e.id)).size === c.events.length &&
    c.sources.every(s => typeof s.id === 'string' && typeof s.name === 'string' && Array.isArray(s.revisions) && s.revisions.length <= 3) &&
    c.events.every(e => typeof e.id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(e.id) && Number.isInteger(e.sequence) && e.sequence >= 0 && validEvent(e.base) &&
      typeof e.base.title === 'string' && (e.base.date === null || /^\d{4}-\d\d-\d\d$/.test(e.base.date)) &&
      typeof e.hidden === 'boolean' && e.overrides && Array.isArray(e.contributions) &&
      e.contributions.every(v => c.sources.some(s => s.id === v.source_id) && validEvent(v.value)) &&
      validEvent({ ...(e.contributions[0] ? e.contributions[0].value : e.base), ...e.overrides })) &&
    legacy.validReport(snapshot.report);
}
function root(wxApi) { return `${wxApi.env.USER_DATA_PATH}/xingcheng`; }
function pack(snapshot) { const payload = JSON.stringify(snapshot); return JSON.stringify({ checksum: hash(payload), payload }); }
function unpack(text) {
  const envelope = JSON.parse(text);
  if (typeof envelope.payload !== 'string' || envelope.checksum !== hash(envelope.payload)) throw Error('备份校验失败');
  const snapshot = JSON.parse(envelope.payload);
  if (!valid(snapshot)) throw Error('日历格式无效或超过本机容量限制');
  return snapshot;
}
function install(state, snapshot) { Object.assign(state, { calendar: snapshot.calendar, report: snapshot.report, personName: snapshot.calendar.personName,
  referenceYear: snapshot.referenceYear, savedAt: snapshot.savedAt, persistenceError: '' }); }
function evidence(value, wxApi, writing) {
  const fs = wxApi.getFileSystemManager(), dir = root(wxApi);
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (key === 'crops' && child && typeof child === 'object') {
      for (const [id, data] of Object.entries(child)) {
        if (!/^[a-f0-9]{20}$/.test(id)) throw Error('图片证据标识无效');
        const path = `${dir}/evidence-${id}.jpg`;
        if (typeof data !== 'string') throw Error('图片证据格式无效');
        if (writing) {
          if (!data.startsWith('evidence:')) {
            if (!/^[A-Za-z0-9+/=]+$/.test(data)) throw Error('图片证据格式无效');
            let existing = null;
            try { existing = fs.readFileSync(path, 'base64'); } catch (_) { /* new evidence file */ }
            if (existing !== null && existing !== data) throw Error('图片证据标识冲突，原文件已保留');
            if (existing === null) fs.writeFileSync(path, data, 'base64');
            const check = fs.readFileSync(path, 'base64');
            if (check !== data) throw Error('图片证据写入失败');
            child[id] = `evidence:${id}:${hash(data)}`;
          } else {
            if (data !== `evidence:${id}:${hash(fs.readFileSync(path, 'base64'))}`) throw Error('图片证据损坏');
          }
        } else if (data.startsWith('evidence:')) {
          const bytes = fs.readFileSync(path, 'base64');
          if (data !== `evidence:${id}:${hash(bytes)}`) throw Error('图片证据损坏');
          child[id] = bytes;
        }
      }
    } else evidence(child, wxApi, writing);
  }
}
function referencedImages(value, ids = new Set()) {
  if (!value || typeof value !== 'object') return ids;
  for (const [key, child] of Object.entries(value)) {
    if (key === 'image' && typeof child === 'string' && /^[a-f0-9]{20}$/.test(child)) ids.add(child);
    else if (child && typeof child === 'object') referencedImages(child, ids);
  }
  return ids;
}
function write(state, snapshot, wxApi = wx) {
  if (!valid(snapshot)) throw Error('日历格式无效，原日历已保留');
  const fs = wxApi.getFileSystemManager(), dir = root(wxApi);
  try { fs.accessSync(dir); } catch (_) { fs.mkdirSync(dir, true); }
  snapshot = clone(snapshot);
  evidence(snapshot, wxApi, true);
  const serialized = pack(snapshot);
  if (encodeURIComponent(serialized).replace(/%[A-F\d]{2}/g, 'x').length > MAX_BYTES) throw Error('本机空间上限，请先备份并清理');
  const previous = wxApi.getStorageSync(POINTER);
  const slot = previous && previous.current === 'a' ? 'b' : 'a';
  const path = `${dir}/${slot}.json`;
  try {
    fs.writeFileSync(path, serialized, 'utf8');
    unpack(fs.readFileSync(path, 'utf8'));
    wxApi.setStorageSync(POINTER, { current: slot, previous: previous && previous.current });
  } catch (_) { throw Error('保存失败，原日历已保留。请清理本机空间后重试'); }
  install(state, snapshot);
}
function commit(state, preview, year, wxApi = wx) {
  const version = state.calendar ? state.calendar.version : 0;
  if (version !== preview.base_version || (state.calendar && preview.calendar.personName !== state.calendar.personName)) throw Error('日历已变化，请重新预览');
  if (preview.calendar.version !== version + 1) throw Error('服务器日历版本无效，请重新预览');
  if (preview.summary && preview.summary.unresolved && preview.summary.unresolved.length) throw Error('请先确认变更对应关系和个人修正');
  write(state, { schema: 2, calendar: preview.calendar, report: preview.report, referenceYear: Number(year), savedAt: new Date().toISOString() }, wxApi);
}
function migrate(snapshot) {
  const calendar = empty(snapshot.personName);
  const report = clone(snapshot.report);
  const sourceMap = new Map();
  for (const event of [...report.events, ...report.pending]) for (const s of event.sources) {
    const key = s.file_id || s.filename;
    if (!sourceMap.has(key)) {
      const source = { id: id(), name: s.filename, rules: {}, revisions: [] };
      sourceMap.set(key, source); calendar.sources.push(source);
    }
  }
  for (const source of calendar.sources) source.revisions.push({ id: id(), imported_at: snapshot.savedAt, coverage: null,
    report: { events: [], pending: [], files: report.files.filter(f => f.filename === source.name), warnings: [], conflicts: [] } });
  const remap = new Map();
  for (const event of [...report.events, ...report.pending]) {
    const stableId = id(); remap.set(event.id, stableId);
    const current = clone(event);
    const original = event.reviews && event.reviews.length ? clone(event.reviews[0].before) : clone(event);
    original.precision = original.precision || (original.end ? 'interval' : original.start ? 'point' : 'date');
    original.status = original.status || (original.date ? 'confirmed' : 'pending');
    delete original.reviews;
    const contributions = [...new Set(event.sources.map(s => s.file_id || s.filename))].map(key => {
      const source = sourceMap.get(key), value = { ...clone(original), sources: original.sources.filter(s => (s.file_id || s.filename) === key) };
      source.revisions[0].report[value.status === 'pending' ? 'pending' : 'events'].push(clone(value));
      return { source_id: source.id, revision_id: source.revisions[0].id, value, raw: clone(value) };
    });
    const overrides = {};
    if (event.reviews && event.reviews.length) for (const k of ['date', 'title', 'shift', 'start', 'end', 'end_date', 'precision', 'location', 'notes', 'status']) overrides[k] = current[k];
    calendar.events.push({ id: stableId, sequence: (event.reviews || []).length, base: original, contributions, overrides, hidden: false, cancelled: false, history: current.reviews || [] });
    event.id = stableId;
  }
  for (const conflict of report.conflicts) conflict.event_ids = conflict.event_ids.map(v => remap.get(v) || v);
  return { schema: 2, calendar, report, referenceYear: snapshot.referenceYear, savedAt: snapshot.savedAt || new Date().toISOString() };
}
function restore(state, wxApi = wx) {
  try {
    const pointer = wxApi.getStorageSync(POINTER);
    if (pointer) {
      for (const slot of [pointer.current, pointer.previous]) {
        if (!['a', 'b'].includes(slot)) continue;
        try {
          const snapshot = unpack(wxApi.getFileSystemManager().readFileSync(`${root(wxApi)}/${slot}.json`, 'utf8'));
          evidence(clone(snapshot), wxApi, true);
          for (const id of referencedImages(snapshot)) wxApi.getFileSystemManager().accessSync(`${root(wxApi)}/evidence-${id}.jpg`);
          install(state, snapshot);
          if (slot !== pointer.current) {
            wxApi.setStorageSync(POINTER, { current: slot });
            state.persistenceError = '上次写入不完整，已恢复上一份完整日历';
          }
          return;
        } catch (_) { /* try the last complete snapshot */ }
      }
      throw Error('本机日历无法读取，请从备份恢复；原文件已保留');
    }
    const prior = legacy.restore(wxApi);
    if (prior.error) throw Error(prior.error);
    if (prior.snapshot) write(state, migrate(prior.snapshot), wxApi);
  } catch (error) { state.persistenceError = error.message; }
}
function backup(state, wxApi = wx) {
  if (!state.calendar) throw Error('暂无日历可备份');
  const path = `${root(wxApi)}/backup-${Date.now()}.json`;
  const snapshot = clone({ schema: 2, calendar: state.calendar, report: state.report, referenceYear: state.referenceYear, savedAt: state.savedAt });
  evidence(snapshot, wxApi, false);
  // Old events may outlive the last three import revisions; include every still-referenced crop.
  snapshot.evidence = { crops: {} };
  for (const id of referencedImages(snapshot)) snapshot.evidence.crops[id] = wxApi.getFileSystemManager().readFileSync(`${root(wxApi)}/evidence-${id}.jpg`, 'base64');
  wxApi.getFileSystemManager().writeFileSync(path, pack(snapshot), 'utf8');
  return path;
}
function clear(state, wxApi = wx) {
  // Tombstone is committed first; interrupted cleanup cannot resurrect a v1 calendar.
  const cleared = { schema: 2, calendar: empty(state.personName || '星辰奕歌'), report: { events: [], pending: [], files: [], warnings: [], conflicts: [] }, savedAt: new Date().toISOString(), referenceYear: new Date().getFullYear() };
  write(state, cleared, wxApi);
  write(state, cleared, wxApi);
  wxApi.removeStorageSync(legacy.KEY);
  const fs = wxApi.getFileSystemManager();
  for (const filename of fs.readdirSync(root(wxApi))) {
    if (/^evidence-[a-f0-9]{20}\.jpg$/.test(filename)) fs.unlinkSync(`${root(wxApi)}/${filename}`);
  }
  state.draft = null;
}
module.exports = { empty, valid, hash, pack, unpack, migrate, restore, write, commit, backup, clear, POINTER };
