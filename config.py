# config.py
import os
import sys

APP_NAME = "Business Jargon Tool"
APP_VERSION = "0.1.0"
DEFAULT_LANG = "ja"          # 默认日语
SUPPORTED_LANGS = ["ja", "zh", "en"]

# 输入限制
MAX_INPUT_LENGTH = 2000
MIN_INPUT_LENGTH = 5

# ========== 路径适配（PyInstaller 打包兼容） ==========
# 打包后 sys.frozen=True，只读资源在 sys._MEIPASS（exe 内部目录）
FROZEN = getattr(sys, "frozen", False)
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(rel_path: str) -> str:
    """只读资源（知识库/语言文件/种子缓存）的路径。"""
    base = sys._MEIPASS if FROZEN else _PROJECT_DIR
    return os.path.join(base, rel_path)


# 可执行文件所在目录：打包后为 exe 同级，开发时为项目目录
APP_DIR = os.path.dirname(sys.executable) if FROZEN else _PROJECT_DIR
# 外置 .env（用户可编辑 API Key）
ENV_FILE = os.path.join(APP_DIR, ".env")

# 日志
LOG_DIR = os.path.join(os.path.expanduser("~"), ".biz_jargon_tool", "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# 本地存储（收藏）
DATA_DIR = os.path.join(os.path.expanduser("~"), ".biz_jargon_tool")
FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")
DB_PATH = os.path.join(DATA_DIR, "favorites.db")

# 本地知识库（RAG，只读资源，随包分发）
KB_FILE = resource_path("knowledge_base.json")
RAG_TOP_K = 5

# Embedding 向量化
EMBEDDING_MODEL = "sonoisa/sentence-bert-base-ja-mean-tokens-v2"  # 日语专用 SBERT
# 向量缓存放用户目录（可写）；打包后首次运行从内置种子文件复制，无需重新计算
EMBEDDING_CACHE_FILE = os.path.join(DATA_DIR, "kb_embeddings.npz")
EMBEDDING_CACHE_SEED = resource_path("kb_embeddings.npz")
# 混合打分权重（日语专用模型语义更准，向量权重上调）
VEC_WEIGHT = 0.75      # 向量余弦相似度权重
STR_WEIGHT = 0.25      # 字符串匹配权重
# HuggingFace 镜像（清华）
HF_ENDPOINT = "https://hf-mirror.com"

# API（Day3 后接入，先用占位）
API_TIMEOUT = 15