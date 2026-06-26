/**
 * Popup 交互逻辑 v2
 * - 自动提取数据
 * - 手动录入回退
 * - 数据预览 + 导入
 */
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:9000';

class PopupController {
  constructor() {
    this.currentTab = null;
    this.extractedData = [];
    this.backendUrl = DEFAULT_BACKEND_URL;
    this.init();
  }

  async init() {
    console.log('[Popup] 初始化...');
    await this.loadSettings();

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    this.currentTab = tab;

    await this.checkPageStatus();
    await this.checkBackendConnection();
    this.bindEvents();

    setInterval(() => this.checkPageStatus(), 5000);
    setInterval(() => this.checkBackendConnection(), 30000);
  }

  // ============================================================
  // 设置管理
  // ============================================================
  async loadSettings() {
    try {
      const settings = await chrome.storage.local.get(['backendUrl', 'autoImport']);
      if (settings.backendUrl) {
        this.backendUrl = settings.backendUrl;
        document.getElementById('backend-url').value = settings.backendUrl;
      }
      if (settings.autoImport !== undefined) {
        document.getElementById('auto-import').value = settings.autoImport;
      }
    } catch (error) {
      console.error('[Popup] 加载设置失败:', error);
    }
  }

  async saveSettings() {
    try {
      const settings = {
        backendUrl: document.getElementById('backend-url').value,
        autoImport: document.getElementById('auto-import').value
      };
      await chrome.storage.local.set(settings);
      this.backendUrl = settings.backendUrl;
    } catch (error) {
      console.error('[Popup] 保存设置失败:', error);
    }
  }

  // ============================================================
  // 状态检查
  // ============================================================
  async checkPageStatus() {
    try {
      const response = await chrome.tabs.sendMessage(this.currentTab.id, { action: 'checkPage' });
      const pageStatus = document.getElementById('page-status');
      const pageStatusText = document.getElementById('page-status-text');
      const extractBtn = document.getElementById('extract-btn');

      if (response && response.success) {
        if (response.isDouyinCreatorPage) {
          pageStatus.className = 'status-indicator active';
          pageStatusText.textContent = '抖音创作中心';
          extractBtn.disabled = !response.isReady;
          extractBtn.textContent = response.isReady ? '📊 提取数据' : '⏳ 页面加载中...';
        } else {
          pageStatus.className = 'status-indicator inactive';
          pageStatusText.textContent = '非创作中心页面';
          extractBtn.disabled = false; // 即使不在创作中心也允许尝试
          extractBtn.textContent = '📊 尝试提取';
        }
      } else {
        pageStatus.className = 'status-indicator inactive';
        pageStatusText.textContent = '页面未加载';
        extractBtn.disabled = true;
      }
    } catch (error) {
      const pageStatus = document.getElementById('page-status');
      const pageStatusText = document.getElementById('page-status-text');
      pageStatus.className = 'status-indicator inactive';
      pageStatusText.textContent = '扩展未注入';
    }
  }

  async checkBackendConnection() {
    try {
      const response = await fetch(`${this.backendUrl}/api/health`, { method: 'GET' });
      const backendStatus = document.getElementById('backend-status');
      const backendStatusText = document.getElementById('backend-status-text');
      if (response.ok) {
        backendStatus.className = 'status-indicator active';
        backendStatusText.textContent = '已连接';
      } else {
        throw new Error('后端响应异常');
      }
    } catch (error) {
      const backendStatus = document.getElementById('backend-status');
      const backendStatusText = document.getElementById('backend-status-text');
      backendStatus.className = 'status-indicator inactive';
      backendStatusText.textContent = '未连接';
    }
  }

  // ============================================================
  // 事件绑定
  // ============================================================
  bindEvents() {
    document.getElementById('extract-btn').addEventListener('click', () => this.extractData());
    document.getElementById('open-douyin-btn').addEventListener('click', () => this.openDouyinCreator());
    document.getElementById('backend-url').addEventListener('change', () => {
      this.saveSettings();
      this.checkBackendConnection();
    });
    document.getElementById('auto-import').addEventListener('change', () => this.saveSettings());

    // 手动录入
    document.getElementById('manual-add-btn').addEventListener('click', () => this.addManualRecord());
  }

  // ============================================================
  // 数据提取
  // ============================================================
  async extractData() {
    this.showLoading(true);
    this.hideMessages();

    try {
      const response = await chrome.tabs.sendMessage(this.currentTab.id, { action: 'extractData' });

      if (response && response.success) {
        this.extractedData = response.data;
        if (this.extractedData.length > 0) {
          this.showDataPreview(response.data);
          const autoImport = document.getElementById('auto-import').value === 'true';
          if (autoImport) {
            await this.importData(response.data);
          } else {
            this.showSuccess(`✅ 成功提取 ${response.data.length} 条数据，点击数据预览中的"导入"按钮确认`);
            // 在数据预览区添加导入按钮
            this.addImportButtonToPreview();
          }
        } else {
          // 提取到 0 条 — 显示手动录入区域
          this.showError('⚠️ 未能自动提取到数据。请使用下方手动录入功能。');
          document.getElementById('manual-entry').style.display = 'block';
          document.getElementById('data-preview').style.display = 'none';
        }
      } else {
        throw new Error(response?.error || '数据提取失败');
      }
    } catch (error) {
      console.error('[Popup] 提取失败:', error);
      this.showError(`提取失败: ${error.message}。请使用下方手动录入功能。`);
      document.getElementById('manual-entry').style.display = 'block';
    } finally {
      this.showLoading(false);
    }
  }

