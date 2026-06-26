"""
测试持续对话功能
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.memory import MemoryManager
from agent.douyin_agent import DouyinAgent

def test_conversation_features():
    """测试对话功能"""
    print("=" * 60)
    print("测试持续对话功能")
    print("=" * 60)

    memory = MemoryManager()
    agent = DouyinAgent()

    # 测试1：创建对话
    print("\n[测试1] 创建对话")
    conversation_id = memory.create_conversation(
        title="测试对话",
        user_id="test_user"
    )
    print(f"[OK] 对话创建成功: {conversation_id}")

    # 测试2：获取对话信息
    print("\n[测试2] 获取对话信息")
    conversation = memory.get_conversation(conversation_id)
    print(f"[OK] 对话信息: {conversation}")

    # 测试3：添加用户消息
    print("\n[测试3] 添加用户消息")
    message_id = memory.add_message(
        conversation_id,
        "user",
        "我家猫今天又把花瓶推倒了",
        {"tags": [], "images": [], "music": []}
    )
    print(f"[OK] 消息添加成功: {message_id}")

    # 测试4：执行Agent（带对话上下文）
    print("\n[测试4] 执行Agent（带对话上下文）")
    user_input = {
        "text": "我家猫今天又把花瓶推倒了",
        "tags": [],
        "images": [],
        "music": []
    }

    result = agent.run(user_input, enable_blackbox=False, conversation_id=conversation_id)
    print(f"[OK] Agent执行完成")
    print(f"  - 评分: {result['evaluation']['score']}/5.0")
    print(f"  - 等级: {result['evaluation']['level']}")

    # 测试5：获取对话历史
    print("\n[测试5] 获取对话历史")
    history = memory.get_conversation_history(conversation_id)
    print(f"[OK] 对话历史: {len(history)} 条消息")
    for msg in history:
        content = msg['content'][:50].encode('utf-8', 'ignore').decode('utf-8')
        print(f"  - [{msg['role']}] {content}...")

    # 测试6：获取上下文
    print("\n[测试6] 获取对话上下文")
    context = memory.get_context_for_agent(conversation_id)
    print(f"[OK] 上下文信息:")
    print(f"  - 消息总数: {context['message_count']}")
    print(f"  - 用户消息: {len(context['user_inputs'])}")
    print(f"  - Agent回复: {len(context['agent_responses'])}")

    # 测试7：继续对话（第二轮）
    print("\n[测试7] 继续对话（第二轮）")
    user_input_2 = {
        "text": "帮我优化一下这个文案",
        "tags": result['session_state'].get('tags', []),
        "images": [],
        "music": []
    }

    result_2 = agent.run(user_input_2, enable_blackbox=False, conversation_id=conversation_id)
    print(f"[OK] 第二轮对话完成")
    print(f"  - 评分: {result_2['evaluation']['score']}/5.0")

    # 测试8：获取对话统计
    print("\n[测试8] 获取对话统计")
    stats = memory.get_conversation_stats(conversation_id)
    print(f"[OK] 对话统计:")
    print(f"  - 总消息数: {stats['total_messages']}")
    print(f"  - 用户消息: {stats['user_messages']}")
    print(f"  - Agent回复: {stats['assistant_messages']}")

    # 测试9：列出所有对话
    print("\n[测试9] 列出所有对话")
    conversations = memory.list_conversations()
    print(f"[OK] 对话列表: {len(conversations)} 个对话")
    for conv in conversations:
        print(f"  - {conv['conversation_id']}: {conv['title']}")

    # 测试10：搜索对话
    print("\n[测试10] 搜索对话")
    search_results = memory.search_conversations("猫")
    print(f"[OK] 搜索结果: {len(search_results)} 个匹配对话")

    # 测试11：删除对话
    print("\n[测试11] 删除对话")
    success = memory.delete_conversation(conversation_id)
    print(f"[OK] 对话删除: {'成功' if success else '失败'}")

    # 验证删除
    deleted_conversation = memory.get_conversation(conversation_id)
    if deleted_conversation is None:
        print("[OK] 验证: 对话已成功删除")
    else:
        print("[FAIL] 验证: 对话删除失败")

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)

if __name__ == "__main__":
    test_conversation_features()