"""
文本向量化封装

使用 sentence-transformers 将中文文本转为 1024-dim 向量，
供 Qdrant 语义检索使用。首次加载会下载模型（~100MB，自动缓存）。

下载策略：
  1. 优先使用 HF_ENDPOINT 镜像站（如 hf-mirror.com）
  2. 回退到 HuggingFace 官方源
  3. 如果已下载到本地缓存，直接加载（离线可用）

降级: 模型不可用时返回零向量，主流程不中断。
"""
import os
import threading
from typing import List

try:
    from sentence_transformers import SentenceTransformer
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False
    SentenceTransformer = None


_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
# 本地模型路径（ModelScope 下载的离线模型，优先于在线下载）
_MODEL_LOCAL_PATH = os.environ.get("EMBEDDING_LOCAL_PATH", "D:/Services/modelscope/BAAI/bge-small-zh-v1___5")
_DEVICE = os.environ.get("EMBEDDING_DEVICE", "cpu")
_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))

# HuggingFace 镜像站（国内加速，不走代理）
_HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "")
# 本地缓存目录
_HF_HOME = os.environ.get("HF_HOME") or os.path.join(
    os.path.expanduser("~"), ".cache", "huggingface"
)

_model: "SentenceTransformer" = None
_model_lock = threading.Lock()
_dim = 0  # 从模型实际输出计算


def get_dim() -> int:
    """返回模型实际向量维度（模型加载后自动获取）"""
    global _dim
    if _dim <= 0:
        model = _get_model()
        if model is not None and model is not False:
            _dim = getattr(model, 'get_embedding_dimension', getattr(model, 'get_sentence_embedding_dimension', lambda: 512))() or 512
        else:
            _dim = 512  # bge-small-zh-v1.5 默认 512
    return _dim


def _configure_hf():
    """配置 HuggingFace 下载源"""
    if _HF_ENDPOINT:
        os.environ["HF_ENDPOINT"] = _HF_ENDPOINT
        print(f"[Embedding] 使用 HF 镜像站: {_HF_ENDPOINT}")
    if _HF_HOME:
        os.environ["HF_HOME"] = _HF_HOME


def _get_model():
    global _model
    if _model is not None:
        return _model
    if not _ST_AVAILABLE:
        print("[Embedding] sentence-transformers 未安装，降级运行")
        return None
    with _model_lock:
        if _model is not None:
            return _model
        _configure_hf()
        import os as _os
        # 优先使用本地已下载的模型
        if _os.path.exists(_MODEL_LOCAL_PATH):
            try:
                _model = SentenceTransformer(_MODEL_LOCAL_PATH, device=_DEVICE)
                print(f"[Embedding] 模型从本地加载: {_MODEL_LOCAL_PATH} (device={_DEVICE})")
                return _model
            except Exception as e:
                print(f"[Embedding] 本地模型加载失败: {e}，回退在线模式")
        # 在线模式（通过 HF 镜像），失败则离线模式降级
        try:
            _model = SentenceTransformer(_MODEL_NAME, device=_DEVICE, cache_folder=_HF_HOME)
            print(f"[Embedding] 模型 {_MODEL_NAME} 加载完成 (device={_DEVICE})")
        except Exception as e1:
            print(f"[Embedding] 在线加载失败: {e1}")
            print(f"[Embedding] 尝试离线模式 (local_files_only=True)...")
            try:
                _model = SentenceTransformer(
                    _MODEL_NAME, device=_DEVICE,
                    cache_folder=_HF_HOME, local_files_only=True
                )
                print(f"[Embedding] 模型从离线缓存加载成功 (device={_DEVICE})")
            except Exception as e2:
                print(f"[Embedding] 离线加载也失败 (降级运行，Qdrant 语义搜索暂时不可用)")
                print(f"            离线错误: {e2}")
                print(f"            手动下载: pip install -U huggingface_hub && huggingface-cli download {_MODEL_NAME}")
                _model = False
    return _model if _model is not False else None


def embed(text: str) -> List[float]:
    """将单条文本转为向量"""
    model = _get_model()
    if model is None:
        return [0.0] * get_dim()
    return model.encode(text, normalize_embeddings=True).tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    """批量文本转向量（比逐条 embed 快 3-5x）"""
    model = _get_model()
    if model is None:
        return [[0.0] * get_dim()] * len(texts)
    return model.encode(texts, normalize_embeddings=True, batch_size=_BATCH_SIZE).tolist()

