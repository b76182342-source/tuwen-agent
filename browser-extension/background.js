/**
 * 后台服务脚本
 * 功能：管理扩展状态、处理跨域请求、存储数据
 */
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:9000';

class BackgroundService {
  constructor() {
    this.init();
  }

  init() {
    console.log('[后台服务] 初始化...');
    this.setupInstallListener();
    this.setupMessageListener();
    this.setupContextMenu();
    this.initializeStorage();
  }

  // 设置安装监听器
  setupInstallListener() {
    chrome.runtime.onInstalled.addListener((details) => {
      console.log('[后台服务] 扩展已安装:', details.reason);

      if (details.reason === 'install') {
        // 首次安装时的初始化
        this.onFirstInstall();
      } else if (details.reason === 'update') {
        // 更新时的处理
        this.onUpdate(details.previousVersion);
      }
    });
  }

  // 首次安装处理
  async onFirstInstall() {
    console.log('[后台服务] 首次安装，初始化默认设置');

    const defaultSettings = {
        backendUrl: DEFAULT_BACKEND_URL,
        autoImport: false,
        notificationEnabled: true,
        lastSyncTime: null,
        totalImported: 0
      };

    await chrome.storage.local.set(defaultSettings);

    // 打开欢迎页面
    chrome.tabs.create({
      url: chrome.runtime.getURL('welcome.html')
    });
  }

