import unittest
from pathlib import Path
from unittest.mock import patch

from zol_scraper.platform_utils import open_directory


class OpenDirectoryTests(unittest.TestCase):
    def test_open_directory_uses_startfile_on_windows(self):
        target = Path("C:/tmp/output")

        with patch("zol_scraper.platform_utils.sys.platform", "win32"):
            with patch("zol_scraper.platform_utils.os.startfile", create=True) as startfile:
                with patch("zol_scraper.platform_utils.subprocess.run") as run:
                    open_directory(target)

        startfile.assert_called_once_with(str(target))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
