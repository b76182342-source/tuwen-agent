import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Image, Row, Col, message } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, LoadingOutlined } from '@ant-design/icons';

/* ============================================================
   ChatMessage — 极简 · 紧凑 · 亲和
   三原则：去色块、高密度、暖灰调
   ============================================================ */

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

// ============================================================
// 音频试听 — 30s 轻量内联
// ============================================================
const PREVIEW_SECONDS = 30;
let _currentAudio: HTMLAudioElement | null = null;
function stopGlobalAudio() { if (_currentAudio) { _currentAudio.pause(); _currentAudio.currentTime = 0; _currentAudio = null; } }

const MusicPreview: React.FC<{ url: string; name: string }> = ({ url, name }) => {
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [progress, setProgress] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (_currentAudio === audioRef.current) _currentAudio = null;
    setPlaying(false); setProgress(0);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const toggle = () => {
    if (playing) { stop(); return; }
    if (error) setError(false);
    setLoading(true);
    if (!audioRef.current) audioRef.current = new Audio();
    const a = audioRef.current; a.src = url; a.volume = 0.7;
    const ok = () => { setLoading(false); stopGlobalAudio(); _currentAudio = a; a.play().catch(() => { setLoading(false); setError(true); message.warning(`无法播放「${name}」`); }); setPlaying(true); timerRef.current = setInterval(() => { if (a.currentTime >= PREVIEW_SECONDS) stop(); setProgress(Math.min((a.currentTime / PREVIEW_SECONDS) * 100, 100)); }, 150); a.removeEventListener('canplay', ok); };
    const fail = () => { setLoading(false); setError(true); a.removeEventListener('canplay', ok); };
    a.addEventListener('canplay', ok); a.addEventListener('error', fail, { once: true });
    setTimeout(() => { if (loading) { setLoading(false); setError(true); a.removeEventListener('canplay', ok); } }, 8000);
  };

  return (
    <span style={{ display:'inline-flex',alignItems:'center',gap:4,flexShrink:0 }}>
      <span onClick={toggle} style={{ cursor:'pointer',display:'inline-flex',alignItems:'center',justifyContent:'center',width:20,height:20,borderRadius:'50%',background:playing?'#D97706':'transparent',color:playing?'#fff':'#A8A29E',fontSize:12,transition:'all 0.15s',userSelect:'none' }}>
        {loading ? <LoadingOutlined spin /> : error ? '⚠' : playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
      </span>
      {playing && (
        <span style={{ width:28,height:2,background:'#E7E5E4',borderRadius:1,overflow:'hidden' }}>
          <span style={{ display:'block',width:`${progress}%`,height:'100%',background:'#D97706',borderRadius:1,transition:'width 0.15s' }} />
        </span>
      )}
    </span>
  );
};

// ============================================================
// 极简技能标记（只用小圆点 + 文字，不用 emoji 色块）
// ============================================================
const skillDot: Record<string, string> = {
  tags: '#D97706', images: '#78716C', music: '#78716C', evaluation: '#D97706', text: '#A8A29E',
};
const skillLabel: Record<string, string> = {
  tags: '标签', images: '图片', music: '配乐', evaluation: '评估', text: '',
};

// ============================================================
// ShowcaseCard — 极简版，去卡片感
// ============================================================
const ShowcaseCard: React.FC<{ s: NonNullable<ChatMessageData['showcase']>; score?: number; level?: string }> = ({ s, score, level }) => {
  const [idx, setIdx] = useState(0);
  const [tagsOpen, setTagsOpen] = useState(false);
  const [musicOpen, setMusicOpen] = useState(false);
  const [mIdx, setMIdx] = useState(0);
  const vt = tagsOpen ? s.tags : s.tags.slice(0, 3);

  return (
    <div style={{ marginTop:16 }}>
      <div style={{ maxWidth:300, margin:'0 auto', borderRadius:10, overflow:'hidden', border:'1px solid #E7E5E4' }}>
        {/* 图片 */}
        {s.images.length > 0 ? (
          <div style={{ position:'relative',aspectRatio:'4/5',background:'#292524' }}>
            <Image src={s.images[idx].url} width="100%" height="100%" style={{ objectFit:'cover' }} preview={false} />
            <div style={{ position:'absolute',bottom:0,left:0,right:0,height:'30%',background:'linear-gradient(transparent,rgba(0,0,0,0.15))',pointerEvents:'none' }} />
            {s.images.length > 1 && <>
              <span onClick={() => setIdx(p=>(p-1+s.images.length)%s.images.length)} style={{ position:'absolute',left:6,top:'50%',transform:'translateY(-50%)',width:24,height:24,borderRadius:'50%',background:'rgba(255,255,255,0.8)',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',fontSize:14,color:'#444' }}>‹</span>
              <span onClick={() => setIdx(p=>(p+1)%s.images.length)} style={{ position:'absolute',right:6,top:'50%',transform:'translateY(-50%)',width:24,height:24,borderRadius:'50%',background:'rgba(255,255,255,0.8)',display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer',fontSize:14,color:'#444' }}>›</span>
              <div style={{ position:'absolute',bottom:8,left:'50%',transform:'translateX(-50%)',display:'flex',gap:4 }}>
                {s.images.map((_,i) => <span key={i} style={{ width:i===idx?14:4,height:4,borderRadius:2,background:i===idx?'#fff':'rgba(255,255,255,0.4)',transition:'all 0.2s' }} />)}
              </div>
            </>}
            <span style={{ position:'absolute',top:8,right:8,background:'rgba(0,0,0,0.3)',color:'#fff',padding:'1px 7px',borderRadius:6,fontSize:10 }}>{idx+1}/{s.images.length}</span>
          </div>
        ) : <div style={{ aspectRatio:'4/5',background:'#F5F5F4',display:'flex',alignItems:'center',justifyContent:'center',color:'#D6D3D1',fontSize:12 }}>暂无图片</div>}

        {/* 文案 + 标签 + 评分 — 紧凑排版 */}
        <div style={{ padding:'12px 14px 10px' }}>
          <div style={{ fontSize:13,lineHeight:1.65,color:'#292524',marginBottom:8,wordBreak:'break-word' }}>{s.text}</div>
          <div style={{ display:'flex',flexWrap:'wrap',gap:4,alignItems:'center',marginBottom:6 }}>
            {vt.map(t => <span key={t} style={{ fontSize:11,color:'#B45309' }}>#{t}</span>)}
            {s.tags.length > 3 && <span onClick={() => setTagsOpen(!tagsOpen)} style={{ fontSize:11,color:'#A8A29E',cursor:'pointer' }}>{tagsOpen?'收起':`+${s.tags.length-3}`}</span>}
          </div>
          {score !== undefined && (
            <span style={{ fontSize:12,fontWeight:600,color:score>=4?'#78716C':'#B45309' }}>
              {score.toFixed(1)} 分{level ? ` · ${level}` : ''}
            </span>
          )}
        </div>

        {/* 配乐 — 极简浮标 */}
        {s.music.length > 0 && (
          <div style={{ position:'relative',padding:'0 14px 12px' }}>
            <span onClick={() => setMusicOpen(!musicOpen)} style={{ display:'inline-flex',alignItems:'center',gap:4,fontSize:11,color:'#78716C',cursor:'pointer',padding:'3px 0' }}>
              ♪ {s.music[mIdx]?.name || '配乐'} {musicOpen?'▲':'▼'}
            </span>
            {musicOpen && (
              <div style={{ position:'absolute',bottom:36,left:6,right:6,background:'#fff',borderRadius:8,border:'1px solid #E7E5E4',boxShadow:'0 2px 12px rgba(0,0,0,0.05)',padding:'2px 0',zIndex:3 }}>
                {s.music.map((m,i) => (
                  <div key={i} onClick={() => { setMIdx(i); setMusicOpen(false); }} style={{ display:'flex',alignItems:'center',gap:6,padding:'6px 12px',cursor:'pointer',fontSize:12,color:i===mIdx?'#B45309':'#44403C',fontWeight:i===mIdx?500:400,background:i===mIdx?'#FFF7ED':'transparent' }}>
                    {m.name}{m.artist && <span style={{ color:'#A8A29E',fontSize:11 }}>— {m.artist}</span>}
                    {m.can_preview && m.preview_url && <MusicPreview url={m.preview_url} name={m.name} />}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <div style={{ textAlign:'center',marginTop:6,fontSize:10,color:'#D6D3D1' }}>{s.tip}</div>
    </div>
  );
};

// ============================================================
// ChatMessage 主组件
// ============================================================
const ChatMessage: React.FC<{ message: ChatMessageData }> = ({ message }) => {
  const { role, skill, content, images, tags, musicList, score, level, suggestions } = message;

  // ── 用户 — 柔暖色气泡，只有背景没有边框 ──
  if (role === 'user') {
    return (
      <div style={{ display:'flex',justifyContent:'flex-end',marginBottom:24,padding:'0 8px' }}>
        <div style={{ maxWidth:'72%' }}>
          <div style={{ background:'#FFF7ED',color:'#44403C',borderRadius:14,padding:'10px 16px',fontSize:14,lineHeight:1.65,wordBreak:'break-word' }}>
            {content}
          </div>
          {images && images.length > 0 && (
            <div style={{ marginTop:6,display:'flex',gap:4,justifyContent:'flex-end' }}>
              {images.slice(0,4).map((img,i) => <Image key={i} src={img.url} width={48} height={48} style={{ borderRadius:6,objectFit:'cover' }} fallback="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>" />)}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Agent — 三段式极简结构：标记行 · 内容区 · 底部行动 ──
  const dot = skill ? skillDot[skill] : '#A8A29E';
  const label = skill ? skillLabel[skill] : '';

  return (
    <div style={{ marginBottom:26,padding:'0 8px' }}>

      {/* 第一段：极简标记 — 仅圆点 + 文字 */}
      <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:8 }}>
        <span style={{ width:6,height:6,borderRadius:'50%',background:dot,flexShrink:0 }} />
        <span style={{ fontSize:12,color:'#A8A29E' }}>Agent{label ? ` · ${label}` : ''}</span>
      </div>

      {/* 第二段：内容 — 无包裹、无背景、无边框 */}
      <div style={{ paddingLeft:14 }}>

        {/* -- 纯文本 -- */}
        {skill === 'text' && <div style={{ fontSize:14,lineHeight:1.75,color:'#44403C' }}>{content}</div>}

        {/* -- 标签：纯文字流，不用色块 -- */}
        {skill === 'tags' && (
          <div style={{ display:'flex',flexWrap:'wrap',columnGap:12,rowGap:4 }}>
            {tags?.map((t,i) => (
              <span key={i} style={{ fontSize:13,color:'#B45309',lineHeight:1.6 }}>#{t}</span>
            ))}
          </div>
        )}

        {/* -- 图片：紧凑网格，无边框 -- */}
        {skill === 'images' && (
          <Row gutter={[6,6]}>
            {images?.map((img,i) => (
              <Col span={6} key={i}>
                <Image src={img.url||img.path} width="100%" style={{ borderRadius:6,objectFit:'cover',aspectRatio:'3/4' }} fallback="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>" />
              </Col>
            ))}
          </Row>
        )}

        {/* -- 配乐：纯文行，无卡片包裹 -- */}
        {skill === 'music' && (
          <div style={{ display:'flex',flexDirection:'column',gap:1 }}>
            {musicList?.map((m,i) => (
              <div key={i} style={{ display:'flex',alignItems:'center',gap:8,padding:'4px 0',fontSize:13 }}>
                {m.can_preview && m.preview_url ? (
                  <MusicPreview url={m.preview_url} name={m.name} />
                ) : (
                  <span style={{ width:20,flexShrink:0 }} />
                )}
                <span style={{ color:'#292524' }}>{m.name}</span>
                {m.artist && <span style={{ color:'#A8A29E',fontSize:12 }}>{m.artist}</span>}
                {m.style && <span style={{ color:'#A8A29E',fontSize:11 }}>· {m.style}</span>}
              </div>
            ))}
          </div>
        )}

        {/* -- 评估：分行紧凑信息 -- */}
        {skill === 'evaluation' && score !== undefined && (
          <div>
            {/* 评分行：所有关键信息在一行 */}
            <div style={{ display:'flex',alignItems:'baseline',gap:8,marginBottom:6 }}>
              <span style={{ fontSize:22,fontWeight:700,color:score>=4?'#78716C':'#B45309',lineHeight:1 }}>
                {score.toFixed(1)}
              </span>
              <span style={{ fontSize:13,color:'#78716C' }}>分</span>
              {level && <span style={{ fontSize:12,color:'#A8A29E' }}>· {level}</span>}
              <span style={{ fontSize:12,color:score>=4?'#78716C':'#B45309' }}>
                · {score>=4?'建议发布':'建议优化'}
              </span>
            </div>

            {/* 建议：纯文逐行 */}
            {suggestions && suggestions.length > 0 && (
              <div style={{ fontSize:13,color:'#78716C',lineHeight:1.7 }}>
                {suggestions.map((s,i) => <div key={i}>· {s}</div>)}
              </div>
            )}

            {/* 样例卡片（若有） */}
            {message.showcase && <ShowcaseCard s={message.showcase} score={score} level={level} />}
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatMessage;
