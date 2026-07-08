// ============================================================
// 对话消息类型（全局共享，store 和组件均依赖）
// ============================================================
export interface ChatMessageData {
  role: 'user' | 'agent';
  skill?: 'tags' | 'images' | 'music' | 'evaluation' | 'text';
  content: string;
  images?: { url?: string; path?: string }[];
  tags?: string[];
  musicList?: { name: string; artist?: string; style?: string; reason?: string; preview_url?: string | null; can_preview?: boolean }[];
  score?: number;
  level?: string;
  suggestions?: string[];
  showcase?: {
    text: string; tags: string[]; images: { url: string; desc: string }[];
    music: { name: string; artist: string; style: string; preview_url?: string | null; can_preview?: boolean }[];
    score: number; tip: string;
  };
}

// 用户输入类型
export interface UserInput {
  text: string;
  tags: string[];
  images: ImageInfo[];
  music: MusicInfo[];
  enable_blackbox?: boolean;
  conversation_id?: string;
}

// 图片信息
export interface ImageInfo {
  id?: number;
  path: string;
  url?: string;
  tags?: string[];
  width?: number;
  height?: number;
  source?: string;
  local_path?: string;
  downloaded?: boolean;
}

// 配乐信息
export interface MusicInfo {
  id?: number;
  name: string;
  url?: string;
  tags?: string[];
  style?: string;
  artist?: string;
  mood?: string;
  reason?: string;
  preview_url?: string;
  can_preview?: boolean;
}

// NLP分析结果
export interface NLPFeatures {
  keywords: string[];
  sentiment: string;
  topic: string;
  tone: string;
  length: number;
  has_question: boolean;
  has_emotion: boolean;
}

// 标签相似度
export interface TagSimilarity {
  text_tag_similarity: number;
  tag_tag_similarity: number;
  tag_hot_similarity: number;
}

// 分析结果
export interface AnalysisResult {
  nlp_features: NLPFeatures;
  tag_similarity: TagSimilarity;
  collected_data: CollectedData;
}

// 收集的数据
export interface CollectedData {
  hot_topics: string[];
  hot_music: string[];
  similar_cases: SimilarCase[];
}

// 相似案例
export interface SimilarCase {
  text: string;
  tags: string[];
  score: number;
  likes: number;
}

// 决策结果
export interface DecisionResult {
  recommended_combination: string[];
  reasons: string[];
  confidence: number;
}

// 执行结果
export interface ExecutionResult {
  creator_content: CreatorContent;
  agent_suggestions: AgentSuggestions;
  execution_log: ExecutionLog[];
  session_state: SessionState;
  evaluation?: EvaluationResult;
}

// 创作者内容
export interface CreatorContent {
  text: string;
  tags: string[];
  images: ImageInfo[];
  music: MusicInfo[];
}

// 优化信息
export interface OptimizationInfo {
  type: string;
  iteration: number;
  previous_score: number;
  delta: number;
}

// Agent建议
export interface AgentSuggestions {
  Skill1?: string[];
  Skill2?: ImageInfo[];
  Skill3?: MusicInfo[];
  _conversational?: OptimizationInfo;
}

// 执行日志
export interface ExecutionLog {
  skill: string;
  status: string;
  timestamp?: string;
}

// 会话状态
export interface SessionState {
  text: string;
  tags: string[];
  images: ImageInfo[];
  music: MusicInfo[];
  evaluation?: EvaluationResult;
}

// 评估展示
export interface EvaluationShowcase {
  text: string;
  tags: string[];
  images: ImageInfo[];
  music: MusicInfo[];
  score: number;
  tip?: string;
}

// 评估结果
export interface EvaluationResult {
  score: number;
  level: string;
  report: string;
  suggestions: string[];
  showcase?: EvaluationShowcase;
  blackbox_recommendation?: BlackboxResult;
  blackbox_prompt?: string;
}