  // ============================================================
  // 数据预览
  // ============================================================
  showDataPreview(data) {
    const preview = document.getElementById('data-preview');
    const dataList = document.getElementById('data-list');
    const dataCount = document.getElementById('data-count');

    if (!data || data.length === 0) {
      preview.style.display = 'none';
      return;
    }

    dataCount.textContent = data.length;
    dataList.innerHTML = data.map((item, index) => `
      <div class="data-item" style="padding:12px;border-bottom:1px solid #f0f0f0;">
        <div class="data-title" style="font-size:13px;font-weight:600;color:#333;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          ${item.text || '未命名'}
        </div>
        <div class="data-stats" style="font-size:11px;color:#666;display:flex;gap:12px;">
          <span>👁️ ${this.formatNumber(item.views)}</span>
          <span>❤️ ${this.formatNumber(item.likes)}</span>
          <span>💬 ${this.formatNumber(item.comments)}</span>
          <span>📊 ${item.engagement_rate || '0%'}</span>
        </div>
      </div>
    `).join('');

    preview.style.display = 'block';
    document.getElementById('manual-entry').style.display = 'none';
  }

  addImportButtonToPreview() {
    const preview = document.getElementById('data-preview');
    // 移除旧按钮
    const oldBtn = document.getElementById('popup-import-btn');
    if (oldBtn) oldBtn.remove();

    const btn = document.createElement('button');
    btn.id = 'popup-import-btn';
    btn.className = 'btn btn-success';
    btn.textContent = '📤 导入到Agent系统';
    btn.style.marginTop = '12px';
    btn.addEventListener('click', () => this.importData(this.extractedData));
    preview.appendChild(btn);
  }

  // ============================================================
  // 手动录入
  // ============================================================
  addManualRecord() {
    const text = document.getElementById('manual-text').value.trim();
    const views = parseInt(document.getElementById('manual-views').value) || 0;
    const likes = parseInt(document.getElementById('manual-likes').value) || 0;
    const comments = parseInt(document.getElementById('manual-comments').value) || 0;

    if (!text) {
      this.showError('请输入文案内容');
      return;
    }

    const record = {
      text: text,
      publish_time: new Date().toISOString(),
      likes: likes,
      comments: comments,
      views: views,
      shares: 0,
      tags: [],
      engagement_rate: views > 0 ? ((likes + comments) / views).toFixed(4) : 0,
    };

    this.extractedData.push(record);
    this.showDataPreview(this.extractedData);

    // 清空表单
    document.getElementById('manual-text').value = '';
    document.getElementById('manual-views').value = '0';
    document.getElementById('manual-likes').value = '0';
    document.getElementById('manual-comments').value = '0';

    this.showSuccess(`✅ 已添加: ${text.slice(0, 30)}... （共 ${this.extractedData.length} 条待导入）`);
  }

  // ============================================================
  // 数据导入
  // ============================================================
  async importData(data) {
    this.showLoading(true);
    this.hideMessages();

    try {
      const response = await fetch(`${this.backendUrl}/api/douyin/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ records: data })
      });

      const result = await response.json();

      if (result.success) {
        this.showSuccess(`✅ 成功导入 ${result.synced} 条数据！可在前端 Web 页面"发布历史"中查看。`);
        this.extractedData = [];
        document.getElementById('data-preview').style.display = 'none';
        document.getElementById('manual-entry').style.display = 'none';
      } else {
        throw new Error(result.message || '导入失败');
      }
    } catch (error) {
      console.error('[Popup] 导入失败:', error);
      this.showError(`导入失败: ${error.message}`);
    } finally {
      this.showLoading(false);
    }
  }

  // ============================================================
  // 辅助方法
  // ============================================================
  openDouyinCreator() {
    chrome.tabs.create({ url: 'https://creator.douyin.com/creator-micro/content/manage' });
  }

  showLoading(show) {
    const loading = document.getElementById('loading');
    loading.classList.toggle('active', show);
  }

  showError(message) {
    const el = document.getElementById('error-message');
    el.textContent = message;
    el.classList.add('active');
    setTimeout(() => el.classList.remove('active'), 8000);
  }

  showSuccess(message) {
    const el = document.getElementById('success-message');
    el.textContent = message;
    el.classList.add('active');
    setTimeout(() => el.classList.remove('active'), 5000);
  }

  hideMessages() {
    document.getElementById('error-message').classList.remove('active');
    document.getElementById('success-message').classList.remove('active');
  }

  formatNumber(num) {
    if (!num) return '0';
    const n = parseInt(num);
    if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return n.toString();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  new PopupController();
});
