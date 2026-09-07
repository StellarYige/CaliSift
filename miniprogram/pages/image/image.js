const api = require('../../utils/api');
Page({
  data: { path: '', rotation: 0, left: 0, top: 0, right: 100, bottom: 100, error: '', busy: false, blocks: [], crops: [], name: '', year: new Date().getFullYear() },
  onLoad(options) { this._camera = !!options.camera; const state = getApp().globalData; this.setData({ name: state.personName || '' }); this.choose(); },
  choose() {
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: this._camera ? ['camera'] : ['album'], success: result => {
      const file = result.tempFiles[0];
      if (file.size > 10 * 1024 * 1024) return this.setData({ error: '图片不能超过 10 MiB' });
      wx.getImageInfo({ src: file.tempFilePath, success: info => {
        if (info.width * info.height > 12000000) return this.setData({ error: '图片不能超过 1200 万像素，请先缩小图片' });
        if (!['png', 'jpeg', 'jpg'].includes(info.type)) return this.setData({ error: '请选择 PNG 或 JPEG 图片' });
        this._file = { id: `image-${Date.now()}`, name: `图片-${Date.now()}.${info.type === 'png' ? 'png' : 'jpg'}`, path: file.tempFilePath, size: file.size, image: true,
          sizeLabel: `${(file.size / 1024 / 1024).toFixed(1)} MB`, status: 'ready', report: null };
        this._corrections = {}; this.setData({ path: file.tempFilePath, width: info.width, height: info.height, error: '', blocks: [] });
      }, fail: () => this.setData({ error: '图片无法读取，请重新选择' }) });
    }, fail: error => { if (!/cancel/i.test(error.errMsg || '')) this.setData({ error: '未能选择图片，请重试' }); } });
  },
  field(event) { this.setData({ [event.currentTarget.dataset.field]: event.detail.value }); this._report = null; },
  rotate() { this.setData({ rotation: (this.data.rotation + 90) % 360, blocks: [], crops: [] }); this._report = null; this._corrections = {}; },
  correct(event) { this._corrections[event.currentTarget.dataset.id] = event.detail.value; this._report = null; },
  options() { return { rotation: this.data.rotation, crop: [this.data.left, this.data.top, this.data.right, this.data.bottom].map(v => Number(v) / 100), corrections: this._corrections || {} }; },
  async recognize() {
    if (!this._file || this.data.busy) return;
    if (!this.data.name.trim()) return this.setData({ error: '请填写完整姓名以精确提取' });
    this.setData({ busy: true, error: '' });
    try {
      const report = await api.upload({ ...this._file, options: this.options() }, this.data.name, this.data.year, () => {});
      this._report = report;
      const ocr = report.files[0].ocr;
      const crops = [];
      for (const [id, data] of Object.entries(ocr.crops || {})) {
        const path = `${wx.env.USER_DATA_PATH}/ocr-preview-${id}.jpg`;
        wx.getFileSystemManager().writeFileSync(path, data, 'base64'); crops.push({ id, path });
      }
      this.setData({ blocks: ocr.blocks.map(b => ({ id: b.id, text: b.text, original: b.original_text, cell: b.cell || '表格外', box: b.box.join(', '), scoreLabel: b.score.toFixed(3) })),
        crops, count: report.events.length, pendingCount: report.pending.length, reliable: ocr.reliable,
        error: report.events.length + report.pending.length ? '' : '未找到完整姓名或相关安排。请对照图片纠正识别文字，再次提取；不会自动匹配相似姓名。' });
    } catch (error) { this.setData({ error: error.message }); } finally { this.setData({ busy: false }); }
  },
  add() {
    if (!this._file || !this._report) return this.setData({ error: '请先识别；修改文字后需再次识别核对' });
    getApp().globalData.imageSelection = { ...this._file, options: this.options(), status: 'done', report: this._report,
      queryKey: require('../../utils/upload-queue').queryKey(this.data.name, Number(this.data.year)) };
    wx.navigateBack();
  },
  onUnload() { for (const crop of this.data.crops) { try { wx.getFileSystemManager().unlinkSync(crop.path); } catch (_) {} } }
});