// 智能黑箱结果
export interface BlackboxResult {
  similar_cases_count: number;
  confidence_score: number;
  recommended_path: string;
  reference_cases: SimilarCase[];
}

// 素材类型
export type MaterialType = 'text' | 'image' | 'music';

// 素材信息
export interface Material {
  id: number;
  material_type: MaterialType;
  original_content?: string;
  image_path?: string;
  music_name?: string;
  music_url?: string;
  created_at: string;
  semantic_tags?: SemanticTag[];
  usage_count?: number;
  total_likes?: number;
  total_views?: number;
  avg_engagement_rate?: number;
}

// 语义标签
export interface SemanticTag {
  tag: string;
  confidence: number;
}

// 发布历史（对齐 content_posts 表）
export interface PublishHistory {
  id: number;
  text: string;
  publish_time: string;
  // 流量指标
  views: number;
  likes: number;
  comments: number;
  shares: number;
  favorites: number;
  swipe_away_rate: number;
  copy_expand_rate: number;
  avg_images_viewed: number;
  // 粉丝指标
  fan_gain: number;
  fan_loss: number;
  fan_play_ratio: number;
  // 元数据
  source: string;
  evaluation_score: number;
  evaluation_level: string;
  tags_json?: string;
  images_json?: string;
  music_json?: string;
  created_at?: string;
  // 日趋势（详情页加载）
  traffic_daily?: TrafficDailyItem[];
  follower_daily?: FollowerDailyItem[];
}

// 流量日趋势
export interface TrafficDailyItem {
  id: number;
  content_id: number;
  date: string;
  views: number;
  source: string;
}

// 粉丝日趋势
export interface FollowerDailyItem {
  id: number;
  content_id: number;
  date: string;
  fan_gain: number;
  fan_loss: number;
  source: string;
}

// 抖音同步数据（浏览器扩展传输格式）
export interface DouyinSyncRecord {
  text: string;
  publish_time: string;
  // 流量
  views: number;
  likes: number;
  comments: number;
  shares?: number;
  favorites?: number;
  swipe_away_rate?: number;
  copy_expand_rate?: number;
  avg_images_viewed?: number;
  // 粉丝
  fan_gain?: number;
  fan_loss?: number;
  fan_play_ratio?: number;
  // 元数据
  tags: string[];
  engagement_rate?: number;
  cover_image?: string;
  evaluation_score?: number;
  evaluation_level?: string;
  source?: string;
  // 日趋势
  traffic_daily?: { date: string; views: number; source: string }[];
  follower_daily?: { date: string; fan_gain: number; fan_loss: number; source: string }[];
}

// 同步结果
export interface SyncResult {
  success: boolean;
  synced: number;
  message: string;
}

// 健康检查结果
export interface HealthCheckResult {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  features?: {
    douyin_sync: boolean;
    material_library: boolean;
    analytics: boolean;
    conversation: boolean;
  };
}

// 个人数据分析
export interface PersonalDataAnalysis {
  total_publishes: number;
  avg_views: number;
  avg_likes: number;
  avg_comments: number;
  avg_shares: number;
  avg_favorites: number;
  avg_swipe_away_rate: number;
  avg_copy_expand_rate: number;
  avg_images_viewed: number;
  total_fan_gain: number;
  total_fan_loss: number;
  avg_fan_play_ratio: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  best_content: PublishHistory | null;
  top_tags: TagPerformance[];
  source_breakdown: Record<string, number>;
}

// 标签表现
export interface TagPerformance {
  tag: string;
  usage_count: number;
  avg_likes: number;
  avg_views: number;
  avg_engagement_rate: number;
}

// Skill执行状态
export type SkillStatus = 'pending' | 'running' | 'completed' | 'failed';

// 执行阶段
export interface ExecutionStage {
  name: string;
  status: SkillStatus;
  data?: any;
  start_time?: string;
  end_time?: string;
}