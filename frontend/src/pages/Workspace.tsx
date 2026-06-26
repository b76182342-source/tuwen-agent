import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Upload, Spin, message, Image, Checkbox, Popconfirm } from 'antd';
import { SendOutlined, PlusOutlined, DeleteOutlined, LoadingOutlined, ReloadOutlined, MessageOutlined, CheckSquareOutlined } from '@ant-design/icons';
import ChatMessage, { type ChatMessageData } from '@/components/ChatMessage';
import ExecutionFlow from '@/components/ExecutionFlow';
import { useAppStore, saveMessagesToCache, loadMessagesFromCache } from '@/stores/appStore';
import type { UploadFile } from 'antd/es/upload/interface';
import { agentApi, conversationApi } from '@/services/api';
import type { ExecutionStage, SkillStatus } from '@/types';

/* ============================================================
   Workspace — Claude Code 式极简对话工作台
   设计原则：去卡片化 · 大留白 · 柔边界 · 内容优先
   ============================================================ */

// TODO: [架构] 当前组件约 386 行，在 React 中属于正常范围。
//       如需拆分，可提取 ConversationListPanel.tsx、MessageInput.tsx 等子组件。
//       当前阶段拆分收益有限，且会引入更多 props 传递和状态同步问题。

// 生成会话摘要：从首条用户消息中提取关键词
const generateConversationSummary = (content: string): string => {
  if (!content) return '新对话';
  const text = content.trim();
  if (text.length <= 20) return text;
  return text.slice(0, 18) + '...';
};