  // 更新处理
  onUpdate(previousVersion) {
    console.log(`[后台服务] 扩展已更新: ${previousVersion} -> ${chrome.runtime.getManifest().version}`);

    // 可以在这里处理版本迁移逻辑
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: '抖音数据导入助手',
      message: '扩展已更新到最新版本'
    });
  }

  // 设置消息监听器
  setupMessageListener() {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      console.log('[后台服务] 收到消息:', request);

      switch (request.action) {
        case 'importData':
          this.handleImportData(request.data, sendResponse);
          return true; // 异步响应

        case 'checkBackend':
          this.checkBackendConnection(request.url, sendResponse);
          return true;

        case 'getSettings':
          this.getSettings(sendResponse);
          return true;

        case 'saveSettings':
          this.saveSettings(request.settings, sendResponse);
          return true;

        case 'getImportHistory':
          this.getImportHistory(sendResponse);
          return true;

        case 'clearHistory':
          this.clearHistory(sendResponse);
          return true;

        default:
          sendResponse({ success: false, error: '未知操作' });
      }
    });
  }

  // 设置右键菜单
  setupContextMenu() {
    chrome.runtime.onInstalled.addListener(() => {
      chrome.contextMenus.create({
        id: 'import-current-page',
        title: '📥 导入当前页面数据',
        contexts: ['page'],
        documentUrlPatterns: ['https://creator.douyin.com/*', 'https://creator.douyin.cn/*']
      });

      chrome.contextMenus.create({
        id: 'open-dashboard',
        title: '🌐 打开Agent系统',
        contexts: ['browser_action']
      });
    });

    chrome.contextMenus.onClicked.addListener((info, tab) => {
      if (info.menuItemId === 'import-current-page') {
        this.handleContextMenuImport(tab);
      } else if (info.menuItemId === 'open-dashboard') {
        chrome.tabs.create({ url: 'http://127.0.0.1:5173' });
      }
    });
  }

  // 初始化存储
  async initializeStorage() {
    try {
      const settings = await chrome.storage.local.get(['backendUrl', 'autoImport']);
      if (!settings.backendUrl) {
        await chrome.storage.local.set({
          backendUrl: DEFAULT_BACKEND_URL,
          autoImport: false
        });
      }
    } catch (error) {
      console.error('[后台服务] 初始化存储失败:', error);
    }
  }

  // 处理数据导入
  async handleImportData(data, sendResponse) {
    try {
      const settings = await chrome.storage.local.get(['backendUrl']);
      const backendUrl = settings.backendUrl || DEFAULT_BACKEND_URL;

      const response = await fetch(`${backendUrl}/api/douyin/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ records: data })
      });

      const result = await response.json();

      if (result.success) {
        // 更新统计
        await this.updateImportStats(data.length);

        // 保存导入历史
        await this.saveImportHistory(data);

        // 发送通知
        if (await this.isNotificationEnabled()) {
          this.sendNotification('数据导入成功', `成功导入 ${result.synced} 条数据`);
        }

        sendResponse({ success: true, data: result });
      } else {
        throw new Error(result.message || '导入失败');
      }
    } catch (error) {
      console.error('[后台服务] 导入数据失败:', error);
      sendResponse({ success: false, error: error.message });
    }
  }

  // 检查后端连接
  async checkBackendConnection(url, sendResponse) {
    try {
      const backendUrl = url || DEFAULT_BACKEND_URL;
      const response = await fetch(`${backendUrl}/api/health`, {
        method: 'GET',
        timeout: 5000
      });

      sendResponse({
        success: response.ok,
        status: response.status,
        url: backendUrl
      });
    } catch (error) {
      console.error('[后台服务] 检查后端连接失败:', error);
      sendResponse({
        success: false,
        error: error.message
      });
    }
  }

  // 获取设置
  async getSettings(sendResponse) {
    try {
      const settings = await chrome.storage.local.get([
        'backendUrl',
        'autoImport',
        'notificationEnabled',
        'lastSyncTime',
        'totalImported'
      ]);
      sendResponse({ success: true, settings });
    } catch (error) {
      console.error('[后台服务] 获取设置失败:', error);
      sendResponse({ success: false, error: error.message });
    }
  }

  // 保存设置
  async saveSettings(settings, sendResponse) {
    try {
      await chrome.storage.local.set(settings);
      sendResponse({ success: true });
    } catch (error) {
      console.error('[后台服务] 保存设置失败:', error);
      sendResponse({ success: false, error: error.message });
    }
  }

  // 获取导入历史
  async getImportHistory(sendResponse) {
    try {
      const history = await chrome.storage.local.get(['importHistory']);
      sendResponse({
        success: true,
        history: history.importHistory || []
      });
    } catch (error) {
      console.error('[后台服务] 获取导入历史失败:', error);
      sendResponse({ success: false, error: error.message });
    }
  }

  // 清除历史
  async clearHistory(sendResponse) {
    try {
      await chrome.storage.local.remove(['importHistory']);
      sendResponse({ success: true });
    } catch (error) {
      console.error('[后台服务] 清除历史失败:', error);
      sendResponse({ success: false, error: error.message });
    }
  }

  // 更新导入统计
  async updateImportStats(count) {
    try {
      const stats = await chrome.storage.local.get(['totalImported', 'lastSyncTime']);
      const newTotal = (stats.totalImported || 0) + count;

      await chrome.storage.local.set({
        totalImported: newTotal,
        lastSyncTime: new Date().toISOString()
      });
    } catch (error) {
      console.error('[后台服务] 更新统计失败:', error);
    }
  }

  // 保存导入历史
  async saveImportHistory(data) {
    try {
      const history = await chrome.storage.local.get(['importHistory']);
      const currentHistory = history.importHistory || [];

      const newRecord = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        count: data.length,
        data: data.slice(0, 5) // 只保存前5条作为示例
      };

      // 保持最近50条记录
      const updatedHistory = [newRecord, ...currentHistory].slice(0, 50);

      await chrome.storage.local.set({
        importHistory: updatedHistory
      });
    } catch (error) {
      console.error('[后台服务] 保存导入历史失败:', error);
    }
  }

  // 检查是否启用通知
  async isNotificationEnabled() {
    try {
      const settings = await chrome.storage.local.get(['notificationEnabled']);
      return settings.notificationEnabled !== false;
    } catch (error) {
      return true;
    }
  }

  // 发送通知
  sendNotification(title, message) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: title,
      message: message
    });
  }

  // 处理右键菜单导入
  async handleContextMenuImport(tab) {
    try {
      const response = await chrome.tabs.sendMessage(tab.id, {
        action: 'extractData'
      });

      if (response && response.success) {
        await this.handleImportData(response.data, (result) => {
          if (result.success) {
            this.sendNotification('导入成功', `成功导入 ${result.data.synced} 条数据`);
          } else {
            this.sendNotification('导入失败', result.error);
          }
        });
      } else {
        this.sendNotification('提取失败', response?.error || '无法提取数据');
      }
    } catch (error) {
      console.error('[后台服务] 右键菜单导入失败:', error);
      this.sendNotification('导入失败', error.message);
    }
  }
}

// 初始化后台服务
const backgroundService = new BackgroundService();

// 导出供测试使用
if (typeof module !== 'undefined' && module.exports) {
  module.exports = backgroundService;
}