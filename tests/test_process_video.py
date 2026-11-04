import tempfile
import unittest
from pathlib import Path

from scripts.process_video import make_ass


class RenderLayoutTest(unittest.TestCase):
    def test_progress_and_captions_stay_in_their_regions(self):
        with tempfile.TemporaryDirectory() as directory:
            ass_path = Path(directory) / "layout.ass"
            make_ass(
                ass_path,
                [(0.0, 1.0, "中文字幕", "English subtitle")],
                [(0.0, 1.0, "01 开场")],
                1.0, 3456, 2160, 60, 112,
            )
            lines = ass_path.read_text(encoding="utf-8").splitlines()

        self.assertIn("PlayResY: 2272", lines)
        styles = {line.split(",", 1)[0]: line.split(",") for line in lines if line.startswith("Style:")}
        self.assertEqual(styles["Style: Zh"][2], "130")
        self.assertEqual(styles["Style: En"][2], "73")
        self.assertEqual(styles["Style: Zh"][21], "331")
        self.assertEqual(styles["Style: En"][21], "253")
        for name in ("Style: Zh", "Style: En"):
            self.assertEqual(styles[name][3], "&H0048E3FF")
            self.assertEqual(styles[name][15], "1")  # No opaque ASS subtitle box.

        progress = next(line for line in lines if line.startswith("Dialogue: 0,"))
        self.assertIn(r"\pos(0,102)", progress)
        self.assertIn("l 3456 10 l 0 10", progress)
        self.assertTrue(any("中文字幕" in line for line in lines))
        self.assertTrue(any("English subtitle" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
