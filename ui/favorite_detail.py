# ui/favorite_detail.py
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from dictionary import Scene, SCENE_I18N_KEY
from i18n import i18n
from logger import logger
import db
from ui.main_window import format_result


class FavoriteDetailWindow(tk.Toplevel):
    def __init__(self, root, fav_id: int, on_delete_callback=None):
        super().__init__(root)
        self.fav_id = fav_id
        self.on_delete_callback = on_delete_callback

        self.record = db.get_favorite(fav_id)
        if not self.record:
            messagebox.showwarning(
                i18n.t("app.title"), i18n.t("error.server")
            )
            self.destroy()
            return

        self._build_ui()
        self._load_data()
        self._refresh_texts()

    def _build_ui(self):
        self.geometry("800x650")
        self.resizable(True, True)

        # 顶部标题
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.title_label = ttk.Label(top, font=("", 14, "bold"))
        self.title_label.pack(side="left")

        # 原文区
        self.original_frame = ttk.LabelFrame(self, padding=4)
        self.original_frame.pack(fill="x", padx=8, pady=(4, 4))
        self.original_label = ttk.Label(self.original_frame)
        self.original_label.pack(anchor="w")
        self.original_text = scrolledtext.ScrolledText(
            self.original_frame, height=5, wrap="word", state="disabled"
        )
        self.original_text.pack(fill="x", padx=4, pady=4)

        # 场景
        scene_row = ttk.Frame(self, padding=4)
        scene_row.pack(fill="x", padx=8)
        self.scene_label = ttk.Label(scene_row)
        self.scene_label.pack(side="left")

        # 结果区
        self.result_frame = ttk.LabelFrame(self, padding=4)
        self.result_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.result_text = scrolledtext.ScrolledText(
            self.result_frame, height=14, wrap="word", state="disabled"
        )
        self.result_text.pack(fill="both", expand=True, padx=4, pady=4)

        # 底部按钮
        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        self.btn_delete = ttk.Button(bottom, command=self._on_delete)
        self.btn_delete.pack(side="left")
        self.btn_close = ttk.Button(bottom, command=self.destroy)
        self.btn_close.pack(side="left", padx=6)

    def _load_data(self):
        rec = self.record
        # 原文
        self.original_text.config(state="normal")
        self.original_text.delete("1.0", "end")
        self.original_text.insert("1.0", rec["original_text"])
        self.original_text.config(state="disabled")

        # 结果
        try:
            result = json.loads(rec["result_json"])
        except Exception as e:
            logger.error(f"parse result_json failed: {e}")
            result = {}
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", format_result(result))
        self.result_text.config(state="disabled")

    def _refresh_texts(self):
        self.title_label.config(text=i18n.t("favorite.detail_title"))
        self.original_label.config(text=i18n.t("favorite.original"))
        self.scene_label.config(
            text=f"{i18n.t('label.scene')}: {self._scene_label()}"
        )
        self.btn_delete.config(text=i18n.t("btn.delete"))
        self.btn_close.config(text=i18n.t("btn.close"))

    def _scene_label(self) -> str:
        scene_val = self.record.get("scene", "")
        for s in Scene:
            if s.value == scene_val:
                return i18n.t(SCENE_I18N_KEY[s])
        return scene_val

    def _on_delete(self):
        if not messagebox.askyesno(
            i18n.t("favorite.detail_title"),
            i18n.t("msg.confirm_delete")
        ):
            return
        db.delete_favorite(self.fav_id)
        if self.on_delete_callback:
            self.on_delete_callback()
        self.destroy()
