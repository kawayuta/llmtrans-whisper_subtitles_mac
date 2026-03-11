import tkinter as tk
import threading
import time
from collections import deque

from config import AppConfig, OverlayDisplayMode


class SubtitleOverlay:
    """Subtitle overlay displayed at the bottom of the screen (short/list mode)"""

    FONT_SIZE_MIN = 10
    FONT_SIZE_MAX = 60

    def __init__(self, config: AppConfig):
        self._config = config
        self._window: tk.Toplevel | None = None
        self._parent: tk.Tk | None = None
        self._lock = threading.Lock()

        self._label: tk.Label | None = None
        self._subtitles: deque[tuple[float, str]] = deque(maxlen=config.subtitle_max_lines)

        self._text_widget: tk.Text | None = None

        self._font_size = config.font_size
        self._display_mode = config.overlay_display_mode

    def create(self, parent: tk.Tk) -> None:
        self._parent = parent
        self._window = tk.Toplevel(parent)
        self._window.overrideredirect(True)
        self._window.attributes('-topmost', True)
        self._window.attributes('-alpha', self._config.overlay_opacity)

        screen_w = self._window.winfo_screenwidth()
        screen_h = self._window.winfo_screenheight()
        x = (screen_w - self._config.overlay_width) // 2
        y = screen_h - self._config.overlay_height - 80

        height = self._config.overlay_height
        if self._display_mode == OverlayDisplayMode.LIST:
            height = max(height, 240)

        self._window.geometry(
            f"{self._config.overlay_width}x{height}+{x}+{y}"
        )

        self._frame = tk.Frame(
            self._window,
            bg=self._config.overlay_bg_color,
            highlightthickness=1,
            highlightbackground="#333355",
        )
        self._frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._build_content()

        # Context menu
        self._context_menu = tk.Menu(self._window, tearoff=0)
        self._context_menu.add_command(label="Font +", command=self._font_increase)
        self._context_menu.add_command(label="Font -", command=self._font_decrease)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Short mode",
                                       command=lambda: self._switch_mode(OverlayDisplayMode.SHORT))
        self._context_menu.add_command(label="List mode",
                                       command=lambda: self._switch_mode(OverlayDisplayMode.LIST))

        self._window.bind('<Button-2>', self._show_context_menu)
        self._window.bind('<Button-3>', self._show_context_menu)
        self._window.bind('<Control-Button-1>', self._show_context_menu)

        self._window.bind('<MouseWheel>', self._on_scroll)

        self._keep_topmost()
        if self._display_mode == OverlayDisplayMode.SHORT:
            self._cleanup_loop()

    def _build_content(self) -> None:
        for w in self._frame.winfo_children():
            w.destroy()
        self._label = None
        self._text_widget = None

        if self._display_mode == OverlayDisplayMode.SHORT:
            self._build_short_mode()
        else:
            self._build_list_mode()

    def _build_short_mode(self) -> None:
        self._label = tk.Label(
            self._frame,
            text="",
            font=(self._config.font_family, self._font_size),
            fg=self._config.overlay_fg_color,
            bg=self._config.overlay_bg_color,
            wraplength=self._config.overlay_width - 40,
            justify=tk.CENTER,
            padx=20,
            pady=10,
        )
        self._label.pack(fill=tk.BOTH, expand=True)

        self._label.bind('<Button-1>', self._start_drag)
        self._label.bind('<B1-Motion>', self._on_drag)

        self._update_short_display()

    def _build_list_mode(self) -> None:
        self._text_widget = tk.Text(
            self._frame,
            font=(self._config.font_family, self._font_size),
            fg=self._config.overlay_fg_color,
            bg=self._config.overlay_bg_color,
            wrap=tk.WORD,
            padx=10,
            pady=5,
            insertbackground=self._config.overlay_fg_color,
            state=tk.DISABLED,
            cursor="arrow",
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(
            self._frame,
            command=self._text_widget.yview,
            bg=self._config.overlay_bg_color,
            troughcolor=self._config.overlay_bg_color,
        )
        self._text_widget.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text_widget.pack(fill=tk.BOTH, expand=True)

        self._text_widget.bind('<Button-1>', self._start_drag)
        self._text_widget.bind('<B1-Motion>', self._on_drag)

    def show_subtitle(self, text: str) -> None:
        """Thread-safe: display a new subtitle line"""
        with self._lock:
            self._subtitles.append((time.time(), text))
        if self._window:
            self._window.after(0, self._dispatch_display, text)

    def _dispatch_display(self, text: str) -> None:
        if self._display_mode == OverlayDisplayMode.SHORT:
            self._update_short_display()
        else:
            self._append_list_entry(text)

    def _update_short_display(self) -> None:
        if not self._label:
            return
        with self._lock:
            lines = [text for _, text in self._subtitles]
        display = "\n".join(lines) if lines else ""
        self._label.config(text=display)

    def _append_list_entry(self, text: str) -> None:
        if not self._text_widget:
            return
        self._text_widget.config(state=tk.NORMAL)
        ts = time.strftime("%H:%M:%S")
        self._text_widget.insert(tk.END, f"[{ts}] {text}\n")
        self._text_widget.see(tk.END)
        self._text_widget.config(state=tk.DISABLED)

    # --- Font size ---

    def _font_increase(self) -> None:
        self._set_font_size(self._font_size + 2)

    def _font_decrease(self) -> None:
        self._set_font_size(self._font_size - 2)

    def _set_font_size(self, size: int) -> None:
        size = max(self.FONT_SIZE_MIN, min(self.FONT_SIZE_MAX, size))
        if size == self._font_size:
            return
        self._font_size = size
        font = (self._config.font_family, self._font_size)
        if self._label:
            self._label.config(font=font)
        if self._text_widget:
            self._text_widget.config(font=font)

    def _on_scroll(self, event) -> None:
        if event.delta > 0:
            self._font_increase()
        elif event.delta < 0:
            self._font_decrease()

    # --- Mode switch ---

    def _switch_mode(self, mode: OverlayDisplayMode) -> None:
        if mode == self._display_mode:
            return
        self._display_mode = mode

        if self._window:
            geo = self._window.geometry()
            parts = geo.split('+')
            pos = f"+{parts[1]}+{parts[2]}" if len(parts) >= 3 else ""
            if mode == OverlayDisplayMode.LIST:
                height = max(240, self._config.overlay_height)
            else:
                height = self._config.overlay_height
            self._window.geometry(f"{self._config.overlay_width}x{height}{pos}")

        self._build_content()

        if mode == OverlayDisplayMode.SHORT:
            self._cleanup_loop()

    # --- Context menu ---

    def _show_context_menu(self, event) -> None:
        self._context_menu.post(event.x_root, event.y_root)

    # --- Always on top ---

    def _keep_topmost(self) -> None:
        if self._window:
            self._window.attributes('-topmost', True)
            self._window.lift()
            self._window.after(3000, self._keep_topmost)

    # --- Short mode cleanup ---

    def _cleanup_loop(self) -> None:
        if self._display_mode != OverlayDisplayMode.SHORT:
            return
        now = time.time()
        with self._lock:
            while (self._subtitles and
                   now - self._subtitles[0][0] > self._config.subtitle_display_seconds):
                self._subtitles.popleft()
        self._update_short_display()
        if self._window:
            self._window.after(500, self._cleanup_loop)

    # --- Drag ---

    def _start_drag(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event) -> None:
        if self._window:
            x = self._window.winfo_x() + event.x - self._drag_x
            y = self._window.winfo_y() + event.y - self._drag_y
            self._window.geometry(f"+{x}+{y}")

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None
