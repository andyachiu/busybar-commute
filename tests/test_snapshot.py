import ctypes
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from commutebar.snapshot import encode, publish


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('cc'):
            raise unittest.SkipTest('C compiler needed for native cache compatibility tests')
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / 'snapshot.so'
        source = Path(__file__).resolve().parents[1] / 'native/upcoming_events/snapshot.c'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', str(source), '-o', str(library)], check=True)
        cls.library = ctypes.CDLL(str(library))
        cls.decode = cls.library.snapshot_decode
        cls.decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        cls.decode.restype = ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def blob(self, count=25):
        cache = dict(fetched_at='2026-09-13T10:00:00-07:00', events=[
            dict(id=str(i), title='Giants vs Padres', venue='Oracle Park', date='2026-09-14',
                 start='2026-09-14T19:15:00-07:00', kind='baseball') for i in range(count)])
        return encode(cache, datetime.fromisoformat('2026-09-13T11:00:00-07:00'))

    def test_python_writer_and_native_reader_agree_at_capacity(self):
        blob = self.blob()
        out = ctypes.create_string_buffer(5448)
        self.assertEqual(len(blob), 5460)
        self.assertTrue(self.decode(blob, len(blob), out))
        self.assertEqual(struct.unpack_from('<I', out.raw, 4)[0], 20)
        self.assertIn(b'Giants vs Padres', out.raw)

    def test_partial_corrupt_and_oversized_leave_previous_snapshot_untouched(self):
        blob = self.blob()
        out = ctypes.create_string_buffer(b'x' * 5448, 5448)
        for bad in (blob[:10], blob[:-1], blob + b'X', blob[:99] + b'X' + blob[100:]):
            self.assertFalse(self.decode(bad, len(bad), out))
            self.assertEqual(out.raw, b'x' * 5448)

    def test_reject_unterminated_string_even_with_correct_checksum(self):
        blob = bytearray(self.blob(1))
        blob[20:100] = b'X' * 80
        struct.pack_into('<I', blob, 8, zlib.crc32(blob[12:]))
        self.assertFalse(self.decode(bytes(blob), len(blob), ctypes.create_string_buffer(5448)))

    def test_empty_is_valid(self):
        blob = self.blob(0)
        self.assertTrue(self.decode(blob, len(blob), ctypes.create_string_buffer(5448)))

    def test_publish_alternates_only_after_ack_and_skips_unchanged(self):
        class Cache:
            state, generation = {}, 0
            def read_native_publish_state(self): return self.state, self.generation
            def write_native_publish_state(self, state, generation):
                self.assert_generation = generation
                self.state, self.generation = state, self.generation + 1
        cache = Cache()
        now = datetime.fromisoformat('2026-09-13T11:00:00-07:00')
        snapshot = dict(fetched_at='2026-09-13T10:00:00-07:00', sources=[], events=[])
        with patch('commutebar.snapshot.upload') as upload:
            self.assertEqual(publish(cache, 'token', snapshot, {}, now), 'published')
            upload.assert_called_once()
            self.assertEqual(upload.call_args.args[1], 'a')
            self.assertEqual(publish(cache, 'token', snapshot, {}, now), 'unchanged')
            self.assertEqual(upload.call_count, 1)
            snapshot = dict(snapshot, fetched_at='2026-09-13T10:15:00-07:00')
            self.assertEqual(publish(cache, 'token', snapshot, {}, now), 'published')
            self.assertEqual(upload.call_args.args[1], 'b')

    def test_provisional_departure_has_no_private_addresses(self):
        cache = dict(fetched_at='2026-09-13T10:00:00-07:00', sources=[], events=[
            dict(id='1', title='Giants game', venue='Oracle Park', date='2026-09-14',
                 start='2026-09-14T17:00:00-07:00', kind='baseball')])
        config = dict(commute_weekdays=[0,1,2,3,4], departure='16:15', deadline='17:00',
                      earliest_departure='15:00', event_warning_minutes=15,
                      arrival_buffer_minutes=120, game_duration_minutes=180, exit_buffer_minutes=60,
                      origin='PRIVATE ADDRESS', destination='PRIVATE HOME')
        blob = encode(cache, datetime.fromisoformat('2026-09-13T10:30:00-07:00'), config)
        self.assertIn(b'Plan: 4:00 PM / provisional', blob)
        self.assertNotIn(b'PRIVATE', blob)
        stale = encode(cache, datetime.fromisoformat('2026-09-13T12:00:00-07:00'), config)
        self.assertNotIn(b'Plan:', stale)
