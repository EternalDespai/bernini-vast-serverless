"""Exercise continuous full-video FFmpeg pipeline with GPU inference mocked."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from long_video_runner import command, frame_count, process_full_video


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class FullVideoPipelineTest(unittest.TestCase):
    def test_single_pass_preserves_frames_and_audio(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs, outputs = root / 'input', root / 'output'
            inputs.mkdir()
            outputs.mkdir()
            original = root / 'source.mp4'
            command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                     'testsrc2=size=64x64:rate=16:duration=14', '-f', 'lavfi', '-i',
                     'sine=frequency=440:duration=14', '-c:v', 'libx264', '-c:a', 'aac', str(original)])
            workflow = json.loads(Path('ui_v6/workflow_api_external_reference.json').read_text())
            graphs = []
            def post(session, base, path, payload):
                graph = payload['prompt']
                graphs.append(graph)
                name = graph['22']['inputs']['filename_prefix'] + '.mp4'
                shutil.copyfile(inputs / graph['21']['inputs']['video'], outputs / name)
                return {'prompt_id': name}
            def result(session, base, prompt_id, timeout):
                return {'outputs': {'22': {'gifs': [{'filename': prompt_id, 'type': 'output'}]}}}
            with patch('r2_bridge.post_json', side_effect=post), patch('r2_bridge.wait_for_result', side_effect=result), patch('long_video_runner.start_progress_watcher', return_value=Mock()):
                temporary, final, frames, chunks = process_full_video(original, 'ref.jpg', workflow, inputs.resolve(), outputs.resolve(), 'http://127.0.0.1:1', 'a'*32, 60, Mock())
                try:
                    self.assertEqual((frames, chunks, frame_count(final)), (224, 1, 224))
                    streams = json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(final)]))['streams']
                    self.assertIn('audio', [s['codec_type'] for s in streams])
                    self.assertEqual([g['5']['inputs']['length'] for g in graphs], [225])
                finally:
                    temporary.cleanup()
