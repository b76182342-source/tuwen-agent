#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.memory import MemoryManager
from skills.hashtag_recommender import HashtagRecommender


def test_short_term_memory():
    """测试短期记忆"""
    print("="*60)
    print("1. 短期记忆测试")
    print("="*60)
    
    mm = MemoryManager()
    
    # 创建新会话
    session = mm.new_session("测试文案：我家猫今天又闯祸了")
    print(f"[OK] 创建会话: {session['session_id']}")
    print(f"  - 当前阶段: {session['stage']}")
    print(f"  - 文案: {session['text']}")
    
    # 更新会话数据
    session["tags"] = ["#猫咪", "#萌宠", "#猫咪日常"]
    session["images"] = ["approved_images/img_1.jpg", "approved_images/img_2.jpg"]
    session["music"] = {"name": "欢快卡点", "style": "欢快"}
    mm.save_session(session)
    print(f"[OK] 更新会话数据")
    
    # 加载会话
    loaded = mm.load_session()
    print(f"[OK] 加载会话")
    print(f"  - tags: {loaded['tags']}")
    print(f"  - images: {loaded['images']}")
    print(f"  - music: {loaded['music']}")
    
    # 更新阶段
    mm.update_stage("图片推荐")
    loaded = mm.load_session()
    print(f"[OK] 更新阶段: {loaded['stage']}")
    
    # 回滚测试
    mm.clear_stage_from("标签推荐")
    loaded = mm.load_session()
    print(f"[OK] 回滚到标签推荐")
    print(f"  - stage: {loaded['stage']}")
    print(f"  - tags: {loaded['tags']}")
    print(f"  - images: {loaded['images']}")
    
    print()


def test_material_library():
    """测试素材库"""
    print("="*60)
    print("2. 素材库测试")
    print("="*60)
    
    mm = MemoryManager()
    
    # 记录素材
    mm.record_material("approved_images/img_1.jpg", "image", ["猫咪", "可爱", "日常"])
    mm.record_material("approved_images/img_2.jpg", "image", ["猫咪", "搞笑", "萌宠"])
    mm.record_material("music/happy_bgm.mp3", "music", ["欢快", "卡点"])
    print(f"[OK] 记录素材")
    
    # 获取图片素材
    images = mm.get_materials_by_type("image", limit=5)
    print(f"[OK] 获取图片素材: {len(images)} 个")
    for img in images:
        print(f"  - {img.get('original_content', img.get('file_path', 'unknown'))} (使用次数: {img.get('usage_count', 0)})")
    
    # 按标签搜索
    cat_materials = mm.get_materials_by_tags(["猫咪"], type_="image", limit=5)
    print(f"[OK] 按标签搜索 '猫咪': {len(cat_materials)} 个")
    
    # 更新素材表现
    mm.update_material_performance("approved_images/img_1.jpg", 150)
    mm.increment_material_usage("approved_images/img_1.jpg")
    print(f"[OK] 更新素材表现")
    
    images = mm.get_materials_by_type("image", limit=5)
    for img in images:
        print(f"  - {img.get('original_content', img.get('file_path', 'unknown'))} (互动: {img.get('avg_engagement_rate', img.get('avg_engagement', 'N/A'))}, 使用: {img.get('usage_count', 0)})")
    
    print()


def test_tag_performance():
    """测试标签表现"""
    print("="*60)
    print("3. 标签表现测试")
    print("="*60)
    
    mm = MemoryManager()
    
    # 增加标签使用次数
    tags = ["#猫咪", "#萌宠", "#猫咪日常", "#搞笑", "#生活"]
    for tag in tags:
        mm.increment_tag_usage(tag)
    print(f"[OK] 增加标签使用次数")
    
    # 获取热门标签
    top_tags = mm.get_top_tags(10) or []
    print(f"[OK] 获取热门标签: {len(top_tags)} 个")
    for i, tag in enumerate(top_tags[:5] if top_tags else [], 1):
        if isinstance(tag, dict):
            print(f"  {i}. {tag.get('tag', tag)} (使用: {tag.get('usage_count', 'N/A')}, 平均点赞: {tag.get('avg_likes', 'N/A')})")
        else:
            print(f"  {i}. {tag}")

    # 模拟标签效果数据
    mm._update_tag_performance(["#猫咪"], likes=120, views=2000, comments=25)
    mm._update_tag_performance(["#猫咪"], likes=180, views=3000, comments=35)
    mm._update_tag_performance(["#萌宠"], likes=80, views=1500, comments=15)

    top_tags = mm.get_top_tags(5) or []
    print(f"[OK] 更新标签效果后")
    for i, tag in enumerate(top_tags[:3], 1):
        if isinstance(tag, dict):
            print(f"  {i}. {tag.get('tag', tag)}")
            print(f"    - 使用次数: {tag.get('usage_count', 'N/A')}")
            print(f"    - 平均点赞: {tag.get('avg_likes', 0):.1f}")
        else:
            print(f"  {i}. {tag}")
        print(f"    - 平均播放: {tag['avg_views']:.1f}")
        print(f"    - 效果评级: {tag['last_effectiveness']}")
    
    print()


