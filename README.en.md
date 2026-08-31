# wasapi-gapless-recorder

[العربية](README.md)

**Input: Windows system audio ← Output: consecutive WAV segments with zero gaps between them.**

A recorder that captures what the speakers play (WASAPI loopback), not the microphone.
It splits the recording into fixed-length WAV files with no loss at the transitions.
Measured on this machine: 334,848 consecutive audio frames across 4 files,
with a waveform jump of only 43 units at the file boundary against a theoretical
per-sample ceiling of 692 — the wave is continuous.

## The problem

Recording a long lecture into one file produces a huge blob you cannot process mid-session.
The naive split — closing and reopening the device for each segment — drops frames at every boundary.
The result is clipped words at the start of every new file.

## How it works

| File | Lines | Role |
|---|---|---|
| `audio_capture.py` | 219 | Capture thread and buffer splitting at boundaries |
| `shared_state.py` | 111 | Thread-safe shared state (13 locked sections) |
| `ui.py` | 506 | Live Tkinter dashboard refreshing every 500 ms |
| `main.py` | 230 | Wiring, plus graceful handling of the optional transcriber |

The capture mechanism, in numbers:

1. The WASAPI loopback stream is opened exactly once for the whole session.
2. Each read pulls 1024 frames (about 21 ms at 48000 Hz).
3. The segment limit in frames = sample rate × segment length (48000 × 300 = 14,400,000).
4. Recording state updates every 0.1 s; the UI polls it every 500 ms.
5. On stop, the final partial segment is kept if it exceeds the 44-byte WAV header.

## The key design decision

**The problem:** the segment boundary usually lands in the middle of a read buffer, not at its end.

**The decision:** splitting happens in the write layer, not the capture layer.
When a 1024-frame buffer crosses the segment limit, it is split byte-exact:
part one completes and closes the current file, part two opens the next file immediately.
One frame = channel count × 2 bytes, so the math is in bytes, not rounded time.

**The cost:** careful manual boundary arithmetic instead of an off-the-shelf splitter.
**The return:** zero lost frames, and the stream is never closed or reopened between segments.

## Measured proof it works

A real recording of a 440 Hz tone, two-second segments, on this machine:

```
segment_0001.wav: frames=96000 rate=48000 ch=2 dur=2.0000s
segment_0002.wav: frames=96000 rate=48000 ch=2 dur=2.0000s
segment_0003.wav: frames=96000 rate=48000 ch=2 dur=2.0000s
segment_0004.wav: frames=46848 rate=48000 ch=2 dur=0.9760s
TOTAL frames=334848 = 6.9760s continuous audio
gapless boundary check (every full segment == rate*2 frames): True
```

And the waveform continuity check across the first file boundary:

```
last 8 L-samples of seg1: (..., -2614, -2588, -2555)
first 8 L-samples of seg2: (-2512, -2461, -2401, ...)
delta ACROSS the file boundary: 43
theoretical max per-sample delta for 440Hz sine: 692
```

The sine wave continues across the two files as if they were one.

## Running it

Windows only (WASAPI is Windows-specific).

```bash
pip install -r requirements.txt
python main.py --segment-seconds 300 --output-dir ./output
```

Stop by closing the window or pressing `Ctrl+C`; the last partial segment is saved automatically.
Transcription is optional: without `transcriber.py`, recording works normally.

## Why I built it

I need long lectures captured from system audio as segments ready for immediate processing.
Naive splitting loses frames at every boundary; this design lost 0 frames across a measured 334,848.
