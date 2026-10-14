# dictionary.py
from enum import Enum


class Scene(str, Enum):
    TASK = "task"           # 任务安排
    HR = "hr"               # HR通知
    REFUSAL = "refusal"     # 委婉拒绝
    MEETING = "meeting"     # 会议汇报
    EMAIL = "email"         # 邮件确认
    OTHER = "other"         # 其他


class ReplyStyle(str, Enum):
    FORMAL = "formal"       # 正式
    CASUAL = "casual"       # 日常
    CONCISE = "concise"     # 简洁


# 场景 -> i18n key
SCENE_I18N_KEY = {
    Scene.TASK: "scene.task",
    Scene.HR: "scene.hr",
    Scene.REFUSAL: "scene.refusal",
    Scene.MEETING: "scene.meeting",
    Scene.EMAIL: "scene.email",
    Scene.OTHER: "scene.other",
}

# 回复风格 -> i18n key
STYLE_I18N_KEY = {
    ReplyStyle.FORMAL: "style.formal",
    ReplyStyle.CASUAL: "style.casual",
    ReplyStyle.CONCISE: "style.concise",
}

# 错误码 -> i18n key
ERROR_I18N_KEY = {
    "E001": "error.empty",
    "E002": "error.too_short",
    "E003": "error.too_long",
    "E004": "error.no_scene",
    "E005": "error.timeout",
    "E006": "error.llm_format",
    "E007": "error.rag_unavailable",
    "E008": "error.server",
}