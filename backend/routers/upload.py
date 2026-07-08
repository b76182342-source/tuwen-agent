"""
图片上传路由
"""
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from backend.constants import PERSONAL_DIR, PUBLIC_DIR, _ALLOWED_UPLOAD_EXTENSIONS
from utils.memory import MemoryManager

router = APIRouter()
memory = MemoryManager()


@router.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传用户图片到个人素材库，返回持久化 URL 并记录到 personal_material_library"""
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    # 验证文件扩展名（防止上传恶意文件类型）
    if ext.lower() not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 .{ext}，仅允许: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}"
        )
    safe_name = f"user_{uuid.uuid4().hex[:8]}_{file.filename or 'image'}"
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-") + f".{ext}"
    file_path = PERSONAL_DIR / safe_name
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    url = f"/personal/{safe_name}"
    # 记录到个人素材库
    try:
        tags = ["用户上传"]
        memory.record_material(url, "image", tags)
    except Exception as e:
        print(f"[上传] 素材库记录失败: {e}")
    print(f"[上传] {file.filename} → {url} ({len(content)} bytes)")
    return {"url": url, "original_name": file.filename, "size": len(content)}
