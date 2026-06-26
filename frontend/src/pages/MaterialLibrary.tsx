import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
  Tabs,
  Image,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOutlined,
  PictureOutlined,
  CustomerServiceOutlined,
  HistoryOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { materialApi, publishApi } from '@/services/api';
import type { Material, MaterialType, PublishHistory } from '@/types';

const fetchMaterials = async (
  activeTab: string,
  setMaterials: (m: Material[]) => void,
  setLoading: (l: boolean) => void
) => {
  setLoading(true);
  try {
    const type = activeTab === 'all' ? undefined : (activeTab as MaterialType);
    const response = await materialApi.getMaterials(type);
    setMaterials(response.data);
  } catch {
    message.error('获取素材列表失败');
  } finally {
    setLoading(false);
  }
};

const MaterialLibrary: React.FC = () => {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>('all');
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingMaterial, setEditingMaterial] = useState<Material | null>(null);
  const [modalType, setModalType] = useState<MaterialType>('text');
  const [form] = Form.useForm();

  // 从发布历史导入相关状态
  const [historyModalVisible, setHistoryModalVisible] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyList, setHistoryList] = useState<PublishHistory[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<PublishHistory[]>([]);

  const loadMaterials = () => fetchMaterials(activeTab, setMaterials, setLoading);

  // 加载发布历史
  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const response = await publishApi.getHistory();
      setHistoryList(response.data);
    } catch {
      message.error('获取发布历史失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  // 打开发布历史模态框
  const handleOpenHistoryModal = () => {
    setSelectedHistory([]);
    loadHistory();
    setHistoryModalVisible(true);
  };

  // 从发布历史导入素材
  const handleImportFromHistory = async () => {
    if (selectedHistory.length === 0) {
      message.warning('请选择要导入的发布记录');
      return;
    }

    let successCount = 0;
    for (const item of selectedHistory) {
      try {
        // 注意：这里需要获取文案内容，由于历史记录中没有存储文案，
        // 需要在后端根据 text_id 查询或直接使用已有的素材
        await materialApi.addMaterial({
          material_type: 'text',
          original_content: `发布记录 #${item.id} (评分: ${item.evaluation_score})`,
        });
        successCount++;
      } catch {
        // 忽略单条失败
      }
    }

    if (successCount > 0) {
      message.success(`成功导入 ${successCount} 条素材`);
      setHistoryModalVisible(false);
      loadMaterials();
    } else {
      message.error('导入失败');
    }
  };

  // 发布历史表格列
  const historyColumns = [
    {
      title: '选择',
      key: 'selection',
      width: 60,
      render: (_: any, record: PublishHistory) => (
        <CheckCircleOutlined
          style={{
            fontSize: 18,
            color: selectedHistory.some((h) => h.id === record.id) ? '#1890ff' : '#d9d9d9',
            cursor: 'pointer',
          }}
          onClick={() => {
            const exists = selectedHistory.some((h) => h.id === record.id);
            if (exists) {
              setSelectedHistory(selectedHistory.filter((h) => h.id !== record.id));
            } else {
              setSelectedHistory([...selectedHistory, record]);
            }
          }}
        />
      ),
    },
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '发布时间',
      dataIndex: 'publish_time',
      key: 'publish_time',
      width: 160,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '评分',
      dataIndex: 'evaluation_score',
      key: 'evaluation_score',
      width: 80,
      render: (score: number) => (
        <Tag color={score >= 4 ? 'green' : score >= 3 ? 'gold' : 'red'}>{score.toFixed(1)}</Tag>
      ),
    },
    {
      title: '互动率',
      dataIndex: 'engagement_rate',
      key: 'engagement_rate',
      width: 80,
      render: (rate: number) => (rate ? `${(rate * 100).toFixed(1)}%` : '-'),
    },
    {
      title: '点赞',
      dataIndex: 'likes',
      key: 'likes',
      width: 80,
    },
    {
      title: '评论',
      dataIndex: 'comments',
      key: 'comments',
      width: 80,
    },
    {
      title: '浏览',
      dataIndex: 'views',
      key: 'views',
      width: 80,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 80,
      render: (source: string) => (
        <Tag color={source === 'extension' ? 'blue' : 'default'}>
          {source === 'extension' ? '扩展' : '手动'}
        </Tag>
      ),
    },
  ];

  useEffect(() => {
    loadMaterials();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const handleAdd = () => {
    setEditingMaterial(null);
    form.resetFields();
    setModalType(activeTab === 'all' ? 'text' : (activeTab as MaterialType));
    setIsModalVisible(true);
  };

  const handleEdit = (material: Material) => {
    setEditingMaterial(material);
    setModalType(material.material_type);
    form.setFieldsValue({
      material_type: material.material_type,
      original_content: material.original_content,
      image_path: material.image_path,
      music_name: material.music_name,
      music_url: material.music_url,
    });
    setIsModalVisible(true);
  };

  const handleDelete = async (id: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除这个素材吗？',
      onOk: async () => {
        try {
          await materialApi.deleteMaterial(id);
          message.success('删除成功');
          loadMaterials();
        } catch {
          message.error('删除失败');
        }
      },
    });
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      const material_type = values.material_type || modalType;

      if (editingMaterial) {
        await materialApi.updateMaterial(editingMaterial.id, values);
        message.success('更新成功');
      } else {
        await materialApi.addMaterial({ ...values, material_type });
        message.success('添加成功');
      }

      setIsModalVisible(false);
      loadMaterials();
    } catch {
      // form validation error — ignore
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: '内容',
      dataIndex: 'original_content',
      key: 'original_content',
      ellipsis: true,
      render: (text: string, record: Material) => {
        if (record.material_type === 'image') {
          return <Image src={record.image_path} width={60} height={60} style={{ objectFit: 'cover', borderRadius: 8 }} />;
        }
        if (record.material_type === 'music') {
          return <span>🎵 {record.music_name}</span>;
        }
        return text;
      },
    },
    {
      title: '标签',
      dataIndex: 'semantic_tags',
      key: 'semantic_tags',
      render: (tags: any[]) => (
        <Space size={[0, 4]} wrap>
          {tags?.map((tag) => (
            <Tag key={tag.tag}>{tag.tag}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '使用次数',
      dataIndex: 'usage_count',
      key: 'usage_count',
      width: 100,
    },
    {
      title: '平均互动率',
      dataIndex: 'avg_engagement_rate',
      key: 'avg_engagement_rate',
      width: 120,
      render: (rate: number) => (rate ? `${(rate * 100).toFixed(1)}%` : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: Material) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const tabItems = [
    { key: 'all', label: <span><FolderOutlined /> 全部素材</span> },
    { key: 'text', label: <span><FolderOutlined /> 文案素材</span> },
    { key: 'image', label: <span><PictureOutlined /> 图片素材</span> },
    { key: 'music', label: <span><CustomerServiceOutlined /> 配乐库</span> },
  ];

  return (
    <div>
      <Card
        title="📦 素材库管理"
        extra={
          <Space>
            <Tooltip title="从发布历史导入素材">
              <Button icon={<HistoryOutlined />} onClick={handleOpenHistoryModal}>
                从历史导入
              </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              添加素材
            </Button>
          </Space>
        }
      >
        <Tabs activeKey={activeTab} items={tabItems} onChange={setActiveTab} />

        <Table
          columns={columns}
          dataSource={materials}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>

      <Modal
        title={editingMaterial ? '编辑素材' : '添加素材'}
        open={isModalVisible}
        onOk={handleModalOk}
        onCancel={() => setIsModalVisible(false)}
        width={600}
      >
        <Form form={form} layout="vertical" initialValues={{ material_type: modalType }}>
          <Form.Item name="material_type" label="素材类型">
            <Select
              onChange={(val) => setModalType(val)}
              disabled={!!editingMaterial}
            >
              <Select.Option value="text">文案</Select.Option>
              <Select.Option value="image">图片</Select.Option>
              <Select.Option value="music">配乐</Select.Option>
            </Select>
          </Form.Item>

          {modalType === 'text' && (
            <Form.Item
              name="original_content"
              label="文案内容"
              rules={[{ required: true, message: '请输入文案内容' }]}
            >
              <Input.TextArea rows={4} placeholder="请输入文案内容" />
            </Form.Item>
          )}

          {modalType === 'image' && (
            <Form.Item name="image_path" label="图片路径" rules={[{ required: true, message: '请输入图片路径' }]}>
              <Input placeholder="请输入图片路径" />
            </Form.Item>
          )}

          {modalType === 'music' && (
            <>
              <Form.Item
                name="music_name"
                label="配乐名称"
                rules={[{ required: true, message: '请输入配乐名称' }]}
              >
                <Input placeholder="请输入配乐名称" />
              </Form.Item>
              <Form.Item name="music_url" label="配乐URL">
                <Input placeholder="请输入配乐URL" />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>

      {/* 从发布历史导入素材模态框 */}
      <Modal
        title={
          <Space>
            <HistoryOutlined />
            从发布历史导入素材
          </Space>
        }
        open={historyModalVisible}
        onOk={handleImportFromHistory}
        onCancel={() => setHistoryModalVisible(false)}
        width={900}
        okText={`导入选中 (${selectedHistory.length})`}
        okButtonProps={{ disabled: selectedHistory.length === 0 }}
      >
        <div style={{ marginBottom: 16 }}>
          <Space>
            <span style={{ color: '#666' }}>选择发布记录将其添加到素材库：</span>
            {selectedHistory.length > 0 && (
              <Tag color="blue">已选择 {selectedHistory.length} 条</Tag>
            )}
          </Space>
        </div>
        <Table
          columns={historyColumns}
          dataSource={historyList}
          rowKey="id"
          loading={historyLoading}
          size="small"
          scroll={{ y: 400 }}
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Modal>
    </div>
  );
};

export default MaterialLibrary;
