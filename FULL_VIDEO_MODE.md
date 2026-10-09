# Full-length Bernini video mode (experimental, requires GPU validation)

## Why the old UI could cut videos

The previous UI let users select 17/33/49/81/161 frames and wrote that
number to BerniniStudio node 5 `length` and VHS_LoadVideo node 21
`frame_load_cap`. Selecting 17 would process only about 1 second at the
workflow's 16 fps even when the MP4 was much longer. Simply increasing
`length` for long clips risks GPU out-of-memory.

## New approach

- Windows UI v4 uses `ffprobe` to detect the source duration automatically.
  There is no manual frame-count dropdown.
- `r2_bridge.py` defaults to `BERNINI_FULL_VIDEO=1` and delegates to
  `long_video_runner.py`. Both `ffmpeg` and `ffprobe` are required on GPU.
- Normalize the **whole** source to 16 fps, count actual decoded frames,
  plan chunks of up to 81 frames with a one-frame overlap, and pad the last
  chunk to a valid Bernini `4n+1` model length.
- Generate chunks sequentially, remove duplicated overlap frames and final
  padding, join the MP4s, and restore the source audio track.
- Count frames again after stitching and after audio muxing. If the final
  output has fewer/more frames, fail the job instead of silently uploading
  a truncated result.
- R2 `status.json` reports `chunk_index`/`chunk_total` plus the current
  sampling-step percentage. Sampling percent is not whole-video percent.
- 10-minute explicit limit (9,600 output frames). This is a **safety cap**,
  not a performance or quality guarantee. Such jobs could cost substantial
  GPU time and may time out.

## Verification status

**Local no-GPU checks performed:** Windows UI v4 parsed a real 6.2-second MP4,
computed ~100 frames at 16fps and generated a per-chunk 81-frame workflow
template; FFmpeg normalization actually yielded 99 frames. Local FFmpeg
extraction, overlap removal, concat and audio mux produced a 99-frame MP4,
matching the normalized source. A separate FFmpeg test showed
`tpad=stop_mode=clone:stop=32` is required to pad the last partial chunk.

**Not verified:** actual Bernini model output for long chunks, memory pressure,
cross-chunk face/identity consistency, audio/video sync on variable-frame-rate
videos, ComfyUI progress events and Vast Serverless integration. An H100 test
of a 6-12-second clip is required before calling this production-ready.
Chunk seams can produce visible changes; no temporal coherence mechanism
between independent chunks is implemented.

**Cost warning:** 30 seconds at 16 fps requires about 6 sequential chunks;
10 minutes can require about 120. Long videos can be slow and expensive.
No price or throughput is guaranteed. A full video is processed at **16 fps**,
not necessarily its original frame rate, and the final duration may differ by
up to approximately one frame interval.

## Run checks

```bash
python -m unittest test_video_chunks.py -v
python -m unittest discover -p 'test_*.py' -v
```

GPU runtime additionally needs `ffmpeg` and `ffprobe` on PATH.
