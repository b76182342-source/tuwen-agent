"""
素材管理路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()


@router.get("/api/materials")
def get_materials(type: Optional[str] = None):
    """获取素材列表"""
    return memory.list_materials(material_type=type)


@router.post("/api/materials")
def add_material(data: dict):
    """添加素材"""
    mat_type = data.get("material_type", "text")
    if mat_type == "text":
        content = data.get("original_content", "")
        mid = memory.add_text_material(content)
    elif mat_type == "image":
        content = data.get("image_path", data.get("original_content", ""))
        mid = memory.add_image_material(content)
    else:
        content = data.get("music_name", data.get("original_content", ""))
        music_url = data.get("music_url", "")
        mid = memory.add_music(content, music_url=music_url)
    return {"id": mid}


@router.put("/api/materials/{material_id}")
def update_material(material_id: int, data: dict):
    """更新素材"""
    mat_type = data.get("material_type", "text")
    if mat_type == "text":
        content = data.get("original_content", "")
    elif mat_type == "image":
        content = data.get("image_path", data.get("original_content", ""))
    else:
        content = data.get("music_name", data.get("original_content", ""))
    success = memory.update_material(material_id, content)
    # 如果有 music_url 则一并更新
    if mat_type == "music" and data.get("music_url"):
        memory.update_material_url(material_id, data["music_url"])
    return {"success": success}


@router.delete("/api/materials/{material_id}")
def delete_material(material_id: int):
    """删除素材"""
    success = memory.delete_material(material_id)
    return {"success": success}


@router.get("/api/materials/by-tags")
def get_materials_by_tags(tags: str):
    """根据标签获取素材"""
    tag_list = tags.split(",") if tags else []
    return memory.get_materials_by_tags(tag_list)


@router.get("/api/materials/top")
def get_top_materials(type: str, limit: int = 10):
    """获取热门素材"""
    return memory.get_top_materials(type, limit)
