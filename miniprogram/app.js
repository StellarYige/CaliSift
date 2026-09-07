const storage = require('./utils/storage');
App({
  globalData: { report: null, personName: '', referenceYear: null, savedAt: '', persistenceError: '' },
  onLaunch() {
    if (wx.getFileSystemManager) { require('./utils/calendar-store').restore(this.globalData); return; }
    const { snapshot, error } = storage.restore();
    if (snapshot) Object.assign(this.globalData, snapshot);
    this.globalData.persistenceError = error;
  }
});
