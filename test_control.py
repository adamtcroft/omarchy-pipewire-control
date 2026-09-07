import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import control


class Tests(unittest.TestCase):
    def test_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / 'card0'
            card.mkdir()
            (card / 'stream0').write_text('Scarlett\nMomentary freq = 44100 Hz\nFormat: S32_LE\nBits: 24\n')
            self.assertEqual(control.hardware(Path(tmp))[0]['bits'], ['24'])
            self.assertEqual(control.hardware(Path(tmp))[0]['rates'], ['44100'])

    def test_save_both_values_writes_pipewire_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sub/default.conf'
            control.save(44100, 128, path)
            content = path.read_text()
            self.assertTrue(content.startswith(control.MARKER))
            self.assertIn('default.clock.rate = 44100', content)
            self.assertIn('default.clock.allowed-rates = [ 44100 ]', content)
            self.assertIn('default.clock.quantum = 128', content)

    def test_rate_only_defaults_omit_auto_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(48000, 0, path)
            content = path.read_text()
            self.assertIn('default.clock.rate = 48000', content)
            self.assertIn('default.clock.allowed-rates = [ 48000 ]', content)
            self.assertNotIn('default.clock.quantum', content)

    def test_buffer_only_defaults_omit_auto_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(0, 256, path)
            content = path.read_text()
            self.assertNotIn('default.clock.rate', content)
            self.assertNotIn('default.clock.allowed-rates', content)
            self.assertIn('default.clock.quantum = 256', content)

    def test_clear_owned_and_absent_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sub/default.conf'
            control.save(44100, 128, path)
            control.save(0, 0, path)
            self.assertFalse(path.exists())
            control.save(0, 0, path)
            self.assertFalse(path.exists())

    @patch('control.hardware', return_value=[])
    @patch('control.metadata', return_value={'clock.rate': '48000'})
    @patch('control.run', return_value='S   ID  QUANT RATE\nR 57 128 44100 1us 2us\n')
    def test_snapshot_reads_saved_values_after_fresh_read(self, run, metadata, hardware):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(48000, 256, path)
            with patch('control.CONFIG', path):
                info = control.snapshot()
        self.assertEqual(info['saved'], {'rate': 48000, 'quantum': 256})

    @patch('control.hardware', return_value=[])
    @patch('control.metadata', return_value={'clock.rate': '48000'})
    @patch('control.run', return_value='S   ID  QUANT RATE\nR 57 128 44100 1us 2us\nR 56 0 0 1us 2us\nR 120 88200 44100 1us 2us + app\n')
    def test_snapshot_uses_live_graph(self, run, metadata, hardware):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('control.CONFIG', Path(tmp) / 'absent'):
                info = control.snapshot()
        self.assertEqual(info['graph'], [{'quantum': 128, 'rate': 44100}])
        self.assertEqual(info['settings']['clock.rate'], '48000')
        self.assertEqual(info['saved'], {})

    def test_invalid_values_leave_existing_file_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(44100, 128, path)
            original = path.read_text()
            for rate, buffer in ((123, 128), (44100, 17)):
                with self.assertRaises(ValueError):
                    control.save(rate, buffer, path)
                self.assertEqual(path.read_text(), original)

    def test_unowned_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            path.write_text('user settings')
            for rate, buffer in ((44100, 128), (0, 0)):
                with self.assertRaises(ValueError):
                    control.save(rate, buffer, path)
                self.assertEqual(path.read_text(), 'user settings')

    def test_symlinks_are_refused_for_save_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'target'
            target.write_text(control.MARKER + 'original')
            link = root / 'link'
            link.symlink_to(target)
            dangling_target = root / 'missing'
            dangling = root / 'dangling'
            dangling.symlink_to(dangling_target)
            for path in (link, dangling):
                for rate, buffer in ((44100, 128), (0, 0)):
                    with self.assertRaises(ValueError):
                        control.save(rate, buffer, path)
            self.assertEqual(target.read_text(), control.MARKER + 'original')
            self.assertTrue(link.is_symlink())
            self.assertTrue(dangling.is_symlink())

    def test_save_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(44100, 128, path)
            original = path.read_text()
            with patch('control.os.replace', side_effect=OSError('replace failed')):
                with self.assertRaises(OSError):
                    control.save(48000, 256, path)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(path.parent.glob('.pipewire-control-*')), [])

    @patch('control.run')
    @patch('control.metadata', return_value={'clock.force-rate': '48000', 'clock.force-quantum': '256'})
    def test_save_and_clear_do_not_change_live_metadata(self, metadata, run):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(44100, 128, path)
            control.save(0, 0, path)
        metadata.assert_not_called()
        run.assert_not_called()

    @patch('control.run')
    @patch('control.metadata', return_value={'clock.force-rate': '48000', 'clock.force-quantum': '256'})
    def test_apply_and_reset_leave_defaults_file_unchanged(self, metadata, run):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            control.save(44100, 128, path)
            original = path.read_text()
            run.side_effect = ['', '', '', '']
            control.apply(48000, 256)
            control.apply(0, 0)
            self.assertEqual(path.read_text(), original)
        self.assertEqual(run.call_count, 4)

    def test_xdg_config_home_redirects_default_path_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env['XDG_CONFIG_HOME'] = tmp
            code = 'import control; control.save(44100, 128)'
            subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent,
                           env=env, check=True, capture_output=True, text=True)
            path = Path(tmp) / 'pipewire/pipewire.conf.d/90-pipewire-control.conf'
            self.assertTrue(path.exists())
            self.assertTrue(path.read_text().startswith(control.MARKER))

    def test_empty_xdg_config_home_falls_back_to_home_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env['HOME'] = tmp
            env['XDG_CONFIG_HOME'] = ''
            code = 'import control; print(control.CONFIG)'
            result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent,
                                    env=env, check=True, capture_output=True, text=True)
            self.assertEqual(Path(result.stdout.strip()), Path(tmp) / '.config/pipewire/pipewire.conf.d/90-pipewire-control.conf')

    def test_empty_hardware_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / 'card0'
            card.mkdir()
            (card / 'stream0').write_text('')
            self.assertEqual(control.hardware(Path(tmp)), [])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            control.validate(123, 128)

    @patch('control.run')
    @patch('control.metadata', return_value={'clock.force-rate': '48000', 'clock.force-quantum': '256'})
    def test_rollback(self, meta, run):
        run.side_effect = ['', RuntimeError('failure'), '', '']
        with self.assertRaises(RuntimeError):
            control.apply(44100, 128)
        self.assertEqual(run.call_args_list[-2].args[0][-1], '48000')
        self.assertEqual(run.call_args_list[-1].args[0][-1], '256')


if __name__ == '__main__':
    unittest.main()
