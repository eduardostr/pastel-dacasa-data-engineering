from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from etl.__main__ import main
from etl.control.lock import writer_lock


class SafetyTests(unittest.TestCase):
    def test_writer_lock_is_exclusive_and_released(self):
        with TemporaryDirectory() as directory:
            with writer_lock(directory):
                with self.assertRaises(RuntimeError):
                    with writer_lock(directory):
                        self.fail("Não deveria obter segundo lock")
            with writer_lock(directory):
                pass

    def test_plan_and_full_guard_never_create_datasets(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / "data"
            args = ["etl", "--mode", "full", "--data-dir", str(target)]
            with patch("sys.argv", args), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertFalse(target.exists())
            with patch("sys.argv", args + ["--execute"]), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(target.exists())
