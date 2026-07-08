import { create } from 'zustand';
import type {
  UserInput,
  ExecutionResult,
  ExecutionStage,
  Material,
  PublishHistory,
  PersonalDataAnalysis,
  ChatMessageData,
} from '@/types';

const CONV_ID_KEY = 'current_conversation_id';
const MSG_CACHE_PREFIX = 'msg_cache_';
const DRAFT_KEY = 'workspace_draft';

/** 合法的 conversationId 格式：本地 "local_xxx" 或后端 "conv_xxx" */
const isValidConversationId = (id: string): boolean => {
  if (!id) return false;
  // 过滤掉 JavaScript 序列化产生的无效值
  if (id === 'undefined' || id === 'null' || id === 'NaN') return false;
  return true;
};

/** 从 localStorage 恢复 conversationId，store 初始化时调用 */
const loadConversationId = (): string => {
  try {
    const raw = localStorage.getItem(CONV_ID_KEY);
    if (raw && isValidConversationId(raw)) return raw;
    // 无效值清理
    if (raw) localStorage.removeItem(CONV_ID_KEY);
    return '';
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

export const saveMessagesToCache = (convId: string | undefined | null, msgs: CachedMessage[]) => {
  if (!convId) return;
  try {
    localStorage.setItem(MSG_CACHE_PREFIX + convId, JSON.stringify(msgs.slice(-50)));
  } catch { /* quota exceeded */ }
};

export const loadMessagesFromCache = (convId: string | undefined | null): CachedMessage[] => {
  if (!convId) return [];
  try {
    const raw = localStorage.getItem(MSG_CACHE_PREFIX + convId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

/** 持久化输入框草稿 */
const saveDraft = (text: string) => {
  try {
    if (text) localStorage.setItem(DRAFT_KEY, text);
    else localStorage.removeItem(DRAFT_KEY);
  } catch {}
};

const loadDraft = (): string => {
  try {
    return localStorage.getItem(DRAFT_KEY) || '';
  } catch {
    return '';
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

  // === 工作台状态（跨页面持久化，解决切换页面丢失问题） ===
  messages: ChatMessageData[];
  inputText: string;
  iteration: number;

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

  // 工作台 actions
  setMessages: (messages: ChatMessageData[]) => void;
  appendMessages: (msgs: ChatMessageData[]) => void;
  setInputText: (text: string) => void;
  setIteration: (n: number) => void;
  incrementIteration: () => void;

  setMaterials: (materials: Material[]) => void;
  setSelectedMaterialType: (type: 'text' | 'image' | 'music' | 'all') => void;
  setPublishHistory: (history: PublishHistory[]) => void;
  setAnalytics: (analytics: PersonalDataAnalysis | null) => void;
  resetExecution: () => void;

  /** 清空当前对话的工作台状态（切换/新建对话时使用） */
  resetWorkspace: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
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

  // 工作台初始状态
  messages: [],
  inputText: loadDraft(),
  iteration: 0,

  materials: [],
  selectedMaterialType: 'all',
  publishHistory: [],
  analytics: null,

  // Actions
  setExecuting: (isExecuting) => set({ isExecuting }),
  setSessionId: (sessionId) => set({ sessionId }),
  setConversationId: (conversationId) => {
    // 防止 conversationId 变为 undefined/null
    const safeId = conversationId ?? '';
    saveConversationId(safeId);
    set({ conversationId: safeId });
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

  // 工作台 actions — 自动同步缓存
  setMessages: (messages) => {
    const { conversationId } = get();
    saveMessagesToCache(conversationId, messages as any);
    set({ messages });
  },
  appendMessages: (msgs) => {
    const { messages, conversationId } = get();
    const updated = [...messages, ...msgs];
    saveMessagesToCache(conversationId, updated as any);
    set({ messages: updated });
  },
  setInputText: (text) => {
    saveDraft(text);
    set({ inputText: text });
  },
  setIteration: (iteration) => set({ iteration }),
  incrementIteration: () => set((s) => ({ iteration: s.iteration + 1 })),

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
  resetWorkspace: () =>
    set({
      messages: [],
      inputText: '',
      iteration: 0,
      executionStages: [],
      executionResult: null,
    }),
}));