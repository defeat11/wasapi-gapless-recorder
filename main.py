import argparse
import sys
import threading
from pathlib import Path
import inspect

from shared_state import SharedState
from audio_capture import AudioCapture
from ui import run_dashboard

# Transcription is an optional add-on. The recorder core works without it.
try:
    from transcriber import Transcriber
except ImportError:
    Transcriber = None

# --- Monkeypatching SharedState for robust UI and component integration ---

# Save original methods
orig_set_status = SharedState.set_status
orig_get_status = SharedState.get_status
orig_current_segment_getter = SharedState.current_segment.fget

def normalized_segment_key(segment) -> str:
    """Normalizes all segment keys to string format 'segment_XXXX' for consistent indexing."""
    if isinstance(segment, int):
        return f"segment_{segment:04d}"
    s = str(segment)
    if not s.startswith("segment_"):
        if s.isdigit():
            return f"segment_{int(s):04d}"
    return s

def custom_set_status(self, segment, status):
    norm_key = normalized_segment_key(segment)
    with self._lock:
        self._statuses[norm_key] = status

def custom_get_status(self, segment):
    norm_key = normalized_segment_key(segment)
    with self._lock:
        return self._statuses.get(norm_key)

def custom_current_segment_setter(self, value):
    norm_key = normalized_segment_key(value)
    with self._lock:
        self._current_segment = norm_key

# Patch methods and properties on SharedState
SharedState.set_status = custom_set_status
SharedState.get_status = custom_get_status
SharedState.current_segment = property(orig_current_segment_getter, custom_current_segment_setter)

# Fix segment_seconds property setter and getter (due to bug in original shared_state.py)
def get_segment_seconds(self):
    with self._lock:
        return self._segment_seconds

def set_segment_seconds(self, value):
    with self._lock:
        self._segment_seconds = value

SharedState.segment_seconds = property(get_segment_seconds, set_segment_seconds)

# Fix latest_key_points property setter and getter (due to decorator/setter bug in original shared_state.py)
def get_latest_key_points(self):
    with self._lock:
        return self._latest_key_points

def set_latest_key_points(self, value):
    with self._lock:
        self._latest_key_points = value

SharedState.latest_key_points = property(get_latest_key_points, set_latest_key_points)

# Map extra properties expected by ui.py to their corresponding SharedState properties
SharedState.elapsed_time = property(lambda self: self.elapsed_seconds)
SharedState.current_segment_progress = property(lambda self: self.segment_progress)
SharedState.status = property(lambda self: self.statuses)

def main():
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description="مسجل المحاضرات الذكي - Smart Lecture Recorder")
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=300,
        help="مدة المقطع الواحد بالثواني (الافتراضي 300)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="مجلد المخرجات لحفظ الملفات الصوتية والتفريغات (الافتراضي ./output)"
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(Path(__file__).resolve().parent),
        help="المجلد الرئيسي للمشروع (الافتراضي مجلد السكربت نفسه)"
    )
    
    args = parser.parse_args()
    
    # Resolve absolute paths
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    audio_dir = output_dir / "audio"
    transcripts_dir = output_dir / "transcripts"
    
    # 2. Initialize directories
    audio_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    
    # 3. Instantiate SharedState
    state = SharedState()
    state.segment_seconds = args.segment_seconds
    
    # Set up stop event for coordination
    stop_event = threading.Event()
    # Support both state.stop_event and local stop_event for flexibility
    if not hasattr(state, "stop_event"):
        state.stop_event = stop_event
    
    # 4. Instantiate Transcriber if available (optional feature)
    transcriber = None
    if Transcriber is not None:
        transcriber_sig = inspect.signature(Transcriber.__init__)
        transcriber_kwargs = {
            "project_root": project_root,
            "transcripts_dir": transcripts_dir,
        }

        # Check if Transcriber accepts 'state' or 'shared_state'
        if "state" in transcriber_sig.parameters:
            transcriber_kwargs["state"] = state
        elif "shared_state" in transcriber_sig.parameters:
            transcriber_kwargs["shared_state"] = state

        transcriber = Transcriber(**transcriber_kwargs)

        # Just in case Transcriber expects state as an attribute instead of a constructor arg
        if not hasattr(transcriber, "state"):
            transcriber.state = state
        if not hasattr(transcriber, "shared_state"):
            transcriber.shared_state = state
    else:
        print("التفريغ النصي غير مفعّل (لا توجد وحدة transcriber). التسجيل يعمل بشكل طبيعي.")

    # When there is no transcriber, mark each finished segment as done directly
    if transcriber is not None:
        on_segment_ready = transcriber.enqueue
    else:
        def on_segment_ready(wav_path):
            state.set_status(Path(wav_path).stem, "done")

    # 5. Instantiate AudioCapture
    audio_capture = AudioCapture(
        output_dir=audio_dir,
        segment_seconds=args.segment_seconds,
        on_segment_ready=on_segment_ready
    )
    
    # 6. Start AudioCapture (and Transcriber if it has a start method)
    if hasattr(transcriber, "start") and callable(getattr(transcriber, "start")):
        transcriber.start()
        
    audio_capture.start(state=state)
    
    # 7. Wire run_dashboard kwargs dynamically
    run_dash_sig = inspect.signature(run_dashboard)
    run_dash_kwargs = {"state": state}
    if "stop_event" in run_dash_sig.parameters:
        run_dash_kwargs["stop_event"] = stop_event
    elif "event" in run_dash_sig.parameters:
        run_dash_kwargs["event"] = stop_event

    try:
        # Run dashboard in the main thread (blocking)
        run_dashboard(**run_dash_kwargs)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] تم كشف طلب إيقاف التسجيل...")
    finally:
        # Signal stop
        stop_event.set()
        if hasattr(state, "stop_event") and hasattr(state.stop_event, "set"):
            state.stop_event.set()
        
        # Stop AudioCapture
        # "أوقف AudioCapture (سيُنهي المقطع الأخير حتى لو جزئياً ويستدعي on_segment_ready له)"
        print("جاري إيقاف التقاط الصوت وحفظ المقطع الأخير...")
        audio_capture.stop()
        
        # Stop Transcriber (only when the optional feature is active)
        if transcriber is not None:
            print("جاري إنهاء تفريغ آخر المقاطع...")

            # Call stop with a default timeout if it takes a timeout parameter
            transcriber_stop_sig = inspect.signature(transcriber.stop)
            if "timeout" in transcriber_stop_sig.parameters:
                transcriber.stop(timeout=600)
            else:
                transcriber.stop()
            
        # Print final summary
        # "ثم اطبع ملخصاً نهائياً بعدد المقاطع الكلي ومسار lecture_full.md، واخرج بأدب."
        lecture_full_path = transcripts_dir / "lecture_full.md"
        
        # Attempt to determine total segments from SharedState
        total_segments = 0
        if hasattr(state, "status") and state.status:
            total_segments = len(state.status)
        elif hasattr(state, "get_status_dict") and callable(state.get_status_dict):
            try:
                total_segments = len(state.get_status_dict())
            except Exception:
                pass
                
        print("\n==========================================")
        print("🎙️ ملخص التسجيل النهائي")
        print("==========================================")
        print(f"• عدد المقاطع الصوتية الكلي: {total_segments}")
        if transcriber is not None:
            print(f"• ملف التفريغ والملخص المجمع: {lecture_full_path.resolve()}")
        print(f"• مجلد المقاطع الصوتية: {audio_dir.resolve()}")
        print("• تم حفظ جميع البيانات وإغلاق البرنامج بنجاح.")
        print("==========================================\n")
        
if __name__ == "__main__":
    main()
