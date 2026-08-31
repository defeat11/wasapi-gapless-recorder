import threading
import wave
import time
from pathlib import Path
from typing import Callable, Optional
import pyaudiowpatch as pyaudio

class AudioCapture:
    """
    Captures system output audio (speaker audio) on Windows using PyAudioWPatch (WASAPI loopback)
    and saves it to gapless WAV segments of a specified length.
    """
    def __init__(
        self, 
        output_dir: Path, 
        segment_seconds: int = 300, 
        on_segment_ready: Callable[[Path], None] = None
    ):
        self.output_dir = Path(output_dir)
        self.segment_seconds = segment_seconds
        self.on_segment_ready = on_segment_ready
        
        self.state = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._p = None
        self._loopback_device = None
        
        # Locate the default WASAPI loopback device
        try:
            self._p = pyaudio.PyAudio()
            self._loopback_device = self._p.get_default_wasapi_loopback()
        except Exception as e:
            # Terminate PyAudio if initialized
            if self._p:
                try:
                    self._p.terminate()
                except Exception:
                    pass
            # Print and raise clear Arabic error if no device is found
            error_msg = (
                "خطأ: لم يتم العثور على جهاز صوت افتراضي (WASAPI loopback) صالح للتسجيل منه. "
                "يرجى التأكد من أن لديك سماعة أو جهاز إخراج صوت افتراضي مفعل في نظام ويندوز."
            )
            print(error_msg, flush=True)
            raise RuntimeError(error_msg) from e

    def start(self, state = None):
        """
        Starts the continuous recording in a background thread.
        Can optionally take a SharedState instance to update progress and status.
        """
        if state is not None:
            self.state = state
            
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Stops the recording safely, closes the current WAV file, and waits for the background thread.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _record_loop(self):
        channels = self._loopback_device.get("maxInputChannels", 2)
        if channels < 1:
            channels = 2
        rate = int(self._loopback_device.get("defaultSampleRate", 44100))
        sample_width = self._p.get_sample_size(pyaudio.paInt16)
        frame_size = channels * sample_width
        
        # Audio buffer size
        chunk_size = 1024
        
        try:
            stream = self._p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=self._loopback_device["index"],
                frames_per_buffer=chunk_size
            )
        except Exception as e:
            msg = f"خطأ عند فتح مجرى صوت النظام (WASAPI loopback): {e}"
            print(msg, flush=True)
            raise RuntimeError(msg) from e

        segment_index = 1
        frames_per_segment = rate * self.segment_seconds
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        def get_wav_path(idx: int) -> Path:
            return self.output_dir / f"segment_{idx:04d}.wav"
            
        current_wav_path = get_wav_path(segment_index)
        
        # Initialize state for segment_0001
        if self.state is not None:
            self.state.set_current_segment(segment_index)
            self.state.set_status(segment_index, "recording")
            
        wf = wave.open(str(current_wav_path), "wb")
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        
        frames_written = 0
        start_time = time.time()
        last_state_update = time.time()
        
        try:
            while not self._stop_event.is_set():
                try:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                except IOError:
                    # Ignore input overflow errors
                    continue
                    
                if not data:
                    time.sleep(0.001)
                    continue
                    
                read_frames = len(data) // frame_size
                if read_frames == 0:
                    continue
                    
                if frames_written + read_frames >= frames_per_segment:
                    # Split chunk: complete current segment and start next segment
                    remaining_frames = frames_per_segment - frames_written
                    part1_bytes = remaining_frames * frame_size
                    part1 = data[:part1_bytes]
                    part2 = data[part1_bytes:]
                    
                    if part1:
                        wf.writeframes(part1)
                    wf.close()
                    
                    # Call segment ready callback
                    if self.on_segment_ready:
                        try:
                            self.on_segment_ready(current_wav_path)
                        except Exception as cb_err:
                            print(f"Error in on_segment_ready callback: {cb_err}", flush=True)
                            
                    # Update state and paths for new segment
                    segment_index += 1
                    current_wav_path = get_wav_path(segment_index)
                    
                    if self.state is not None:
                        self.state.set_current_segment(segment_index)
                        self.state.set_status(segment_index, "recording")
                        
                    # Open next WAV file
                    wf = wave.open(str(current_wav_path), "wb")
                    wf.setnchannels(channels)
                    wf.setsampwidth(sample_width)
                    wf.setframerate(rate)
                    
                    if part2:
                        wf.writeframes(part2)
                        frames_written = len(part2) // frame_size
                    else:
                        frames_written = 0
                else:
                    wf.writeframes(data)
                    frames_written += read_frames
                    
                # Update state periodically (every 0.1 seconds)
                now = time.time()
                if now - last_state_update >= 0.1:
                    elapsed = now - start_time
                    progress = frames_written / rate
                    if self.state is not None:
                        self.state.set_elapsed_seconds(elapsed)
                        self.state.set_segment_progress(progress)
                    last_state_update = now
                    
        finally:
            # Clean up stream
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
                
            # Close WAV file
            try:
                wf.close()
            except Exception:
                pass
                
            # Invoke callback for last segment if it has content
            if current_wav_path.exists() and current_wav_path.stat().st_size > 44:
                if self.on_segment_ready:
                    try:
                        self.on_segment_ready(current_wav_path)
                    except Exception as cb_err:
                        print(f"Error in on_segment_ready callback for final segment: {cb_err}", flush=True)
            else:
                # Delete empty WAV
                try:
                    if current_wav_path.exists():
                        current_wav_path.unlink()
                except Exception:
                    pass

    def __del__(self):
        if self._p:
            try:
                self._p.terminate()
            except Exception:
                pass
