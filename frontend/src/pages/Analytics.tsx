/**
 * 数据分析页 v2 — 对齐抖音数据维度
 */
import React, { useEffect, useRef, useState } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Progress, message } from 'antd';
import {
  LikeOutlined, MessageOutlined, EyeOutlined, TrophyOutlined,
  ShareAltOutlined, RiseOutlined, FallOutlined, StarOutlined,
  UserSwitchOutlined, PercentageOutlined, PictureOutlined,
} from '@ant-design/icons';
import { analyticsApi } from '@/services/api';
import type { PersonalDataAnalysis, TrafficDailyItem, FollowerDailyItem } from '@/types';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useGSAP, gsap, createStaggerTimeline, animateScrollReveal } from '@/hooks/useAnimations';

const CHART = {
  cyan: '#2563eb', teal: '#0891b2', purple: '#7c4dff', stone: '#94a3b8',
  blue: '#60a5fa', red: '#ef4444', pink: '#f472b6',
};

const Analytics: React.FC = () => {
  const [analytics, setAnalytics] = useState<PersonalDataAnalysis | null>(null);
  const [trafficTrend, setTrafficTrend] = useState<TrafficDailyItem[]>([]);
  const [followerTrend, setFollowerTrend] = useState<FollowerDailyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

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

  // GSAP: 时间线编排 — 卡片先入场，图表跟随
  useGSAP(() => {
    if (loading || !analytics) return;
    const tl = createStaggerTimeline({
      container: containerRef.current,
      cardSelector: '.analytics-card',
      stagger: 0.06,
      y: 20,
    });
    // 图表在卡片之后略微延迟入场 — 先 set 隐藏，再 to 显示（避免闪现）
    gsap.set('.analytics-chart', { opacity: 0, y: 16 });
    tl.to('.analytics-chart', {
      opacity: 1, y: 0, duration: 0.4, stagger: 0.15, ease: 'power2.out',
    }, '+=0.15');
  }, { dependencies: [loading, analytics], scope: containerRef });

  // GSAP: ScrollTrigger 滚动揭示图表（仅触发一次）
  useGSAP(() => {
    if (loading || !analytics) return;
    const charts = gsap.utils.toArray<HTMLElement>('.analytics-chart');
    charts.forEach((el) => {
      animateScrollReveal(el, { y: 20, start: 'top 90%' });
    });
  }, { dependencies: [loading, analytics], scope: containerRef });

  if (loading || !analytics) return <Card loading={true} />;
  const a = analytics;

  // 流量概览指标卡
  const flowCards = [
    { title: '总发布', value: a.total_publishes, icon: <TrophyOutlined />, color: CHART.cyan, bg: '#eff6ff' },
    { title: '总播放', value: a.total_views, icon: <EyeOutlined />, color: CHART.blue, bg: '#EFF6FF' },
    { title: '总点赞', value: a.total_likes, icon: <LikeOutlined />, color: CHART.teal, bg: '#ecfeff' },
    { title: '总评论', value: a.total_comments, icon: <MessageOutlined />, color: CHART.stone, bg: '#f1f5f9' },
  ];

  // 粉丝指标卡
  const fanCards = [
    { title: '涨粉', value: a.total_fan_gain, icon: <RiseOutlined />, color: CHART.teal },
    { title: '脱粉', value: a.total_fan_loss, icon: <FallOutlined />, color: CHART.red },
    { title: '粉丝播放占比', value: `${(a.avg_fan_play_ratio * 100).toFixed(1)}%`, icon: <PercentageOutlined />, color: CHART.purple },
    { title: '净增粉', value: a.total_fan_gain - a.total_fan_loss, icon: <UserSwitchOutlined />, color: a.total_fan_gain >= a.total_fan_loss ? CHART.teal : CHART.red },
  ];

  // 互动率指标卡
  const engagementCards = [
    { title: '平均播放', value: a.avg_views.toFixed(0), icon: <EyeOutlined />, color: CHART.blue },
    { title: '平均点赞', value: a.avg_likes.toFixed(1), icon: <LikeOutlined />, color: CHART.teal },
    { title: '平均评论', value: a.avg_comments.toFixed(1), icon: <MessageOutlined />, color: CHART.stone },
    { title: '平均分享', value: a.avg_shares.toFixed(1), icon: <ShareAltOutlined />, color: CHART.purple },
    { title: '平均收藏', value: a.avg_favorites.toFixed(1), icon: <StarOutlined />, color: CHART.cyan },
    { title: '平均浏览图片', value: a.avg_images_viewed.toFixed(1), icon: <PictureOutlined />, color: CHART.pink },
  ];

  // 流量质量指标
  const qualityCards = [
    { title: '划走率', value: `${(a.avg_swipe_away_rate * 100).toFixed(1)}%`, icon: <FallOutlined />, color: CHART.red },
    { title: '文案展开率', value: `${(a.avg_copy_expand_rate * 100).toFixed(1)}%`, icon: <RiseOutlined />, color: CHART.teal },
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
      render: (rate: number) => <Progress percent={Math.round(rate * 100)} size="small" strokeColor={{ '0%': '#2563eb', '100%': '#0891b2' }} format={p => `${p}%`} /> },
  ];

  // 数据来源分布
  const sourceData = Object.entries(a.source_breakdown || {}).map(([name, value]) => ({
    name: name === 'extension' ? '浏览器扩展' : name === 'manual' ? '手动录入' : name === 'agent' ? 'Agent生成' : name,
    value,
  }));

  return (
    <div ref={containerRef}>
      {/* 第一行：总览 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        {flowCards.map(c => (
          <Col span={6} key={c.title}>
            <Card size="small" className="analytics-card">
              <Statistic title={c.title} value={c.value} prefix={c.icon} valueStyle={{ color: c.color, fontSize: 20, fontWeight: 700 }} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 第二行：粉丝 + 数据来源 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title={<span><UserSwitchOutlined /> 粉丝数据</span>} size="small" className="analytics-card">
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
          <Card title="数据来源分布" size="small" className="analytics-card">
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
          <Card title="流量质量" size="small" className="analytics-card">
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
          <Card title="互动指标（均值）" size="small" className="analytics-card">
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
      <Card title={<span><TrophyOutlined /> 最佳内容</span>} size="small" className="analytics-card" style={{ marginBottom: 16 }}>
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
          <div style={{ color: '#555568', textAlign: 'center', padding: 16 }}>暂无数据</div>
        )}
      </Card>

      {/* 第五行：流量趋势图 */}
      <Card title="📈 流量日趋势" size="small" className="analytics-chart" style={{ marginBottom: 16 }}>
        {trafficChartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={trafficChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="views" stroke={CHART.blue} name="播放量" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: '#555568', textAlign: 'center', padding: 24 }}>暂无趋势数据</div>
        )}
      </Card>

      {/* 第六行：标签排行 + 粉丝趋势 */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="🏷️ 热门标签" size="small" className="analytics-chart">
            <Table columns={tagColumns} dataSource={a.top_tags} rowKey="tag" pagination={false} size="small"
              locale={{ emptyText: '暂无标签数据' }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="📊 粉丝变化趋势" size="small" className="analytics-chart">
            {followerChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={followerChartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="gain" fill={CHART.teal} name="涨粉" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="loss" fill={CHART.red} name="脱粉" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ color: '#555568', textAlign: 'center', padding: 24 }}>暂无趋势数据</div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Analytics;
