import React from 'react';
import { Steps, Spin } from 'antd';
import { CheckCircleOutlined, LoadingOutlined, ClockCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { useAppStore } from '@/stores/appStore';

/* ============================================================
   ExecutionFlow — 极简步骤条，无卡片包裹
   ============================================================ */

const ExecutionFlow: React.FC = () => {
  const { executionStages } = useAppStore();

  const getStatus = (name: string) => {
    const s = executionStages.find(x => x.name === name || x.name?.includes(name) || name.includes(x.name));
    if (!s) return 'wait';
    if (s.status === 'completed') return 'finish';
    if (s.status === 'running') return 'process';
    if (s.status === 'failed') return 'error';
    return 'wait';
  };

  const getIcon = (name: string) => {
    const s = executionStages.find(x => x.name === name || x.name?.includes(name) || name.includes(x.name));
    if (!s) return <ClockCircleOutlined />;
    if (s.status === 'completed') return <CheckCircleOutlined />;
    if (s.status === 'running') return <LoadingOutlined spin />;
    if (s.status === 'failed') return <CloseCircleOutlined />;
    return <ClockCircleOutlined />;
  };

  const steps = [
    { title: '标签', desc: '生成抖音标签' },
    { title: '图片', desc: '匹配图片素材' },
    { title: '配乐', desc: '推荐配乐' },
    { title: '评估', desc: '质量评分与建议' },
  ];

  const currentStep = executionStages.findIndex(s => s.status === 'running');
  const allDone = executionStages.length > 0 && executionStages.every(s => s.status === 'completed');
  const hasFailed = executionStages.some(s => s.status === 'failed');
  const isRunning = executionStages.some(s => s.status === 'running');

  const dotColor = allDone ? '#78716C' : hasFailed ? '#B45309' : isRunning ? '#D97706' : '#D6D3D1';

  if (executionStages.length === 0) return null;

  return (
    <div style={{ padding:'2px 0 6px' }}>
      {/* 极简状态行 */}
      <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:6 }}>
        <span style={{ width:6,height:6,borderRadius:'50%',background:dotColor,flexShrink:0,transition:'background 0.3s' }} />
        <span style={{ fontSize:12,color:'#A8A29E' }}>
          {allDone ? '全部完成' : hasFailed ? '执行出错' : isRunning ? '执行中...' : '等待执行'}
        </span>
        {isRunning && <Spin size="small" />}
      </div>

      {/* Steps — 紧凑尺寸 */}
      <Steps
        size="small"
        current={currentStep >= 0 ? currentStep : executionStages.length}
        items={steps.map(s => ({
          title: s.title,
          description: s.desc,
          status: getStatus(s.title),
          icon: getIcon(s.title),
        }))}
        style={{ fontSize:12 }}
      />
    </div>
  );
};

export default ExecutionFlow;