def test_publish_history():
    """测试发布历史"""
    print("="*60)
    print("4. 发布历史测试")
    print("="*60)
    
    mm = MemoryManager()

    # 创建测试会话
    session = mm.new_session("我家猫今天又把花瓶推倒了")
    session["tags"] = ["#猫咪", "#萌宠", "#猫咪日常"]
    session["images"] = ["approved_images/img_1.jpg"]
    session["music"] = {"name": "欢快卡点", "style": "欢快"}
    session["evaluation"] = {"score": 4.2}
    mm.save_session(session)

    # 记录发布（使用新 API 签名）
    text_id = mm.add_text_material(session["text"])
    record_id = mm.record_publish(
        text_id=text_id,
        image_ids=[],
        music_id=0,
        evaluation_score=4.2,
        evaluation_level="较好",
        session_id=session["session_id"]
    )
    print(f"[OK] 记录发布 ID: {record_id}")

    # 获取发布历史
    history = mm.get_publish_history(10)
    print(f"[OK] 获取发布历史: {len(history)} 条")

    for record in history[:2]:
        print(f"  - 文案ID: {record.get('text_id', 'N/A')}")
        print(f"    评分: {record.get('evaluation_score', 'N/A')}, 等级: {record.get('evaluation_level', 'N/A')}")
        print(f"    发布时间: {record.get('publish_time', 'N/A')}")

    # 更新发布结果
    mm.update_publish_results(record_id, likes=200, comments=30, views=3500)
    updated = mm.get_publish_history(1)[0]
    print(f"[OK] 更新发布结果")
    print(f"  - 点赞: {updated.get('real_likes', 'N/A')}, 评论: {updated.get('real_comments', 'N/A')}, 播放: {updated.get('real_views', 'N/A')}")
    
    print()


def test_hashtag_with_memory():
    """测试标签推荐器集成记忆层"""
    print("="*60)
    print("5. 标签推荐器集成记忆层测试")
    print("="*60)
    
    # 测试带记忆的推荐
    print("[OK] 带记忆层推荐:")
    tags = HashtagRecommender.recommend("我家猫今天又把花瓶推倒了", count=6, use_memory=True)
    for i, tag in enumerate(tags):
        print(f"  {i+1}. {tag['tag']} - {tag['reason']}")
    
    print()
    
    # 测试不带记忆的推荐
    print("[OK] 不带记忆层推荐:")
    tags_no_mem = HashtagRecommender.recommend("我家猫今天又把花瓶推倒了", count=6, use_memory=False)
    for i, tag in enumerate(tags_no_mem):
        print(f"  {i+1}. {tag['tag']} - {tag['reason']}")
    
    print()


def test_user_preferences():
    """测试用户偏好"""
    print("="*60)
    print("6. 用户偏好测试")
    print("="*60)
    
    mm = MemoryManager()
    
    # 设置偏好
    mm.set_preference("default_tag_count", "8", "hashtag")
    mm.set_preference("default_strategy", "balanced", "hashtag")
    mm.set_preference("favorite_category", "猫", "content")
    print(f"[OK] 设置用户偏好")
    
    # 获取偏好
    tag_count = mm.get_preference("default_tag_count")
    strategy = mm.get_preference("default_strategy")
    category = mm.get_preference("favorite_category")
    print(f"[OK] 获取用户偏好")
    print(f"  - 默认标签数量: {tag_count}")
    print(f"  - 默认策略: {strategy}")
    print(f"  - 偏好类别: {category}")
    
    # 获取分类偏好
    hashtag_prefs = mm.get_preferences_by_category("hashtag")
    print(f"[OK] 获取分类偏好: {len(hashtag_prefs)} 个")
    if isinstance(hashtag_prefs, dict):
        for k, v in hashtag_prefs.items():
            print(f"  - {k}: {v}")
    else:
        for pref in hashtag_prefs:
            print(f"  - {pref.get('key', pref)}: {pref.get('value', '')}")
    
    print()


if __name__ == "__main__":
    print("="*60)
    print("记忆层完整功能测试")
    print("="*60)
    print()
    
    try:
        test_short_term_memory()
        test_material_library()
        test_tag_performance()
        test_publish_history()
        test_hashtag_with_memory()
        test_user_preferences()
        
        print("="*60)
        print("所有测试通过！")
        print("="*60)
        
    except Exception as e:
        print(f"\n[错误] 测试失败: {e}")
        import traceback
        traceback.print_exc()