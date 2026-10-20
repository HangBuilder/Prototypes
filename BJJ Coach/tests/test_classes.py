"""Synthetic two-video class workflow, not semantic analysis of instructor footage."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from bjj_coach.classes import create_class, class_snapshot, save_class, validate_class
from bjj_coach.pipeline import prepare, read_json, write_json, sha256


class ClassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.roots = []
        for i, frequency in enumerate((440, 880)):
            source = cls.base / f'synthetic-{i}.mov'
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                'testsrc2=size=160x120:rate=10', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:sample_rate=48000',
                '-t', '2', '-c:v', 'libx264', '-threads', '2', '-c:a', 'pcm_s16le', str(source)], check=True)
            root = prepare(source, cls.base / 'runs', frame_interval=1)
            (root / 'asr').mkdir()
            write_json(root / 'asr/synthetic.json', {'settings': {'model': 'synthetic'}, 'segments': [
                {'id': f'synthetic-{i}', 'start': .2, 'end': 1, 'text': 'SYNTHETIC hand control', 'flags': []}]})
            manifest = read_json(root / 'manifest.json')
            manifest['stages']['asr/synthetic'] = {'status': 'complete', 'artifacts': {
                'asr/synthetic.json': sha256(root / 'asr/synthetic.json')}}
            write_json(root / 'manifest.json', manifest)
            cls.roots.append(root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.file = self.base / f'class-{self.id().split(".")[-1]}.json'
        create_class(self.file, self.roots, 'Synthetic class')

    def linked(self):
        d = read_json(self.file)
        d['techniques'] = [{'id': 'technique', 'name': 'Synthetic guard pull'}]
        d['details'] = [{'id': 'detail', 'name': 'Synthetic hand control', 'conditions': 'Test only', 'technique_ids': ['technique']}]
        d['occurrences'] = [{'id': f'occurrence-{i}', 'detail_id': 'detail', 'video_id': v['id'],
            'start': .1, 'end': 1.2, 'role': 'initial_explanation' if i == 0 else 'correction',
            'basis': 'spoken', 'reference': f'synthetic-{i}', 'excerpt': 'SYNTHETIC hand control',
            'note': '', 'review_status': 'user_linked'} for i, v in enumerate(d['videos'])]
        return d

    def test_links_persist_with_history_and_class_order(self):
        d = self.linked()
        save_class(self.file, d)
        snapshot = class_snapshot(self.file)
        self.assertEqual(snapshot['document'], d)
        self.assertEqual(len(snapshot['document']['occurrences']), 2)
        self.assertEqual([v['run_path'] for v in snapshot['videos']], [str(r) for r in self.roots])
        self.assertEqual(len(read_json(self.file.with_name(self.file.stem + '.history.json'))), 1)

    def test_invalid_bounds_references_and_identity_are_rejected(self):
        for mutate in (
            lambda d: d['occurrences'][0].update(end=9),
            lambda d: d['occurrences'][0].update(detail_id='missing'),
            lambda d: d['occurrences'][0].update(reference='synthetic-1'),
            lambda d: d['occurrences'][0].update(excerpt='invented quote'),
            lambda d: d['occurrences'][0].update(start=float('nan')),
            lambda d: d['videos'][0].update(run_path='/tmp/unregistered'),
        ):
            d = self.linked()
            mutate(d)
            with self.assertRaises(ValueError):
                save_class(self.file, d)
        self.assertEqual(read_json(self.file)['occurrences'], [])

    def test_corrected_spoken_visual_and_inferred_evidence(self):
        d = self.linked()
        write_json(self.roots[0] / 'corrections.json', [{'target': 'synthetic-0', 'text': 'CORRECTED test', 'unclear': False}])
        try:
            d['occurrences'][0]['excerpt'] = 'CORRECTED test'
            save_class(self.file, d)
            self.assertEqual(class_snapshot(self.file)['videos'][0]['transcripts'][0]['segments'][0]['text'], 'CORRECTED test')
            evidence = d['occurrences'][0]
            evidence.update(basis='visual', reference='frames/0000.jpg', start=0, excerpt='Synthetic visible shapes')
            validate_class(d)
            evidence.update(basis='inferred', reference='', excerpt='', note='Synthetic interpretation')
            validate_class(d)
            evidence['note'] = ''
            with self.assertRaises(ValueError):
                validate_class(d)
        finally:
            (self.roots[0] / 'corrections.json').unlink(missing_ok=True)

    def test_existing_file_and_duplicate_video_protected(self):
        with self.assertRaises(ValueError):
            create_class(self.file, self.roots, 'Replacement')
        with self.assertRaises(ValueError):
            create_class(self.base / 'duplicate.json', [self.roots[0], self.roots[0]], 'Duplicate')

    def test_http_serves_both_videos_and_persists_linked_detail(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, '-m', 'bjj_coach.cli', 'class-review', str(self.file), '--port', str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    conn.request('GET', '/api/class')
                    response = conn.getresponse()
                    state = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.05)
            conn.request('GET', '/')
            self.assertIn(b'All moments for this detail', conn.getresponse().read())
            for v in state['document']['videos']:
                conn.request('GET', f"/class/videos/{v['id']}/original", headers={'Range': 'bytes=0-31'})
                response = conn.getresponse()
                self.assertEqual(response.status, 206)
                source = Path(read_json(Path(v['run_path']) / 'manifest.json')['source_path'])
                self.assertEqual(response.read(), source.read_bytes()[:32])
            conn.request('POST', '/api/class', body=json.dumps(self.linked()))
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.request('POST', '/api/class', body=json.dumps(self.linked()), headers={'X-Review-Token': state['token']})
            response = conn.getresponse()
            self.assertEqual(response.status, 200, response.read())
            conn.request('GET', '/api/class')
            self.assertEqual(len(json.loads(conn.getresponse().read())['document']['occurrences']), 2)
            conn.request('GET', '/class/videos/unregistered/original')
            response = conn.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            conn.close()
        finally:
            process.terminate()
            process.communicate(timeout=5)
