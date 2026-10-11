"""Factory sbom-<framework>-<attempt> artifacts through the unchanged normalizer, offline."""
import ast
import copy
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.pipeline.analytics import artifact_input
from scripts.pipeline.analytics.artifact_input import CONSUMED, stage
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError
from scripts.pipeline.analytics.normalize import export, prepare, read_completed
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import prepare_snapshot, publish_snapshot, recover_snapshot, save_plan
from scripts.pipeline.analytics.spdx import AnalyticsError, canonical, document, sha256
from tests.unit.pipeline.analytics.s3_support import FakeS3

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / 'tests/fixtures/sbom-analytics/build-artifacts'
ZIPS = {'go1-26': FIXTURES / 'sbom-go1-26-1.zip', 'go1-26-dev': FIXTURES / 'sbom-go1-26-dev-1.zip'}
ARTIFACT_IDS = {'go1-26': 11562328737, 'go1-26-dev': 11562923040}
HISTORICAL = dict(repository='alric-corp/alric-containers-image-base', run_id=37806495087, run_attempt=1,
                  source_sha='4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3', event='push', ref='refs/heads/develop')
REGISTRY = 'registry.example.invalid'


def members(path):
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def write_zip(path, contents, *, mode=None, flag_bits=0, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, 'w', compression) as archive:
        for name, body in contents.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 8, 16, 10, 0))
            info.compress_type = compression
            info.external_attr = (mode if mode is not None else stat.S_IFREG | 0o644) << 16
            archive.writestr(info, body)
        for info in archive.infolist():
            info.flag_bits |= flag_bits  # zipfile resets local flags; the central directory keeps these.
    return path


def selection(paths, *, origin=HISTORICAL, attempt=None, ids=True, **extra):
    attempt = origin['run_attempt'] if attempt is None else attempt
    artifacts = []
    for framework, path in paths.items():
        item = dict(framework=framework, name='sbom-%s-%d' % (framework, attempt), path=str(path))
        if ids:
            item['artifact_id'] = ARTIFACT_IDS[framework]
        artifacts.append(item)
    value = dict(schema_version=1, origin=dict(origin), image_registry=REGISTRY, repository_prefix='image-base-',
                 artifacts=artifacts)
    value.update(extra)
    return value


class ArtifactInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sbom-artifact-input-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def staged(self, value, name='work'):
        receipt = stage(value, self.root / name)
        context = document((self.root / name / 'context.json').read_bytes())
        return receipt, context, prepare(context, base_directory=self.root / name)

    def corporate_zip(self, framework, transform=None):
        """DERIVED: only the six reported members, re-zipped from the real LAB artifact."""
        contents = {name: body for name, body in members(ZIPS[framework]).items() if name in CONSUMED}
        if transform:
            transform(contents)
        return write_zip(self.root / ('corporate-%s-%d.zip' % (framework, len(list(self.root.iterdir())))), contents)

    def assert_rejected(self, value, pattern):
        target = self.root / ('rejected-%d' % len(list(self.root.iterdir())))
        with self.assertRaisesRegex(AnalyticsError, pattern):
            stage(value, target)
        self.assertFalse(target.exists())

    def test_corporate_shaped_zip_and_extracted_directory_stage_the_same_batch(self):
        _, _, real = self.staged(selection(ZIPS), 'real')
        derived = {f: self.corporate_zip(f) for f in ZIPS}
        receipt, _, six = self.staged(selection(derived), 'six')
        self.assertEqual(six.records, real.records)
        self.assertTrue(all(item['unconsumed'] == {} for item in receipt['artifacts']))
        directories = {}
        for framework, path in derived.items():
            directory = self.root / ('sbom-%s-1' % framework)
            for name, body in members(path).items():
                (directory / name).parent.mkdir(parents=True, exist_ok=True)
                (directory / name).write_bytes(body)
            directories[framework] = directory
        receipt, _, extracted = self.staged(selection(directories), 'directory')
        self.assertEqual(extracted.records, real.records)
        self.assertIsNone(receipt['artifacts'][0]['archive_sha256'])

    def test_index_and_platform_documents_stay_separate_and_bound_to_their_subjects(self):
        _, context, projection = self.staged(selection({'go1-26': ZIPS['go1-26']}))
        index = document(members(ZIPS['go1-26'])['validated-index.json'])
        expected = {None: index['digest'], 'linux/amd64': index['platforms']['linux/amd64'],
                    'linux/arm64': index['platforms']['linux/arm64']}
        hashes = {r['path']: r['sha256'] for r in index['sboms']}
        rows = document(projection.records)['observations']
        self.assertEqual({r['document_platform']: r['subject_digest'] for r in rows}, expected)
        self.assertEqual({r['document_platform']: r['sbom_sha256'] for r in rows},
                         {None: hashes['sbom/sbom-index.spdx.json'], 'linux/amd64': hashes['sbom/sbom-x86_64.spdx.json'],
                          'linux/arm64': hashes['sbom/sbom-aarch64.spdx.json']})
        self.assertEqual({r['document_platform']: r['sbom_scope'] for r in rows},
                         {None: 'index', 'linux/amd64': 'platform', 'linux/arm64': 'platform'})
        packages = document(projection.records)['packages']
        subjects = [p for p in packages if p['is_document_subject']]
        self.assertEqual(len(subjects), 3)
        self.assertEqual(context['images'][0]['validation']['reference'],
                         'alric-corp/alric-containers-image-base@run:37806495087/attempt:1/artifact:sbom-go1-26-1/id:11562328737')

    def test_new_run_identity_changes_observations_but_not_package_records(self):
        _, _, first = self.staged(selection(ZIPS), 'first')
        other = dict(HISTORICAL, repository='example-org/example-factory', run_id=4242, run_attempt=2)
        _, _, second = self.staged(selection(ZIPS, origin=other), 'second')
        a, b = document(first.records), document(second.records)
        self.assertEqual(a['packages'], b['packages'])
        self.assertTrue({r['observation_id'] for r in a['observations']}.isdisjoint(r['observation_id'] for r in b['observations']))
        self.assertEqual({(r['repository'], r['run_id'], r['run_attempt']) for r in b['observations']},
                         {('example-org/example-factory', 4242, 2)})
        self.assertNotEqual(first.batch_id, second.batch_id)
        output = self.root / 'batches'
        self.assertEqual(export(second, output)['status'], 'CREATED')
        self.assertEqual(export(second, output)['status'], 'ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(export(first, output)['status'], 'CREATED')

    def test_missing_consumed_member_is_rejected_before_anything_is_staged(self):
        for name in CONSUMED:
            path = self.corporate_zip('go1-26', lambda contents: contents.pop(name))
            self.assert_rejected(selection({'go1-26': path}), 'artifact member missing: ' + name)

    def test_hash_subject_and_metadata_contradictions_are_rejected(self):
        def index_change(change):
            def transform(contents):
                value = json.loads(contents['validated-index.json'])
                change(value)
                contents['validated-index.json'] = canonical(value)
            return transform

        def swap(contents):
            contents['sbom/sbom-x86_64.spdx.json'], contents['sbom/sbom-aarch64.spdx.json'] = (
                contents['sbom/sbom-aarch64.spdx.json'], contents['sbom/sbom-x86_64.spdx.json'])

        def swap_with_hashes(contents):
            swap(contents)
            index_change(lambda v: [r.update(sha256=sha256(contents[r['path']])) for r in v['sboms']])(contents)

        def tamper(contents):
            contents['sbom/sbom-x86_64.spdx.json'] = contents['sbom/sbom-x86_64.spdx.json'].replace(b'"name"', b'"name" ', 1)

        cases = [
            (tamper, 'hash mismatch'),
            (index_change(lambda v: v['sboms'][0].update(sha256='0' * 64)), 'hash mismatch'),
            (swap, 'hash mismatch'),
            (swap_with_hashes, 'subject checksum differs'),
            (index_change(lambda v: v.update(digest='sha256:' + 'e' * 64)), 'subject checksum differs'),
            (index_change(lambda v: v['platforms'].update({'linux/amd64': v['platforms']['linux/arm64'],
                                                           'linux/arm64': v['platforms']['linux/amd64']})),
             'subject checksum differs'),
            (index_change(lambda v: v.update(extra=True)), 'missing/unknown fields'),
            (index_change(lambda v: v['sboms'].pop()), 'SBOM inventory differs'),
            (lambda c: c.update({'apko.lock.json': c['apko.lock.json'] + b' '}), 'lock_sha256'),
            (lambda c: c.update({'build-inputs.json': c['build-inputs.json'].replace(b'4c1783e8', b'5c1783e8', 1)}),
             'revision differs'),
        ]
        for transform, pattern in cases:
            with self.subTest(pattern=pattern):
                self.assert_rejected(selection({'go1-26': self.corporate_zip('go1-26', transform)}), pattern)
        path = self.corporate_zip('go1-26')
        self.assert_rejected(selection({'go1-26': path}, origin=dict(HISTORICAL, source_sha='f' * 40)), 'revision differs')
        self.assert_rejected(selection({'go1-26': path}, attempt=2), 'artifact name differs')
        wrong = selection({'go1-26': path})
        wrong['artifacts'][0]['framework'] = 'go1-26-dev'
        self.assert_rejected(wrong, 'artifact name differs')
        expected = selection({'go1-26': path})
        expected['artifacts'][0]['expected_index_digest'] = 'sha256:' + 'a' * 64
        self.assert_rejected(expected, 'expected index digest')
        expected['artifacts'][0]['expected_index_digest'] = document(members(path)['validated-index.json'])['digest']
        self.assertEqual(stage(expected, self.root / 'expected')['status'], 'STAGED')

    def test_unsafe_or_malformed_artifacts_are_rejected(self):
        base = {name: body for name, body in members(ZIPS['go1-26']).items() if name in CONSUMED}
        cases = [
            (dict(base, **{'../escape.json': b'{}'}), 'unsafe artifact member path'),
            (dict(base, **{'/absolute.json': b'{}'}), 'unsafe artifact member path'),
            (dict(base, **{'sbom\\windows.json': b'{}'}), 'unsafe artifact member path'),
            (dict(base, **{'sbom/./x.json': b'{}'}), 'unsafe artifact member path'),
        ]
        for contents, pattern in cases:
            with self.subTest(pattern=pattern, names=sorted(set(contents) - set(base))):
                self.assert_rejected(selection({'go1-26': write_zip(self.root / 'unsafe.zip', contents)}), pattern)
        traversal = write_zip(self.root / 'directory-entry.zip', base)
        with zipfile.ZipFile(traversal, 'a') as archive:
            entry = zipfile.ZipInfo('../outside/')
            entry.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(entry, b'')
        self.assert_rejected(selection({'go1-26': traversal}), 'unsafe artifact member path')
        link = write_zip(self.root / 'link.zip', base, mode=stat.S_IFLNK | 0o777)
        self.assert_rejected(selection({'go1-26': link}), 'regular file')
        encrypted = write_zip(self.root / 'encrypted.zip', base, flag_bits=1)
        self.assert_rejected(selection({'go1-26': encrypted}), 'encrypted')
        bzip = write_zip(self.root / 'bzip.zip', base, compression=zipfile.ZIP_BZIP2)
        self.assert_rejected(selection({'go1-26': bzip}), 'unsupported artifact compression')
        truncated = self.root / 'truncated.zip'
        truncated.write_bytes(ZIPS['go1-26'].read_bytes()[:-100])
        self.assert_rejected(selection({'go1-26': truncated}), 'invalid artifact ZIP')
        duplicate = self.root / 'duplicate.zip'
        with zipfile.ZipFile(duplicate, 'w') as archive, patch('warnings.warn'):
            for name, body in base.items():
                archive.writestr(name, body)
            archive.writestr('validated-index.json', base['validated-index.json'])
        self.assert_rejected(selection({'go1-26': duplicate}), 'duplicate artifact member')
        many = dict(base, **{'extra/%02d.json' % i: b'{}' for i in range(artifact_input.UNCONSUMED_LIMIT + 1)})
        self.assert_rejected(selection({'go1-26': write_zip(self.root / 'many.zip', many)}), 'member count limit')
        with patch.dict(artifact_input.LIMITS, document_bytes=1024):
            self.assert_rejected(selection({'go1-26': self.corporate_zip('go1-26')}), 'member byte limit')
        directory = self.root / 'linked'
        directory.mkdir()
        (directory / 'validated-index.json').symlink_to(self.root / 'elsewhere.json')
        self.assert_rejected(selection({'go1-26': directory}), 'symlink')
        plain = self.root / 'artifact.tar'
        plain.write_bytes(b'not a zip')
        self.assert_rejected(selection({'go1-26': plain}), 'directory or .zip')
        existing = self.root / 'existing'
        existing.mkdir()
        for path in (ZIPS['go1-26'], truncated):  # Refused before any artifact is read.
            with self.assertRaisesRegex(AnalyticsError, 'staging directory must not exist'):
                stage(selection({'go1-26': path}), existing)
        self.assertEqual(list(existing.iterdir()), [])

    def test_selection_and_destination_require_explicit_values_without_lab_defaults(self):
        value = selection({'go1-26': ZIPS['go1-26']})
        for key in ('image_registry', 'repository_prefix', 'origin', 'artifacts'):
            broken = copy.deepcopy(value)
            del broken[key]
            self.assert_rejected(broken, 'missing/unknown fields')
        for registry in ('', 'https://registry.example.invalid', '<REGISTRY>', 'Registry.Example', 'host/'):
            self.assert_rejected(dict(value, image_registry=registry), 'registry host required')
        self.assert_rejected(dict(value, unexpected=True), 'missing/unknown fields')
        self.assert_rejected(dict(value, origin=dict(HISTORICAL, run_id='37806495087')), 'run_id')
        broken = copy.deepcopy(value)
        broken['artifacts'][0]['unexpected'] = 1
        self.assert_rejected(broken, 'missing/unknown fields')
        for destination in (dict(bucket='<ANALYTICS_BUCKET>', prefix='sbom', region='sa-east-1', expected_bucket_owner=None),
                            dict(bucket='example-sbom-analytics', prefix='../sbom', region='sa-east-1', expected_bucket_owner=None),
                            dict(bucket='example-sbom-analytics', prefix='sbom', region='sa-east-1',
                                 expected_bucket_owner='<AWS_ACCOUNT_ID>')):
            with self.assertRaises(IngestionError):
                Destination(**destination)
        with self.assertRaises(TypeError):
            Destination(bucket='example-sbom-analytics', prefix='sbom', region='sa-east-1')

    def test_offline_staging_plan_and_injected_transport_make_no_sdk_or_network_calls(self):
        def refuse(*args, **kwargs):
            raise AssertionError('network access attempted')

        destination = Destination('example-sbom-analytics', 'sbom-analytics/v1', 'sa-east-1', '000000000000')
        with patch.dict(sys.modules, {'boto3': None, 'botocore': None}), \
                patch.object(socket, 'socket', refuse), patch.object(socket, 'create_connection', refuse):
            _, _, projection = self.staged(selection(ZIPS))
            batch = Path(export(projection, self.root / 'output')['path'])
            plan = prepare_snapshot(batch, destination)
            self.assertEqual(save_plan(plan, self.root / 'plan'), 'CREATED')
            client = FakeS3('sa-east-1')
            adapter = S3Adapter(client, destination)
            self.assertEqual(publish_snapshot(plan, adapter)['code'], 'SNAPSHOT_CREATED')
            self.assertEqual(publish_snapshot(plan, adapter)['code'], 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
            recover_snapshot(adapter, plan.snapshot_id, self.root / 'recovered')
            self.assertEqual(read_completed(self.root / 'recovered'), document(projection.records))
        self.assertTrue(client.calls)
        for _, request in client.calls:
            self.assertEqual(request['Bucket'], 'example-sbom-analytics')
            self.assertEqual(request.get('ExpectedBucketOwner'), '000000000000')
            self.assertTrue(request.get('Key', request.get('Prefix', '')).startswith('sbom-analytics/v1/snapshots/'))

    def test_nulls_arrays_licenses_and_references_keep_their_source_shape(self):
        _, _, projection = self.staged(selection(ZIPS), 'real')
        rows = document(projection.records)['packages']
        self.assertEqual(sum(r['purls'] is None for r in rows), 32)  # This corpus only, as read by Athena.
        self.assertEqual(sum(r['purls'] == [] for r in rows), 0)
        self.assertTrue(any(r['purls'] and r['external_references'] for r in rows))
        self.assertTrue(all(ref['comment'] is None for r in rows for ref in r['external_references'] or ()))
        self.assertTrue({r['license_declared'] for r in rows} - {None, 'NOASSERTION'})

        def synthetic(contents):  # SYNTHETIC: one added record, with the validated-index hash kept consistent.
            value = json.loads(contents['sbom/sbom-x86_64.spdx.json'])
            value['packages'].append(dict(SPDXID='SPDXRef-synthetic-empty', name='synthetic-empty', externalRefs=[]))
            contents['sbom/sbom-x86_64.spdx.json'] = canonical(value)
            index = json.loads(contents['validated-index.json'])
            for record in index['sboms']:
                record['sha256'] = sha256(contents[record['path']])
            contents['validated-index.json'] = canonical(index)

        _, _, changed = self.staged(selection({'go1-26': self.corporate_zip('go1-26', synthetic)}), 'synthetic')
        row = next(r for r in document(changed.records)['packages'] if r['package_spdx_id'] == 'SPDXRef-synthetic-empty')
        self.assertEqual((row['package_version'], row['purls'], row['external_references'], row['license_declared']),
                         (None, [], [], None))
        batch = Path(export(changed, self.root / 'output')['path'])
        recovered = next(r for r in read_completed(batch)['packages'] if r['package_spdx_id'] == 'SPDXRef-synthetic-empty')
        self.assertEqual(recovered, row)  # Local Parquet only; Athena's empty-array reading is not exercised.

    def test_cli_writes_context_for_the_existing_normalizer_cli(self):
        path = self.root / 'selection.json'
        value = selection({'go1-26': ZIPS['go1-26']})
        path.write_bytes(canonical(value))
        with patch('sys.stdout'):
            self.assertEqual(artifact_input.main(['--selection', str(path), '--work', str(self.root / 'work')]), 0)
        from scripts.pipeline.analytics import normalize
        with patch('sys.stdout'):
            self.assertEqual(normalize.main(['--input', str(self.root / 'work/context.json'),
                                             '--output', str(self.root / 'output')]), 0)
        with patch('sys.stderr'):
            self.assertEqual(artifact_input.main(['--selection', str(path), '--work', str(self.root / 'work')]), 1)


class ConsumerClosureTests(unittest.TestCase):
    def test_consumer_modules_import_without_the_lab_release_platform(self):
        tree = ast.parse((ROOT / 'scripts/pipeline/analytics/normalize.py').read_text())
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn('scripts.pipeline.release.release_manifest', imported)
        code = '\n'.join((
            'import sys',
            'class Block:',
            '    def find_spec(self, name, path=None, target=None):',
            '        blocked = ("boto3", "botocore", "scripts.pipeline.release.release_manifest",',
            '                   "scripts.pipeline.governance", "scripts.pipeline.consumer_apps", "scripts.pipeline.runtime")',
            '        if name.startswith(blocked):',
            '            raise ImportError("blocked " + name)',
            'sys.meta_path.insert(0, Block())',
            'import scripts.pipeline.analytics.artifact_input, scripts.pipeline.analytics.ingest',
            'import scripts.pipeline.analytics.s3_ingestion, scripts.pipeline.analytics.snapshot',
            'print(sorted(m for m in sys.modules if m.startswith("scripts.")))'))
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = set(ast.literal_eval(result.stdout))
        self.assertEqual({m for m in loaded if not m.startswith('scripts.pipeline.analytics')} - {'scripts'},
                         {'scripts.pipeline', 'scripts.pipeline.artifacts', 'scripts.pipeline.artifacts.image_reference',
                          'scripts.pipeline.artifacts.oci_artifact', 'scripts.pipeline.release',
                          'scripts.pipeline.release.verify_publication'})


if __name__ == '__main__':
    unittest.main()
