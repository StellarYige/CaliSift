const config = require('../config');

function messageFor(data, fallback) {
  if (typeof data === 'string') return data;
  if (data && typeof data.detail === 'string') return data.detail;
  if (data && Array.isArray(data.detail)) return data.detail.map(item => String(item.msg || '输入格式不正确').replace(/^Value error, /, '')).join('；') || '输入格式不正确';
  return fallback;
}

function parseResponse(response) {
  let data;
  try { data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data; }
  catch (_) { throw new Error('服务器返回了无法识别的结果'); }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(messageFor(data, `请求失败（${response.statusCode}）`));
  }
  if (!data || !Array.isArray(data.events) || !Array.isArray(data.files) || !Array.isArray(data.pending)) {
    throw new Error('服务器返回的日程不完整');
  }
  return data;
}

function upload(file, name, year, onProgress, wxApi = wx) {
  return new Promise((resolve, reject) => {
    const task = wxApi.uploadFile({
      url: `${config.apiBaseUrl}/api/${file.image ? 'ocr' : 'parse'}`, filePath: file.path, name: file.image ? 'file' : 'files',
      formData: { name, reference_year: String(year), original_filename: file.name, ...(file.image ? { options: JSON.stringify(file.options || {}) } : {}),
        ...(file.layout_hint ? { layout_hint: JSON.stringify(file.layout_hint) } : {}) }, timeout: file.image ? 120000 : 60000,
      success(response) {
        try {
          const report = parseResponse(response);
          const failure = report.files.find(item => item.status === 'error');
          if (failure) throw new Error(failure.error || '文件解析失败');
          resolve(report);
        } catch (error) { reject(error); }
      },
      fail() { reject(new Error('连接失败，请检查网络和服务是否可用')); }
    });
    if (task && task.onProgressUpdate) task.onProgressUpdate(value => onProgress(value.progress));
  });
}

function merge(reports, wxApi = wx) {
  return new Promise((resolve, reject) => wxApi.request({
    url: `${config.apiBaseUrl}/api/merge`, method: 'POST', data: { reports }, timeout: 60000,
    success(response) { try { resolve(parseResponse(response)); } catch (error) { reject(error); } },
    fail() { reject(new Error('合并失败，请检查连接后重试；已上传的结果仍保留')); }
  }));
}

function review(report, edits, wxApi = wx) {
  return new Promise((resolve, reject) => wxApi.request({
    url: `${config.apiBaseUrl}/api/review`, method: 'POST', data: { report, edits }, timeout: 60000,
    success(response) { try { resolve(parseResponse(response)); } catch (error) { reject(error); } },
    fail() { reject(new Error('修正未保存，请检查服务连接后重试；填写的内容仍在当前页面')); }
  }));
}
function request(path, data, raw = false, wxApi = wx) {
  return new Promise((resolve, reject) => wxApi.request({ url: `${config.apiBaseUrl}${path}`, method: 'POST', data, timeout: 120000,
    success(response) {
      if (response.statusCode < 200 || response.statusCode >= 300) return reject(Error(messageFor(response.data, '操作失败，请重试')));
      resolve(response.data);
    }, fail() { reject(Error('连接失败，原日历已保留，请检查网络后重试')); }
  }));
}
const transform = (calendar, operation) => request('/api/calendar/transform', { calendar, expected_version: calendar.version, operation });
module.exports = { upload, merge, review, parseResponse, request, transform };
