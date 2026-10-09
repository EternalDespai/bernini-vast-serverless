"""Deterministic 16-fps long-video chunk planning.

Bernini's validated workflow runs at 16 fps. Long video cannot safely be
processed by simply increasing node 5 'length': memory scales with frames.
Use overlapping 4n+1-frame chunks, process sequentially, and drop the
overlap when stitching. This is a segmentation *plan*, not a quality claim.
"""
from dataclasses import dataclass
import math

FPS = 16
MAX_CHUNK_FRAMES = 81
MAX_VIDEO_SECONDS = 180  # explicit paid-compute safety cap


@dataclass(frozen=True)
class Chunk:
    index: int
    start_frame: int
    source_frames: int
    model_frames: int
    trim_first: int
    output_frames: int


def plan_chunks(total_frames: int, chunk_frames: int = MAX_CHUNK_FRAMES):
    if not isinstance(total_frames, int) or total_frames < 1:
        raise ValueError("Video has no frames")
    if total_frames > FPS * MAX_VIDEO_SECONDS:
        raise ValueError(f"Video exceeds {MAX_VIDEO_SECONDS}s safety cap")
    if chunk_frames < 17 or (chunk_frames - 1) % 4 != 0:
        raise ValueError("Chunk length must be 4n+1 and at least 17")
    chunks = []
    cursor = 0
    index = 0
    while cursor < total_frames:
        overlap = 1 if index else 0
        start = cursor - overlap
        count = min(chunk_frames, total_frames - start)
        # Pad the final short chunk to Bernini's 4n+1 frame shape.
        model_count = max(17, 1 + 4 * math.ceil((count - 1) / 4))
        chunks.append(Chunk(index, start, count, model_count,
                            overlap, count - overlap))
        cursor += count - overlap
        index += 1
    assert sum(c.output_frames for c in chunks) == total_frames
    return chunks
