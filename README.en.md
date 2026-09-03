# wasapi-gapless-recorder

[العربية](README.md)

**Input: Windows system audio ← Output: consecutive WAV segments with zero gaps between them.**

A recorder that captures what the speakers play (WASAPI loopback), not the microphone.
It splits the recording into fixed-length WAV files, and loses nothing at the transitions.
Measured on this machine: 334,848 audio frames in a row across 4 files.
The waveform jumps only 43 units at the file boundary. The theoretical
per-sample ceiling is 692 units. So the wave is continuous.

## The problem

One long lecture in one file gives you a huge blob.
You cannot process any part of it while the recording runs.
The simple split closes and reopens the device for each segment.
That drops frames at every boundary.
The result is clipped words at the start of every new file.

## How it works

| File | Lines | Role |
|---|---|---|
| `audio_capture.py` | 219 | Capture thread, and buffer splitting at boundaries |
| `shared_state.py` | 111 | Thread-safe shared state (13 locked sections) |
| `ui.py` | 506 | Live Tkinter dashboard, refreshes every 500 ms |
| `main.py` | 230 | Wiring, and safe handling of the optional transcriber |

The capture mechanism, in numbers:

1. The app opens the WASAPI loopback stream once for the whole session.
2. Each read pulls 1024 frames (about 21 ms at 48000 Hz).
3. The segment limit in frames = sample rate × segment length (48000 × 300 = 14,400,000).
4. The recording state updates every 0.1 s. The UI reads it every 500 ms.
5. On stop, the app checks the last partial segment. It keeps the segment if it is bigger than the 44-byte WAV header.

## The key design decision

**The problem:** the segment boundary usually lands in the middle of a read buffer.
It rarely lands at the end of one.

**The decision:** the split happens in the write layer, not the capture layer.
When a 1024-frame buffer crosses the segment limit, the writer cuts it byte-exact.
Part one fills the current file and closes it. Part two opens the next file at once.
One frame = channel count × 2 bytes. So the math works in bytes, not in rounded time.

**The cost:** careful manual boundary arithmetic instead of a ready-made splitter.
**The return:** zero lost frames. The app never closes or reopens the stream between segments.

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

The sine wave continues across the two files as if they were one file.

## Running it

Windows only (WASAPI is Windows-specific).

```bash
pip install -r requirements.txt
python main.py --segment-seconds 300 --output-dir ./output
```

To stop, close the window or press `Ctrl+C`. The app saves the last partial segment.
Transcription is optional. Without `transcriber.py`, the recording still works.

## Why I built it

I record long lectures from the system audio.
I need them as segments I can process right away.
A simple split loses frames at every boundary.
This design lost 0 frames out of a measured 334,848.
