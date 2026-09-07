// Compile the actual WXML with WeChat's installed compiler. The static HTML
// previews use its generated virtual DOM; they are not a WeChat runtime.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawnSync } = require('node:child_process');
const { buildTimeline } = require('../miniprogram/utils/timeline');
const { formFor, historyFor } = require('../miniprogram/utils/review');

const root = path.resolve(__dirname, '..');
const mini = path.join(root, 'miniprogram');
const output = path.join(root, 'artifacts');
const devtools = process.env.WECHAT_DEVTOOLS || 'D:/微信web开发者工具';
const compiler = path.join(devtools, 'code/package.nw/node_modules/wcc-exec');
fs.mkdirSync(output, { recursive: true });

function run(executable, args) {
  const result = spawnSync(path.join(compiler, executable), args, { cwd: mini, encoding: 'utf8', windowsHide: true, timeout: 20000 });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  if (result.stderr) console.error(result.stderr);
}

const pages = ['upload', 'timeline', 'review', 'mine', 'confirm', 'rules', 'image'];
run('wcc.exe', ['-o', path.join(output, 'wxml-compiled.js'), ...pages.map(name => `pages/${name}/${name}.wxml`)]);
for (const name of ['app', ...pages]) {
  const file = name === 'app' ? 'app.wxss' : `pages/${name}/${name}.wxss`;
  run('wcsc.exe', ['-o', path.join(output, `${name}-compiled.css`), file]);
}
const errors = [];
const context = { window: {}, console: { log: (...args) => errors.push(args.join(' ')), warn: (...args) => errors.push(args.join(' ')) } };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(output, 'wxml-compiled.js'), 'utf8'), context);
const escape = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function html(node) {
  if (node == null) return '';
  if (typeof node !== 'object') return escape(node);
  const children = (node.children || []).map(html).join('');
  if (node.tag === 'virtual') return children;
  const attrs = Object.entries(node.attr || {}).filter(([key,value]) => value !== undefined && ['class', 'placeholder', 'value', 'disabled', 'type', 'src', 'checked', 'style'].includes(key))
    .filter(([key, value]) => key !== 'disabled' || value)
    .map(([key, value]) => ` ${key}="${escape(key === 'src' && value.startsWith('/assets/') ? `data:image/svg+xml;base64,${fs.readFileSync(path.join(mini, value.slice(1))).toString('base64')}` : value)}"`).join('');
  if (node.tag === 'wx-input') return `<input${attrs}>`;
  if (node.tag === 'wx-image') return `<img${attrs} alt="">`;
  if (node.tag === 'wx-textarea') return `<textarea${attrs}>${escape(node.attr.value || '')}</textarea>`;
  if (node.tag === 'wx-switch') return `<input type="checkbox"${attrs}>`;
  return `<${node.tag}${attrs}>${children}</${node.tag}>`;
}
const reportPath = path.join(output, 'http-smoke-report.json');
if (!fs.existsSync(reportPath)) throw new Error('Run npm run smoke against the backend before compiling the preview.');
const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
const reviewed = JSON.parse(fs.readFileSync(path.join(output, 'reviewed-smoke-report.json'), 'utf8'));
const pending = JSON.parse(fs.readFileSync(path.join(output, 'pending-smoke-report.json'), 'utf8'));
const edited = reviewed.events.find(event => event.reviews.length);
const data = {
  mine: { name: '星辰奕歌', hasCalendar: true, sources: [{name: '全部来源'}], sourceIndex: 0, alarms: ['不提醒'], alarmIndex: 0, colors: ['#6a59d7'], colorIndex: 0, hidden: [] },
  confirm: { modes: ['追加安排', '更新已有来源'], mode: 0, rows: buildTimeline(report).groups.flatMap(g => g.events), files: report.files, preview: { added: 5, pending: 0, duplicates: 1, changed: [], cancelled: [], corrections: [], unresolved: [], warnings: [] }, acknowledged: true },
  rules: { sources: [{ name: '单位月度排班' }], index: 0, shifts: [{name:'早班',aliases:['早','早班'],start:'08:00',end:'16:00'}], weeks:20, layouts:['逐行明细表'],templateLayout:0,parityLabels:['全部周'],parity:0, preview:null },
  image: {path:'',blocks:[],crops:[],busy:false,error:''},
  upload: { name: '', year: 2026, files: [], busy: false, error: '', hasSuccess: false, hasErrors: false },
  timeline: { name: '星辰奕歌', ...buildTimeline(report), showDiagnostics: false, savedLocally: true, view: 'timeline', sources:[{name:'全部来源'}],sourceIndex:0 },
  review: { form: formFor(edited), errors: {}, error: '', busy: false, sources: buildTimeline(reviewed).groups.flatMap(g => g.events).find(e => e.edited).sources,
    history: historyFor(edited), warnings: [], showEvidence: true, isPending: false }
};
const variants = [
  ...pages.map(name => ({ name, page: name, data: data[name] })),
  {name:'daily-large',page:'timeline',data:{...data.timeline,view:'daily',large:true,today:'2026-09-07',todayEvents:buildTimeline(report).groups[0].events,weekEvents:buildTimeline(report).groups.flatMap(g=>g.events),nextEvent:buildTimeline(report).groups[0].events[0]}},
  {name:'month',page:'timeline',data:{...data.timeline,view:'month',month:'2026-09',monthCells:require('../miniprogram/utils/daily').monthCells('2026-09',report.events)}},
  { name: 'upload-saved', page: 'upload', data: { ...data.upload, hasSaved: true, savedName: '星辰奕歌', savedCount: 5, savedLocally: true } },
  { name: 'upload-error', page: 'upload', data: { ...data.upload, error: '部分文件未完成，可以重试或先查看成功结果', hasSuccess: true, hasErrors: true,
    files: [{ id: '1', name: '九月综合培训及节假日值班安排（修订版）.xlsx', sizeLabel: '24 KB', status: 'error', error: '连接失败，请检查网络和服务是否可用' }] } },
  { name: 'timeline-edited', page: 'timeline', data: { ...data.timeline, ...buildTimeline(reviewed) } },
  { name: 'timeline-pending', page: 'timeline', data: { ...data.timeline, ...buildTimeline(pending) } },
  { name: 'timeline-empty', page: 'timeline', data: { ...data.timeline, ...buildTimeline({ events: [], pending: [], files: [], warnings: [], conflicts: [] }) } },
  { name: 'review-error', page: 'review', data: { ...data.review, form: { ...data.review.form, date: '', end: '06:00' }, showEvidence: false,
    errors: { date: '请选择有效日期', end: '结束需晚于开始；跨夜请选择次日结束' }, error: '修正未保存，请检查服务连接后重试；填写的内容仍在当前页面' } }
];
const baseStyles = 'html,body{margin:0;padding:0}wx-page,wx-view,wx-picker{display:block}wx-text{display:inline}wx-button{display:block;text-align:center;line-height:2.55;cursor:pointer}input,textarea{font-family:inherit;outline:none;min-width:0}img{object-fit:contain}';
for (const variant of variants) {
  const name = variant.page;
  const render = context.$gwx(`pages/${name}/${name}.wxml`);
  const tree = render(variant.data, {});
  fs.writeFileSync(path.join(output, `${variant.name}-vdom.json`), JSON.stringify(tree, null, 2));
  const styles = ['app', name].map(key => fs.readFileSync(path.join(output, `${key}-compiled.css`), 'utf8')).join('\n')
    .replace(/%%HERESUFFIX%%/g, '').replace(/%%\?(-?[\d.]+)rpx\?%%/g, (_, value) => `calc(${value} * 100vw / 750)`)
    .replace(/wx-input/g, 'input').replace(/wx-image/g, 'img').replace(/wx-textarea/g, 'textarea');
  fs.writeFileSync(path.join(output, `${variant.name}-preview.html`), `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>星程 · 排版预览</title><style>${baseStyles}\n${styles}</style>${html(tree)}</html>`);
  for (const width of [320,390]) fs.writeFileSync(path.join(output, `${variant.name}-${width}-preview.html`), `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>星程固定宽度排版核验</title><style>${baseStyles}\n${styles.replace(/100vw/g,`${width}px`)}\nhtml,body{width:${width}px}input{border:0;background:transparent;width:100%;font-size:inherit}wx-button{max-width:100%}</style>${html(tree)}</html>`);
}
if (errors.length) throw new Error(errors.join('\n'));
fs.writeFileSync(path.join(output, 'preview.html'), `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>星程排版核验</title><style>body{background:#e7e8ef;font-family:sans-serif;color:#555;margin:24px}main{display:flex;gap:28px;flex-wrap:wrap}iframe{width:390px;height:844px;border:0;border-radius:22px;box-shadow:0 10px 40px #3332}p{font-size:14px}</style><p>星程 · WXML 编译产物排版预览（非微信模拟器；控件仅静态展示）</p><main>${variants.map(v => `<section><p>${v.name}</p><iframe src="${v.name}-preview.html" title="${v.name}"></iframe></section>`).join('')}</main></html>`);
console.log(`PASS: ${pages.length} WXML pages + ${pages.length + 1} WXSS files compiled; ${variants.length} populated UI states rendered without errors.`);
