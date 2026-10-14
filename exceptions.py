# exceptions.py
class AppError(Exception):
    """业务异常基类"""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(message)


class InputEmptyError(AppError):
    def __init__(self):
        super().__init__("E001", "Input is empty")


class InputTooShortError(AppError):
    def __init__(self):
        super().__init__("E002", "Input too short")


class InputTooLongError(AppError):
    def __init__(self):
        super().__init__("E003", "Input too long")


class SceneNotSelectedError(AppError):
    def __init__(self):
        super().__init__("E004", "Scene not selected")


class NetworkTimeoutError(AppError):
    def __init__(self):
        super().__init__("E005", "Network timeout")


class LLMFormatError(AppError):
    def __init__(self):
        super().__init__("E006", "LLM format error")


class RAGUnavailableError(AppError):
    def __init__(self):
        super().__init__("E007", "RAG unavailable")


class ServerError(AppError):
    def __init__(self):
        super().__init__("E008", "Server error")


class APIKeyMissingError(AppError):
    def __init__(self):
        super().__init__("E009", "API key not configured")