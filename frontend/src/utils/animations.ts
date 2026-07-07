import gsap from 'gsap';

// ============================================================
// GSAP 动画辅助函数 — 替代 framer-motion，用于 React 组件
// 用法：
//   const elRef = useRef<HTMLDivElement>(null);
//   useEffect(() => {
//     const ctx = gsap.context(() => {
//       animateFadeIn(elRef.current);
//     });
//     return () => ctx.revert(); // 组件卸载时自动清理
//   }, []);
// ============================================================

/** 基础淡入 */
export const animateFadeIn = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.4,
) => {
  gsap.from(el, { opacity: 0, duration, delay, ease: 'power2.out' });
};

/** 底部滑入 */
export const animateSlideUp = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.4,
) => {
  gsap.from(el, { opacity: 0, y: 20, duration, delay, ease: 'power2.out' });
};

/** 右侧滑入 */
export const animateSlideInRight = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.35,
) => {
  gsap.from(el, { opacity: 0, x: 20, duration, delay, ease: 'power2.out' });
};

/** 左侧滑入 */
export const animateSlideInLeft = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.35,
) => {
  gsap.from(el, { opacity: 0, x: -20, duration, delay, ease: 'power2.out' });
};

/** 缩放弹入 */
export const animateScaleIn = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.3,
) => {
  gsap.from(el, { opacity: 0, scale: 0.95, duration, delay, ease: 'power2.out' });
};

/** 消息气泡入场 */
export const animateMessageBubble = (
  el: gsap.TweenTarget,
  fromRight = false,
) => {
  gsap.from(el, {
    opacity: 0,
    y: 10,
    x: fromRight ? 12 : -12,
    scale: 0.98,
    duration: 0.35,
    ease: 'back.out(1.4)',
  });
};

/** 卡片揭示入场 */
export const animateCardReveal = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.4,
) => {
  gsap.from(el, { opacity: 0, y: 24, duration, delay, ease: 'power2.out' });
};

/** 列表交错入场 — 对容器内子元素做 stagger */
export const animateStaggerList = (
  itemsSelector: string,
  scope?: gsap.TweenTarget,
  stagger = 0.06,
  duration = 0.3,
) => {
  gsap.from(itemsSelector, {
    opacity: 0,
    y: 16,
    duration,
    stagger,
    ease: 'power2.out',
    ...(scope ? { scope } : {}),
  });
};

/** 数字递增动画 */
export const animateCountUp = (
  el: gsap.TweenTarget,
  end: number,
  decimals = 0,
  duration = 1.5,
) => {
  const obj = { value: 0 };
  gsap.to(obj, {
    value: end,
    duration,
    ease: 'power2.out',
    onUpdate() {
      if (el && typeof el === 'object' && 'textContent' in el && !Array.isArray(el)) {
        (el as HTMLElement).textContent = obj.value.toFixed(decimals);
      }
    },
  });
};

/** 呼吸脉冲 */
export const animatePulse = (
  el: gsap.TweenTarget,
  scale = 1.05,
  duration = 0.6,
) => {
  return gsap.to(el, {
    scale,
    duration,
    yoyo: true,
    repeat: -1,
    ease: 'sine.inOut',
  });
};

/** 元素高度展开（用于下拉面板等） */
export const animateExpand = (
  el: gsap.TweenTarget,
  duration = 0.25,
) => {
  gsap.from(el, {
    height: 0,
    opacity: 0,
    duration,
    ease: 'power2.out',
  });
};

/** 元素交叉淡入淡出 */
export const animateCrossfade = (
  el: gsap.TweenTarget,
  duration = 0.2,
) => {
  gsap.fromTo(el, { opacity: 0.4 }, { opacity: 1, duration, ease: 'power2.out' });
};

/** 页面路由切换 — 内容区淡入 */
export const animatePageEnter = (
  el: gsap.TweenTarget,
  duration = 0.25,
) => {
  gsap.fromTo(el, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration, ease: 'power2.out' });
};

// ============================================================
// 共享过渡配置（保持与原 framer-motion 版本相同的语义）
// ============================================================

export const easeTransition = {
  duration: 0.3,
  ease: 'power2.out' as const,
};

export const springTransition = {
  duration: 0.4,
  ease: 'back.out(1.4)' as const,
};

// ============================================================
// 高级工具 — 时间线、ScrollerTrigger、预设配置
// （Phase 2 新增，供 useGSAP() + useRef 配合使用）
// ============================================================

/** createStaggerTimeline 配置 */
export interface StaggerConfig {
  container: gsap.TweenTarget;
  cardSelector: string;
  duration?: number;
  stagger?: number;
  y?: number;
  ease?: string;
  onComplete?: () => void;
}

/**
 * 创建卡片交错入场时间线。
 * 替代各页面重复的 gsap.from('.xxx-card', { ...stagger... })。
 */
export function createStaggerTimeline(config: StaggerConfig): gsap.core.Timeline {
  const {
    cardSelector,
    duration = 0.4,
    stagger = 0.06,
    y = 20,
    ease = 'power2.out',
    onComplete,
  } = config;
  // 先隐藏所有卡片，避免 from() 之前闪现
  gsap.set(cardSelector, { opacity: 0, y });
  const tl = gsap.timeline({ onComplete });
  tl.to(cardSelector, { opacity: 1, y: 0, duration, stagger, ease });
  return tl;
}

/**
 * ScrollTrigger 滚动揭示动画。
 * 元素进入 viewport 时淡入上移，滚出后 reversed。
 */
