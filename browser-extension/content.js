/**
 * 抖音创作中心 — 数据提取脚本 (v2)
 * 使用 DOM-agnostic 策略，不依赖特定 CSS 类名
 */
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:9000';

class DouyinDataExtractor {
  constructor() {
    this.isReady = false;
    this.extractedData = [];
    this.init();
  }

  init() {
    console.log('[抖音助手] 初始化 v2...');
    this.waitForPageLoad();
    this.setupMessageListener();
    this.injectImportButton();
  }

  waitForPageLoad() {
    if (document.readyState === 'complete') {
      this.onPageReady();
    } else {
      window.addEventListener('load', () => this.onPageReady());
    }
  }

  onPageReady() {
    this.isReady = true;
    console.log('[抖音助手] 页面加载完成');
    this.injectImportButton();
  }

  setupMessageListener() {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      console.log('[抖音助手] 收到消息:', request);

      if (request.action === 'extractData') {
        this.extractData().then(data => {
          sendResponse({ success: true, data });
        }).catch(error => {
          sendResponse({ success: false, error: error.message });
        });
        return true;
      }

      if (request.action === 'checkPage') {
        sendResponse({
          success: true,
          isDouyinCreatorPage: this.isDouyinCreatorPage(),
          isReady: this.isReady
        });
      }
    });
  }

  isDouyinCreatorPage() {
    return window.location.hostname.includes('creator.douyin.com') ||
           window.location.hostname.includes('creator.douyin.cn');
  }

  // ============================================================
  // 注入导入按钮
  // ============================================================
  injectImportButton() {
    if (document.getElementById('douyin-agent-import-btn')) return;

    try {
      const btn = document.createElement('button');
      btn.id = 'douyin-agent-import-btn';
      btn.innerHTML = '📥 导入到Agent';
      btn.style.cssText = `
        position: fixed; top: 80px; right: 20px; z-index: 9999;
        padding: 12px 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; border-radius: 8px;
        font-size: 14px; font-weight: 600; cursor: pointer;
        box-shadow: 0 4px 12px rgba(102,126,234,0.4); transition: all 0.3s ease;
        display: flex; align-items: center; gap: 8px;
      `;

      btn.addEventListener('mouseenter', () => {
        btn.style.transform = 'translateY(-2px)';
        btn.style.boxShadow = '0 6px 16px rgba(102,126,234,0.5)';
      });
      btn.addEventListener('mouseleave', () => {
        btn.style.transform = 'translateY(0)';
        btn.style.boxShadow = '0 4px 12px rgba(102,126,234,0.4)';
      });
      btn.addEventListener('click', () => this.handleImportClick());

      document.body.appendChild(btn);
      console.log('[抖音助手] 导入按钮已注入');
    } catch (error) {
      console.error('[抖音助手] 注入按钮失败:', error);
    }
  }

  async handleImportClick() {
    try {
      const data = await this.extractData();
      if (data.length > 0) {
        this.showImportPreview(data);
      } else {
        alert('⚠️ 未找到可导入的数据。\n\n请确保在抖音创作中心的以下页面之一：\n• 内容管理页\n• 视频列表页\n• 数据分析页\n\n也可以通过扩展弹窗中的"手动录入"添加数据。');
      }
    } catch (error) {
      alert('数据提取失败: ' + error.message);
    }
  }

  // ============================================================
  // 主提取方法：多策略尝试
  // ============================================================
  async extractData() {
    console.log('[抖音助手] 开始提取数据...');
    const allData = [];

    // 按优先级尝试多种策略
    const strategies = [
      { name: '表格', fn: this.extractFromTables.bind(this) },
      { name: '数据卡片', fn: this.extractFromStatCards.bind(this) },
      { name: '列表项', fn: this.extractFromListItems.bind(this) },
      { name: '页面全局扫描', fn: this.extractGlobalScan.bind(this) },
    ];

    for (const strategy of strategies) {
      try {
        const data = strategy.fn();
        if (data && data.length > 0) {
          allData.push(...data);
          console.log(`[抖音助手] ${strategy.name}: ${data.length} 条`);
          if (allData.length >= 5) break; // 找到足够数据就停止
        }
      } catch (e) {
        console.warn(`[抖音助手] ${strategy.name} 失败:`, e);
      }
    }

    // 去重
    const seen = new Set();
    const unique = allData.filter(item => {
      const key = item.text + item.views + item.likes;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    console.log(`[抖音助手] 最终提取 ${unique.length} 条（去重后）`);
    return unique;
  }

  // ============================================================
  // 策略 1: 从标准 HTML 表格提取
  // ============================================================
  extractFromTables() {
    const data = [];
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
      const headers = [];
      const ths = table.querySelectorAll('th');
      ths.forEach(th => headers.push(th.textContent.trim()));

      const rows = table.querySelectorAll('tr');
      rows.forEach((row, idx) => {
        if (idx === 0 && headers.length > 0) return; // 有表头则跳过第一行
        const cells = row.querySelectorAll('td');
        if (cells.length < 2) return;

        const item = this.tableRowToRecord(cells, headers);
        if (item) data.push(item);
      });
    });
    return data;
  }

  tableRowToRecord(cells, headers) {
    // 映射常见列名
    const colMap = {};
    headers.forEach((h, i) => {
      const hLower = h.toLowerCase();
      if (/title|标题|文案|描述|内容/.test(hLower)) colMap.text = i;
      if (/view|play|播放|浏览/.test(hLower)) colMap.views = i;
      if (/like|赞|点赞|喜欢/.test(hLower)) colMap.likes = i;
      if (/comment|评论|回复/.test(hLower)) colMap.comments = i;
      if (/share|分享|转发/.test(hLower)) colMap.shares = i;
      if (/time|date|时间|日期/.test(hLower)) colMap.time = i;
    });

    // 如果没有识别到表头，按位置猜测
    if (!colMap.text && cells.length >= 3) {
      colMap.text = 0;
      colMap.views = 1;
      colMap.likes = cells.length >= 3 ? 2 : 1;
    }

    const text = colMap.text != null ? (cells[colMap.text]?.textContent?.trim() || '') : '';
    const views = this.parseNumber(colMap.views != null ? cells[colMap.views]?.textContent : '0');
    const likes = this.parseNumber(colMap.likes != null ? cells[colMap.likes]?.textContent : '0');
    const comments = this.parseNumber(colMap.comments != null ? cells[colMap.comments]?.textContent : '0');

    if (!text && views === 0) return null;

    return this.buildRecord(text, views, likes, comments, 0);
  }

  // ============================================================
  // 策略 2: 从统计数字卡片提取
  // ============================================================
  extractFromStatCards() {
    const data = [];
    const allEls = document.querySelectorAll('div, li, section, article');
    const candidates = new Map(); // parent -> count

    // 统计每个父元素下有多少个数字子元素
    allEls.forEach(el => {
      const children = el.querySelectorAll('span, div, p, em, strong, h1, h2, h3, h4, h5, h6');
      let numberCount = 0;
      const nums = [];
      children.forEach(child => {
        const text = child.textContent?.trim() || '';
        const num = this.parseNumber(text);
        if (num > 0 && /[\d]/.test(text)) {
          numberCount++;
          nums.push({ el: child, num, text });
        }
      });
      // 包含 ≥3 个数字 + 有足够文本（可能是数据卡片）
      const fullText = el.textContent?.trim() || '';
      if (numberCount >= 3 && fullText.length >= 30 && fullText.length < 600) {
        candidates.set(el, { count: numberCount, nums, text: fullText });
      }
    });

    // 只保留最内层容器（去重嵌套）
    const sorted = [...candidates.entries()]
      .filter(([el]) => ![...candidates.keys()].some(other => other !== el && other.contains(el)))
      .slice(0, 30);

    sorted.forEach(([el, info]) => {
      const record = this.parseStatCard(info);
      if (record) data.push(record);
    });

    return data;
  }

  parseStatCard(info) {
    const { nums, text } = info;
    // 提取标题：找第一个非纯数字的文本
    let title = '';
    for (const item of nums) {
      // 标题通常是较长文本，不纯是数字
      const clean = item.text.replace(/[\d,.\s万w亿k]+/g, '').trim();
      if (clean.length > 3 && clean.length < 100) {
        title = clean;
        break;
      }
    }
    if (!title) {
      // 用整体文本的前几个字
      title = text.replace(/[\d,.\s万w亿k]+/g, ' ').trim().slice(0, 60);
    }

    // 数字排序找 views/likes/comments
    const sortedNums = [...nums].sort((a, b) => b.num - a.num);
    const views = sortedNums[0]?.num || 0;
    const likes = sortedNums[1]?.num || 0;
    const comments = sortedNums[2]?.num || 0;

    if (!title || views === 0) return null;
    return this.buildRecord(title, views, likes, comments, 0);
  }

  // ============================================================
  // 策略 3: 从列表项提取
  // ============================================================
  extractFromListItems() {
    const data = [];
    const containers = document.querySelectorAll('ul, ol, [role="list"]');
    containers.forEach(container => {
      const items = container.querySelectorAll('li, [role="listitem"]');
      items.forEach(li => {
        const record = this.parseGenericItem(li);
        if (record) data.push(record);
      });
    });
    return data;
  }

  parseGenericItem(el) {
    const fullText = el.textContent?.trim() || '';
    if (fullText.length < 10 || fullText.length > 500) return null;

    // 提取所有数字
    const numMatches = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    let node;
    while (node = walker.nextNode()) {
      const text = node.textContent?.trim();
      if (!text) continue;
      const num = this.parseNumber(text);
      if (num > 0) {
        numMatches.push({ num, text });
      }
    }

    if (numMatches.length < 2) return null;

    // 数字排序
    const sorted = [...numMatches].sort((a, b) => b.num - a.num);
    const views = sorted[0]?.num || 0;
    const likes = sorted[1]?.num || 0;
    const comments = sorted[2]?.num || 0;

    // 提取标题：最长的非纯数字文本
    let title = '';
    const walker2 = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, null, false);
    let node2;
    const textCandidates = [];
    while (node2 = walker2.nextNode()) {
      const t = node2.textContent?.trim() || '';
      if (t.length > 3 && t.length < 150 && !/^\d/.test(t) && !/^[\d,.\s万w亿k]+$/.test(t)) {
        textCandidates.push(t);
      }
    }
    title = textCandidates[0] || fullText.slice(0, 80);

    if (!title || views === 0) return null;
    return this.buildRecord(title, views, likes, comments, 0);
  }

  // ============================================================
  // 策略 4: 全局扫描 — 找页面中所有看起来像"标题+数据"的模式
  // ============================================================
  extractGlobalScan() {
    const data = [];

    // 尝试从 window.__INITIAL_STATE__ 或类似全局变量获取数据
    const globalKeys = Object.keys(window).filter(k =>
      /(store|state|data|props|config)/i.test(k) && typeof window[k] === 'object'
    );
    for (const key of globalKeys) {
      try {
        const obj = window[key];
        if (!obj) continue;
        // 递归查找包含 text/views/likes 的对象数组
        const found = this.findDataInObject(obj, 0);
        if (found.length > 0) {
          console.log(`[抖音助手] 从 window.${key} 提取到 ${found.length} 条`);
          data.push(...found);
          break;
        }
      } catch (e) {
        // ignore
      }
    }

    return data;
  }

  findDataInObject(obj, depth) {
    if (depth > 4) return [];
    if (!obj || typeof obj !== 'object') return [];

    const results = [];

    if (Array.isArray(obj) && obj.length > 0 && obj.length < 200) {
      // 检查是否像数据列表
      const first = obj[0];
      if (first && typeof first === 'object') {
        const keys = Object.keys(first);
        const hasTextField = keys.some(k => /(text|title|desc|content|caption)/i.test(k) && typeof first[k] === 'string');
        const hasNumFields = keys.some(k => /(view|like|comment|share|play|count|num)/i.test(k) && typeof first[k] === 'number');
        if (hasTextField && hasNumFields) {
          obj.forEach(item => {
            const text = this.findField(item, ['text', 'title', 'desc', 'content', 'caption', 'name']);
            const views = this.findNumField(item, ['view', 'play', 'watch', 'view_count', 'play_count']);
            const likes = this.findNumField(item, ['like', 'digg', 'digg_count', 'like_count', 'favorite']);
            const comments = this.findNumField(item, ['comment', 'reply', 'comment_count', 'reply_count']);
            const shares = this.findNumField(item, ['share', 'forward', 'share_count', 'forward_count']);
            if (text || views > 0) {
              results.push(this.buildRecord(String(text || ''), views, likes, comments, shares));
            }
          });
        }
      }
    }

    // 递归查找
    if (results.length === 0) {
      for (const key of Object.keys(obj)) {
        try {
          const subResults = this.findDataInObject(obj[key], depth + 1);
          if (subResults.length > 0) {
            results.push(...subResults);
            break;
          }
        } catch (e) { /* skip */ }
      }
    }

    return results;
  }

  findField(obj, candidates) {
    for (const key of candidates) {
      for (const k of Object.keys(obj)) {
        if (k.toLowerCase().includes(key.toLowerCase()) && typeof obj[k] === 'string') {
          return obj[k];
        }
      }
    }
    return '';
  }

  findNumField(obj, candidates) {
    for (const key of candidates) {
      for (const k of Object.keys(obj)) {
        if (k.toLowerCase().includes(key.toLowerCase()) && typeof obj[k] === 'number') {
          return obj[k];
        }
      }
    }
    return 0;
  }

  // ============================================================
  // 通用工具方法
  // ============================================================
  buildRecord(text, views, likes, comments, shares) {
    return {
      text: text || '未命名',
      publish_time: new Date().toISOString(),
      likes: likes || 0,
      comments: comments || 0,
      views: views || 0,
      shares: shares || 0,
      cover_image: '',
      tags: [],
      engagement_rate: views > 0 ? ((likes + comments) / views).toFixed(4) : 0,
    };
  }

  parseNumber(text) {
    if (!text) return 0;
    let cleaned = String(text).trim();
    // 处理中文单位：1.2万 → 12000
    const wanMatch = cleaned.match(/^([\d,.]+)\s*万$/);
    if (wanMatch) return Math.round(parseFloat(wanMatch[1].replace(/,/g, '')) * 10000);
    const yiMatch = cleaned.match(/^([\d,.]+)\s*亿$/);
    if (yiMatch) return Math.round(parseFloat(yiMatch[1].replace(/,/g, '')) * 100000000);
    // 处理 k/w 后缀
    const kMatch = cleaned.match(/^([\d,.]+)\s*k$/i);
    if (kMatch) return Math.round(parseFloat(kMatch[1].replace(/,/g, '')) * 1000);
    const wMatch = cleaned.match(/^([\d,.]+)\s*w$/i);
    if (wMatch) return Math.round(parseFloat(wMatch[1].replace(/,/g, '')) * 10000);

    cleaned = cleaned.replace(/[^\d.]/g, '');
    if (!cleaned) return 0;
    const num = parseFloat(cleaned);
    return isNaN(num) ? 0 : Math.round(num);
  }

  // ============================================================
  // 预览弹窗
  // ============================================================
  showImportPreview(data) {
    const html = `
      <div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;" id="preview-overlay"></div>
      <div style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.2);z-index:10000;width:650px;max-height:80vh;overflow:auto;padding:24px;">
        <h2 style="margin:0 0 12px 0;color:#333;">📥 数据导入预览</h2>
        <p style="color:#666;margin-bottom:12px;">找到 <b>${data.length}</b> 条数据，确认导入到Agent系统？</p>
        <div style="background:#f5f5f5;border-radius:8px;padding:12px;margin-bottom:16px;max-height:350px;overflow:auto;">
          ${data.map((item, i) => `
            <div style="padding:10px;border-bottom:1px solid #e0e0e0;${i === data.length - 1 ? 'border-bottom:none;' : ''}">
              <div style="font-weight:600;color:#333;margin-bottom:4px;word-break:break-all;">${item.text}</div>
              <div style="font-size:12px;color:#666;">
                👁️ ${this.fmtNum(item.views)} | ❤️ ${this.fmtNum(item.likes)} | 💬 ${this.fmtNum(item.comments)} | 📊 ${item.engagement_rate}
              </div>
            </div>
          `).join('')}
        </div>
        <div style="display:flex;gap:12px;justify-content:flex-end;">
          <button id="cancel-import" style="padding:10px 20px;border:1px solid #ddd;background:white;border-radius:6px;cursor:pointer;font-size:14px;">取消</button>
          <button id="confirm-import" style="padding:10px 20px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;">确认导入 (${data.length}条)</button>
        </div>
      </div>`;

    const container = document.createElement('div');
    container.innerHTML = html;
    document.body.appendChild(container);

    document.getElementById('cancel-import').addEventListener('click', () => document.body.removeChild(container));
    document.getElementById('confirm-import').addEventListener('click', () => {
      this.importData(data);
      document.body.removeChild(container);
    });
    document.getElementById('preview-overlay').addEventListener('click', () => document.body.removeChild(container));
  }

  async importData(data) {
    console.log('[抖音助手] 开始导入...');
    // 从扩展配置读取后端地址
    let backendUrl = DEFAULT_BACKEND_URL;
    try {
      const settings = await chrome.storage.local.get(['backendUrl']);
      if (settings.backendUrl) backendUrl = settings.backendUrl;
    } catch (e) { /* use default */ }

    try {
      const response = await fetch(`${backendUrl}/api/douyin/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ records: data })
      });
      const result = await response.json();
      if (result.success) {
        alert(`✅ 成功导入 ${result.synced} 条数据！\n\n可在前端 Web 页面 "发布历史" 中查看。`);
        console.log('[抖音助手] 导入成功:', result);
      } else {
        alert(`❌ 导入失败: ${result.message}\n\n请确保后端服务已启动。`);
      }
    } catch (error) {
      alert(`❌ 连接后端失败: ${error.message}\n\n请确保后端运行在 ${backendUrl}`);
    }
  }

  fmtNum(num) {
    if (!num) return '0';
    const n = parseInt(num);
    if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return n.toString();
  }
}

// 初始化
const extractor = new DouyinDataExtractor();
window.douyinDataExtractor = extractor;
