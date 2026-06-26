import { create } from 'zustand';
import type {
  UserInput,
  ExecutionResult,
  ExecutionStage,
  Material,
  PublishHistory,
  PersonalDataAnalysis,
} from '@/types';

const CONV_ID_KEY = 'current_conversation_id';
const MSG_CACHE_PREFIX = 'msg_cache_';

/** 从 localStorage 恢复 conversationId，store 初始化时调用 */
const loadConversationId = (): string => {
  try {
    return localStorage.getItem(CONV_ID_KEY) || '';
  } catch {
    return '';
  }
};

/** 持久化 conversationId 到 localStorage */
const saveConversationId = (id: string) => {
  try {
    if (id) localStorage.setItem(CONV_ID_KEY, id);
    else localStorage.removeItem(CONV_ID_KEY);
  } catch { /* 无痕模式等 */ }
};

// ============================================================
// 消息本地缓存（后端不可用时的降级方案）
// ============================================================
export interface CachedMessage {
  role: string;
  content: string;
  tags?: string[];
  images?: any[];
  music?: any[];
  score?: number;
  level?: string;
  timestamp: string;
}

export const saveMessagesToCache = (convId: string, msgs: CachedMessage[]) => {
  if (!convId) return;
  try {
    localStorage.setItem(MSG_CACHE_PREFIX + convId, JSON.stringify(msgs.slice(-50)));
  } catch { /* quota exceeded */ }
};

export const loadMessagesFromCache = (convId: string): CachedMessage[] => {
  if (!convId) return [];
  try {
    const raw = localStorage.getItem(MSG_CACHE_PREFIX + convId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

interface AppState {
  // Agent执行状态
  isExecuting: boolean;
  sessionId: string | null;
  conversationId: string;
  executionStages: ExecutionStage[];
  executionResult: ExecutionResult | null;

  // 用户输入
  userInput: UserInput;

  // 素材库
  materials: Material[];
  selectedMaterialType: 'text' | 'image' | 'music' | 'all';

  // 发布历史
  publishHistory: PublishHistory[];

  // 数据分析
  analytics: PersonalDataAnalysis | null;

  // Actions
  setExecuting: (isExecuting: boolean) => void;
  setSessionId: (sessionId: string | null) => void;
  setConversationId: (conversationId: string) => void;
  setExecutionStages: (stages: ExecutionStage[]) => void;
  updateExecutionStage: (stageName: string, updates: Partial<ExecutionStage>) => void;
  setExecutionResult: (result: ExecutionResult | null) => void;
  setUserInput: (input: Partial<UserInput>) => void;
  setMaterials: (materials: Material[]) => void;
  setSelectedMaterialType: (type: 'text' | 'image' | 'music' | 'all') => void;
  setPublishHistory: (history: PublishHistory[]) => void;
  setAnalytics: (analytics: PersonalDataAnalysis | null) => void;
  resetExecution: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  isExecuting: false,
  sessionId: null,
  conversationId: loadConversationId(),
  executionStages: [],
  executionResult: null,
  userInput: {
    text: '',
    tags: [],
    images: [],
    music: [],
    enable_blackbox: false,
  },
  materials: [],
  selectedMaterialType: 'all',
  publishHistory: [],
  analytics: null,

  // Actions
  setExecuting: (isExecuting) => set({ isExecuting }),
  setSessionId: (sessionId) => set({ sessionId }),
  setConversationId: (conversationId) => {
    saveConversationId(conversationId);
    set({ conversationId });
  },
  setExecutionStages: (executionStages) => set({ executionStages }),
  updateExecutionStage: (stageName, updates) =>
    set((state) => ({
      executionStages: state.executionStages.map((stage) =>
        stage.name === stageName ? { ...stage, ...updates } : stage
      ),
    })),
  setExecutionResult: (executionResult) => set({ executionResult }),
  setUserInput: (input) =>
    set((state) => ({ userInput: { ...state.userInput, ...input } })),
  setMaterials: (materials) => set({ materials }),
  setSelectedMaterialType: (selectedMaterialType) => set({ selectedMaterialType }),
  setPublishHistory: (publishHistory) => set({ publishHistory }),
  setAnalytics: (analytics) => set({ analytics }),
  resetExecution: () =>
    set({
      isExecuting: false,
      sessionId: null,
      executionStages: [],
      executionResult: null,
    }),
}));