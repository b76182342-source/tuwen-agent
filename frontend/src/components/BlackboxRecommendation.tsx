import React, { useState } from 'react';
import { Card, Alert, Button, Space, List, Tag, Progress, message } from 'antd';
import { ThunderboltOutlined, CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useAppStore } from '@/stores/appStore';
import { agentApi } from '@/services/api';

const BlackboxRecommendation: React.FC = () => {
  const { executionResult, conversationId, setExecutionResult, setExecutionStages } = useAppStore();
  const [reExecuting, setReExecuting] = useState(false);

  if (!executionResult?.evaluation?.blackbox_recommendation) return null;
  const { blackbox_recommendation, blackbox_prompt } = executionResult.evaluation;

  const handleReExecute = async () => {
    if (!conversationId) { message.warning('没有活跃的对话'); return; }
    setReExecuting(true);
    try {
      const response = await agentApi.run({ text: executionResult.creator_content?.text || '', tags: executionResult.creator_content?.tags || [], images: executionResult.creator_content?.images || [], music: executionResult.creator_content?.music || [], enable_blackbox: true, conversation_id: conversationId });
      const result: any = response.data; setExecutionResult(result);
      if (result.execution_log?.length) {
        const now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        setExecutionStages(result.execution_log.map((log: any) => ({ name: log.skill || log.name, status: log.status || 'completed', start_time: log.start_time || log.timestamp || now, end_time: log.end_time || (log.status === 'completed' ? now : undefined) })));
      }
      message.success('已按照推荐路径重新执行');
    } catch (e: any) { message.error(`重新执行失败: ${e?.response?.data?.detail || e?.message || '重新执行失败'}`); }
    finally { setReExecuting(false); }
  };

  return (
    <Card
      title={<Space><span style={{ width:28,height:28,borderRadius:8,background:'#eff6ff',display:'inline-flex',alignItems:'center',justifyContent:'center',border:'1px solid #bfdbfe' }}><ThunderboltOutlined style={{ color:'#2563eb',fontSize:14 }} /></span><span>智能黑箱建议</span></Space>}
      style={{ marginTop: 24, borderRadius: 14 }}
    >
      <Alert message="评估未通过，智能黑箱已生成优化建议" description={blackbox_prompt} type="warning" showIcon style={{ marginBottom:16,borderRadius:10 }} />
      <Space direction="vertical" size="large" style={{ width:'100%' }}>
        <div>
          <div style={{ fontWeight:600,marginBottom:12,fontSize:14,color:'#1e293b' }}>📋 相似成功案例（{blackbox_recommendation.similar_cases_count}个）</div>
          <List dataSource={blackbox_recommendation.reference_cases} renderItem={(item: any) => (
            <List.Item><List.Item.Meta title={<Space><span>{item.text}</span><Tag color="green">评分: {item.score.toFixed(1)}</Tag></Space>} description={<Space><span>标签: {item.tags.join(', ')}</span><span>点赞: {item.likes}</span></Space>} /></List.Item>
          )} />
        </div>
        <div>
          <div style={{ fontWeight:600,marginBottom:12,fontSize:14,color:'#1e293b' }}>🗺️ 推荐执行路径</div>
          <Space size="middle">{blackbox_recommendation.recommended_path.split(' → ').map((step: string, idx: number) => <Tag key={idx} color="gold" style={{ fontSize:14,padding:'4px 14px',borderRadius:8 }}>{step}</Tag>)}</Space>
        </div>
        <div>
          <div style={{ fontWeight:600,marginBottom:12,fontSize:14,color:'#1e293b' }}>置信度: {(blackbox_recommendation.confidence_score * 100).toFixed(0)}%</div>
          <Progress percent={Math.round(blackbox_recommendation.confidence_score * 100)} status="active" strokeColor={{ '0%': '#2563eb', '100%': '#0891b2' }} />
        </div>
        <Space style={{ width:'100%',justifyContent:'flex-end' }}>
          <Button icon={<CloseCircleOutlined />} onClick={() => setExecutionResult(null)} style={{ borderRadius:10 }}>忽略建议</Button>
          <Button type="primary" icon={reExecuting ? <LoadingOutlined /> : <CheckCircleOutlined />} loading={reExecuting} onClick={handleReExecute} style={{ borderRadius:10 }}>{reExecuting ? '重新执行中...' : '按照推荐路径重新执行'}</Button>
        </Space>
      </Space>
    </Card>
  );
};

export default BlackboxRecommendation;
