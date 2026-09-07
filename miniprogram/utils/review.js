function formFor(event) {
  return { date: event.date || '', title: event.title, shift: event.shift || '', location: event.location || '',
    start: event.start || '', end: event.end || '', next_day: !!(event.end_date && event.end_date !== event.date),
    notes: (event.notes || []).join('\n') };
}

function validate(form) {
  const errors = {};
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(form.date);
  const parsed = new Date(`${form.date}T00:00:00Z`);
  if (!parts || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== form.date) errors.date = '请选择有效日期';
  if (!form.title.trim()) errors.title = '请填写事项';
  for (const key of ['start', 'end']) {
    if (form[key] && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(form[key])) errors[key] = '请选择有效时间';
  }
  if (form.end && !form.start) errors.start = '请先填写开始时间';
  if (form.next_day && !form.end) errors.end = '次日结束需要填写结束时间';
  if (form.start && form.end && !form.next_day && form.end <= form.start) errors.end = '结束需晚于开始；跨夜请选择次日结束';
  const notes = form.notes.split('\n').map(note => note.trim()).filter(Boolean);
  if (notes.length > 100 || notes.some(note => note.length > 2000)) errors.notes = '备注最多 100 行，每行不超过 2000 字';
  return { errors, values: { ...form, title: form.title.trim(), start: form.start || null, end: form.end || null, notes } };
}

function historyFor(event) {
  return (event.reviews || []).map((review, index) => {
    const before = review.before || {};
    return { key: String(index), title: before.title || '未注明事项',
      summary: `${before.date || '日期待确认'} · ${before.start || '时间未注明'}${before.end ? `–${before.end_date && before.end_date !== before.date ? '次日 ' : ''}${before.end}` : ''}`,
      detail: [before.shift, before.location, ...(before.notes || []), ...(before.warnings || [])].filter(Boolean).join(' · ') };
  });
}
module.exports = { formFor, validate, historyFor };
