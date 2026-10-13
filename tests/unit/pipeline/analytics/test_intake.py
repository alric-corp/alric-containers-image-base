"""Opt-in intake of new SBOM lots (audit G11): local filesystem and transport doubles only.

Synthetic artifacts are built here; the only real bytes are the historical LAB
artifacts and frozen plan already versioned as fixtures. No GitHub, S3 or AWS call.
"""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from scripts.pipeline.analytics import intake, s3_run
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError
from scripts.pipeline.analytics.normalize import read_completed
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, publish_snapshot, recover_snapshot
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics.s3_support import FakeS3
from tests.unit.pipeline.analytics.test_artifact_input_lab import LAB_VALUES

ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ID = 4242
DESTINATION = dict(bucket='example-analytics', prefix='sbom-analytics/v1', region='test-region-1',
                   expected_bucket_owner='123456789012')
CONFIG = dict(protocol_version=1, destination=DESTINATION)
ORIGIN = dict(repository='example-org/example-factory', event='push', ref='refs/heads/develop')
DOCUMENTS = {'index': 'sbom/sbom-index.spdx.json', 'linux/amd64': 'sbom/sbom-x86_64.spdx.json',
             'linux/arm64': 'sbom/sbom-aarch64.spdx.json'}


def artifact_zip(source_sha, seed, *, packages=(('zlib', '1.3.1-r0'), ('busybox', '1.37.0-r1')), drop=()):
    """SYNTHETIC Factory sbom-<framework>-<attempt> artifact: three bound SPDXs plus build inputs."""
    subjects = {key: 'sha256:' + sha256((seed + key).encode()) for key in DOCUMENTS}
    members = {}
    for key, path in DOCUMENTS.items():
        members[path] = canonical(dict(spdxVersion='SPDX-2.3', SPDXID='SPDXRef-DOCUMENT',
            documentNamespace='https://example.invalid/spdx/' + seed, documentDescribes=['SPDXRef-image'],
            packages=[dict(SPDXID='SPDXRef-image', name='image', checksums=[dict(algorithm='SHA256', checksumValue=subjects[key][7:])])]
            + [dict(SPDXID='SPDXRef-p%d' % i, name=name, versionInfo=version) for i, (name, version) in enumerate(packages)]))
    members['apko.lock.json'] = canonical(dict(synthetic_lock=seed))
    members['build-inputs.json'] = canonical(dict(revision=source_sha, lock_sha256=sha256(members['apko.lock.json'])))
    members['validated-index.json'] = canonical(dict(digest=subjects['index'],
        platforms={k: subjects[k] for k in ('linux/amd64', 'linux/arm64')},
        sboms=[dict(path=path, subject=subjects[key], sha256=sha256(members[path])) for key, path in DOCUMENTS.items()]))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            if name not in drop:
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 13, 12, 0, 0))
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o100644 << 16
                archive.writestr(info, members[name])
    return stream.getvalue(), subjects


class FakeArtifacts:
    """Read-only transport double with saved GitHub artifact metadata; it proves no API behavior."""

    def __init__(self):
        self.items, self.calls, self.failures = {}, [], {}

    def add(self, artifact_id, metadata, raw):
        self.items[artifact_id] = (metadata, raw)

    def describe(self, artifact_id):
        self.calls.append(('describe', artifact_id))
        return copy.deepcopy(self.items[artifact_id][0])

    def read(self, artifact_id, limit):
        self.calls.append(('read', artifact_id))
        if artifact_id in self.failures:
            raise self.failures[artifact_id]
        return self.items[artifact_id][1]


def metadata(artifact_id, name, raw, run_id, source_sha, *, repository_id=REPOSITORY_ID, branch='develop'):
    return dict(id=artifact_id, name=name, size_in_bytes=len(raw), expired=False, digest='sha256:' + sha256(raw),
                workflow_run=dict(id=run_id, repository_id=repository_id, head_repository_id=repository_id,
                                  head_branch=branch, head_sha=source_sha))


def tree(directory):
    """Every path, mode and byte below a directory."""
    digest = hashlib.sha256()
    for path in sorted(Path(directory).rglob('*')):
        digest.update(path.relative_to(directory).as_posix().encode() + b'\0' + oct(path.stat().st_mode).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class IntakeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sbom-intake-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'intake'
        self.source = FakeArtifacts()

    def lot(self, lot_id, run_id, attempt, source_sha, frameworks, *, register=True, **overrides):
        """frameworks: {name: seed}; artifact IDs derive from run/framework order."""
        artifacts = []
        for number, (framework, seed) in enumerate(sorted(frameworks.items())):
            raw, subjects = artifact_zip(overrides.get('content_sha', source_sha), seed)
            identity, name = run_id * 100 + number, 'sbom-%s-%d' % (framework, attempt)
            if register:
                self.source.add(identity, metadata(identity, name, raw, run_id, source_sha), raw)
            artifacts.append(dict(framework=framework, artifact_id=identity, name=name, archive_sha256=sha256(raw),
                                  archive_bytes=len(raw), expected_index_digest=subjects['index'],
                                  expected_platforms={k: subjects[k] for k in ('linux/amd64', 'linux/arm64')}))
        return dict(schema_version=1, lot_id=lot_id, origin=dict(ORIGIN, run_id=run_id, run_attempt=attempt, source_sha=source_sha),
                    repository_id=REPOSITORY_ID, image_registry='registry.example.invalid', repository_prefix='image-base-',
                    artifacts=artifacts)

    def process(self, request, config=CONFIG, root=None):
        return intake.process(request, config, self.source, root or self.root)

    def assert_nothing_visible(self):
        if not self.root.exists():
            return  # Refused before the private root was even created.
        self.assertFalse((self.root / 'lots').exists() and any((self.root / 'lots').iterdir()))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name not in ('lots', 'closed')], [])

    def assert_rejected(self, request, code, *, reason=None, config=CONFIG):
        with self.assertRaises(IngestionError) as raised:
            self.process(request, config)
        self.assertEqual(raised.exception.code, code)
        if reason:
            self.assertIn(reason, raised.exception.observed['reason'])
        self.assert_nothing_visible()
        return raised.exception

    def test_two_independent_lots_become_two_closed_snapshots_and_the_first_never_changes(self):
        first = self.process(self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1', 'alpha-dev': 'a-2'}))
        self.assertEqual((first['code'], first['observations'], first['frameworks']), ('LOT_CREATED', 6, ['alpha', 'alpha-dev']))
        before = tree(self.root / 'lots/lot-a')
        second = self.process(self.lot('lot-b', 202, 2, 'b' * 40, {'alpha': 'b-1', 'beta': 'b-2'}))
        self.assertEqual(second['code'], 'LOT_CREATED')
        self.assertNotEqual((first['batch_id'], first['snapshot_id']), (second['batch_id'], second['snapshot_id']))
        self.assertEqual(tree(self.root / 'lots/lot-a'), before)
        for result in (first, second):
            lot = json.loads((self.root / 'lots' / result['lot_id'] / 'lot.json').read_bytes())
            self.assertEqual((lot['coverage']['scope'], lot['coverage']['complete_factory_inventory'], lot['publication'],
                              lot['cryptographic_authenticity'], lot['publication_authority']),
                             ('SELECTED_ARTIFACTS_ONLY', False, 'NOT_PUBLISHED', 'NOT_REVALIDATED', False))
            self.assertEqual(intake.verify(self.root, result['lot_id'])['snapshot_id'], result['snapshot_id'])
        rows = read_completed(self.root / 'lots/lot-b/plan/batch')['observations']
        self.assertEqual({(r['run_id'], r['run_attempt'], r['source_sha']) for r in rows}, {(202, 2, 'b' * 40)})
        self.assertEqual({r['image_repository'] for r in rows},
                         {'registry.example.invalid/image-base-alpha', 'registry.example.invalid/image-base-beta'})

    def test_same_lot_is_deterministic_across_roots_and_selection_order(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1', 'beta': 'a-2'})
        first = self.process(request)
        reordered = dict(request, artifacts=list(reversed(request['artifacts'])))
        second = self.process(reordered, root=self.base / 'other-root')
        self.assertEqual((first['batch_id'], first['snapshot_id']), (second['batch_id'], second['snapshot_id']))
        self.assertEqual((self.root / 'lots/lot-a/plan/plan.json').read_bytes(),
                         (self.base / 'other-root/lots/lot-a/plan/plan.json').read_bytes())

    def test_declared_identity_mismatches_are_rejected_before_anything_is_visible(self):
        base = lambda: self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'})

        def reported(run=None, **values):
            request = base()
            saved = self.source.items[request['artifacts'][0]['artifact_id']][0]
            saved.update(values)
            saved['workflow_run'].update(run or {})
            return request

        cases = [
            ('source divergent (reported head SHA)', 'ARTIFACT_SOURCE_DIFFERS', None,
             lambda: reported(dict(head_sha='c' * 40))),
            ('source divergent (artifact content)', 'STAGING_REJECTED', 'build-inputs revision differs from origin',
             lambda: self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'}, content_sha='c' * 40)),
            ('attempt divergent (declared name)', 'ARTIFACT_ATTEMPT_DIFFERS', None,
             lambda: dict(base(), origin=dict(base()['origin'], run_attempt=2))),
            ('attempt divergent (reported name)', 'ARTIFACT_IDENTITY_DIFFERS', None,
             lambda: reported(name='sbom-alpha-2')),
            ('run divergent', 'ARTIFACT_RUN_DIFFERS', None,
             lambda: reported(dict(id=999))),
            ('fork repository', 'ARTIFACT_REPOSITORY_DIFFERS', None,
             lambda: reported(dict(head_repository_id=1))),
            ('other branch', 'ARTIFACT_BRANCH_DIFFERS', None,
             lambda: reported(dict(head_branch='feature'))),
            ('expired artifact', 'ARTIFACT_EXPIRED', None, lambda: reported(expired=True)),
            ('subject divergent (index)', 'STAGING_REJECTED', 'validated index differs from the expected index digest',
             lambda: self.with_item(base(), expected_index_digest='sha256:' + 'e' * 64)),
            ('subject divergent (platform)', 'EXPECTED_SUBJECT_DIFFERS', None,
             lambda: self.with_item(base(), expected_platforms={'linux/amd64': 'sha256:' + 'e' * 64,
                                                                'linux/arm64': 'sha256:' + 'f' * 64})),
            ('invalid digest', 'INVALID_DIGEST', None, lambda: self.with_item(base(), expected_index_digest='sha256:XYZ')),
            ('invalid archive digest', 'INVALID_DIGEST', None, lambda: self.with_item(base(), archive_sha256='A' * 64)),
            ('archive bytes differ', 'ARCHIVE_DIGEST_DIFFERS', None, lambda: self.with_item(base(), archive_sha256='0' * 64)),
            ('reported digest differs', 'ARCHIVE_DIGEST_DIFFERS', None,
             lambda: reported(digest='sha256:' + '0' * 64)),
            ('bytes differ without a reported digest', 'ARCHIVE_DIGEST_DIFFERS', None, lambda: self.tampered(base())),
            ('artifact absent', 'ARTIFACT_MISSING', None, lambda: self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'}, register=False)),
            ('member absent', 'STAGING_REJECTED', 'artifact member missing: validated-index.json',
             lambda: self.replace_archive(base(), drop=('validated-index.json',))),
            ('unknown field (a tag)', 'INVALID_REQUEST', None, lambda: dict(base(), tag='stable')),
            ('duplicate framework', 'DUPLICATE_ARTIFACT', None,
             lambda: dict(base(), artifacts=base()['artifacts'] * 2)),
        ]
        for name, code, reason, build in cases:
            with self.subTest(case=name):
                self.source = FakeArtifacts()
                self.assert_rejected(build(), code, reason=reason)

    def tampered(self, request):
        identity = request['artifacts'][0]['artifact_id']
        saved, raw = self.source.items[identity]
        del saved['digest']
        self.source.items[identity] = (saved, raw[:-1] + bytes([raw[-1] ^ 1]))  # Same size, other bytes.
        return request

    def with_item(self, request, **values):
        request['artifacts'][0].update(values)
        return request

    def replace_archive(self, request, **options):
        item = request['artifacts'][0]
        raw, _ = artifact_zip(request['origin']['source_sha'], 'a-1', **options)
        self.source.add(item['artifact_id'], metadata(item['artifact_id'], item['name'], raw, request['origin']['run_id'],
                                                      request['origin']['source_sha']), raw)
        item.update(archive_sha256=sha256(raw), archive_bytes=len(raw))
        return request

    def test_identical_retry_reads_nothing_and_changes_nothing(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'})
        created = self.process(request)
        before, calls = tree(self.root), len(self.source.calls)
        retry = self.process(copy.deepcopy(request))
        self.assertEqual(retry['code'], 'LOT_ALREADY_PRESENT_IDENTICAL')
        self.assertEqual({k: retry[k] for k in ('batch_id', 'snapshot_id')}, {k: created[k] for k in ('batch_id', 'snapshot_id')})
        self.assertEqual((tree(self.root), len(self.source.calls)), (before, calls))

    def test_conflicting_retry_or_tampered_lot_fails_closed_and_is_never_repaired(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1', 'beta': 'a-2'})
        self.process(request)
        before = tree(self.root)
        for conflict, config in ((dict(request, artifacts=request['artifacts'][:1]), CONFIG),
                                 (request, dict(CONFIG, destination=dict(DESTINATION, prefix='other/v1')))):
            with self.subTest(config=config['destination']['prefix']), self.assertRaises(IngestionError) as raised:
                self.process(conflict, config)
            self.assertEqual(raised.exception.code, 'LOT_CONFLICT')
        self.assertEqual(tree(self.root), before)
        parquet = next((self.root / 'lots/lot-a/plan/batch/analytics').rglob('*.parquet'))
        parquet.write_bytes(parquet.read_bytes() + b'\0')
        tampered = tree(self.root)
        with self.assertRaises(IngestionError) as raised:
            self.process(request)
        self.assertEqual(raised.exception.code, 'LOT_INTEGRITY_FAILED')
        self.assertEqual(tree(self.root), tampered)

    def test_recorded_coverage_must_match_the_frozen_batch(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'})
        self.process(request)
        path = self.root / 'lots/lot-a/lot.json'
        lot = json.loads(path.read_bytes())
        lot['observation_ids'] = lot['observation_ids'][1:]  # A ledger that would hide a duplicate.
        path.write_bytes(canonical(lot))
        for check in (lambda: intake.verify(self.root, 'lot-a'), lambda: self.process(request)):
            with self.assertRaises(IngestionError) as raised:
                check()
            self.assertEqual((raised.exception.code, raised.exception.observed), ('LOT_INTEGRITY_FAILED', {'part': 'coverage'}))

    def test_artifacts_already_covered_by_another_lot_are_refused(self):
        self.process(self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'}))
        repeated = self.lot('lot-c', 101, 1, 'a' * 40, {'alpha': 'a-1'})
        error = self.assert_rejected_after_existing(repeated, 'ARTIFACT_ALREADY_INGESTED')
        self.assertEqual((error.observed['kind'], error.observed['name']), ('LOT', 'lot-a'))
        conflicting = self.lot('lot-d', 101, 1, 'a' * 40, {'alpha': 'other-bytes'})
        self.assert_rejected_after_existing(conflicting, 'ARTIFACT_IDENTITY_CONFLICT')
        self.assertEqual(sorted(p.name for p in (self.root / 'lots').iterdir()), ['lot-a'])

    def assert_rejected_after_existing(self, request, code):
        before = tree(self.root)
        with self.assertRaises(IngestionError) as raised:
            self.process(request)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(tree(self.root), before)
        return raised.exception

    def test_partial_failure_leaves_nothing_visible_and_the_same_request_then_succeeds(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1', 'beta': 'a-2'})
        second = request['artifacts'][1]['artifact_id']
        self.source.failures[second] = TimeoutError('transport')
        error = self.assert_rejected(request, 'ARTIFACT_SOURCE_ERROR')
        self.assertTrue(error.retryable)
        del self.source.failures[second]
        with patch.object(intake, 'save_plan', side_effect=IngestionError('PLAN_READBACK_DIFFERS', stage='FREEZE_PLAN')):
            self.assert_rejected(request, 'PLAN_READBACK_DIFFERS')
        self.assertEqual(self.process(request)['code'], 'LOT_CREATED')
        intake.verify(self.root, 'lot-a')

    @unittest.skipUnless(hasattr(signal, 'SIGKILL'), 'POSIX process kill required')
    def test_killed_intake_leaves_no_lot_and_requires_an_explicit_unlock(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'})
        artifacts = self.base / 'artifacts'
        artifacts.mkdir()
        for identity, (value, raw) in self.source.items.items():
            (artifacts / ('%d.json' % identity)).write_bytes(canonical(value))
            (artifacts / ('%d.zip' % identity)).write_bytes(raw)
        files = {'request.json': request, 'config.json': CONFIG}
        for name, value in files.items():
            (self.base / name).write_bytes(canonical(value))
        marker = self.base / 'inside-export'
        child = '\n'.join((
            'import sys, time',
            'from pathlib import Path',
            'from scripts.pipeline.analytics import intake',
            'def export(*args, **kwargs):',
            '    Path(sys.argv[1]).write_bytes(b"")',
            '    time.sleep(120)',
            'intake.export = export',
            'sys.exit(intake.main(sys.argv[2:]))'))
        process = subprocess.Popen([sys.executable, '-B', '-c', child, str(marker), 'process',
                                    '--request', str(self.base / 'request.json'), '--config', str(self.base / 'config.json'),
                                    '--artifacts', str(artifacts), '--root', str(self.root),
                                    '--report', str(self.base / 'killed.json')],
                                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(marker.exists(), 'the child never reached normalization')
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=30)
        self.assertFalse((self.root / 'lots').exists())
        self.assertTrue((self.root / '.intake.lock').exists())
        self.assertFalse((self.base / 'killed.json').exists())
        with self.assertRaises(IngestionError) as raised:
            intake.process(request, CONFIG, intake.DirectoryArtifacts(artifacts), self.root)
        self.assertEqual((raised.exception.code, raised.exception.retryable), ('INTAKE_BUSY', True))
        (self.root / '.intake.lock').unlink()  # The operator confirms no intake is running.
        result = intake.process(request, CONFIG, intake.DirectoryArtifacts(artifacts), self.root)
        self.assertEqual(result['code'], 'LOT_CREATED')
        intake.verify(self.root, 'lot-a')

    def test_independent_recovery_from_the_lot_directory_and_a_fake_transport(self):
        created = self.process(self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1', 'beta': 'a-2'}))
        reader = self.base / 'reader-copy'
        reader.mkdir()
        os.rename(self.root / 'lots', reader / 'lots')  # Only the lot directory travels; no request, source or index.
        self.source = None
        verified = intake.verify(reader, 'lot-a')
        self.assertEqual((verified['code'], verified['source_reads']), ('LOT_VERIFIED', 0))
        plan = load_plan(reader / 'lots/lot-a/plan')
        client = FakeS3('test-region-1')
        published = publish_snapshot(plan, S3Adapter(client, Destination(**DESTINATION)))
        self.assertEqual((published['code'], published['snapshot_id']), ('SNAPSHOT_CREATED', created['snapshot_id']))
        recovered = recover_snapshot(S3Adapter(client, Destination(**DESTINATION)), created['snapshot_id'], self.base / 'recovered')
        self.assertEqual(recovered['batch_id'], created['batch_id'])
        self.assertEqual(read_completed(self.base / 'recovered'), read_completed(reader / 'lots/lot-a/plan/batch'))

    def test_the_closed_v1_snapshot_is_registered_unchanged_and_blocks_its_artifacts(self):
        expected = s3_run.config(ROOT / 'policies/analytics/s3.json')
        plan = self.base / 'closed-plan'
        s3_run.unpack(ROOT / 'tests/fixtures/sbom-analytics/frozen-plan-v1.zip',
                      ROOT / 'tests/fixtures/sbom-analytics/frozen-plan-v1.json', plan, expected)
        before = tree(plan)
        registered = intake.register_closed(self.root, plan, 'sbom-analytics-v1')
        self.assertEqual((registered['code'], registered['batch_id'], registered['snapshot_id'], registered['observations']),
                         ('CLOSED_REGISTERED', expected['batch_id'], expected['snapshot_id'], 6))
        self.assertEqual(intake.register_closed(self.root, plan, 'sbom-analytics-v1')['code'], 'CLOSED_ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(tree(plan), before)
        historical = dict(repository='alric-corp/alric-containers-image-base', run_id=37806495087, run_attempt=1,
                          source_sha='4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3', event='push', ref='refs/heads/develop')
        artifacts = []
        for framework, identity in (('go1-26', 11562328737), ('go1-26-dev', 11562923040)):
            raw = (ROOT / 'tests/fixtures/sbom-analytics/build-artifacts' / ('sbom-%s-1.zip' % framework)).read_bytes()
            index = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read('validated-index.json'))['digest']
            name = 'sbom-%s-1' % framework
            # Real historical bytes; the saved metadata is a TEST double of the GitHub artifact record.
            self.source.add(identity, metadata(identity, name, raw, historical['run_id'], historical['source_sha'],
                                               repository_id=1360616627), raw)
            artifacts.append(dict(framework=framework, artifact_id=identity, name=name, archive_sha256=sha256(raw),
                                  archive_bytes=len(raw), expected_index_digest=index))
        request = dict(schema_version=1, lot_id='replay-of-closed', origin=historical, repository_id=1360616627,
                       image_registry='registry.example.invalid', repository_prefix='image-base-', artifacts=artifacts)
        with self.assertRaises(IngestionError) as raised:
            self.process(request)
        self.assertEqual(raised.exception.code, 'ARTIFACT_ALREADY_INGESTED')
        self.assertEqual((raised.exception.observed['kind'], raised.exception.observed['snapshot_id']),
                         ('CLOSED_IMPORTED', expected['snapshot_id']))
        self.assertFalse((self.root / 'lots').exists())
        self.assertEqual(tree(plan), before)

    def test_opt_in_only_never_wired_into_build_publication_promotion_or_cloud(self):
        workflows = '\n'.join(p.read_text() for p in (ROOT / '.github/workflows').glob('*.yml'))
        self.assertNotIn('analytics.intake', workflows)
        for path in (ROOT / 'scripts/pipeline').rglob('*.py'):
            if path.name != 'intake.py':
                self.assertNotIn('analytics.intake', path.read_text(), path)
                self.assertNotIn('analytics import intake', path.read_text(), path)
        source = (ROOT / 'scripts/pipeline/analytics/intake.py').read_text()
        imported = {alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
        self.assertEqual({m for m in imported if not m.startswith('scripts.pipeline.analytics')},
                         {'argparse', 'contextlib', 'dataclasses', 'os', 'pathlib', 're', 'tempfile'})
        self.assertNotIn('stable', source)
        for value in LAB_VALUES:  # Portable core: no LAB account, region, bucket or round identity.
            self.assertNotIn(value, source)
        with patch('socket.socket', side_effect=AssertionError('no network')), \
                patch('subprocess.run', side_effect=AssertionError('no executables')):
            result = self.process(self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'}))
        self.assertEqual((result['cloud_calls'], result['publication'], result['publication_authority']),
                         (0, 'NOT_PUBLISHED', False))

    def test_cli_process_verify_and_reports(self):
        request = self.lot('lot-a', 101, 1, 'a' * 40, {'alpha': 'a-1'})
        artifacts = self.base / 'artifacts'
        artifacts.mkdir()
        for identity, (value, raw) in self.source.items.items():
            (artifacts / ('%d.json' % identity)).write_bytes(canonical(value))
            (artifacts / ('%d.zip' % identity)).write_bytes(raw)
        (self.base / 'request.json').write_bytes(canonical(request))
        (self.base / 'config.json').write_bytes(canonical(CONFIG))
        base = ['process', '--request', str(self.base / 'request.json'), '--config', str(self.base / 'config.json'),
                '--artifacts', str(artifacts), '--root', str(self.root)]

        def run(argv):
            with patch('sys.stdout', new_callable=io.StringIO) as out:
                status = intake.main(argv)
            return status, json.loads(out.getvalue())

        status, result = run(base + ['--report', str(self.base / 'reports/process.json')])
        self.assertEqual((status, result['code']), (0, 'LOT_CREATED'))
        self.assertEqual(json.loads((self.base / 'reports/process.json').read_bytes()), result)
        status, result = run(['verify', '--root', str(self.root), '--lot', 'lot-a', '--report', str(self.base / 'reports/verify.json')])
        self.assertEqual((status, result['code']), (0, 'LOT_VERIFIED'))
        status, result = run(base + ['--report', str(self.root / 'inside.json')])
        self.assertEqual((status, result['code']), (1, 'REPORT_INSIDE_INPUT'))
        (artifacts / ('%d.zip' % request['artifacts'][0]['artifact_id'])).unlink()
        request['lot_id'] = 'lot-missing'
        (self.base / 'request.json').write_bytes(canonical(request))
        status, result = run(base + ['--report', str(self.base / 'reports/missing.json')])
        self.assertEqual((status, result['code'], result['status']), (1, 'ARTIFACT_MISSING', 'ERROR'))
        status, result = run(['process', '--root', str(self.root)])
        self.assertEqual((status, result['code']), (1, 'INTAKE_ARGUMENTS_INVALID'))


if __name__ == '__main__':
    unittest.main()
