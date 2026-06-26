/**
 * 数据分析页 v2 — 对齐抖音数据维度
 */
import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Progress, message } from 'antd';
import {
  LikeOutlined, MessageOutlined, EyeOutlined, TrophyOutlined,
  ShareAltOutlined, RiseOutlined, FallOutlined, StarOutlined,
  UserSwitchOutlined, PercentageOutlined, PictureOutlined,
} from '@ant-design/icons';
import { analyticsApi } from '@/services/api';
import type { PersonalDataAnalysis, TrafficDailyItem, FollowerDailyItem } from '@/types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';

const CHART = {
  amber: '#D97706', green: '#059669', purple: '#7C3AED', stone: '#78716C',
  blue: '#2563EB', red: '#DC2626', pink: '#EC4899',
};

const Analytics: React.FC = () => {
  const [analytics, setAnalytics] = useState<PersonalDataAnalysis | null>(null);
  const [trafficTrend, setTrafficTrend] = useState<TrafficDailyItem[]>([]);
  const [followerTrend, setFollowerTrend] = useState<FollowerDailyItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      analyticsApi.getOverview(),
      analyticsApi.getTrafficTrend(undefined, 30),
      analyticsApi.getFollowerTrend(undefined, 30),
    ]).then(([a, t, f]) => {
      setAnalytics(a.data);
      setTrafficTrend(t.data || []);
      setFollowerTrend(f.data || []);
    }).catch(() => message.error('获取数据分析失败'))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !analytics) return <Card loading={true} />;
  const a = analytics;

  // 流量概览指标卡
  const flowCards = [
    { title: '总发布', value: a.total_publishes, icon: <TrophyOutlined />, color: CHART.amber, bg: '#FFF7ED' },
    { title: '总播放', value: a.total_views, icon: <EyeOutlined />, color: CHART.blue, bg: '#EFF6FF' },
    { title: '总点赞', value: a.total_likes, icon: <LikeOutlined />, color: CHART.green, bg: '#ECFDF5' },
    { title: '总评论', value: a.total_comments, icon: <MessageOutlined />, color: CHART.stone, bg: '#F5F5F4' },
  ];

  // 粉丝指标卡
  const fanCards = [
    { title: '涨粉', value: a.total_fan_gain, icon: <RiseOutlined />, color: CHART.green },
    { title: '脱粉', value: a.total_fan_loss, icon: <FallOutlined />, color: CHART.red },
    { title: '粉丝播放占比', value: `${(a.avg_fan_play_ratio * 100).toFixed(1)}%`, icon: <PercentageOutlined />, color: CHART.purple },
    { title: '净增粉', value: a.total_fan_gain - a.total_fan_loss, icon: <UserSwitchOutlined />, color: a.total_fan_gain >= a.total_fan_loss ? CHART.green : CHART.red },
  ];

  // 互动率指标卡
  const engagementCards = [
    { title: '平均播放', value: a.avg_views.toFixed(0), icon: <EyeOutlined />, color: CHART.blue },
    { title: '平均点赞', value: a.avg_likes.toFixed(1), icon: <LikeOutlined />, color: CHART.green },
    { title: '平均评论', value: a.avg_comments.toFixed(1), icon: <MessageOutlined />, color: CHART.stone },
    { title: '平均分享', value: a.avg_shares.toFixed(1), icon: <ShareAltOutlined />, color: CHART.purple },
    { title: '平均收藏', value: a.avg_favorites.toFixed(1), icon: <StarOutlined />, color: CHART.amber },
    { title: '平均浏览图片', value: a.avg_images_viewed.toFixed(1), icon: <PictureOutlined />, color: CHART.pink },
  ];

  // 流量质量指标
  const qualityCards = [
    { title: '划走率', value: `${(a.avg_swipe_away_rate * 100).toFixed(1)}%`, icon: <FallOutlined />, color: CHART.red },
    { title: '文案展开率', value: `${(a.avg_copy_expand_rate * 100).toFixed(1)}%`, icon: <RiseOutlined />, color: CHART.green },
  ];

  // 流量趋势图数据
  const trafficChartData = trafficTrend.map(t => ({
    date: t.date?.slice(5, 16) || t.date,
    views: t.views,
    source: t.source,
  }));

  // 粉丝趋势图数据
  const followerChartData = followerTrend.map(f => ({
    date: f.date?.slice(5, 16) || f.date,
    gain: f.fan_gain,
    loss: f.fan_loss,
  }));

  // 标签表格
  const tagColumns = [
    { title: '排名', key: 'rank', render: (_: any, __: any, i: number) => i + 1, width: 60 },
    { title: '标签', dataIndex: 'tag', render: (tag: string) => <Tag color="gold">{tag}</Tag> },
    { title: '使用次数', dataIndex: 'usage_count', width: 90 },
    { title: '平均点赞', dataIndex: 'avg_likes', width: 90 },
    { title: '平均播放', dataIndex: 'avg_views', width: 90 },
    { title: '互动率', dataIndex: 'avg_engagement_rate', width: 120,
      render: (rate: number) => <Progress percent={Math.round(rate * 100)} size="small" strokeColor={{ '0%': '#D97706', '100%': '#059669' }} format={p => `${p}%`} /> },
  ];

  // 数据来源分布
  const sourceData = Object.entries(a.source_breakdown || {}).map(([name, value]) => ({
    name: name === 'extension' ? '浏览器扩展' : name === 'manual' ? '手动录入' : name === 'agent' ? 'Agent生成' : name,
    value,
  }));

  return (
    <div>
      {/* 第一行：总览 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {flowCards.map(c => (
          <Col span={6} key={c.title}>
            <Card size="small">
              <Statistic title={c.title} value={c.value} prefix={c.icon} valueStyle={{ color: c.color, fontSize: 20, fontWeight: 700 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 第二行：粉丝 + 数据来源 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title={<span><UserSwitchOutlined /> 粉丝数据</span>} size="small">
            <Row gutter={12}>
              {fanCards.map(c => (
                <Col span={6} key={c.title}>
                  <Statistic title={c.title} value={c.value} valueStyle={{ color: c.color, fontSize: 18, fontWeight: 600 }} />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="数据来源分布" size="small">
            <Row gutter={12}>
              {sourceData.map(s => (
                <Col span={8} key={s.name}>
                  <Statistic title={s.name} value={s.value} suffix="条" />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      {/* 第三行：流量质量 + 互动指标 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card title="流量质量" size="small">
            <Row gutter={12}>
              {qualityCards.map(c => (
                <Col span={12} key={c.title}>
                  <Statistic title={c.title} value={c.value} prefix={c.icon} valueStyle={{ color: c.color }} />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="互动指标（均值）" size="small">
            <Row gutter={8}>
              {engagementCards.map(c => (
                <Col span={4} key={c.title}>
                  <Statistic title={c.title} value={c.value} prefix={c.icon} valueStyle={{ fontSize: 16, fontWeight: 600, color: c.color }} />
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>

      {/* 第四行：最佳内容 */}
      <Card title={<span><TrophyOutlined /> 最佳内容</span>} size="small" style={{ marginBottom: 16 }}>
        {a.best_content ? (
          <Row gutter={16}>
            <Col span={8}>
              <Statistic title="文案" value={a.best_content.text?.slice(0, 30) || '-'} valueStyle={{ fontSize: 14 }} />
            </Col>
            <Col span={4}>
              <Statistic title="播放量" value={a.best_content.views || 0} prefix={<EyeOutlined />} />
            </Col>
            <Col span={4}>
              <Statistic title="点赞" value={a.best_content.likes || 0} prefix={<LikeOutlined />} />
            </Col>
            <Col span={4}>
              <Statistic title="划走率" value={`${((a.best_content.swipe_away_rate || 0) * 100).toFixed(1)}%`} />
            </Col>
            <Col span={4}>
              <Statistic title="涨粉" value={a.best_content.fan_gain || 0} prefix={<RiseOutlined />} />
            </Col>
          </Row>
        ) : (
          <div style={{ color: '#A8A29E', textAlign: 'center', padding: 16 }}>暂无数据</div>
        )}
      </Card>

      {/* 第五行：流量趋势图 */}
      <Card title="📈 流量日趋势" size="small" style={{ marginBottom: 16 }}>
        {trafficChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={trafficChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E7E5E4" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="views" stroke={CHART.blue} name="播放量" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: '#A8A29E', textAlign: 'center', padding: 24 }}>暂无趋势数据</div>
        )}
      </Card>

      {/* 第六行：标签排行 + 粉丝趋势 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="🏷️ 热门标签" size="small">
            <Table columns={tagColumns} dataSource={a.top_tags} rowKey="tag" pagination={false} size="small"
              locale={{ emptyText: '暂无标签数据' }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="📊 粉丝变化趋势" size="small">
            {followerChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={followerChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E7E5E4" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="gain" fill={CHART.green} name="涨粉" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="loss" fill={CHART.red} name="脱粉" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ color: '#A8A29E', textAlign: 'center', padding: 24 }}>暂无趋势数据</div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Analytics;
