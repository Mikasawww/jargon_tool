# main.py
import os

from config import ENV_FILE

# .env 模板：首次运行（打包后 exe 同级无 .env 时）自动生成，
# 用户可直接编辑该文件填写/修改 API Key，无需重新打包
_ENV_TEMPLATE = """\
# ===== API 配置（修改后重启程序生效）=====
# DeepSeek API Key（必填）
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com

# OpenAI 备用（未启用，可留空）
OPENAI_API_KEY=
"""


def _ensure_env_file():
    """外置 .env 不存在时生成模板，保证用户有可编辑的 API Key 文件。"""
    if os.path.exists(ENV_FILE):
        return
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(_ENV_TEMPLATE)
    except OSError:
        pass


_ensure_env_file()

from dotenv import load_dotenv
load_dotenv(ENV_FILE)

import tkinter as tk
from ui.main_window import MainWindow
from logger import logger


def main():
    logger.info("app start")
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
    logger.info("app exit")


if __name__ == "__main__":
    main()
