import time
import threading
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Dict, Any, Optional
from pathlib import Path

if TYPE_CHECKING:
    try:
        from shared_state import SharedState
    except ImportError:
        pass


def clean_segment_key(key: Any) -> str:
    """
    Cleans segment key strings (e.g. 'segment_0001.wav' -> '0001') for cleaner display.
    If the key is numeric, formats it as a zero-padded string.
    """
    s = str(key)
    if s.startswith("segment_"):
        s = s[len("segment_"):]
    if s.endswith(".wav"):
        s = s[:-4]
    try:
        val = int(s)
        return f"{val:04d}"
    except ValueError:
        return s


def get_sorted_segments(status_dict: Dict[Any, str]) -> list:
    """
    Sorts segment keys numerically if possible, otherwise alphabetically.
    """
    try:
        def sort_key(k):
            s = str(k)
            digits = ''.join(c for c in s if c.isdigit())
            return int(digits) if digits else s
        return sorted(status_dict.keys(), key=sort_key)
    except Exception:
        return sorted(status_dict.keys(), key=str)


def extract_last_two_key_points(text: str) -> str:
    """
    Extracts the last two lines of the 'key points' section from the transcription summary text.
    """
    if not text:
        return ""
    
    # Try to isolate the text after "النقاط الرئيسية:" header if present
    if "النقاط الرئيسية:" in text:
        parts = text.split("النقاط الرئيسية:", 1)
        text = parts[1]
    elif "النقاط الرئيسية" in text:
        parts = text.split("النقاط الرئيسية", 1)
        text = parts[1]
        
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    
    # Select the last 2 lines
    last_two = lines[-2:] if len(lines) >= 2 else lines
    return "\n".join(last_two)


