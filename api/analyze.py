# api/analyze.py
import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from config import MAX_INPUT_LENGTH, MIN_INPUT_LENGTH, ENV_FILE
from exceptions import (
    InputEmptyError, InputTooShortError, InputTooLongError,
    SceneNotSelectedError, LLMFormatError, APIKeyMissingError
)
from logger import logger
from api.rag import retrieve, build_context

# 外置 .env（打包后为 exe 同级，开发时为项目根目录）
load_dotenv(ENV_FILE)

# ========== 客户端初始化 ==========
# 懒加载：Key 未配置时（如打包后首次运行、外置 .env 为模板）
# 不立即崩溃，仅在点击"分析"时提示配置
_client = None


def _get_client():
    """创建并缓存 OpenAI 客户端；未配置 API Key 时返回 None。"""
    global _client
    if _client is None:
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            return None
        _client = OpenAI(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        )
    return _client


MODEL_NAME = "deepseek-chat"

# 方案B：OpenAI（注释掉上面，取消下面注释）
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# MODEL_NAME = "gpt-4o-mini"


# ========== System Prompt（三言語） ==========
SYSTEM_PROMPT_JA = """あなたは日本のビジネスコミュニケーションの専門アシスタントです。
以下のルールに従って、ユーザーが入力したビジネス文書を分析してください：

1. 「忖度」や「感情」を推測しない（例：「上司は私を信頼していない」など）
2. あくまで文書に書かれている客観的な情報のみを抽出する
3. 不明確な情報（期限、担当者、優先度など）は「不明」と明示する
4. 出力は必ず指定されたJSONフォーマットに従う
5. ビジネス用語やカタカナ語の説明には、提供されたRAG情報を優先する

必ず以下のJSON形式で出力してください。他のテキストは一切出力しないでください。
すべての内容は日本語で記述してください。
{
  "summary": "一言で理解（簡潔に、日本語で）",
  "difficultTerms": [{"term": "用語", "explanation": "説明（日本語で）"}],
  "actionItems": {
    "what": "何をするか",
    "deadline": "締切（不明の場合は「不明」）",
    "assignee": "担当者（不明の場合は「不明」）"
  },
  "missingInfo": ["不足している情報"],
  "suggestedQuestions": ["確認すべき質問"],
  "replyDraft": {
    "formal": "正式な返信（です・ます調＋敬語）",
    "casual": "日常的な返信（普通体）",
    "concise": "簡潔な返信"
  }
}"""

SYSTEM_PROMPT_ZH = """你是商务沟通专业助手。
请按以下规则分析用户输入的商务文书：

1. 不要揣测"言外之意"或"情感"（例如："上司不信任我"等）
2. 仅抽取文书中客观书写的信息
3. 不明确的信息（期限、负责人、优先度等）明确标注为"不明"
4. 输出必须严格遵循指定的JSON格式
5. 商务用语或外来语的解释，优先使用提供的RAG信息

请务必按以下JSON格式输出，不要输出任何其他文本。
所有内容均使用中文撰写。
{
  "summary": "一句话理解（简洁，中文）",
  "difficultTerms": [{"term": "术语", "explanation": "解释（中文）"}],
  "actionItems": {
    "what": "做什么",
    "deadline": "截止日期（不明时填"不明"）",
    "assignee": "负责人（不明时填"不明"）"
  },
  "missingInfo": ["缺失的信息"],
  "suggestedQuestions": ["应确认的问题"],
  "replyDraft": {
    "formal": "正式回复（敬语体）",
    "casual": "日常回复（口语体）",
    "concise": "简洁回复"
  }
}"""

SYSTEM_PROMPT_EN = """You are a professional business communication assistant.
Analyze the business document provided by the user following these rules:

1. Do not speculate on "implied meaning" or "emotions" (e.g., "my boss doesn't trust me")
2. Extract only the objective information written in the document
3. Explicitly mark unclear information (deadlines, assignees, priorities) as "unknown"
4. Output must strictly follow the specified JSON format
5. For business jargon or loanwords, prioritize the provided RAG information

Output strictly in the following JSON format. Do not output any other text.
All content must be written in English.
{
  "summary": "One-line understanding (concise, in English)",
  "difficultTerms": [{"term": "term", "explanation": "explanation (in English)"}],
  "actionItems": {
    "what": "what to do",
    "deadline": "deadline (use 'unknown' if unclear)",
    "assignee": "assignee (use 'unknown' if unclear)"
  },
  "missingInfo": ["missing information"],
  "suggestedQuestions": ["questions to confirm"],
  "replyDraft": {
    "formal": "formal reply",
    "casual": "casual reply",
    "concise": "concise reply"
  }
}"""

SYSTEM_PROMPTS = {
    "ja": SYSTEM_PROMPT_JA,
    "zh": SYSTEM_PROMPT_ZH,
    "en": SYSTEM_PROMPT_EN,
}


