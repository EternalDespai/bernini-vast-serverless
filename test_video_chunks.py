"""No-GPU regression tests for complete-video chunk accounting."""
import unittest

from video_chunks import FPS, MAX_VIDEO_SECONDS, plan_chunks


class ChunkPlanTests(unittest.TestCase):
    def test_no_truncation_for_variable_lengths(self):
        for total in (1, 16, 17, 33, 49, 80, 81, 82, 83, 100, 161,
                      162, 257, 1000, 9600):
            with self.subTest(total=total):
                chunks = plan_chunks(total)
                self.assertEqual(sum(c.output_frames for c in chunks), total)
                self.assertEqual(chunks[0].start_frame, 0)
                self.assertTrue(all(c.model_frames <= 81 for c in chunks))
                self.assertTrue(all((c.model_frames - 1) % 4 == 0 for c in chunks))
                for c in chunks:
                    self.assertGreaterEqual(c.model_frames, c.source_frames)
                    self.assertEqual(c.output_frames, c.source_frames - c.trim_first)
                for prev, nxt in zip(chunks, chunks[1:]):
                    self.assertEqual(nxt.start_frame, prev.start_frame + prev.source_frames - 1)

    def test_reject_excessive_video(self):
        with self.assertRaises(ValueError):
            plan_chunks(FPS * MAX_VIDEO_SECONDS + 1)

    def test_reject_invalid_chunk_size(self):
        with self.assertRaises(ValueError):
            plan_chunks(100, chunk_frames=80)


if __name__ == "__main__":
    unittest.main()