def get_latest_key_points_from_disk() -> str:
    """
    Self-healing fallback to read key points directly from output transcripts on disk,
    in case SharedState's properties are not updated or are empty due to external bugs.
    """
    candidates = [
        Path("./output/transcripts"),
        Path(__file__).resolve().parent / "output" / "transcripts"
    ]
    for path in candidates:
        if path.exists() and path.is_dir():
            txt_files = list(path.glob("segment_*.txt"))
            # Filter out error files
            txt_files = [f for f in txt_files if not f.name.endswith("_ERROR.txt")]
            if txt_files:
                txt_files.sort(key=lambda p: p.name)
                latest_file = txt_files[-1]
                try:
                    with open(latest_file, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
    return ""


def run_dashboard(state: "SharedState", stop_event: Optional[threading.Event] = None) -> None:
    """
    Main function to run the live dashboard in a Tkinter GUI.
    Updates every 500ms showing recording progress, segment statuses, and key points.
    
    Args:
        state: SharedState object containing status dict, elapsed time, current segment, etc.
        stop_event: Optional threading.Event to signal shutdown.
    """
    # Use the passed stop_event or fall back to the one attached to the state
    if stop_event is None:
        stop_event = getattr(state, "stop_event", None)
    if not isinstance(stop_event, threading.Event):
        stop_event = threading.Event()

    # Create root window
    root = tk.Tk()
    root.title("🎙️ مسجل المحاضرات الذكي")
    root.geometry("700x550")
    root.configure(bg="#1e1e2e")
    
    # Primary font settings (fallback to Tahoma if Segoe UI isn't loaded)
    main_font = ("Segoe UI", 12)
    heading_font = ("Segoe UI", 12, "bold")
    title_font = ("Segoe UI", 16, "bold")
    
    # Root container
    main_frame = tk.Frame(root, bg="#1e1e2e", padx=15, pady=15)
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 1. Header Frame (Title + Elapsed Time)
    header_frame = tk.Frame(main_frame, bg="#252538", bd=1, relief="flat", padx=15, pady=10)
    header_frame.pack(fill=tk.X, pady=(0, 10))
    
    title_label = tk.Label(
        header_frame,
        text="🎙️ مسجل المحاضرات الذكي",
        font=title_font,
        fg="#89b4fa",
        bg="#252538"
    )
    title_label.pack(anchor="center")
    
    time_label = tk.Label(
        header_frame,
        text="الوقت المنقضي الكلي: 00:00:00",
        font=heading_font,
        fg="#a6e3a1",
        bg="#252538"
    )
    time_label.pack(anchor="center", pady=(5, 0))

    # 2. Progress Frame (Current segment info + progressbar side by side)
    progress_frame = tk.Frame(main_frame, bg="#252538", bd=1, relief="flat", padx=15, pady=12)
    progress_frame.pack(fill=tk.X, pady=(0, 10))
    
    # Configure columns for progress frame (column 0 = text, column 1 = progressbar)
    progress_frame.columnconfigure(0, weight=1)
    progress_frame.columnconfigure(1, weight=1)
    
    progress_label = tk.Label(
        progress_frame,
        text="المقطع الحالي: - | الوقت: 0.0 ثانية / 300 ثانية (0.0%)",
        font=main_font,
        fg="#cdd6f4",
        bg="#252538",
        anchor="w",
        justify="left"
    )
    progress_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
    
    # Setup ttk style for Progressbar
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure(
        "Custom.Horizontal.TProgressbar",
        troughcolor="#313244",
        background="#89b4fa",
        thickness=16,
        borderwidth=0
    )
    
    progress_bar = ttk.Progressbar(
        progress_frame,
        orient="horizontal",
        mode="determinate",
        style="Custom.Horizontal.TProgressbar"
    )
    progress_bar.grid(row=0, column=1, sticky="ew")

    # 3. Table Frame (Treeview)
    table_frame = tk.Frame(main_frame, bg="#252538", bd=1, relief="flat", padx=15, pady=10)
    table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    
    table_title = tk.Label(
        table_frame,
        text="📋 جدول حالة المقاطع",
        font=heading_font,
        fg="#f9e2af",
        bg="#252538"
    )
    table_title.pack(anchor="w", pady=(0, 5))
    
    tree_container = tk.Frame(table_frame, bg="#252538")
    tree_container.pack(fill=tk.BOTH, expand=True)
    
    # Customize Treeview style
    style.configure(
        "Treeview",
        background="#252538",
        foreground="#cdd6f4",
        fieldbackground="#252538",
        rowheight=28,
        font=main_font
    )
    style.configure(
        "Treeview.Heading",
        background="#313244",
        foreground="#cdd6f4",
        font=heading_font
    )
    style.map("Treeview.Heading", background=[('active', '#45475A')])
    
    # Treeview tag background color compatibility fix
    try:
        def fixed_map(option):
            return [elm for elm in style.map("Treeview", query_opt=option)
                    if elm[:2] != ("!disabled", "!selected")]
        style.map("Treeview", foreground=fixed_map("foreground"), background=fixed_map("background"))
    except Exception:
        pass
        
    tree = ttk.Treeview(tree_container, columns=("segment", "status"), show="headings")
    tree.heading("segment", text="رقم المقطع", anchor="center")
    tree.heading("status", text="الحالة", anchor="center")
    
    tree.column("segment", anchor="center", width=250)
    tree.column("status", anchor="center", width=250)
    
    scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Table tag configurations (Yellow = recording/transcribing, Green = done, Red = error, Gray = queued)
    tree.tag_configure("yellow", foreground="#f9e2af", background="#252538")
    tree.tag_configure("green", foreground="#a6e3a1", background="#252538")
    tree.tag_configure("red", foreground="#f38ba8", background="#252538")
    tree.tag_configure("gray", foreground="#7f849c", background="#252538")
    tree.tag_configure("white", foreground="#cdd6f4", background="#252538")

    # 4. Key Points Frame (Text widget)
    preview_frame = tk.Frame(main_frame, bg="#252538", bd=1, relief="flat", padx=15, pady=10)
    preview_frame.pack(fill=tk.X)
    
    preview_title = tk.Label(
        preview_frame,
        text="📝 معاينة النقاط الرئيسية (آخر سطرين)",
        font=heading_font,
        fg="#f5c2e7",
        bg="#252538"
    )
    preview_title.pack(anchor="w", pady=(0, 5))
    
    text_preview = tk.Text(
        preview_frame,
        height=3,
        bg="#181825",
        fg="#cdd6f4",
        insertbackground="#cdd6f4",
        font=main_font,
        relief="flat",
        wrap=tk.WORD,
        padx=10,
        pady=8,
        highlightthickness=1,
        highlightbackground="#313244",
        highlightcolor="#89b4fa"
    )
    text_preview.pack(fill=tk.X)
    text_preview.insert("1.0", "في انتظار تفريغ أول مقطع وعرض النقاط الرئيسية...")
    text_preview.config(state=tk.DISABLED)

    # Set up UI update loop state
    ui_start_time = time.time()
    last_statuses = {}
    last_preview_content = ""
    
    def update_loop():
        nonlocal last_statuses, last_preview_content
        
        # 8. Check external stop_event
        if stop_event.is_set():
            root.destroy()
            return
            
        try:
            # 1. Total Elapsed Time
            elapsed = 0.0
            if hasattr(state, "elapsed_seconds"):
                elapsed = state.elapsed_seconds
            elif hasattr(state, "get_elapsed_seconds"):
                elapsed = state.get_elapsed_seconds()
            elif hasattr(state, "elapsed_time"):
                elapsed = state.elapsed_time
                
            # If state elapsed time is zero/not updating, fall back to UI local elapsed time
            if not elapsed or elapsed == 0.0:
                elapsed = time.time() - ui_start_time
                
            if isinstance(elapsed, (int, float)):
                hours = int(elapsed) // 3600
                minutes = (int(elapsed) % 3600) // 60
                secs = int(elapsed) % 60
                elapsed_str = f"{hours:02d}:{minutes:02d}:{secs:02d}"
            else:
                elapsed_str = str(elapsed)
                
            time_label.config(text=f"الوقت المنقضي الكلي: {elapsed_str}")
            
            # 2. Current Segment Progress Bar
            segment_seconds = 300
            if hasattr(state, "segment_seconds"):
                segment_seconds = state.segment_seconds
            if not segment_seconds:
                segment_seconds = 300
                
            curr_progress = 0.0
            if hasattr(state, "segment_progress"):
                curr_progress = state.segment_progress
            elif hasattr(state, "get_segment_progress"):
                curr_progress = state.get_segment_progress()
            elif hasattr(state, "current_segment_progress"):
                curr_progress = state.current_segment_progress
                
            # If segment_progress is not updating, fallback to calculating modulo segment_seconds
            if not curr_progress or curr_progress == 0.0:
                if isinstance(elapsed, (int, float)):
                    curr_progress = elapsed % segment_seconds
            
            curr_progress = max(0.0, min(float(curr_progress), float(segment_seconds)))
            
            curr_seg = "-"
            if hasattr(state, "current_segment"):
                curr_seg = state.current_segment
            elif hasattr(state, "get_current_segment"):
                curr_seg = state.get_current_segment()
                
            cleaned_curr_seg = clean_segment_key(curr_seg)
            pct = (curr_progress / segment_seconds) * 100 if segment_seconds else 0.0
            
            progress_label.config(
                text=f"المقطع الحالي: {cleaned_curr_seg} | الوقت: {curr_progress:.1f}ث / {segment_seconds}ث ({pct:.1f}%)"
            )
            progress_bar.config(maximum=segment_seconds, value=curr_progress)
            
            # 3. Status Table
            statuses = {}
            if hasattr(state, "statuses"):
                statuses = state.statuses
            elif hasattr(state, "status"):
                statuses = state.status
            elif hasattr(state, "get_all_statuses"):
                statuses = state.get_all_statuses()
                
            lock = getattr(state, "lock", None)
            if not lock:
                lock = getattr(state, "_lock", None)
                
            if lock:
                with lock:
                    statuses_copy = dict(statuses) if statuses else {}
            else:
                statuses_copy = dict(statuses) if statuses else {}
                
            # Update only when status dictionary changes to prevent Treeview blinking
            if statuses_copy != last_statuses:
                # Clear all elements
                for item in tree.get_children():
                    tree.delete(item)
                    
                sorted_keys = get_sorted_segments(statuses_copy)
                for key in sorted_keys:
                    val = statuses_copy[key]
                    cleaned_key = clean_segment_key(key)
                    
                    s = str(val).strip()
                    tag = "white"
                    # أصفر=تسجيل/جارٍ التفريغ، أخضر=تم، أحمر=خطأ، رمادي=بالطابور
                    if s in ("تسجيل", "جارٍ التفريغ", "جاري التفريغ", "جاري", "recording", "transcribing", "processing"):
                        tag = "yellow"
                    elif s in ("تم", "done", "completed"):
                        tag = "green"
                    elif s in ("خطأ", "error", "failed"):
                        tag = "red"
                    elif s in ("بالطابور", "queued", "queue"):
                        tag = "gray"
                        
                    tree.insert("", "end", values=(cleaned_key, val), tags=(tag,))
                last_statuses = statuses_copy.copy()
                
            # 4. Key Points Preview
            key_points = ""
            if hasattr(state, "latest_key_points"):
                key_points = state.latest_key_points
            elif hasattr(state, "get_latest_key_points"):
                key_points = state.get_latest_key_points()
            elif hasattr(state, "key_points"):
                key_points = state.key_points
                
            if not key_points or len(key_points.strip()) == 0:
                try:
                    key_points = get_latest_key_points_from_disk()
                except Exception:
                    pass
                    
            preview_content = extract_last_two_key_points(key_points)
            if not preview_content:
                preview_content = "في انتظار تفريغ أول مقطع وعرض النقاط الرئيسية..."
                
            if preview_content != last_preview_content:
                text_preview.config(state=tk.NORMAL)
                text_preview.delete("1.0", tk.END)
                text_preview.insert("1.0", preview_content)
                text_preview.config(state=tk.DISABLED)
                last_preview_content = preview_content
                
        except Exception as e:
            print(f"Error in UI update loop: {e}")
            
        # Re-schedule update in 500ms
        root.after(500, update_loop)

    # 7. Window close handler
    def on_close():
        stop_event.set()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_close)
    
    # Start the periodic update loop and Tkinter main loop
    root.after(500, update_loop)
    root.mainloop()


