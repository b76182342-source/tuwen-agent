/**
 * 扩展配置管理
 * 统一管理后端地址等可配置项
 */

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:9000';

class ExtensionConfig {
  static async getBackendUrl() {
    try {
      const settings = await chrome.storage.local.get(['backendUrl']);
      return settings.backendUrl || DEFAULT_BACKEND_URL;
    } catch (e) {
      console.warn('[Config] 读取后端地址失败，使用默认值');
      return DEFAULT_BACKEND_URL;
    }
  }

  static async setBackendUrl(url) {
    try {
      await chrome.storage.local.set({ backendUrl: url });
      return true;
    } catch (e) {
      console.error('[Config] 保存后端地址失败:', e);
      return false;
    }
  }

  static async initDefaults() {
    try {
      const settings = await chrome.storage.local.get(['backendUrl']);
      if (!settings.backendUrl) {
        await chrome.storage.local.set({ backendUrl: DEFAULT_BACKEND_URL });
      }
    } catch (e) {
      console.error('[Config] 初始化默认配置失败:', e);
    }
  }

  static getDefaultBackendUrl() {
    return DEFAULT_BACKEND_URL;
  }
}