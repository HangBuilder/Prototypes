"""Integration fixtures are SYNTHETIC, never instructor footage or analysis."""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import wave

from bjj_coach.pipeline import (prepare, enhance, read_json, write_json, validate_claims, sha256, subtitle_time)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.source = cls.base / 'synthetic.mov'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=160x120:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', '2', '-c:v', 'libx264', '-threads', '2', '-c:a', 'pcm_s16le', '-ac', '2', str(cls.source)], check=True)
        cls.original_hash = sha256(cls.source)
        cls.root = prepare(cls.source, cls.base / 'runs', frame_interval=1, max_frames=2)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_extraction_preserves_original_and_reference_channels(self):
        self.assertEqual(sha256(self.source), self.original_hash)
        from bjj_coach.pipeline import probe
        reference = probe(self.root / 'reference.wav')['streams'][0]
        baseline = probe(self.root / 'baseline.wav')['streams'][0]
        self.assertEqual((reference['channels'], reference['sample_rate']), (2, '48000'))
        self.assertEqual((baseline['channels'], baseline['sample_rate']), (1, '16000'))
        self.assertEqual([f['time'] for f in read_json(self.root / 'frames.json')], [0, 1])
        self.assertIsNone(read_json(self.root / 'manifest.json')['confirmed_metadata']['instructor'])

    def test_resume_and_corrupt_artifact_repair(self):
        initial = read_json(self.root / 'manifest.json')['stages']['baseline_audio']
        prepare(self.source, self.base / 'runs', frame_interval=1, max_frames=2)
        self.assertEqual(initial, read_json(self.root / 'manifest.json')['stages']['baseline_audio'])
        (self.root / 'baseline.wav').write_bytes(b'corrupt')
        prepare(self.source, self.base / 'runs', frame_interval=1, max_frames=2)
        self.assertEqual(sha256(self.root / 'baseline.wav'), initial['artifacts']['baseline.wav'])

    def test_enhancement_separate_and_repeatable(self):
        baseline = sha256(self.root / 'baseline.wav')
        enhance(self.root)
        first = read_json(self.root / 'manifest.json')['stages']['enhanced_audio']
        enhance(self.root)
        self.assertEqual(first, read_json(self.root / 'manifest.json')['stages']['enhanced_audio'])
        self.assertEqual(sha256(self.root / 'baseline.wav'), baseline)
        self.assertNotEqual(sha256(self.root / 'enhanced.wav'), baseline)

    def claims(self):
        return {'video_sha256': self.original_hash, 'segments': [{
            'id': 'synthetic-segment', 'start': 0, 'end': 1.5, 'candidate_techniques': [],
            'candidate_positions': [], 'perspectives': ['unknown'], 'intents': [], 'attire': 'unknown',
            'review_status': 'machine_proposed', 'claims': [{'id': 'synthetic-claim',
            'kind': 'essential_detail', 'content': 'Synthetic test image has colored shapes; not BJJ analysis.',
            'basis': 'visual', 'review_status': 'machine_proposed', 'evidence': [
                {'basis': 'visual', 'start': 0, 'end': 1, 'reference': 'frames/0000.jpg',
                 'excerpt': 'Synthetic test fixture, not real instructional evidence.'}]}]}]}

    def validate(self, value):
        file = self.base / 'candidate.json'
        write_json(file, value)
        return validate_claims(self.root, file)

    def test_schema_accepts_synthetic_frame_reference(self):
        self.validate(self.claims())

    def test_rejects_out_of_bounds_and_missing_evidence(self):
        value = self.claims()
        value['segments'][0]['end'] = 999
        with self.assertRaises(ValueError):
            self.validate(value)
        value = self.claims()
        value['segments'][0]['claims'][0]['evidence'] = []
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_rejects_fabricated_spoken_reference_and_wrong_source(self):
        value = self.claims()
        claim = value['segments'][0]['claims'][0]
        claim['basis'] = claim['evidence'][0]['basis'] = 'spoken'
        claim['evidence'][0]['reference'] = 'nonexistent-transcript'
        with self.assertRaises(ValueError):
            self.validate(value)
        value = self.claims()
        value['video_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_subtitle_carry(self):
        self.assertEqual(subtitle_time(59.9999), '00:01:00,000')

    def test_audio_offset_is_padded_on_video_timeline(self):
        source = self.base / 'offset.mov'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=160x120:rate=10:duration=2', '-itsoffset', '0.5', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=1', '-c:v', 'libx264', '-threads', '2',
            '-c:a', 'pcm_s16le', str(source)], check=True)
        root = prepare(source, self.base / 'offset-runs', max_frames=0)
        manifest = read_json(root / 'manifest.json')
        self.assertAlmostEqual(manifest['audio_alignment']['reference_offset_seconds'], .5, places=2)
        with wave.open(str(root / 'baseline.wav')) as audio:
            self.assertEqual(audio.readframes(6400), b'\x00' * 12800)

    def test_transcription_adapter_exports_and_resumes_synthetic_response(self):
        # No inference: verify only adapter conversion, exports, flags, and cache contract.
        from bjj_coach.pipeline import transcribe
        @dataclass
        class SyntheticSegment:
            start: float = .1
            end: float = .8
            text: str = 'SYNTHETIC words, not ASR output'
            no_speech_prob: float = .7
        @dataclass
        class SyntheticInfo:
            language: str = 'en'
        engine = MagicMock()
        engine.transcribe.return_value = (iter([SyntheticSegment()]), SyntheticInfo())
        constructor = MagicMock(return_value=engine)
        with patch.dict(sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=constructor)}), \
                patch('importlib.metadata.version', return_value='synthetic-test'):
            output = transcribe(self.root, sample_seconds=1, model='synthetic-local-model')
            data = read_json(output)
            self.assertIn('possible_silence_hallucination', data['segments'][0]['flags'])
            self.assertEqual(data['settings']['sample_seconds'], 1)
            self.assertIn('00:00:00,100 --> 00:00:00,800', output.with_suffix('.srt').read_text())
            self.assertEqual(read_json(output.with_suffix('.raw.json'))['segments'][0]['text'], SyntheticSegment().text)
            transcribe(self.root, sample_seconds=1, model='synthetic-local-model')
            self.assertEqual(constructor.call_count, 1)

    def test_draft_schema_constraints(self):
        db = sqlite3.connect(':memory:')
        db.executescript((Path(__file__).parents[1] / 'schemas/001_draft.sql').read_text())
        db.execute("INSERT INTO classification_term VALUES ('a','submission','action',NULL)")
        db.execute("INSERT INTO classification_term VALUES ('b','choke','submission_subtype','a')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE classification_term SET parent_id='b' WHERE id='a'")
        db.execute("INSERT INTO video(id,file_reference,sha256,duration,uploaded_at,processing_status) VALUES ('synthetic','fixture',?,2,'synthetic','complete')", ('a'*64,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO instructional_segment(id,video_id,start,end) VALUES ('bad','synthetic',0,3)")
        db.close()

    def test_review_http_seeking_corrections_and_claim_history(self):
        # Explicit synthetic adapter fixture; this does NOT test or claim ASR accuracy.
        relative = 'asr/synthetic'
        (self.root / 'asr').mkdir(exist_ok=True)
        transcript_file = self.root / f'{relative}.json'
        write_json(transcript_file, {'settings': {'synthetic': True}, 'segments': [
            {'id': 'synthetic-transcript', 'start': 0, 'end': 1, 'text': 'SYNTHETIC test words', 'flags': []}]})
        manifest = read_json(self.root / 'manifest.json')
        manifest['stages'][relative] = {'status': 'complete', 'artifacts': {f'{relative}.json': sha256(transcript_file)}}
        write_json(self.root / 'manifest.json', manifest)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, '-m', 'bjj_coach.cli', 'review', str(self.root), '--port', str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    connection.request('GET', '/api/state')
                    response = connection.getresponse()
                    state = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(.05)
            connection.request('GET', '/')
            response = connection.getresponse()
            self.assertIn(b'Review the evidence', response.read())
            connection.request('GET', '/video', headers={'Range': 'bytes=0-31'})
            response = connection.getresponse()
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), self.source.read_bytes()[:32])
            connection.request('GET', '/video', headers={'Range': 'bytes=999999999-'})
            response = connection.getresponse()
            self.assertEqual(response.status, 416)
            response.read()
            correction = {'target': 'synthetic-transcript', 'text': 'Human test correction', 'unclear': True}
            connection.request('POST', '/api/corrections', body=json.dumps(correction))
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            headers = {'Content-Type': 'application/json', 'X-Review-Token': state['token']}
            connection.request('POST', '/api/corrections', body=json.dumps(correction), headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertEqual(read_json(self.root / 'corrections.json')[-1]['text'], correction['text'])
            self.assertEqual(read_json(transcript_file)['segments'][0]['text'], 'SYNTHETIC test words')
            connection.request('POST', '/api/claims', body=json.dumps(self.claims()), headers=headers)
            response = connection.getresponse()
            self.assertEqual(response.status, 200, response.read())
            self.assertTrue((self.root / 'claims-review-history.json').exists())
            self.assertEqual(read_json(self.root / 'claims.json')['segments'], [])
            connection.request('GET', '/../../etc/passwd')
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            connection.close()
        finally:
            process.terminate()
            process.communicate(timeout=5)
