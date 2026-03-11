import tkinter as tk
from tkinter import ttk
from typing import Callable
import logging

from config import AppConfig, AudioBackendType, OverlayDisplayMode, WhisperModelSize
from audio.process_list import ProcessInfo, list_gui_apps
from translation import translator
from translation.translator import LANGUAGES

logger = logging.getLogger(__name__)


class AppSelectorWindow:
    """アプリ選択・設定画面"""

    def __init__(self, root: tk.Tk,
                 on_start: Callable[[AppConfig], None],
                 on_stop: Callable[[], None],
                 sck_available: bool = False,
                 blackhole_available: bool = False):
        self._root = root
        self._on_start = on_start
        self._on_stop = on_stop
        self._sck_available = sck_available
        self._blackhole_available = blackhole_available
        self._processes: list[ProcessInfo] = []
        self._is_running = False

        self._root.title("LLM Trans - リアルタイム字幕")
        self._root.geometry("520x700")
        self._root.resizable(False, False)

        self._saved = AppConfig.load()
        self._build_ui()
        self._restore_settings()
        self._refresh_processes()

    def _build_ui(self) -> None:
        pad = {'padx': 10, 'pady': 5}

        # --- バックエンド選択 ---
        frame_backend = ttk.LabelFrame(self._root, text="音声キャプチャ方式")
        frame_backend.pack(fill=tk.X, **pad)

        self._backend_var = tk.StringVar(value="sck")
        backends = []
        if self._sck_available:
            backends.append(("ScreenCaptureKit (アプリ別)", "sck"))
        if self._blackhole_available:
            backends.append(("BlackHole (システム音声)", "blackhole"))

        if not backends:
            backends.append(("利用可能なバックエンドなし", "none"))

        for text, val in backends:
            ttk.Radiobutton(
                frame_backend, text=text, variable=self._backend_var,
                value=val, command=self._on_backend_change
            ).pack(anchor=tk.W, padx=20)

        if not self._sck_available and not self._blackhole_available:
            ttk.Label(frame_backend,
                      text="画面収録の権限を許可してください",
                      foreground="red").pack(padx=20)

        # --- アプリ選択 ---
        frame_apps = ttk.LabelFrame(self._root, text="対象アプリ")
        frame_apps.pack(fill=tk.BOTH, expand=True, **pad)

        list_frame = ttk.Frame(frame_apps)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._app_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set,
            font=("Menlo", 12), height=8
        )
        self._app_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._app_listbox.yview)

        ttk.Button(frame_apps, text="更新",
                   command=self._refresh_processes).pack(pady=5)

        # --- モデル選択 ---
        frame_model = ttk.LabelFrame(self._root, text="Whisperモデル")
        frame_model.pack(fill=tk.X, **pad)

        model_frame = ttk.Frame(frame_model)
        model_frame.pack(padx=20, pady=5)

        ttk.Label(model_frame, text="モデル:").pack(side=tk.LEFT)
        self._model_var = tk.StringVar(value="large-v3")
        model_combo = ttk.Combobox(
            model_frame, textvariable=self._model_var,
            values=["tiny", "base", "small", "medium", "large-v3"],
            state="readonly", width=12
        )
        model_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(model_frame, text="言語:").pack(side=tk.LEFT, padx=(10, 0))
        self._lang_var = tk.StringVar(value="en")
        lang_combo = ttk.Combobox(
            model_frame, textvariable=self._lang_var,
            values=["ja", "en", "zh", "ko", "auto"],
            state="readonly", width=6
        )
        lang_combo.pack(side=tk.LEFT, padx=5)

        # --- オーバーレイ設定 ---
        frame_overlay = ttk.LabelFrame(self._root, text="字幕表示")
        frame_overlay.pack(fill=tk.X, **pad)

        overlay_inner = ttk.Frame(frame_overlay)
        overlay_inner.pack(padx=20, pady=5)

        ttk.Label(overlay_inner, text="フォントサイズ:").pack(side=tk.LEFT)
        self._font_size_var = tk.IntVar(value=24)
        font_spin = ttk.Spinbox(
            overlay_inner, from_=10, to=60, increment=2,
            textvariable=self._font_size_var, width=4,
        )
        font_spin.pack(side=tk.LEFT, padx=5)

        ttk.Label(overlay_inner, text="表示:").pack(side=tk.LEFT, padx=(10, 0))
        self._display_mode_var = tk.StringVar(value="short")
        mode_combo = ttk.Combobox(
            overlay_inner, textvariable=self._display_mode_var,
            values=["short", "list"], state="readonly", width=6,
        )
        mode_combo.pack(side=tk.LEFT, padx=5)

        # --- 翻訳設定 ---
        frame_trans = ttk.LabelFrame(self._root, text="翻訳 (Ollama)")
        frame_trans.pack(fill=tk.X, **pad)

        self._trans_enabled_var = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(
            frame_trans, text="翻訳を有効にする",
            variable=self._trans_enabled_var,
            command=self._on_translation_toggle,
        )
        chk.pack(anchor=tk.W, padx=20, pady=(5, 0))

        trans_inner = ttk.Frame(frame_trans)
        trans_inner.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(trans_inner, text="ホスト:").grid(row=0, column=0, sticky=tk.W)
        self._ollama_host_var = tk.StringVar(value="http://localhost:11434")
        host_entry = ttk.Entry(trans_inner, textvariable=self._ollama_host_var, width=28)
        host_entry.grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Label(trans_inner, text="モデル:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        model_trans_frame = ttk.Frame(trans_inner)
        model_trans_frame.grid(row=1, column=1, padx=5, pady=(5, 0), sticky=tk.W)

        self._ollama_model_var = tk.StringVar(value="translategemma:4b")
        self._ollama_model_combo = ttk.Combobox(
            model_trans_frame, textvariable=self._ollama_model_var,
            values=[], state="readonly", width=20,
        )
        self._ollama_model_combo.pack(side=tk.LEFT)

        self._refresh_models_btn = ttk.Button(
            model_trans_frame, text="取得",
            command=self._refresh_ollama_models, width=5,
        )
        self._refresh_models_btn.pack(side=tk.LEFT, padx=5)

        lang_labels = [f"{code} ({name})" for code, name in LANGUAGES.items()]
        lang_codes = list(LANGUAGES.keys())

        ttk.Label(trans_inner, text="翻訳元:").grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        src_frame = ttk.Frame(trans_inner)
        src_frame.grid(row=2, column=1, padx=5, pady=(5, 0), sticky=tk.W)

        self._trans_src_var = tk.StringVar(value="en (English)")
        src_combo = ttk.Combobox(
            src_frame, textvariable=self._trans_src_var,
            values=lang_labels, state="readonly", width=24,
        )
        src_combo.pack(side=tk.LEFT)

        ttk.Label(trans_inner, text="翻訳先:").grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        tgt_frame = ttk.Frame(trans_inner)
        tgt_frame.grid(row=3, column=1, padx=5, pady=(5, 5), sticky=tk.W)

        self._trans_tgt_var = tk.StringVar(value="ja (Japanese)")
        tgt_combo = ttk.Combobox(
            tgt_frame, textvariable=self._trans_tgt_var,
            values=lang_labels, state="readonly", width=24,
        )
        tgt_combo.pack(side=tk.LEFT)

        self._trans_widgets = [host_entry, self._ollama_model_combo,
                               self._refresh_models_btn, src_combo, tgt_combo]
        self._on_translation_toggle()

        # --- ステータス + ボタン ---
        frame_bottom = ttk.Frame(self._root)
        frame_bottom.pack(fill=tk.X, **pad)

        self._status_label = ttk.Label(
            frame_bottom, text="準備完了", font=("Hiragino Sans", 11)
        )
        self._status_label.pack(side=tk.LEFT, expand=True)

        self._stop_btn = ttk.Button(
            frame_bottom, text="停止", command=self._stop_clicked,
            state=tk.DISABLED
        )
        self._stop_btn.pack(side=tk.RIGHT, padx=5)

        self._start_btn = ttk.Button(
            frame_bottom, text="開始", command=self._start_clicked
        )
        self._start_btn.pack(side=tk.RIGHT, padx=5)

    def _on_backend_change(self) -> None:
        is_sck = self._backend_var.get() == "sck"
        state = tk.NORMAL if is_sck else tk.DISABLED
        self._app_listbox.config(state=state)

    def _refresh_processes(self) -> None:
        self._app_listbox.delete(0, tk.END)
        self._processes = list_gui_apps()
        for proc in self._processes:
            self._app_listbox.insert(tk.END, f"{proc.name}  (PID: {proc.pid})")
        if self._processes:
            self._app_listbox.selection_set(0)

    def _start_clicked(self) -> None:
        backend_str = self._backend_var.get()

        if backend_str == "none":
            self.set_status("バックエンドが利用できません", "red")
            return

        if backend_str == "sck":
            sel = self._app_listbox.curselection()
            if not sel:
                self.set_status("アプリを選択してください", "red")
                return
            proc = self._processes[sel[0]]
            backend_type = AudioBackendType.SCK
            target_pid = proc.pid
            target_name = proc.name
        else:
            backend_type = AudioBackendType.BLACKHOLE
            target_pid = None
            target_name = None

        model_map = {v.value: v for v in WhisperModelSize}
        model_size = model_map.get(self._model_var.get(), WhisperModelSize.SMALL)

        mode_map = {v.value: v for v in OverlayDisplayMode}
        display_mode = mode_map.get(self._display_mode_var.get(),
                                    OverlayDisplayMode.SHORT)

        config = AppConfig(
            audio_backend=backend_type,
            whisper_model=model_size,
            language=self._lang_var.get(),
            target_pid=target_pid,
            target_app_name=target_name,
            font_size=self._font_size_var.get(),
            overlay_display_mode=display_mode,
            enable_translation=self._trans_enabled_var.get(),
            ollama_host=self._ollama_host_var.get().strip(),
            ollama_model=self._ollama_model_var.get().strip(),
            translation_source_lang=self._trans_src_var.get().split(" ")[0],
            translation_target_lang=self._trans_tgt_var.get().split(" ")[0],
        )

        config.save()

        self._is_running = True
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self.set_status("初期化中...", "orange")

        self._on_start(config)

    def _stop_clicked(self) -> None:
        self._is_running = False
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._on_stop()
        self.set_status("停止しました")

    def _on_translation_toggle(self) -> None:
        enabled = self._trans_enabled_var.get()
        state = tk.NORMAL if enabled else tk.DISABLED
        for w in self._trans_widgets:
            w.config(state=state)

    def _refresh_ollama_models(self) -> None:
        host = self._ollama_host_var.get().strip()
        models = translator.list_models(host)
        self._ollama_model_combo["values"] = models
        if models:
            self._ollama_model_var.set(models[0])
        else:
            self._ollama_model_var.set("")
            self.set_status("Ollamaモデル取得失敗", "red")

    def _restore_settings(self) -> None:
        """保存済みの設定をUIに復元する。"""
        s = self._saved
        self._backend_var.set(s.audio_backend.value)
        self._model_var.set(s.whisper_model.value)
        self._lang_var.set(s.language)
        self._font_size_var.set(s.font_size)
        self._display_mode_var.set(s.overlay_display_mode.value)
        self._trans_enabled_var.set(s.enable_translation)
        self._ollama_host_var.set(s.ollama_host)
        self._ollama_model_var.set(s.ollama_model)
        # 言語コード → コンボボックス表示値
        src_name = LANGUAGES.get(s.translation_source_lang, s.translation_source_lang)
        tgt_name = LANGUAGES.get(s.translation_target_lang, s.translation_target_lang)
        self._trans_src_var.set(f"{s.translation_source_lang} ({src_name})")
        self._trans_tgt_var.set(f"{s.translation_target_lang} ({tgt_name})")
        self._on_translation_toggle()
        self._on_backend_change()

    def set_status(self, text: str, color: str = "black") -> None:
        def _update():
            self._status_label.config(text=text, foreground=color)
        self._root.after(0, _update)
