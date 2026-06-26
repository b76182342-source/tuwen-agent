import axios from 'axios';
import { message } from 'antd';
import type {
  UserInput,
  ExecutionResult,
  ExecutionStage,
  Material,
  MaterialType,
  PublishHistory,
  PersonalDataAnalysis,
  DouyinSyncRecord,
  SyncResult,
  HealthCheckResult,
  TrafficDailyItem,
  FollowerDailyItem,
} from '@/types';

const api = axios.create({
  baseURL: '/api',
  timeout: 180000,  // 3 分钟，后端 Agent 全流程可能耗时较长
});

// ============================================================
// 请求拦截器：附加 X-Request-Id
// ============================================================

api.interceptors.request.use((config) => {
  config.headers['X-Request-Id'] = crypto.randomUUID?.() ||
    `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return config;
});

// ============================================================
// 响应拦截器：统一错误处理
// ============================================================

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const status = error.response.status;
      const detail = error.response.data?.detail || error.response.data?.message || error.message;
      if (status >= 500) {
        message.error(`服务器错误 (${status}): ${detail}`);
      } else if (status >= 400) {
        message.warning(`请求错误 (${status}): ${detail}`);
      }
    } else if (error.request) {
      message.error('网络连接失败，请检查网络后重试');
    } else {
      message.error(`请求配置错误: ${error.message}`);
    }
    return Promise.reject(error);
  }
);

// ============================================================
// Mock 数据（后端不可用时自动降级）
// ============================================================

// Mock 模式由 Settings 页面控制，存储在 localStorage（每次调用时动态读取）
const isMockMode = (): boolean => {
  try {
    return localStorage.getItem('settings_mock_mode') === 'true';
  } catch {
    return false;
  }
};
// USE_MOCK 语义保留为函数调用: USE_MOCK() → boolean
const USE_MOCK = isMockMode;

const getMockMaterials = (): Material[] => [
  { id: 1, material_type: 'text', original_content: '我的猫把花瓶推倒了', created_at: '2026-06-20T10:00:00', usage_count: 5, avg_engagement_rate: 0.045 },
  { id: 2, material_type: 'image', image_path: '/approved_images/cat_vase.jpg', created_at: '2026-06-20T10:01:00', usage_count: 3, avg_engagement_rate: 0.052 },
  { id: 3, material_type: 'music', music_name: '欢快卡点', created_at: '2026-06-20T10:02:00', usage_count: 8, avg_engagement_rate: 0.038 },
];

const getMockHistory = (): PublishHistory[] => [
  { id: 1, text: '我的猫把花瓶推倒了', publish_time: '2026-06-20T12:00:00',
    views: 3200, likes: 230, comments: 45, shares: 35, favorites: 12,
    swipe_away_rate: 0.38, copy_expand_rate: 0.04, avg_images_viewed: 2.0,
    fan_gain: 15, fan_loss: 2, fan_play_ratio: 0.08,
    evaluation_score: 4.2, evaluation_level: '较好', source: 'extension' },
  { id: 2, text: '夏日傍晚的微风', publish_time: '2026-06-21T15:00:00',
    views: 1800, likes: 120, comments: 20, shares: 15, favorites: 8,
    swipe_away_rate: 0.45, copy_expand_rate: 0.02, avg_images_viewed: 1.5,
    fan_gain: 5, fan_loss: 1, fan_play_ratio: 0.05,
    evaluation_score: 3.8, evaluation_level: '中等', source: 'manual' },
  { id: 3, text: '毕业季不说再见', publish_time: '2026-06-22T09:00:00',
    views: 8500, likes: 580, comments: 90, shares: 88, favorites: 35,
    swipe_away_rate: 0.32, copy_expand_rate: 0.06, avg_images_viewed: 3.0,
    fan_gain: 45, fan_loss: 3, fan_play_ratio: 0.12,
    evaluation_score: 4.5, evaluation_level: '很好', source: 'extension' },
];

const getMockAnalytics = (): PersonalDataAnalysis => {
  const history = getMockHistory();
  return {
    total_publishes: 12,
    avg_views: 4500, avg_likes: 310, avg_comments: 52,
    avg_shares: 28, avg_favorites: 15,
    avg_swipe_away_rate: 0.42, avg_copy_expand_rate: 0.03, avg_images_viewed: 2.5,
    total_fan_gain: 120, total_fan_loss: 15, avg_fan_play_ratio: 0.065,
    total_views: 54000, total_likes: 3720, total_comments: 624,
    best_content: history[2],
    top_tags: [
      { tag: '#猫咪日常', usage_count: 8, avg_likes: 250, avg_views: 4200, avg_engagement_rate: 0.06 },
      { tag: '#萌宠', usage_count: 6, avg_likes: 180, avg_views: 3100, avg_engagement_rate: 0.058 },
      { tag: '#搞笑', usage_count: 5, avg_likes: 220, avg_views: 3800, avg_engagement_rate: 0.058 },
      { tag: '#生活', usage_count: 4, avg_likes: 160, avg_views: 2800, avg_engagement_rate: 0.057 },
      { tag: '#毕业季', usage_count: 3, avg_likes: 310, avg_views: 5100, avg_engagement_rate: 0.061 },
    ],
    source_breakdown: { extension: 7, manual: 5 },
  };
};

const getMockExecutionStages = (): ExecutionStage[] => [
  { name: '标签推荐', status: 'completed', start_time: '10:00:00', end_time: '10:00:02' },
  { name: '图片推荐', status: 'completed', start_time: '10:00:02', end_time: '10:00:08' },
  { name: '配乐推荐', status: 'completed', start_time: '10:00:08', end_time: '10:00:12' },
  { name: '内容评估', status: 'running', start_time: '10:00:12' },
];

// ============================================================
// Agent相关API
// ============================================================

export const agentApi = {
  run: async (data: UserInput & { conversation_id?: string }): Promise<{ data: ExecutionResult }> => {
    if (USE_MOCK()) {
      await new Promise((r) => setTimeout(r, 1500));
      return {
        data: {
          creator_content: { text: data.text, tags: data.tags, images: data.images, music: data.music },
          agent_suggestions: {
            Skill1: ['#猫咪日常', '#萌宠', '#搞笑日常', '#养猫日常', '#猫咪捣蛋'],
            Skill2: getMockMaterials().filter((m) => m.material_type === 'image') as any,
            Skill3: getMockMaterials().filter((m) => m.material_type === 'music') as any,
          },
          execution_log: getMockExecutionStages()
            .filter((s) => s.status === 'completed')
            .map((s) => ({ skill: s.name, status: s.status })),
          session_state: {
            text: data.text,
            tags: data.tags,
            images: data.images,
            music: data.music,
            evaluation: { score: 4.2, level: '较好', report: '## Mock 评估报告\n\n内容质量良好，可通过。', suggestions: ['可添加更多图片', '标签可精简到6个'] },
          },
        },
      };
    }
    const params = data.conversation_id ? { conversation_id: data.conversation_id } : {};
    const body = { text: data.text, tags: data.tags, images: data.images, music: data.music, enable_blackbox: data.enable_blackbox };
    return api.post<ExecutionResult>('/agent/run', body, { params });
  },

  getStatus: async (sessionId: string) => {
    if (USE_MOCK()) {
      await new Promise((r) => setTimeout(r, 500));
      return { data: { stages: getMockExecutionStages() } };
    }
    return api.get<{ stages: ExecutionStage[] }>(`/agent/status/${sessionId}`);
  },

  rollback: async (sessionId: string, targetSkill: string) => {
    if (USE_MOCK()) {
      return { data: { success: true, message: `已回滚到 ${targetSkill}` } };
    }
    return api.post<{ success: boolean; message: string }>('/agent/rollback', {
      session_id: sessionId,
      target_skill: targetSkill,
    });
  },
};

// ============================================================
// 对话管理API
// ============================================================

export interface Conversation {
  id: string;
  conversation_id: string;
  title: string;
  user_id?: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  conversation_id: string;
  role: string;
  content: string;
  metadata?: any;
  created_at: string;
}

export interface ConversationContext {
  conversation_id: string;
  message_count: number;
  user_inputs: string[];
  agent_responses: string[];
  last_message_time: string;
}

export interface ConversationStats {
  total_messages: number;
  user_messages: number;
  assistant_messages: number;
  created_at: string;
  updated_at: string;
}

export const conversationApi = {
  create: async (data: { title?: string; user_id?: string }) => {
    return api.post<{ conversation_id: string }>('/conversations', data);
  },

  get: async (conversationId: string) => {
    return api.get<Conversation>(`/conversations/${conversationId}`);
  },

  list: async (params?: { user_id?: string; limit?: number }) => {
    return api.get<Conversation[]>('/conversations', { params });
  },

  delete: async (conversationId: string) => {
    return api.delete<{ success: boolean }>(`/conversations/${conversationId}`);
  },

  batchDelete: async (conversationIds: string[]) => {
    return api.post<{ deleted_count: number; total: number }>('/conversations/batch-delete', { conversation_ids: conversationIds });
  },

  updateTitle: async (conversationId: string, title: string) => {
    return api.put<{ success: boolean }>(`/conversations/${conversationId}`, { title });
  },

  addMessage: async (data: { conversation_id: string; role: string; content: string; metadata?: any }) => {
    return api.post<{ message_id: number }>('/conversations/messages', data);
  },

  getHistory: async (conversationId: string, limit?: number) => {
    return api.get<ConversationMessage[]>(`/conversations/${conversationId}/messages`, { params: { limit } });
  },

  getContext: async (conversationId: string, maxMessages?: number) => {
    return api.get<ConversationContext>(`/conversations/${conversationId}/context`, { params: { max_messages: maxMessages } });
  },

  getStats: async (conversationId: string) => {
    return api.get<ConversationStats>(`/conversations/${conversationId}/stats`);
  },

  search: async (params: { keyword: string; user_id?: string; limit?: number }) => {
    return api.get<Conversation[]>('/conversations/search', { params });
  },
};

// ============================================================
// 素材管理API
// ============================================================

export const materialApi = {
  getMaterials: async (type?: MaterialType) => {
    if (USE_MOCK()) {
      const filtered = type ? getMockMaterials().filter((m) => m.material_type === type) : getMockMaterials();
      return { data: filtered };
    }
    return api.get<Material[]>('/materials', { params: { type } });
  },

  addMaterial: async (data: any) => {
    if (USE_MOCK()) return { data: { id: 99 } };
    return api.post<{ id: number }>('/materials', data);
  },

  updateMaterial: async (id: number, data: Partial<Material>) => {
    if (USE_MOCK()) return { data: { success: true } };
    return api.put(`/materials/${id}`, data);
  },

  deleteMaterial: async (id: number) => {
    if (USE_MOCK()) return { data: { success: true } };
    return api.delete(`/materials/${id}`);
  },

  getMaterialsByTags: async (tags: string[]) => {
    if (USE_MOCK()) {
      return { data: getMockMaterials().filter((m) => (m as any).semantic_tags?.some((t: any) => tags.includes(t.tag))) };
    }
    return api.get<Material[]>('/materials/by-tags', { params: { tags } });
  },

  getTopMaterials: async (type: MaterialType, limit: number = 10) => {
    if (USE_MOCK()) {
      return { data: getMockMaterials().filter((m) => m.material_type === type).slice(0, limit) };
    }
    return api.get<Material[]>('/materials/top', { params: { type, limit } });
  },
};

// ============================================================
// 发布历史API
// ============================================================

export const publishApi = {
  getHistory: async () => {
    if (USE_MOCK()) return { data: getMockHistory() };
    return api.get<PublishHistory[]>('/publish/history');
  },

  getPublish: async (id: number) => {
    if (USE_MOCK()) return { data: getMockHistory().find((h) => h.id === id)! };
    return api.get<PublishHistory>(`/publish/${id}`);
  },

  updatePublishData: async (id: number, data: { likes?: number; comments?: number; views?: number }) => {
    if (USE_MOCK()) return { data: { success: true } };
    return api.put(`/publish/${id}/data`, data);
  },

  delete: async (id: number) => {
    if (USE_MOCK()) return { data: { success: true } };
    return api.delete<{ success: boolean }>(`/publish/${id}`);
  },
};

// ============================================================
// 数据分析API
// ============================================================

export const analyticsApi = {
  getOverview: async () => {
    if (USE_MOCK()) return { data: getMockAnalytics() };
    return api.get<PersonalDataAnalysis>('/analytics/overview');
  },

  getTrafficTrend: async (contentId?: number, limit?: number) => {
    return api.get<TrafficDailyItem[]>('/analytics/traffic-trend', { params: { content_id: contentId, limit } });
  },

  getFollowerTrend: async (contentId?: number, limit?: number) => {
    return api.get<FollowerDailyItem[]>('/analytics/follower-trend', { params: { content_id: contentId, limit } });
  },

  getContentDetail: async (postId: number) => {
    return api.get<PublishHistory>(`/content/${postId}`);
  },
};

// ============================================================
// 抖音同步API（配合浏览器扩展）
// ============================================================

export const douyinSyncApi = {
  sync: async (records: DouyinSyncRecord[]): Promise<{ data: SyncResult }> => {
    if (USE_MOCK()) {
      await new Promise((r) => setTimeout(r, 500));
      return { data: { success: true, synced: records.length, message: `成功同步 ${records.length} 条记录` } };
    }
    return api.post<SyncResult>('/douyin/sync', { records });
  },

  healthCheck: async (): Promise<{ data: HealthCheckResult }> => {
    if (USE_MOCK()) {
      return {
        data: {
          status: 'ok',
          service: 'douyin-agent-backend',
          version: '1.0.0',
          timestamp: new Date().toISOString(),
          features: {
            douyin_sync: true,
            material_library: true,
            analytics: true,
            conversation: true,
          },
        },
      };
    }
    return api.get<HealthCheckResult>('/health');
  },

  getSyncHistory: async () => {
    if (USE_MOCK()) {
      return { data: [] };
    }
    return api.get('/douyin/sync-history');
  },
};

export default api;