const Workspace: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [inputText, setInputText] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [sending, setSending] = useState(false);
  const [iteration, setIteration] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [conversations, setConversations] = useState<any[]>([]);
  const [showConversationList, setShowConversationList] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(true);
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedConversations, setSelectedConversations] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);
  const {
    conversationId, setConversationId,
    setExecutionStages, setExecutionResult,
  } = useAppStore();

  useEffect(() => {
    initConversation();
    const republishData = localStorage.getItem('republish_data');
    if (republishData) {
      try { const data = JSON.parse(republishData); if (data.text) setInputText(data.text); localStorage.removeItem('republish_data'); }
      catch { localStorage.removeItem('republish_data'); }
    }
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

  // focus input on mount
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 300); }, [loaded]);

  const initConversation = async () => {
    const convId = useAppStore.getState().conversationId;
    try {
      if (convId) { await loadConversationHistory(convId); setBackendAvailable(true); }
      else { await createNewConversation(); }
      loadConversations().catch(() => {});
    } catch {
      setBackendAvailable(false);
      if (convId) {
        const cached = loadMessagesFromCache(convId);
        if (cached.length > 0) { setMessages(cached as ChatMessageData[]); message.warning('后端未连接，显示本地缓存'); }
        else { message.warning('后端未连接，请检查服务是否启动'); }
      }
    } finally { setLoaded(true); }
  };

  const createNewConversation = async () => {
    try {
      const r = await conversationApi.create({ title: '新对话', user_id: 'default_user' });
      setConversationId(r.data.conversation_id); setMessages([]); setIteration(0); setExecutionStages([]); setExecutionResult(null);
      setBackendAvailable(true); message.success('新对话已创建');
    } catch {
      const localId = 'local_' + Date.now(); setConversationId(localId); setMessages([]); setBackendAvailable(false);
    }
  };

  const loadConversationHistory = async (convId: string) => {
    try {
      const r = await conversationApi.getHistory(convId);
      const msgs = r.data.map((msg: any) => {
        const m = msg.metadata ? JSON.parse(msg.metadata) : {};
        return { role: msg.role, content: msg.content, tags: m.tags || [], images: m.images || [], musicList: m.music || [], score: m.evaluation_score, level: m.evaluation_level, suggestions: m.agent_suggestions || [] } as ChatMessageData;
      });
      setMessages(msgs); setIteration(Math.floor(msgs.length / 2));
      if (msgs.length > 0) saveMessagesToCache(convId, msgs as any);
    } catch {
      const cached = loadMessagesFromCache(convId);
      if (cached.length > 0) { setMessages(cached as ChatMessageData[]); message.warning('后端未连接，显示本地缓存'); }
    }
  };

  const loadConversations = async () => { try { const r = await conversationApi.list({ limit: 20 }); setConversations(r.data); } catch {} };
  const switchConversation = async (id: string) => { setConversationId(id); setShowConversationList(false); setMultiSelectMode(false); setSelectedConversations(new Set()); await loadConversationHistory(id); message.success('已切换对话'); };
  const deleteConversation = async (id: string) => {
    if (!confirm('确定要删除这个对话吗？')) return;
    try { await conversationApi.delete(id); if (id === conversationId) await createNewConversation(); await loadConversations(); message.success('对话已删除'); }
    catch { message.error('删除对话失败'); }
  };
  const batchDeleteConversations = async () => {
    if (selectedConversations.size === 0) { message.warning('请先选择要删除的对话'); return; }
    if (!confirm(`确定要删除选中的 ${selectedConversations.size} 个对话吗？`)) return;
    try {
      const ids = Array.from(selectedConversations);
      await conversationApi.batchDelete(ids);
      if (ids.includes(conversationId || '')) await createNewConversation();
      await loadConversations();
      setSelectedConversations(new Set());
      setMultiSelectMode(false);
      message.success(`已删除 ${ids.length} 个对话`);
    } catch { message.error('批量删除失败'); }
  };
  const toggleConversationSelect = (id: string) => {
    const newSet = new Set(selectedConversations);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedConversations(newSet);
  };
  const toggleSelectAll = () => {
    if (selectedConversations.size === conversations.length) setSelectedConversations(new Set());
    else setSelectedConversations(new Set(conversations.map(c => c.conversation_id)));
  };
  // 更新对话标题：从首条消息生成摘要
  const updateConversationTitle = async (convId: string, firstUserMessage: string) => {
    const summary = generateConversationSummary(firstUserMessage);
    if (summary && summary !== '新对话') {
      try { await conversationApi.updateTitle(convId, summary); } catch {}
    }
  };

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text && fileList.length === 0) return;
    const originFiles = fileList.filter(f => f.originFileObj);
    // 本地预览用 blob URL
    const userImages = originFiles.map(f => ({ url: URL.createObjectURL(f.originFileObj!), path: f.name }));
    const userMsg: ChatMessageData = { role: 'user', content: text || '(图片素材)', images: userImages };
    const newMsgs = [...messages, userMsg];
    setMessages(newMsgs); setInputText(''); setSending(true);
    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setExecutionStages([
      { name: '标签推荐', status: 'pending', start_time: now } as ExecutionStage,
      { name: '图片推荐', status: 'pending', start_time: now } as ExecutionStage,
      { name: '配乐推荐', status: 'pending', start_time: now } as ExecutionStage,
      { name: '内容评估', status: 'pending', start_time: now } as ExecutionStage,
    ]);
    setMessages([...newMsgs, { role: 'agent', skill: 'text', content: '思考中...' }]);

    try {
      // 上传用户图片到后端 → 获得持久化 URL（跨轮次可用）
      let uploadedUrls: { url: string; path: string }[] = [];
      if (originFiles.length > 0) {
        const uploadPromises = originFiles.map(async (f) => {
          const form = new FormData();
          form.append('file', f.originFileObj as Blob, (f.originFileObj as File).name || f.name);
          const res = await fetch('/api/upload', { method: 'POST', body: form });
          const data = await res.json();
          return { url: data.url, path: data.original_name || f.name };
        });
        uploadedUrls = await Promise.all(uploadPromises);
      }

      const r = await agentApi.run({ text, tags: [], images: uploadedUrls, music: [], enable_blackbox: false, conversation_id: conversationId });
      const result: any = r.data; const agentMsgs: ChatMessageData[] = [];
      if (result.execution_log?.length) {
        const m: Record<string, SkillStatus> = { completed: 'completed', running: 'running', failed: 'failed', pending: 'pending' };
        setExecutionStages(result.execution_log.map((l: any) => ({ name: l.skill || l.name, status: (m[l.status] || 'completed') as SkillStatus, start_time: l.start_time || l.timestamp || now, end_time: l.end_time || (l.status === 'completed' ? new Date().toLocaleTimeString('zh-CN', { hour12: false }) : undefined) })));
      }
      setExecutionResult(result);
      if (result.agent_suggestions?.Skill1?.length) agentMsgs.push({ role: 'agent', skill: 'tags', content: '标签推荐', tags: result.agent_suggestions.Skill1 });
      if (result.agent_suggestions?.Skill2?.length) agentMsgs.push({ role: 'agent', skill: 'images', content: '图片推荐', images: result.agent_suggestions.Skill2.map((img: any) => ({ url: img.original_url, path: img.local_path || img.description })) });
      if (result.agent_suggestions?.Skill3?.length) agentMsgs.push({ role: 'agent', skill: 'music', content: '配乐推荐', musicList: result.agent_suggestions.Skill3.map((m: any) => ({ name: m.name, artist: m.artist, style: m.style, reason: m.reason })) });
      if (result.evaluation) { const ev = result.evaluation; agentMsgs.push({ role: 'agent', skill: 'evaluation', content: '内容评估', score: ev.score, level: ev.level, suggestions: ev.suggestions, showcase: ev.showcase }); }
      const finalMsgs = [...newMsgs, ...agentMsgs];
      setMessages(finalMsgs); setIteration(p => p + 1);
      saveMessagesToCache(conversationId, finalMsgs as any);
      // 自动更新对话标题为用户首条消息的摘要
      if (messages.length === 0 && text) updateConversationTitle(conversationId, text);
      await loadConversations();
    } catch (e: any) {
      const err = e?.response?.data?.detail || e?.message || '未知错误';
      setMessages([...newMsgs, { role: 'agent', skill: 'text', content: `请求失败: ${err}` }]);
      saveMessagesToCache(conversationId, [...newMsgs, { role: 'agent', skill: 'text', content: `请求失败: ${err}` }] as any);
      message.error(`请求失败: ${err}`);
      setExecutionStages([
        { name: '标签推荐', status: 'failed' as SkillStatus, start_time: now, end_time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) } as ExecutionStage,
        { name: '图片推荐', status: 'failed' as SkillStatus, start_time: now, end_time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) } as ExecutionStage,
        { name: '配乐推荐', status: 'failed' as SkillStatus, start_time: now, end_time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) } as ExecutionStage,
        { name: '内容评估', status: 'failed' as SkillStatus, start_time: now, end_time: new Date().toLocaleTimeString('zh-CN', { hour12: false }) } as ExecutionStage,
      ]);
    } finally { setSending(false); setFileList([]); }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  if (!loaded) return <div style={{ display:'flex',justifyContent:'center',alignItems:'center',height:400 }}><Spin size="large" /></div>;

  return (
    <div style={{ display:'flex',flexDirection:'column',height:'calc(100vh - 140px)',maxWidth:860,margin:'0 auto',width:'100%' }}>
      {/* 离线提示 */}
      {!backendAvailable && (
        <div style={{ background:'#FFF7ED',border:'1px solid #FED7AA',borderRadius:10,padding:'8px 16px',marginBottom:12,display:'flex',alignItems:'center',justifyContent:'space-between' }}>
          <span style={{ color:'#B45309',fontSize:13 }}>⚠️ 后端未连接，显示本地缓存</span>
          <Button size="small" onClick={initConversation} style={{ borderRadius:8 }}>重新连接</Button>
        </div>
      )}

      {/* 顶部工具栏 — 极简 */}
      <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',padding:'0 0 12px',marginBottom:4 }}>
        <div style={{ display:'flex',alignItems:'center',gap:12 }}>
          <span
            onClick={() => setShowConversationList(!showConversationList)}
            style={{ fontSize:13,color:'#78716C',cursor:'pointer',display:'flex',alignItems:'center',gap:6,userSelect:'none',padding:'4px 0' }}
          >
            <MessageOutlined style={{ fontSize:14 }} /> 对话列表
          </span>
          <span style={{ color:'#D6D3D1',fontSize:13 }}>·</span>
          <span style={{ fontSize:12,color:'#A8A29E' }}>{conversationId?.slice(-8)} · 第 {iteration} 轮</span>
        </div>
        <span onClick={createNewConversation} style={{ fontSize:13,color:'#78716C',cursor:'pointer',padding:'4px 0' }}>
          <ReloadOutlined style={{ marginRight:4 }} />新对话
        </span>
      </div>

      {/* 对话列表面板 — 浮层式 */}
      {showConversationList && (
        <div style={{ marginBottom:12,background:'#FAF9F6',border:'1px solid #E7E5E4',borderRadius:12,padding:16 }}>
          <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14 }}>
            <div style={{ display:'flex',alignItems:'center',gap:8 }}>
              <span style={{ fontWeight:600,fontSize:14,color:'#292524' }}>对话列表</span>
              {multiSelectMode && <span style={{ fontSize:12,color:'#78716C' }}>（已选 {selectedConversations.size} 项）</span>}
            </div>
            <div style={{ display:'flex',gap:8,alignItems:'center' }}>
              {multiSelectMode ? (
                <>
                  <Button size="small" onClick={toggleSelectAll} style={{ borderRadius:6 }}>
                    {selectedConversations.size === conversations.length ? '取消全选' : '全选'}
                  </Button>
                  <Popconfirm title="确定批量删除？" onConfirm={batchDeleteConversations} okText="删除" cancelText="取消">
                    <Button size="small" danger disabled={selectedConversations.size === 0} style={{ borderRadius:6 }}>
                      删除({selectedConversations.size})
                    </Button>
                  </Popconfirm>
                  <Button size="small" onClick={() => { setMultiSelectMode(false); setSelectedConversations(new Set()); }} style={{ borderRadius:6 }}>取消</Button>
                </>
              ) : (
                <>
                  <Button size="small" icon={<CheckSquareOutlined />} onClick={() => setMultiSelectMode(true)} style={{ borderRadius:6 }}>多选</Button>
                  <span onClick={() => setShowConversationList(false)} style={{ cursor:'pointer',color:'#A8A29E',fontSize:14,marginLeft:4 }}>✕</span>
                </>
              )}
            </div>
          </div>
          <Button type="primary" size="small" block style={{ marginBottom:12,borderRadius:8 }} onClick={createNewConversation}>+ 新对话</Button>
          <div style={{ maxHeight:260,overflowY:'auto' }}>
            {conversations.map(c => (
              <div key={c.conversation_id}
                onClick={() => multiSelectMode ? toggleConversationSelect(c.conversation_id) : switchConversation(c.conversation_id)}
                style={{
                  padding:'8px 12px',borderRadius:8,cursor:'pointer',marginBottom:4,
                  background: selectedConversations.has(c.conversation_id) ? '#E8F5E9' : c.conversation_id === conversationId ? '#FFF7ED' : 'transparent',
                  border: selectedConversations.has(c.conversation_id) ? '1px solid #81C784' : c.conversation_id === conversationId ? '1px solid #FED7AA' : '1px solid transparent',
                  transition:'all 0.15s',
                  display:'flex',alignItems:'center',gap:8,
                }}
                onMouseEnter={e => { if (!selectedConversations.has(c.conversation_id) && c.conversation_id !== conversationId) { e.currentTarget.style.background='#F5F5F4'; } }}
                onMouseLeave={e => { if (!selectedConversations.has(c.conversation_id) && c.conversation_id !== conversationId) { e.currentTarget.style.background='transparent'; } }}
              >
                {multiSelectMode && (
                  <Checkbox checked={selectedConversations.has(c.conversation_id)} onChange={() => toggleConversationSelect(c.conversation_id)} onClick={e => e.stopPropagation()} />
                )}
                <div style={{ flex:1,minWidth:0 }}>
                  <div style={{ fontSize:13,fontWeight:500,color:'#292524',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis' }}>
                    {c.title || '未命名'}
                  </div>
                  {c.updated_at && (
                    <div style={{ fontSize:11,color:'#A8A29E',marginTop:2 }}>
                      {new Date(c.updated_at).toLocaleString('zh-CN', { month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit' })}
                    </div>
                  )}
                </div>
                {!multiSelectMode && (
                  <DeleteOutlined style={{ fontSize:12,color:'#D6D3D1',cursor:'pointer',flexShrink:0 }} onClick={e => { e.stopPropagation(); deleteConversation(c.conversation_id); }} />
                )}
              </div>
            ))}
            {conversations.length === 0 && (
              <div style={{ textAlign:'center',padding:'24px 0',color:'#A8A29E',fontSize:13 }}>暂无对话记录</div>
            )}
          </div>
        </div>
      )}

      {/* 执行流程 — 轻量内嵌 */}
      <div style={{ marginBottom:8 }}>
        <ExecutionFlow />
      </div>

      {/* 消息区域 — 核心对话空间 */}
      <div style={{ flex:1,overflowY:'auto',padding:'4px 0 20px' }}>
        {messages.length === 0 ? (
          <div style={{ display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',minHeight:320 }}>
            <div style={{ fontSize:40,marginBottom:16,opacity:0.6 }}>💬</div>
            <div style={{ fontSize:20,fontWeight:600,color:'#292524',marginBottom:6 }}>开始创作</div>
            <div style={{ fontSize:14,color:'#A8A29E',marginBottom:28,textAlign:'center',lineHeight:1.8 }}>
              输入你的文案或想法，Agent 会帮你<br />补全标签、图片和配乐
            </div>
            <div style={{ display:'flex',gap:8,flexWrap:'wrap',justifyContent:'center' }}>
              {['春日旅行随拍','我的猫把花瓶推倒了','浴室好物推荐'].map(h => (
                <span key={h} onClick={() => setInputText(h)}
                  style={{
                    padding:'6px 14px',borderRadius:18,fontSize:13,color:'#78716C',
                    background:'#fff',border:'1px solid #E7E5E4',cursor:'pointer',
                    transition:'all 0.15s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.background='#FFF7ED'; e.currentTarget.style.borderColor='#FED7AA'; e.currentTarget.style.color='#B45309'; }}
                  onMouseLeave={e => { e.currentTarget.style.background='#fff'; e.currentTarget.style.borderColor='#E7E5E4'; e.currentTarget.style.color='#78716C'; }}
                >💡 {h}</span>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => <ChatMessage key={i} message={msg} />)
        )}
        {sending && (
          <div style={{ display:'flex',alignItems:'center',gap:10,padding:'12px 0',color:'#A8A29E',fontSize:13 }}>
            <Spin size="small" /> Agent 思考中...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 图片预览 */}
      {fileList.length > 0 && (
        <div style={{ display:'flex',gap:8,padding:'0 0 8px' }}>
          {fileList.map(f => (
            <div key={f.uid} style={{ position:'relative' }}>
              <Image src={URL.createObjectURL(f.originFileObj!)} width={48} height={48} style={{ borderRadius:8,objectFit:'cover',border:'1px solid #E7E5E4' }} preview={false} />
              <span onClick={() => setFileList(p => p.filter(x => x.uid !== f.uid))}
                style={{ position:'absolute',top:-6,right:-6,width:18,height:18,borderRadius:'50%',background:'#fff',border:'1px solid #E7E5E4',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',fontSize:10,color:'#A8A29E' }}
              >✕</span>
            </div>
          ))}
        </div>
      )}

      {/* 输入区 — Claude Code 式极简 */}
      <div style={{ padding:'12px 0 4px',borderTop:'1px solid #F5F5F4' }}>
        <div style={{ display:'flex',gap:8,alignItems:'flex-end',background:'#fff',border:'1px solid #E7E5E4',borderRadius:14,padding:'4px 6px',transition:'border-color 0.2s' }}
          onFocusCapture={() => {} }
        >
          <Upload fileList={[]} beforeUpload={file => { setFileList(p => [...p, { uid:`${Date.now()}`,name:file.name,originFileObj:file } as UploadFile]); return false; }} showUploadList={false} accept="image/*" multiple>
            <Button type="text" icon={<PlusOutlined />} disabled={sending} style={{ borderRadius:8,color:'#A8A29E',height:34 }} />
          </Upload>
          <Input.TextArea
            ref={inputRef}
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入文案，或上传图片让 Agent 识别..."
            autoSize={{ minRows:1,maxRows:5 }}
            disabled={sending}
            style={{ flex:1,border:'none',background:'transparent',boxShadow:'none',resize:'none',padding:'6px 0',fontSize:14,lineHeight:1.6 }}
          />
          <Button
            type="primary"
            icon={sending ? <LoadingOutlined /> : <SendOutlined />}
            onClick={handleSend}
            disabled={sending || (!inputText.trim() && fileList.length === 0)}
            style={{ borderRadius:10,height:34,width:34,minWidth:34,padding:0,display:'flex',alignItems:'center',justifyContent:'center' }}
          />
        </div>
        <div style={{ textAlign:'center',padding:'6px 0 0',fontSize:11,color:'#D6D3D1' }}>
          创作者主导 · 智能辅助 — Agent 不会自动发布内容
        </div>
      </div>
    </div>
  );
};

export default Workspace;
