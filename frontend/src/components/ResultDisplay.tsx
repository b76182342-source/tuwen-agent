import React from 'react';
import { Card, Row, Col, Tag, Button, Space, Descriptions, Rate } from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useAppStore } from '@/stores/appStore';

const ResultDisplay: React.FC = () => {
  const { executionResult } = useAppStore();

  if (!executionResult) return null;

  const { creator_content, agent_suggestions, evaluation } = executionResult;

  if (!evaluation) return null;

  return (
    <Row gutter={16}>
      {/* 创作者内容 */}
      <Col span={8}>
        <Card
          title={<span>📝 创作者内容</span>}
          extra={<Tag color="blue">原始输入</Tag>}
          style={{ height: '100%', borderRadius: 16 }}
        >
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="文案">
              {creator_content.text || '无'}
            </Descriptions.Item>
            <Descriptions.Item label="标签">
              <Space size={[0, 8]} wrap>
                {creator_content.tags.map((tag) => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="图片">
              {creator_content.images.length > 0 ? (
                <Space size={[8, 8]} wrap>
                  {creator_content.images.map((img, idx) => (
                    <img
                      key={idx}
                      src={img.url}
                      alt={img.path}
                      style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 8 }}
                    />
                  ))}
                </Space>
              ) : (
                '无'
              )}
            </Descriptions.Item>
            <Descriptions.Item label="配乐">
              {creator_content.music.length > 0
                ? creator_content.music.map((m) => m.name).join(', ')
                : '无'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>

      {/* Agent 建议 */}
      <Col span={8}>
        <Card
          title={<span>🤖 Agent 建议</span>}
          extra={<Tag color="green">智能推荐</Tag>}
          style={{ height: '100%', borderRadius: 16 }}
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {agent_suggestions.Skill1 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>推荐标签：</div>
                <Space size={[0, 8]} wrap>
                  {agent_suggestions.Skill1.map((tag) => (
                    <Tag key={tag} color="blue">{tag}</Tag>
                  ))}
                </Space>
              </div>
            )}

            {agent_suggestions.Skill2 && agent_suggestions.Skill2.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>推荐图片：</div>
                <Space size={[8, 8]} wrap>
                  {agent_suggestions.Skill2.map((img, idx) => (
                    <img
                      key={idx}
                      src={img.url}
                      alt={img.path}
                      style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 10 }}
                    />
                  ))}
                </Space>
              </div>
            )}

            {agent_suggestions.Skill3 && agent_suggestions.Skill3.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>推荐配乐：</div>
                {agent_suggestions.Skill3.map((music, idx) => (
                  <Tag key={idx} color="purple" style={{ marginBottom: 4 }}>
                    {music.name} ({music.style})
                  </Tag>
                ))}
              </div>
            )}

            <Button type="primary" icon={<CheckOutlined />} block style={{ borderRadius: 10 }}>
              应用建议
            </Button>
            <Button icon={<CloseOutlined />} block style={{ borderRadius: 10 }}>
              忽略建议
            </Button>
          </Space>
        </Card>
      </Col>

      {/* 评估结果 */}
      <Col span={8}>
        <Card
          title={<span>📊 评估结果</span>}
          extra={
            <Tag color={evaluation.score >= 4 ? 'green' : 'orange'}>
              {evaluation.level}
            </Tag>
          }
          style={{ height: '100%', borderRadius: 16 }}
        >
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>综合评分：</div>
              <Rate disabled value={Math.round(evaluation.score)} />
              <span style={{
                marginLeft: 8, fontSize: 20, fontWeight: 700,
                color: evaluation.score >= 4 ? '#10B981' : '#F59E0B',
              }}>
                {evaluation.score.toFixed(1)}/5.0
              </span>
            </div>

            <div>
              <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>详细报告：</div>
              <div style={{
                whiteSpace: 'pre-wrap', fontSize: 12, color: '#6B7280',
                background: '#F9FAFB', padding: 10, borderRadius: 8,
                lineHeight: 1.7,
              }}>
                {evaluation.report}
              </div>
            </div>

            {evaluation.suggestions.length > 0 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>优化建议：</div>
                <ul style={{ margin: 0, paddingLeft: 20, color: '#6B7280', fontSize: 13 }}>
                  {evaluation.suggestions.map((suggestion, idx) => (
                    <li key={idx} style={{ marginBottom: 4 }}>{suggestion}</li>
                  ))}
                </ul>
              </div>
            )}

            <Button type="primary" icon={<ReloadOutlined />} block style={{ borderRadius: 10 }}>
              重新生成
            </Button>
          </Space>
        </Card>
      </Col>
    </Row>
  );
};

export default ResultDisplay;