def detect_language(text: str) -> str:
    """
    检测文本语言（扫描全文，不能在首个字符就返回）：
    - 含平假名/片假名（含日语特有符号）→ ja
    - 无假名但含汉字 → zh
    - 其余 → en
    注意：日语句子常以汉字开头（資料、会議、来週…），
    若遇首个汉字即判中文会把日语误判为中文。
    """
    has_kana = False
    has_cjk = False
    for ch in text:
        cp = ord(ch)
        # 平假名、片假名、中点・、長音符ー
        if 0x3040 <= cp <= 0x30FF:
            has_kana = True
        # 々（3005）、半角片假名（FF65–FF9F）也是日语特征
        elif cp == 0x3005 or 0xFF65 <= cp <= 0xFF9F:
            has_kana = True
        elif 0x4E00 <= cp <= 0x9FFF:       # CJK 统一汉字
            has_cjk = True
    if has_kana:
        return "ja"
    if has_cjk:
        return "zh"
    return "en"


# ========== 输入校验 ==========
def validate_input(text: str, scene: str | None):
    if not text or not text.strip():
        raise InputEmptyError()
    if len(text.strip()) < MIN_INPUT_LENGTH:
        raise InputTooShortError()
    if len(text) > MAX_INPUT_LENGTH:
        raise InputTooLongError()
    if not scene:
        raise SceneNotSelectedError()


# ========== 真实 AI 调用 ==========
def analyze_text(text: str, scene: str) -> dict:
    """
    调用大模型进行场景化分析，返回结构化 JSON。
    """
    validate_input(text, scene)
    logger.info(f"analyze start, scene={scene}, len={len(text)}")

    # 检测输入语言，动态选择 System Prompt 和场景描述
    lang = detect_language(text)
    system_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPT_JA)
    logger.info(f"detected language: {lang}")

    # 场景描述（按检测语言输出）
    scene_descs = {
        "ja": {
            "task": "タスク指示（上司からの仕事の依頼）",
            "hr": "HR通知（人事からの連絡）",
            "refusal": "婉曲な断り（曖昧な拒否表現）",
            "meeting": "会議報告（会議での発言）",
            "email": "メール確認（ビジネスメール）",
            "other": "その他"
        },
        "zh": {
            "task": "任务指示（上司交办的工作）",
            "hr": "HR通知（人事联络）",
            "refusal": "委婉拒绝（含糊的拒绝表达）",
            "meeting": "会议汇报（会议中的发言）",
            "email": "邮件确认（商务邮件）",
            "other": "其他"
        },
        "en": {
            "task": "Task instruction (work assigned by supervisor)",
            "hr": "HR notice (communication from HR)",
            "refusal": "Indirect refusal (ambiguous rejection)",
            "meeting": "Meeting report (statements in meetings)",
            "email": "Email confirmation (business email)",
            "other": "Other"
        }
    }
    scene_desc = scene_descs.get(lang, scene_descs["ja"]).get(scene, "その他")

    # RAG 检索（失败时降级为纯 LLM，不阻断分析）
    try:
        kb_entries = retrieve(text, scene)
    except Exception as e:
        logger.warning(f"RAG retrieve failed: {e}")
        kb_entries = []
    rag_context = build_context(kb_entries, lang)
    logger.info(f"RAG hits: {len(kb_entries)}")

    # 用户提示词模板（按检测语言，避免日语指令把输出带向日语）
    user_templates = {
        "ja": "【シーン】{scene}\n【原文】\n{text}\n\n{rag}\n"
              "上記の原文を分析し、指定されたJSON形式で出力してください。",
        "zh": "【场景】{scene}\n【原文】\n{text}\n\n{rag}\n"
              "请分析以上原文，并按指定的JSON格式输出。",
        "en": "[Scene] {scene}\n[Source text]\n{text}\n\n{rag}\n"
              "Analyze the source text above and output in the specified JSON format.",
    }
    user_prompt = user_templates.get(lang, user_templates["ja"]).format(
        scene=scene_desc, text=text, rag=rag_context
    )

    client = _get_client()
    if client is None:
        logger.error("DEEPSEEK_API_KEY not configured (check .env)")
        raise APIKeyMissingError()

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,          # 降低随机性，保证格式稳定
            response_format={"type": "json_object"}  # 强制 JSON 输出
        )
        raw = response.choices[0].message.content
        logger.info("LLM response received")

        # 解析 JSON
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}, raw={raw[:200]}")
            raise LLMFormatError()

        # 补全缺失字段（防止模型漏字段导致前端报错）
        result.setdefault("summary", "")
        result.setdefault("difficultTerms", [])
        result.setdefault("actionItems", {"what": "", "deadline": "不明", "assignee": "不明"})
        result.setdefault("missingInfo", [])
        result.setdefault("suggestedQuestions", [])
        result.setdefault("replyDraft", {"formal": "", "casual": "", "concise": ""})

        logger.info("analyze done")
        return result

    except LLMFormatError:
        raise
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise

