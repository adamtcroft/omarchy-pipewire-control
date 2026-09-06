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

    def test_save_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sub/default.conf'
            control.save(44100, 128, path)
            self.assertIn('default.clock.rate = 44100', path.read_text())
            control.save(0, 0, path)
            self.assertFalse(path.exists())

    def test_unowned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'default.conf'
            path.write_text('user settings')
            with self.assertRaises(ValueError):
                control.save(44100, 128, path)
            self.assertEqual(path.read_text(), 'user settings')

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'
            target.write_text(control.MARKER + 'original')
            link = Path(tmp) / 'link'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                control.save(44100, 128, link)
            self.assertEqual(target.read_text(), control.MARKER + 'original')

    def test_empty_hardware_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / 'card0'
            card.mkdir()
            (card / 'stream0').write_text('')
            self.assertEqual(control.hardware(Path(tmp)), [])

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