export function animateScrollReveal(
  el: gsap.TweenTarget,
  options?: {
    y?: number;
    duration?: number;
    start?: string;
  },
): gsap.core.Tween {
  const { y = 30, duration = 0.5, start = 'top 85%' } = options || {};
  return gsap.from(el, {
    opacity: 0,
    y,
    duration,
    ease: 'power2.out',
    scrollTrigger: {
      trigger: el as Element,
      start,
      toggleActions: 'play none none none',
      once: true,
    },
  });
}

/** 各页面预设配置 — 与 createStaggerTimeline 配合使用 */
export const CARD_STAGGER_PRESETS = {
  analytics: { stagger: 0.06, duration: 0.4, y: 20 },
  history: { stagger: 0.08, duration: 0.4, y: 20 },
  material: { stagger: 0.06, duration: 0.4, y: 20 },
  sync: { stagger: 0.08, duration: 0.4, y: 20 },
} as const;

// ============================================================
// 科幻特效 — 霓虹 / 故障 / 扫描线 / 终端
// ============================================================

/**
 * 霓虹发光脉冲 — 元素呼吸式发光
 * 适用于按钮、卡片边框、状态指示器
 */
export const animateNeonPulse = (
  el: gsap.TweenTarget,
  glowColor = 'rgba(37, 99, 235, 0.15)',
  duration = 2,
): gsap.core.Tween => {
  return gsap.to(el, {
    boxShadow: `0 0 20px ${glowColor}, 0 0 3px ${glowColor}`,
    duration: duration / 2,
    yoyo: true,
    repeat: -1,
    ease: 'sine.inOut',
  });
};

/**
 * 终端光标闪烁
 */
export const animateCursorBlink = (
  el: gsap.TweenTarget,
  duration = 0.8,
): gsap.core.Tween => {
  return gsap.to(el, {
    opacity: 0,
    duration,
    repeat: -1,
    yoyo: true,
    ease: 'steps(1)',
  });
};

/**
 * 数据流扫描线 — 水平扫过元素
 * 需要目标元素有 overflow:hidden
 */
export const animateScanLine = (
  el: gsap.TweenTarget,
  duration = 3,
): gsap.core.Tween => {
  return gsap.fromTo(el,
    { x: '-100%' },
    {
      x: '200%',
      duration,
      ease: 'power2.inOut',
      repeat: -1,
      repeatDelay: 2,
    },
  );
};

/**
 * 文字渐现 + 微光闪过
 */
export const animateTextGlow = (
  el: gsap.TweenTarget,
  delay = 0,
  duration = 0.6,
): gsap.core.Timeline => {
  const tl = gsap.timeline({ delay });
  tl.fromTo(el,
    { opacity: 0, textShadow: '0 0 0px rgba(0,229,255,0)' },
    { opacity: 1, textShadow: '0 0 8px rgba(0,229,255,0.3)', duration: duration * 0.3, ease: 'power2.out' },
  );
  tl.to(el, {
    textShadow: '0 0 0px rgba(0,229,255,0)',
    duration: duration * 0.7,
    ease: 'power2.out',
  });
  return tl;
};

/**
 * 悬浮装饰元素 — 随机浮动
 */
export const animateFloatingDeco = (
  elements: gsap.TweenTarget,
  range = 12,
  duration = 4,
): gsap.core.Tween => {
  return gsap.to(elements, {
    y: `random(-${range}, ${range})`,
    rotation: `random(-8, 8)`,
    duration: `random(${duration * 0.7}, ${duration})`,
    ease: 'sine.inOut',
    force3D: true,
    repeat: -1,
    yoyo: true,
    repeatRefresh: true,
    stagger: { each: 0.3, repeat: -1, yoyo: true },
  });
};

/**
 * 故障闪烁 — 短暂 opacity + 位移抖动
 */
export const animateGlitchFlash = (
  el: gsap.TweenTarget,
  intensity = 0.05,
): gsap.core.Timeline => {
  const tl = gsap.timeline();
  tl.to(el, { opacity: 0.6, x: `random(-${intensity * 2}, ${intensity * 2})`, duration: 0.05, ease: 'steps(2)' })
    .to(el, { opacity: 1, x: 0, duration: 0.08, ease: 'power2.out' })
    .to(el, { opacity: 0.8, x: `random(-${intensity}, ${intensity})`, duration: 0.04, ease: 'steps(1)' }, '+=0.02')
    .to(el, { opacity: 1, x: 0, duration: 0.1, ease: 'power2.out' });
  return tl;
};

/**
 * 霓虹边框闪烁 — 边框颜色/发光短暂切换
 */
export const animateNeonFlicker = (
  el: gsap.TweenTarget,
  flickerColor = 'rgba(37, 99, 235, 0.5)',
): gsap.core.Timeline => {
  const tl = gsap.timeline();
  tl.to(el, { borderColor: flickerColor, boxShadow: `0 0 10px ${flickerColor}`, duration: 0.1, ease: 'steps(1)' })
    .to(el, { borderColor: 'rgba(0,229,255,0.12)', boxShadow: 'none', duration: 0.15, ease: 'power2.out' })
    .to(el, { borderColor: flickerColor, boxShadow: `0 0 6px ${flickerColor}`, duration: 0.08, ease: 'steps(1)' }, '+=0.03')
    .to(el, { borderColor: 'rgba(0,229,255,0.08)', boxShadow: 'none', duration: 0.2, ease: 'power2.out' });
  return tl;
};

// ============================================================
// React 中使用 GSAP 的最佳实践:
//
//   import { useGSAP, gsap } from '@/hooks/useAnimations';
//
//   const containerRef = useRef<HTMLDivElement>(null);
//   useGSAP(() => {
//     gsap.from('.item', { opacity: 0, y: 20, stagger: 0.06 });
//   }, { scope: containerRef });
//
//   // useGSAP() 内部已使用 gsap.context()，自动清理
// ============================================================
