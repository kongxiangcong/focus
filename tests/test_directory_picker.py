"""Host directory selection does not require an optional Tk installation."""
import subprocess
import os
import unittest
from unittest.mock import patch

from host.workbench import Workbench


@unittest.skipUnless(os.name == 'nt', 'Windows native picker')
class DirectoryPickerTests(unittest.TestCase):
    def test_windows_picker_opens_native_dialog_without_tk(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"path":"D:\\\\阅读 文件"}', '')) as run:
            value = Workbench.choose_directory(None)
        self.assertEqual('D:\\阅读 文件', value['path'])
        self.assertNotIn('error', value)
        self.assertIn('-STA', run.call_args.args[0])

    def test_native_cancel_has_no_error_or_selection(self):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"path":null}', '')):
            self.assertEqual({'path': None}, Workbench.choose_directory(None))

    def test_native_failure_retains_manual_path_fallback(self):
        with patch('subprocess.run', side_effect=OSError('unavailable')):
            value = Workbench.choose_directory(None)
        self.assertIsNone(value['path'])
        self.assertIn('手动输入', value['error'])


if __name__ == '__main__':
    unittest.main()
