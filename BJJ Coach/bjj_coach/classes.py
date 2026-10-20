"""Local class collections and reviewed cross-video evidence links."""
import math
from pathlib import Path
import uuid

from .pipeline import artifacts_valid, now, read_json, write_json, sha256

ROLES = ('initial_explanation', 'repetition', 'correction', 'variation', 'exception', 'follow_up')


def create_class(path, roots, title):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Class file already exists; choose another filename')
    if len(roots) < 2:
        raise ValueError('Choose at least two processed video run directories')
    videos = []
    for root in roots:
        root = Path(root).expanduser().resolve(strict=True)
        manifest = read_json(root / 'manifest.json')
        identity = manifest['source_sha256']
        if any(v['id'] == identity for v in videos):
            raise ValueError('Each class video must have a different source hash')
        videos.append({'id': identity, 'run_path': str(root),
                       'title': Path(manifest['source_path']).name})
    document = {'id': uuid.uuid4().hex, 'title': title, 'videos': videos,
                'techniques': [], 'details': [], 'occurrences': []}
    validate_class(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, document)
    return path


def class_snapshot(path):
    document = read_json(path)
    videos = []
    for item in document['videos']:
        root = Path(item['run_path'])
        manifest = read_json(root / 'manifest.json')
        transcripts = []
        corrections = read_json(root / 'corrections.json') if (root / 'corrections.json').exists() else []
        latest = {c['target']: c for c in corrections}
        for name, record in manifest['stages'].items():
            if not name.startswith('asr/') or not artifacts_valid(root, record):
                continue
            transcript = read_json(root / f'{name}.json')
            segments = []
            for segment in transcript['segments']:
                correction = latest.get(segment['id'])
                segments.append({**segment, 'original_text': segment['text'],
                    'text': correction['text'] if correction else segment['text'],
                    'unclear': correction['unclear'] if correction else bool(segment.get('flags'))})
            transcripts.append({'id': name, 'settings': transcript.get('settings', {}), 'segments': segments})
        record = manifest['stages'].get('enhanced_video')
        enhanced_available = bool(artifacts_valid(root, record) and (root / 'enhanced.wav').is_file()
                                  and record['settings']['audio_sha256'] == sha256(root / 'enhanced.wav'))
        videos.append({**item, 'duration': manifest['duration'], 'transcripts': transcripts,
                       'enhanced_video_available': enhanced_available,
                       'frames': read_json(root / 'frames.json')})
    return {'document': document, 'videos': videos, 'roles': ROLES}


def validate_class(document, existing=None):
    """Structural evidence validation; a saved link is a user's proposal, not verified fact."""
    if not isinstance(document, dict) or set(document) != {'id', 'title', 'videos', 'techniques', 'details', 'occurrences'}:
        raise ValueError('Invalid class document fields')
    def text(value):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 20000
    if not text(document['id']) or not text(document['title']):
        raise ValueError('Class ID and title are required')
    if existing and (document['id'] != existing['id'] or document['videos'] != existing['videos']):
        raise ValueError('Class identity and registered video paths cannot be changed through review')
    for field in ('videos', 'techniques', 'details', 'occurrences'):
        if not isinstance(document[field], list):
            raise ValueError(f'{field} must be an array')
    if len(document['videos']) < 2:
        raise ValueError('A class comparison needs at least two videos')
    seen = set()
    def identity(item):
        if not isinstance(item, dict) or not text(item.get('id')) or item['id'] in seen:
            raise ValueError('Every entity needs a unique nonempty ID')
        seen.add(item['id'])
    videos = {}
    for video in document['videos']:
        identity(video)
        if set(video) != {'id', 'run_path', 'title'} or not text(video['title']):
            raise ValueError('Invalid video record')
        root = Path(video['run_path'])
        manifest = read_json(root / 'manifest.json')
        if manifest['source_sha256'] != video['id']:
            raise ValueError('Video identity does not match its source manifest')
        videos[video['id']] = (root, manifest)
    techniques = set()
    for technique in document['techniques']:
        identity(technique)
        if set(technique) != {'id', 'name'} or not text(technique['name']):
            raise ValueError('Invalid technique')
        techniques.add(technique['id'])
    details = set()
    for detail in document['details']:
        identity(detail)
        if set(detail) != {'id', 'technique_ids', 'name', 'conditions'} or not text(detail['name']) or not isinstance(detail['conditions'], str):
            raise ValueError('Invalid technical detail')
        if not isinstance(detail['technique_ids'], list) or not detail['technique_ids'] or any(t not in techniques for t in detail['technique_ids']):
            raise ValueError('A detail must link to existing techniques')
        details.add(detail['id'])
    for occurrence in document['occurrences']:
        identity(occurrence)
        if set(occurrence) != {'id', 'detail_id', 'video_id', 'start', 'end', 'role', 'basis', 'reference', 'excerpt', 'note', 'review_status'}:
            raise ValueError('Invalid occurrence fields')
        if occurrence['detail_id'] not in details or occurrence['video_id'] not in videos:
            raise ValueError('Occurrence references an unknown detail or video')
        root, manifest = videos[occurrence['video_id']]
        start, end = occurrence['start'], occurrence['end']
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (start, end)) or not 0 <= start < end <= manifest['duration']:
            raise ValueError('Occurrence must lie within the selected video duration')
        if occurrence['role'] not in ROLES or occurrence['basis'] not in ('spoken', 'visual', 'inferred'):
            raise ValueError('Invalid teaching role or evidence basis')
        if occurrence['review_status'] != 'user_linked':
            raise ValueError('Manual links use user_linked, not instructor verification')
        if not all(isinstance(occurrence[f], str) for f in ('reference', 'excerpt', 'note')):
            raise ValueError('Evidence reference, excerpt, and note must be text')
        if occurrence['basis'] == 'spoken':
            target = None
            for name, record in manifest['stages'].items():
                if name.startswith('asr/') and artifacts_valid(root, record):
                    for segment in read_json(root / f'{name}.json')['segments']:
                        if segment['id'] == occurrence['reference']:
                            target = segment
            if target is None or not start <= target['start'] < target['end'] <= end:
                raise ValueError('Spoken occurrence must contain the referenced transcript segment')
            corrections = read_json(root / 'corrections.json') if (root / 'corrections.json').exists() else []
            versions = [target['text']] + [c['text'] for c in corrections if c['target'] == target['id']]
            if not occurrence['excerpt'] or not any(occurrence['excerpt'] in version for version in versions):
                raise ValueError('Spoken excerpt must quote machine or saved corrected transcript text')
        elif occurrence['basis'] == 'visual':
            frames = {f['id']: f for f in read_json(root / 'frames.json')}
            frame = frames.get(occurrence['reference'])
            if not frame or not start <= frame['time'] <= end or not occurrence['excerpt'].strip():
                raise ValueError('Visual evidence needs an included timestamped frame and an observation')
        elif not occurrence['note'].strip():
            raise ValueError('Inferred links need a note explaining the interpretation')
    return document


def save_class(path, document):
    path = Path(path)
    validate_class(document, read_json(path))
    history_path = path.with_name(path.stem + '.history.json')
    history = read_json(history_path) if history_path.exists() else []
    write_json(history_path, history + [{'saved_at': now(), 'document': read_json(path)}])
    write_json(path, document)
