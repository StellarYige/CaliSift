const test = require('node:test');
const assert = require('node:assert/strict');
const store = require('../miniprogram/utils/calendar-store');
const daily = require('../miniprogram/utils/daily');
const legacy = require('../miniprogram/utils/storage');
const event = { id:'original',date:'2026-09-07',title:'早班',start:'08:00',end:'16:00',end_date:'2026-09-07',precision:'interval',status:'confirmed',
  sources:[{file_id:'file',filename:'工作.csv',sheet:'CSV',name_cell:'B2',evidence:{}}],notes:[],warnings:[],reviews:[] };
const report = {events:[event],pending:[],files:[{file_id:'file',filename:'工作.csv',status:'ok',sheets:[]}],warnings:[],conflicts:[]};
function mock() {
  const files = new Map(), values = new Map();
  const fs = { accessSync: () => {}, mkdirSync: () => {}, writeFileSync: (path,text) => files.set(path,text),
    readFileSync: path => { if (!files.has(path)) throw Error('missing'); return files.get(path); },
    readdirSync: dir => [...files.keys()].filter(p => p.startsWith(dir+'/')).map(p => p.slice(dir.length+1)), unlinkSync: p => files.delete(p) };
  return { files, values, fs, env:{USER_DATA_PATH:'/local'}, getFileSystemManager: () => fs, getStorageSync: k => values.get(k),
    setStorageSync: (k,v) => values.set(k,structuredClone(v)), removeStorageSync: k => values.delete(k) };
}
function snapshot() { return store.migrate({personName:'星辰奕歌',report:structuredClone(report),referenceYear:2026,savedAt:'2026-09-07T00:00:00Z'}); }

test('v1 migration preserves corrections and old storage until successful file commit', () => {
  const wxApi=mock(),state={};const prior={version:1,personName:'星辰奕歌',report:structuredClone(report),referenceYear:2026};
  prior.report.events[0].reviews=[{before:structuredClone(event)}]; prior.report.events[0].title='我改的班次';
  wxApi.values.set(legacy.KEY,prior);
  wxApi.fs.writeFileSync=()=>{throw Error('quota');};
  store.restore(state,wxApi);assert.ok(state.persistenceError);assert.ok(wxApi.values.has(legacy.KEY));assert.equal(state.calendar,undefined);
  wxApi.fs.writeFileSync=(p,t)=>wxApi.files.set(p,t);store.restore(state,wxApi);
  assert.equal(state.calendar.events[0].overrides.title,'我改的班次');
  assert.equal(state.calendar.events[0].base.title,'早班');assert.ok(wxApi.values.has(legacy.KEY));
  assert.notEqual(state.report.events[0].id,'original');
});

test('atomic snapshots survive interrupted writes and pointer failures without changing live state', () => {
  const wxApi=mock(),state={};const first=snapshot();store.write(state,first,wxApi);const old=structuredClone(state);
  const next=structuredClone(first);next.calendar.version++;
  wxApi.fs.writeFileSync=(p,t)=>{wxApi.files.set(p,t.slice(0,20));throw Error('interrupted');};
  assert.throws(()=>store.write(state,next,wxApi),/保存失败/);assert.deepEqual(state,old);
  const restored={};store.restore(restored,wxApi);assert.deepEqual(restored.calendar,old.calendar);
  wxApi.fs.writeFileSync=(p,t)=>wxApi.files.set(p,t);wxApi.setStorageSync=()=>{throw Error('quota');};
  assert.throws(()=>store.write(state,next,wxApi),/保存失败/);assert.deepEqual(state,old);
});

test('corrupt latest file falls back to previous complete snapshot', () => {
  const wxApi=mock(),state={};const first=snapshot();store.write(state,first,wxApi);
  const second=structuredClone(first);second.calendar.version=1;store.write(state,second,wxApi);
  const slot=wxApi.values.get(store.POINTER).current;wxApi.files.set(`/local/xingcheng/${slot}.json`,'broken');
  const restored={};store.restore(restored,wxApi);assert.equal(restored.calendar.version,0);assert.match(restored.persistenceError,/恢复/);
});

test('stale previews, unresolved updates, and changed persons cannot overwrite current calendar', () => {
  const wxApi=mock(),state={};const first=snapshot();store.write(state,first,wxApi);
  const preview={base_version:0,calendar:{...first.calendar,version:1},report:first.report,summary:{unresolved:[]}};
  store.commit(state,preview,2026,wxApi);assert.throws(()=>store.commit(state,preview,2026,wxApi),/已变化/);
  assert.throws(()=>store.commit(state,{...preview,base_version:1,calendar:{...preview.calendar,version:2},summary:{unresolved:[{}]}},2026,wxApi),/确认/);
  assert.throws(()=>store.commit(state,{...preview,base_version:1,calendar:{...preview.calendar,personName:'其他人'}},2026,wxApi),/已变化/);
});

test('backup restores offline, validates corruption, and clear cannot resurrect v1 data', () => {
  const wxApi=mock(),state={};store.write(state,snapshot(),wxApi);
  const path=store.backup(state,wxApi);const backup=store.unpack(wxApi.files.get(path));
  const other=mock(),restored={};store.write(restored,backup,other);assert.deepEqual(restored.calendar,state.calendar);
  assert.throws(()=>store.unpack(wxApi.files.get(path).replace('早班','夜班')),/校验/);
  store.clear(state,wxApi);const reopened={};store.restore(reopened,wxApi);assert.equal(reopened.calendar.events.length,0);
});

test('cross-midnight active events appear today, rest can hide, search supports source names', () => {
  const night={...event,id:'night',date:'2026-09-06',start:'22:00',end:'08:00',end_date:'2026-09-07'};
  const r={...report,events:[night,{...event,id:'rest',title:'休息'},{...event,id:'next',date:'2026-09-08',end_date:'2026-09-08'}]};
  const selected=daily.select(r,null,{hideRest:true},new Date('2026-09-07T07:00:00'));
  assert.equal(selected.todayEvents.length,1);assert.equal(selected.todayEvents[0].id,'night');assert.equal(selected.next.id,'next');
  assert.equal(daily.select(r,null,{},new Date('2026-09-07T09:00:00')).todayEvents.length,1);
  const cells=daily.monthCells('2026-09',r.events);assert.equal(cells.filter(c=>c.day).length,30);
  assert.equal(daily.select(report,null,{query:'工作.csv'}).report.events.length,1);
});

test('long-term sources are independent of the ten-file batch limit', () => {
  const c=snapshot();
  c.calendar.sources=Array.from({length:100},(_,i)=>({...c.calendar.sources[0],id:i===0?c.calendar.sources[0].id:`s${i}`}));
  assert.ok(store.valid(c));c.calendar.sources.push({...c.calendar.sources[0],id:'extra'});assert.equal(store.valid(c),false);
});

test('backup retains image evidence after its import revision has aged out', () => {
  const wxApi=mock(),state={},snap=snapshot(),imageId='a'.repeat(20);
  snap.calendar.events[0].base.sources[0].evidence.image=imageId;
  snap.calendar.events[0].contributions[0].value.sources[0].evidence.image=imageId;
  snap.report.events[0].sources[0].evidence.image=imageId;
  snap.report.files[0].ocr={crops:{[imageId]:'aGVsbG8='}};
  store.write(state,snap,wxApi);
  delete state.report.files[0].ocr;
  const backup=store.unpack(wxApi.files.get(store.backup(state,wxApi)));
  assert.equal(backup.evidence.crops[imageId],'aGVsbG8=');
  const other=mock();store.write({},backup,other);
  assert.equal(other.files.get(`/local/xingcheng/evidence-${imageId}.jpg`),'aGVsbG8=');
  const corrupt=structuredClone(backup);corrupt.evidence.crops[imageId]='YmFk';
  assert.throws(()=>store.write({},corrupt,other),/标识冲突/);
  assert.equal(other.files.get(`/local/xingcheng/evidence-${imageId}.jpg`),'aGVsbG8=');
});
