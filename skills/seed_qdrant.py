"""
Qdrant 种子数据灌入 — REST API 版本
"""
import sys, os, json, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.embeddings import embed_batch
from skills.hashtag_recommender import _load_tag_rules

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
tag_rules = _load_tag_rules()
hot_tags = tag_rules.get("hot_tags", {})

all_tags = []
tag_meta = {}
for category, tiers in hot_tags.items():
    for tier in ("super", "hot", "potential"):
        for tag in tiers[tier]:
            tag_clean = tag.lstrip("#")
            if tag_clean not in tag_meta:
                all_tags.append(tag_clean)
                tag_meta[tag_clean] = {"tag": tag_clean, "category": category, "tier": tier}

print(f"[Seed] 共 {len(all_tags)} 个标签，生成 embeddings...")
embeddings = embed_batch(all_tags)
print(f"[Seed] embeddings 完成，写入 Qdrant...")

# 删除旧 collection
requests.delete(f"{QDRANT_URL}/collections/public_tags")

# 创建新 collection
requests.put(f"{QDRANT_URL}/collections/public_tags", json={
    "vectors": {"size": len(embeddings[0]), "distance": "Cosine"}
})

# 批量插入
points = [
    {
        "id": i,
        "vector": embeddings[i],
        "payload": tag_meta[tag],
    }
    for i, tag in enumerate(all_tags)
]

# REST API upsert（分批）
batch_size = 100
for i in range(0, len(points), batch_size):
    batch = points[i:i+batch_size]
    resp = requests.put(
        f"{QDRANT_URL}/collections/public_tags/points",
        json={"points": batch},
    )
    if resp.status_code == 200:
        print(f"  批次 {i//batch_size+1}: {len(batch)} 个点 OK")
    else:
        print(f"  批次 {i//batch_size+1}: 错误 {resp.status_code}")

print(f"[Seed] 完成！{len(points)} 个标签已写入 Qdrant")
