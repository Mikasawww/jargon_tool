# ui/main_window.py
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from config import (
    APP_NAME, APP_VERSION, MAX_INPUT_LENGTH,
    SUPPORTED_LANGS, DATA_DIR
)
from dictionary import Scene, ReplyStyle, SCENE_I18N_KEY, STYLE_I18N_KEY
from exceptions import AppError
from i18n import i18n
from logger import logger
from api.analyze import analyze_text
import db


def format_result(result: dict) -> str:
    lines = []
    lines.append(f"【{i18n.t('result.summary')}】")
    lines.append(result.get("summary", ""))
    lines.append("")

    lines.append(f"【{i18n.t('result.terms')}】")
    for t in result.get("difficultTerms", []):
        lines.append(f"  🔹 {t['term']} → {t['explanation']}")
    lines.append("")

    ai = result.get("actionItems", {})
    lines.append(f"【{i18n.t('result.actions')}】")
    lines.append(f"  ✅ what: {ai.get('what', '')}")
    lines.append(f"  ⚠️ deadline: {ai.get('deadline', '')}")
    lines.append(f"  ⚠️ assignee: {ai.get('assignee', '')}")
    lines.append("")

    lines.append(f"【{i18n.t('result.missing')}】")
    for m in result.get("missingInfo", []):
        lines.append(f"  • {m}")
    lines.append("")

    lines.append(f"【{i18n.t('result.questions')}】")
    for q in result.get("suggestedQuestions", []):
        lines.append(f"  • {q}")

    return "\n".join(lines)


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_result = None
        self._preserved_scene = None
        self._preserved_style = None
        self._detail_window = None
        self._analyzing = False
        db.init_db()
        self.favorites = db.get_all_favorites()

        self._build_ui()
        self._refresh_texts()

        # 后台预热 embedding 模型，避免首次点"分析"时
        # 在主线程加载 420MB 模型导致界面卡死
        self._preload_embedding()

    def _preload_embedding(self):
        def _warm():
            try:
                from api.embedding import get_model
                get_model()
                logger.info("embedding model preloaded")
            except Exception as e:
                logger.warning(f"embedding preload failed: {e}")
        threading.Thread(target=_warm, daemon=True).start()

    # ---------- 本地收藏 ----------
    def _load_favorites(self) -> list:
        return db.get_all_favorites()

    # ---------- UI ----------
    def _build_ui(self):
        self.root.geometry("900x700")

        # 顶部：标题 + 语言切换
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        self.title_label = ttk.Label(top, font=("", 14, "bold"))
        self.title_label.pack(side="left")

        lang_frame = ttk.Frame(top)
        lang_frame.pack(side="right")
        self.lang_var = tk.StringVar(value=i18n.lang)
        for lang in SUPPORTED_LANGS:
            ttk.Radiobutton(
                lang_frame, text=lang.upper(), value=lang,
                variable=self.lang_var, command=self._on_lang_change
            ).pack(side="left", padx=2)

        # Tab
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.workspace_tab = ttk.Frame(self.notebook)
        self.favorites_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.workspace_tab, text="")
        self.notebook.add(self.favorites_tab, text="")

        self._build_workspace()
        self._build_favorites()

    def _build_workspace(self):
        f = self.workspace_tab

        # 输入标签
        self.input_label = ttk.Label(f)
        self.input_label.pack(anchor="w", padx=8, pady=(8, 0))

        # 输入框
        self.input_text = scrolledtext.ScrolledText(f, height=6, wrap="word")
        self.input_text.pack(fill="x", padx=8)
        self.input_text.bind("<KeyRelease>", self._on_text_change)

        # 字数
        self.char_label = ttk.Label(f, foreground="gray")
        self.char_label.pack(anchor="e", padx=8)

        # 隐私提示
        self.privacy_label = ttk.Label(f, foreground="#b36b00")
        self.privacy_label.pack(anchor="w", padx=8)

        # 场景
        scene_row = ttk.Frame(f)
        scene_row.pack(fill="x", padx=8, pady=4)
        self.scene_label = ttk.Label(scene_row)
        self.scene_label.pack(side="left")

        self.scene_var = tk.StringVar()
        self.scene_combo = ttk.Combobox(
            scene_row, textvariable=self.scene_var, state="readonly", width=20
        )
        self.scene_combo.pack(side="left", padx=8)

        # 按钮
        btn_row = ttk.Frame(f)
        btn_row.pack(fill="x", padx=8, pady=6)
        self.btn_analyze = ttk.Button(btn_row, command=self._on_analyze)
        self.btn_clear = ttk.Button(btn_row, command=self._on_clear)
        self.btn_analyze.pack(side="left")
        self.btn_clear.pack(side="left", padx=6)

        # 结果区
        self.result_frame = ttk.LabelFrame(f)
        self.result_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self.result_text = scrolledtext.ScrolledText(
            self.result_frame, height=10, wrap="word", state="disabled"
        )
        self.result_text.pack(fill="both", expand=True, padx=6, pady=6)

        # 底部按钮（收藏）
        bottom = ttk.Frame(self.result_frame)
        bottom.pack(fill="x", padx=6, pady=(0, 6))
        self.btn_save = ttk.Button(bottom, command=self._on_save)
        self.btn_save.pack(side="left")

        # 回复风格选择
        style_row = ttk.Frame(f)
        style_row.pack(fill="x", padx=8, pady=4)
        self.style_label = ttk.Label(style_row)
        self.style_label.pack(side="left")

        self.style_var = tk.StringVar()
        self.style_combo = ttk.Combobox(
            style_row, textvariable=self.style_var,
            state="readonly", width=15
        )
        self.style_combo.pack(side="left", padx=8)
        self.style_combo.bind(
            "<<ComboboxSelected>>", self._on_style_change
        )

        # 结果区2：回复草稿
        self.reply_frame = ttk.LabelFrame(f)
        self.reply_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self.reply_text = scrolledtext.ScrolledText(
            self.reply_frame, height=6, wrap="word", state="disabled"
        )
        self.reply_text.pack(fill="both", expand=True, padx=6, pady=6)

        # 结果区2底部按钮（复制回复）
        reply_bottom = ttk.Frame(self.reply_frame)
        reply_bottom.pack(fill="x", padx=6, pady=(0, 6))
        self.btn_copy = ttk.Button(reply_bottom, command=self._on_copy)
        self.btn_copy.pack(side="left")

    def _build_favorites(self):
        f = self.favorites_tab
        self.fav_list = tk.Listbox(f)
        self.fav_list.pack(fill="both", expand=True, padx=8, pady=8)
        self.fav_list.bind("<Double-Button-1>", self._on_fav_double_click)
        self.fav_empty_label = ttk.Label(f, foreground="gray")
        self.fav_empty_label.pack(pady=4)

    # ---------- 事件 ----------
    def _on_lang_change(self):
        self._preserved_scene = self._scene_from_label(self.scene_var.get())
        self._preserved_style = self._style_from_label(self.style_var.get())
        i18n.set_lang(self.lang_var.get())
        self._refresh_texts()

    def _on_text_change(self, _event=None):
        count = len(self.input_text.get("1.0", "end-1c"))
        self.char_label.config(
            text=i18n.t("label.char_count", count=count, max=MAX_INPUT_LENGTH)
        )

    def _on_clear(self):
        if messagebox.askyesno(i18n.t("app.title"), "Clear all?"):
            self.input_text.delete("1.0", "end")
            self.scene_var.set("")
            self.style_var.set("")
            self._set_result("")
            self._set_reply("")
            self.current_result = None

    def _on_analyze(self):
        if self._analyzing:
            return
        text = self.input_text.get("1.0", "end-1c")
        scene_key = self.scene_var.get()
        scene = self._scene_from_label(scene_key)
        scene_value = scene.value if scene else None

        # 后台线程执行模型加载/检索/网络请求，避免阻塞 UI
        self._set_busy(True)
        threading.Thread(
            target=self._analyze_worker,
            args=(text, scene_value),
            daemon=True
        ).start()

    def _analyze_worker(self, text: str, scene_value: str | None):
        """在后台线程中运行，禁止直接操作 tkinter 控件。"""
        try:
            result = analyze_text(text, scene_value)
        except AppError as e:
            self.root.after(0, self._on_analyze_failed, ("app", e.code))
            return
        except Exception as e:
            logger.error(f"unexpected error: {e}")
            self.root.after(0, self._on_analyze_failed, ("server", None))
            return
        self.root.after(0, self._on_analyze_ok, result)

    def _on_analyze_ok(self, result: dict):
        self._set_busy(False)
        self.current_result = result
        self._render_result(result)

    def _on_analyze_failed(self, err: tuple):
        self._set_busy(False)
        kind, code = err
        if kind == "app":
            messagebox.showwarning(
                i18n.t("app.title"),
                i18n.t(f"error.{self._err_key(code)}")
            )
        else:
            messagebox.showerror(
                i18n.t("app.title"), i18n.t("error.server")
            )

    def _set_busy(self, busy: bool):
        self._analyzing = busy
        self.btn_analyze.config(state="disabled" if busy else "normal")
        self.btn_clear.config(state="disabled" if busy else "normal")
        self.btn_analyze.config(
            text=i18n.t("btn.analyzing" if busy else "btn.analyze")
        )
        self.root.update_idletasks()

    def _on_copy(self):
        reply_text = self.reply_text.get("1.0", "end-1c").strip()
        if not reply_text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(reply_text)
        messagebox.showinfo(i18n.t("app.title"), i18n.t("msg.copied"))

    def _on_save(self):
        if not self.current_result:
            return
        original_text = self.input_text.get("1.0", "end-1c")
        scene = self._scene_from_label(self.scene_var.get())
        scene_value = scene.value if scene else ""
        result_json = json.dumps(
            self.current_result, ensure_ascii=False, indent=2
        )
        db.add_favorite(original_text, scene_value, result_json)
        self._refresh_favorites()
        messagebox.showinfo(i18n.t("app.title"), i18n.t("msg.saved"))

    def _on_style_change(self, _event=None):
        if self.current_result is not None:
            self._render_reply(self.current_result)

    # ---------- 渲染 ----------
    def _render_result(self, result: dict):
        self._set_result(format_result(result))
        self._render_reply(result)

    def _render_reply(self, result: dict):
        style = self._style_from_label(self.style_var.get())
        text = ""
        if style is not None:
            rd = result.get("replyDraft", {})
            text = rd.get(style.value, "")
        self._set_reply(text)

    def _set_result(self, text: str):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.config(state="disabled")

    def _set_reply(self, text: str):
        self.reply_text.config(state="normal")
        self.reply_text.delete("1.0", "end")
        self.reply_text.insert("1.0", text)
        self.reply_text.config(state="disabled")

    def _refresh_favorites(self):
        self.favorites = db.get_all_favorites()
        self.fav_list.delete(0, "end")
        if not self.favorites:
            self.fav_empty_label.config(text=i18n.t("msg.no_favorites"))
            return
        self.fav_empty_label.config(text="")
        for item in self.favorites:
            scene_val = item.get("scene", "")
            scene_label = scene_val
            for s in Scene:
                if s.value == scene_val:
                    scene_label = i18n.t(SCENE_I18N_KEY[s])
                    break
            snippet = item["original_text"][:30].replace("\n", " ")
            self.fav_list.insert(
                "end", f"[{scene_label}] {snippet}…"
            )

    def _on_fav_double_click(self, _event=None):
        sel = self.fav_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.favorites):
            return
        fav_id = self.favorites[idx]["id"]
        # 关闭旧的详情窗口
        if self._detail_window is not None:
            try:
                self._detail_window.destroy()
            except Exception:
                pass
            self._detail_window = None
        from ui.favorite_detail import FavoriteDetailWindow
        self._detail_window = FavoriteDetailWindow(
            self.root, fav_id, self._refresh_favorites
        )

    def _refresh_texts(self):
        self.root.title(f"{i18n.t('app.title')} v{APP_VERSION}")
        self.title_label.config(text=i18n.t("app.title"))
        self.notebook.tab(0, text=i18n.t("tab.workspace"))
        self.notebook.tab(1, text=i18n.t("tab.favorites"))
        self.input_label.config(text=i18n.t("label.input"))
        self.privacy_label.config(text=i18n.t("privacy.notice"))
        self.scene_label.config(text=i18n.t("label.scene"))
        self.style_label.config(text=i18n.t("label.style"))
        self.btn_analyze.config(text=i18n.t(
            "btn.analyzing" if self._analyzing else "btn.analyze"
        ))
        self.btn_clear.config(text=i18n.t("btn.clear"))
        self.btn_copy.config(text=i18n.t("btn.copy"))
        self.btn_save.config(text=i18n.t("btn.save"))
        self.reply_frame.config(text=i18n.t("result.reply"))

        # 场景下拉
        scene_labels = [i18n.t(SCENE_I18N_KEY[s]) for s in Scene]
        self.scene_combo["values"] = scene_labels
        if self._preserved_scene is not None:
            self.scene_var.set(i18n.t(SCENE_I18N_KEY[self._preserved_scene]))
            self._preserved_scene = None
        elif self.scene_var.get() not in scene_labels:
            self.scene_var.set("")

        # 回复风格下拉
        style_labels = [i18n.t(STYLE_I18N_KEY[s]) for s in ReplyStyle]
        self.style_combo["values"] = style_labels
        if self._preserved_style is not None:
            self.style_var.set(
                i18n.t(STYLE_I18N_KEY[self._preserved_style])
            )
            self._preserved_style = None
        elif self.style_var.get() not in style_labels:
            self.style_var.set("")

        self._on_text_change()
        self._refresh_favorites()
        if self.current_result is not None:
            self._render_result(self.current_result)

    def _scene_from_label(self, label: str):
        for s in Scene:
            if i18n.t(SCENE_I18N_KEY[s]) == label:
                return s
        return None

    def _style_from_label(self, label: str):
        for s in ReplyStyle:
            if i18n.t(STYLE_I18N_KEY[s]) == label:
                return s
        return None

    def _err_key(self, code: str) -> str:
        return {
            "E001": "empty", "E002": "too_short", "E003": "too_long",
            "E004": "no_scene", "E005": "timeout", "E006": "llm_format",
            "E007": "rag_unavailable", "E008": "server", "E009": "no_api_key",
        }.get(code, "server")