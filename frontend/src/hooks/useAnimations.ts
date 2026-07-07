// ============================================================
// GSAP 动画统一入口 — 桶文件
// 所有组件应从此文件导入，而非直接 import gsap
// ============================================================

export { useGSAP } from '@gsap/react';
export { default as gsap } from 'gsap';

// 重导出 animations.ts 全部工具函数
export {
  animateFadeIn,
  animateSlideUp,
  animateSlideInRight,
  animateSlideInLeft,
  animateScaleIn,
  animateMessageBubble,
  animateCardReveal,
  animateStaggerList,
  animateCountUp,
  animatePulse,
  animateExpand,
  animateCrossfade,
  animatePageEnter,
  easeTransition,
  springTransition,
  // Phase 2 新增 — 时间线 / ScrollTrigger / 预设
  createStaggerTimeline,
  animateScrollReveal,
  CARD_STAGGER_PRESETS,
  // 科幻特效
  animateNeonPulse,
  animateCursorBlink,
  animateScanLine,
  animateTextGlow,
  animateFloatingDeco,
  animateGlitchFlash,
  animateNeonFlicker,
} from '@/utils/animations';
export type { StaggerConfig } from '@/utils/animations';

// ============================================================
// 共享 Hook — 页面卡片交错入场
// ============================================================

import { useRef, useCallback } from 'react';
import { useGSAP as useGSAPRaw } from '@gsap/react';
import { default as gsapLib } from 'gsap';
import { createStaggerTimeline, CARD_STAGGER_PRESETS, type StaggerConfig } from '@/utils/animations';

/**
 * 通用卡片交错入场 Hook。
 * 替代 Analytics/PublishHistory/MaterialLibrary/DouyinSync 的重复代码。
 *
 * 用法：
 *   const ref = useRef<HTMLDivElement>(null);
 *   useCardStagger({ container: ref, cardSelector: '.my-card' });
 */
export function useCardStagger(config: Omit<StaggerConfig, 'container'> & { container: React.RefObject<HTMLElement | null> }): void {
  useGSAPRaw(() => {
    createStaggerTimeline({ ...config, container: config.container.current });
  }, {
    dependencies: [config.cardSelector],
    scope: config.container,
  });
}

/**
 * 便捷版 — 用 CARD_STAGGER_PRESETS 预设值。
 *
 * 用法：
 *   const ref = useRef<HTMLDivElement>(null);
 *   usePresetCardStagger(ref, 'analytics-card', 'analytics', { ready: !loading });
 */
export function usePresetCardStagger(
  containerRef: React.RefObject<HTMLElement | null>,
  cardClass: string,
  preset: keyof typeof CARD_STAGGER_PRESETS,
  opts?: {
    ready?: boolean;
    extraConfig?: Partial<Omit<StaggerConfig, 'container' | 'cardSelector'>>;
  },
): void {
  const presetConfig = CARD_STAGGER_PRESETS[preset];
  const ready = opts?.ready ?? true;
  useGSAPRaw(() => {
    if (!ready || !containerRef.current) return;
    createStaggerTimeline({
      container: containerRef.current,
      cardSelector: `.${cardClass}`,
      ...presetConfig,
      ...opts?.extraConfig,
    });
  }, {
    dependencies: [cardClass, preset, ready],
    scope: containerRef,
  });
}

// ============================================================
// 共享 Hook — GSAP Hover 交互
// ============================================================

/**
 * GSAP hover 动画 hook。
 * 替代内联 onMouseEnter/onMouseLeave 直接改 style。
 * 自动 kill 旧 tween 防止动画队列堆积。
 *
 * 用法：
 *   const hover = useGSAPHover(
 *     { backgroundColor: '#FFF7ED', duration: 0.15 },
 *     { backgroundColor: 'transparent', duration: 0.15 },
 *   );
 *   <div {...hover}>hover me</div>
 */
export function useGSAPHover(
  enterVars: Record<string, unknown>,
  leaveVars: Record<string, unknown>,
): {
  onMouseEnter: React.MouseEventHandler;
  onMouseLeave: React.MouseEventHandler;
} {
  const tweenRef = useRef<{ kill: () => void } | null>(null);

  const onMouseEnter = useCallback((e: React.MouseEvent) => {
    tweenRef.current?.kill();
    tweenRef.current = gsapLib.to(e.currentTarget, { ...enterVars, overwrite: 'auto' });
  }, [enterVars]);

  const onMouseLeave = useCallback((e: React.MouseEvent) => {
    tweenRef.current?.kill();
    tweenRef.current = gsapLib.to(e.currentTarget, { ...leaveVars, overwrite: 'auto' });
  }, [leaveVars]);

  return { onMouseEnter, onMouseLeave };
}