if __name__ == "__main__":
    # Mock class to simulate SharedState when running ui.py directly
    class MockSharedState:
        def __init__(self):
            self.elapsed_time = 0.0
            self.segment_seconds = 15
            self.current_segment = "segment_0003"
            self.current_segment_progress = 0.0
            self.status = {
                "segment_0001": "تم",
                "segment_0002": "بالطابور",
                "segment_0003": "تسجيل"
            }
            self.latest_key_points = "النقاط الرئيسية:\n- تم بدء التسجيل وتجهيز الميكروفون الافتراضي\n- جاري العمل على استخراج التفريغ النصي للمقطع الأول\n- جاري كتابة ملف lecture_full.md"
            self.stop_event = threading.Event()
            self.lock = threading.Lock()

    print("Starting mock GUI dashboard simulation... Close the window or press Ctrl+C in simulation to stop.")
    mock_state = MockSharedState()
    
    # Thread to simulate updates to the state
    def simulate_state_updates():
        try:
            while not mock_state.stop_event.is_set():
                time.sleep(0.5)
                with mock_state.lock:
                    mock_state.elapsed_time += 0.5
                    mock_state.current_segment_progress += 0.5
                    
                    # Cycle segment after segment_seconds
                    if mock_state.current_segment_progress >= mock_state.segment_seconds:
                        prev_seg = mock_state.current_segment
                        mock_state.status[prev_seg] = "تم"
                        
                        seg_num = int(prev_seg.split("_")[1]) + 1
                        new_seg = f"segment_{seg_num:04d}"
                        mock_state.current_segment = new_seg
                        mock_state.current_segment_progress = 0.0
                        mock_state.status[new_seg] = "تسجيل"
                        
                        queued_segs = [k for k, v in mock_state.status.items() if v == "بالطابور"]
                        if queued_segs:
                            mock_state.status[queued_segs[0]] = "تم"
                        
                        mock_state.status[prev_seg] = "جارٍ التفريغ"
                        
                        mock_state.latest_key_points = (
                            f"النقاط الرئيسية:\n"
                            f"- تم تفريغ المقطع {prev_seg} بنجاح\n"
                            f"- هذا سطر ملخص افتراضي للمقطع {prev_seg}\n"
                            f"- تم حفظ الملف lecture_full.md وتحديث القائمة"
                        )
                    
                    for k, v in list(mock_state.status.items()):
                        if v == "جارٍ التفريغ" and mock_state.current_segment_progress > 5.0:
                            mock_state.status[k] = "تم"
        except Exception:
            pass

    t = threading.Thread(target=simulate_state_updates, daemon=True)
    t.start()
    
    try:
        run_dashboard(mock_state)
    except KeyboardInterrupt:
        print("\nStopping simulation.")
        mock_state.stop_event.set()
