"""Inspect MP4 duration and derive the Bernini 16fps frame budget."""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

FPS = 16
MAX_SECONDS = 600


def ffprobe_path():
    candidates = [os.environ.get('BERNINI_FFPROBE', ''), shutil.which('ffprobe')]
    for item in candidates:
        if item and Path(item).is_file():
            return str(item)
    raise ValueError('Не найден ffprobe.exe. Установи FFmpeg (включая ffprobe) и добавь его bin в PATH либо укажи BERNINI_FFPROBE.')


def inspect_video(path):
    try:
        result = subprocess.run([
            ffprobe_path(), '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'format=duration:stream=width,height',
            '-of', 'json', str(path)], capture_output=True, text=True,
            timeout=45, check=True)
        info = json.loads(result.stdout)
        streams = info.get('streams', [])
        duration = float(info.get('format', {}).get('duration', 0))
        if not streams or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Не удалось определить длительность видео')
        if duration > MAX_SECONDS:
            raise ValueError(f'Видео длится {duration:.1f} сек. Текущий защитный лимит — {MAX_SECONDS} сек (10 минут).')
        # Estimated before ffmpeg normalization. The worker counts the exact
        # resulting frames and adjusts its final chunk, never silently truncates.
        frames = max(1, math.ceil(duration * FPS))
        return {'duration_seconds': round(duration, 3), 'fps_target': FPS,
                'estimated_frames': frames, 'width': streams[0].get('width'),
                'height': streams[0].get('height')}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        raise ValueError('Не удалось прочитать MP4 через ffprobe: ' + type(exc).__name__) from exc
