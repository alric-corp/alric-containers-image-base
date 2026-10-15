"""Binding of downloaded build artifacts to their declared origin, offline and with a SYNTHETIC sample.

Every byte here is generated in a temporary directory and labelled SYNTHETIC:
no LAB account, repository, run or artifact identity is used. LAB real
artifacts and API records are covered separately in test_artifact_binding_lab.py.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.pipeline.analytics import artifact_binding
from scripts.pipeline.analytics.artifact_binding import bind
from scripts.pipeline.analytics.normalize import export, prepare, read_completed
from scripts.pipeline.analytics.spdx import AnalyticsError, canonical, document, sha256

ROOT = Path(__file__).resolve().parents[4]
SOURCE_SHA = 'a' * 40
ORIGIN = dict(repository='example-org/example-factory', run_id=4242, run_attempt=1, source_sha=SOURCE_SHA,
              event='push', ref='refs/heads/develop')
REPOSITORY_ID = 777


def oci(label):
    return 'sha256:' + hashlib.sha256(('SYNTHETIC ' + label).encode()).hexdigest()


def spdx(label, subject):
    """SYNTHETIC SPDX 2.3 document with the Factory documentDescribes/SHA256 subject contract."""
    return canonical(dict(
        spdxVersion='SPDX-2.3', SPDXID='SPDXRef-DOCUMENT', name='synthetic-' + label,
        documentNamespace='https://example.invalid/spdx/' + label,
        creationInfo=dict(created='2026-10-13T00:00:00Z', creators=['Tool: synthetic-test']),
        documentDescribes=['SPDXRef-Package-root'],
        packages=[dict(SPDXID='SPDXRef-Package-root', name='image', versionInfo='1',
                       checksums=[dict(algorithm='SHA256', checksumValue=subject[7:])]),
                  dict(SPDXID='SPDXRef-Package-lib', name='libexample', versionInfo='1.2.3',
                       licenseDeclared='MIT', externalRefs=[dict(referenceCategory='PACKAGE-MANAGER',
                                                                  referenceType='purl',
                                                                  referenceLocator='pkg:apk/example/libexample@1.2.3')])],
        relationships=[dict(spdxElementId='SPDXRef-DOCUMENT', relationshipType='DESCRIBES',
                            relatedSpdxElement='SPDXRef-Package-root')]))


def artifact(framework, *, source_sha=SOURCE_SHA):
    """The six members of a SYNTHETIC `sbom-<framework>-<attempt>` artifact plus its subjects."""
    subjects = {'index': oci(framework + ' index'), 'linux/amd64': oci(framework + ' amd64'),
                'linux/arm64': oci(framework + ' arm64')}
    members = {'sbom/sbom-index.spdx.json': spdx(framework + '-index', subjects['index']),
               'sbom/sbom-x86_64.spdx.json': spdx(framework + '-amd64', subjects['linux/amd64']),
               'sbom/sbom-aarch64.spdx.json': spdx(framework + '-arm64', subjects['linux/arm64'])}
    lock = canonical(dict(version='v1', contents=dict(packages=[dict(name='libexample', version='1.2.3')])))
    members['apko.lock.json'] = lock
    members['build-inputs.json'] = canonical(dict(revision=source_sha, lock_sha256=sha256(lock),
                                                  annotations=dict(revision=source_sha)))
    members['validated-index.json'] = canonical(dict(
        digest=subjects['index'], platforms={k: subjects[k] for k in ('linux/amd64', 'linux/arm64')},
        sboms=[dict(path=path, subject=subjects[key], sha256=sha256(members[path]))
               for key, path in (('index', 'sbom/sbom-index.spdx.json'), ('linux/amd64', 'sbom/sbom-x86_64.spdx.json'),
                                 ('linux/arm64', 'sbom/sbom-aarch64.spdx.json'))]))
    return members, subjects


class ArtifactBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sbom-artifact-binding-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()

    def sample(self, framework='go1-26', *, attempt=1, record_changes=None, members_change=None, archive=None):
        members, subjects = artifact(framework)
        if members_change:
            members_change(members)
        name = 'sbom-%s-%d' % (framework, attempt)
        path = self.inputs / (name + '.zip')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for member, body in members.items():
                zipped.writestr(zipfile.ZipInfo(member, date_time=(2026, 10, 13, 0, 0, 0)), body)
        raw = path.read_bytes()
        artifact_id = 9000 + len(framework)
        record = dict(id=artifact_id, name=name, size_in_bytes=len(raw), expired=False,
                      digest='sha256:' + sha256(raw), workflow_run=dict(
                          id=ORIGIN['run_id'], repository_id=REPOSITORY_ID, head_repository_id=REPOSITORY_ID,
                          head_branch='develop', head_sha=SOURCE_SHA))
        if record_changes:
            record_changes(record)  # only the saved API record diverges; the declared identity stays
        (self.inputs / (name + '.artifact-api.json')).write_bytes(canonical(record))
        return dict(framework=framework, name=name, path=archive or path.name, artifact_id=artifact_id,
                    api_record=name + '.artifact-api.json', expected_subjects=dict(subjects),
                    subjects_source='SYNTHETIC publication evidence')

    def manifest(self, *items, **changes):
        value = dict(schema_version=1, sample_classification='SYNTHETIC', origin=dict(ORIGIN),
                     repository_id=REPOSITORY_ID, image_registry='registry.example.invalid',
                     repository_prefix='image-base-', archive_digest_policy='REQUIRED',
                     artifacts=list(items) or [self.sample()])
        value.update(changes)
        return value

    def bind(self, manifest, name='work'):
        return bind(manifest, self.root / name, base_directory=self.inputs)

    def assert_refused(self, manifest, pattern):
        target = self.root / 'refused'
        with self.assertRaisesRegex(AnalyticsError, pattern):
            bind(manifest, target, base_directory=self.inputs)
        self.assertFalse(target.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('.sbom-')], [])

    def test_bound_artifacts_stage_for_the_unchanged_normalizer_without_cloud(self):
        items = [self.sample('go1-26'), self.sample('go1-26-dev')]

        def refuse(*args, **kwargs):
            raise AssertionError('network access attempted')

        with patch.dict(sys.modules, {'boto3': None, 'botocore': None}), \
                patch.object(socket, 'socket', refuse), patch.object(socket, 'create_connection', refuse):
            receipt = self.bind(self.manifest(*items))
            context = document((self.root / 'work/context.json').read_bytes())
            projection = prepare(context, base_directory=self.root / 'work')
            batch = Path(export(projection, self.root / 'output')['path'])
        self.assertEqual(receipt['status'], 'BOUND_AND_STAGED')
        self.assertEqual((receipt['cloud_calls'], receipt['network_calls'], receipt['ingestion'],
                          receipt['custody_record'], receipt['hosted_execution']),
                         (0, 0, 'NOT_PERFORMED', 'NOT_REQUIRED', 'NOT_PROVEN'))
        self.assertEqual(receipt['sample_classification'], 'SYNTHETIC')
        for entry in receipt['artifacts']:
            self.assertEqual(set(entry['checks'].values()), {'MATCHED'}, entry['checks'])
        stored = document((self.root / 'work/binding-receipt.json').read_bytes())
        self.assertEqual(stored, receipt)
        self.assertEqual(receipt['staging_receipt_sha256'],
                         sha256((self.root / 'work/staging-receipt.json').read_bytes()))
        rows = read_completed(batch)['observations']
        self.assertEqual({(r['repository'], r['run_id'], r['run_attempt'], r['source_sha']) for r in rows},
                         {(ORIGIN['repository'], 4242, 1, SOURCE_SHA)})
        self.assertEqual(len(rows), 6)

    def test_divergent_run_attempt_source_or_repository_is_refused(self):
        def run(**changes):
            return lambda record: record['workflow_run'].update(changes)

        cases = [
            (run(id=4243), 'ARTIFACT_RUN_DIFFERS'),
            (run(head_sha='b' * 40), 'ARTIFACT_SOURCE_DIFFERS'),
            (run(repository_id=778), 'ARTIFACT_REPOSITORY_DIFFERS'),
            (run(head_repository_id=999), 'ARTIFACT_REPOSITORY_DIFFERS'),
            (run(head_branch='feature/x'), 'ARTIFACT_BRANCH_DIFFERS'),
            (lambda record: record.update(id=1), 'ARTIFACT_ID_DIFFERS'),
            (lambda record: record.update(name='sbom-go1-26-2'), 'ARTIFACT_NAME_DIFFERS'),
        ]
        for change, pattern in cases:
            with self.subTest(pattern=pattern):
                self.assert_refused(self.manifest(self.sample(record_changes=change)), pattern)
        self.assert_refused(self.manifest(self.sample(attempt=2)), 'ARTIFACT_ATTEMPT_DIFFERS')
        other_commit = self.sample(members_change=lambda m: m.update({'build-inputs.json': canonical(
            dict(revision='c' * 40, lock_sha256=sha256(m['apko.lock.json'])))}))
        self.assert_refused(self.manifest(other_commit), 'STAGING_REFUSED: .*revision differs')

    def test_divergent_subjects_or_archive_bytes_are_refused(self):
        item = self.sample()
        index = copy.deepcopy(item)
        index['expected_subjects']['index'] = oci('another index')
        self.assert_refused(self.manifest(index), 'STAGING_REFUSED: .*expected index digest')
        platform = copy.deepcopy(item)
        platform['expected_subjects']['linux/arm64'] = oci('another arm64')
        self.assert_refused(self.manifest(platform), 'SUBJECT_DIFFERS')
        swapped = copy.deepcopy(item)
        subjects = swapped['expected_subjects']
        subjects['linux/amd64'], subjects['linux/arm64'] = subjects['linux/arm64'], subjects['linux/amd64']
        self.assert_refused(self.manifest(swapped), 'SUBJECT_DIFFERS')
        tampered = self.sample(record_changes=lambda r: r.update(digest='sha256:' + '0' * 64))
        self.assert_refused(self.manifest(tampered), 'ARCHIVE_DIGEST_DIFFERS')
        resized = self.sample(record_changes=lambda r: r.update(size_in_bytes=1))
        self.assert_refused(self.manifest(resized), 'ARCHIVE_SIZE_DIFFERS')

    def test_absent_facts_are_never_inferred(self):
        missing_digest = self.sample(record_changes=lambda r: r.pop('digest'))
        self.assert_refused(self.manifest(missing_digest), 'ARCHIVE_DIGEST_NOT_PROVIDED')
        receipt = self.bind(self.manifest(missing_digest, archive_digest_policy='RECORD_ONLY'))
        self.assertEqual(receipt['artifacts'][0]['checks']['archive_digest'], 'NOT_PROVIDED')
        no_head = self.sample('go1-25', record_changes=lambda r: [r['workflow_run'].pop(k)
                                                                    for k in ('head_repository_id', 'head_branch')])
        receipt = self.bind(self.manifest(no_head), 'no-head')
        self.assertEqual({k: receipt['artifacts'][0]['checks'][k] for k in ('head_repository', 'branch')},
                         {'head_repository': 'NOT_PROVIDED', 'branch': 'NOT_PROVIDED'})
        incomplete = self.sample('java21', record_changes=lambda r: r['workflow_run'].pop('head_sha'))
        self.assert_refused(self.manifest(incomplete), 'ARTIFACT_RECORD_INCOMPLETE')
        for key in ('event', 'ref'):
            origin = dict(ORIGIN)
            origin.pop(key)
            self.assert_refused(self.manifest(self.sample('java25'), origin=origin), 'STAGING_REFUSED')
        subjects = self.sample('nodejs22')
        subjects['expected_subjects'].pop('linux/arm64')
        self.assert_refused(self.manifest(subjects), 'expected_subjects')
        for key in ('sample_classification', 'repository_id', 'archive_digest_policy'):
            broken = self.manifest()
            broken.pop(key)
            self.assert_refused(broken, 'missing/unknown fields')
        self.assert_refused(self.manifest(image_registry='<REGISTRY>'), 'placeholder')

    def test_extracted_directory_is_record_only(self):
        item = self.sample()
        directory = self.inputs / 'extracted'
        with zipfile.ZipFile(self.inputs / item['path']) as zipped:
            zipped.extractall(directory)
        item = dict(item, path='extracted')
        self.assert_refused(self.manifest(item), 'ARCHIVE_NOT_VERIFIABLE')
        receipt = self.bind(self.manifest(item, archive_digest_policy='RECORD_ONLY'))
        self.assertEqual(receipt['artifacts'][0]['checks']['archive_digest'], 'NOT_APPLICABLE')
        self.assertIsNone(receipt['artifacts'][0]['archive_sha256'])

    def test_staged_bytes_are_the_hashed_bytes(self):
        item = self.sample()
        original = (self.inputs / item['path']).read_bytes()
        real_stage = artifact_binding.stage

        def swap_then_stage(*args, **kwargs):
            # The integrator's file changes after hashing; staging must still use the hashed copy.
            (self.inputs / item['path']).write_bytes(b'not the artifact')
            return real_stage(*args, **kwargs)

        with patch.object(artifact_binding, 'stage', swap_then_stage):
            receipt = self.bind(self.manifest(item))
        self.assertEqual(receipt['artifacts'][0]['archive_sha256'], sha256(original))

    def test_cli_reports_a_stable_code_and_creates_nothing_on_refusal(self):
        item = self.sample(record_changes=lambda r: r['workflow_run'].update(id=1))
        path = self.inputs / 'binding.json'
        path.write_bytes(canonical(self.manifest(item)))
        with patch('sys.stderr') as stderr:
            self.assertEqual(artifact_binding.main(['--manifest', str(path), '--work', str(self.root / 'cli')]), 1)
        message = ''.join(call.args[0] for call in stderr.write.call_args_list)
        self.assertEqual(json.loads(message.splitlines()[0])['code'], 'ARTIFACT_RUN_DIFFERS')
        self.assertFalse((self.root / 'cli').exists())
        path.write_bytes(canonical(self.manifest(self.sample('go1-26-dev'))))
        with patch('sys.stdout'):
            self.assertEqual(artifact_binding.main(['--manifest', str(path), '--work', str(self.root / 'cli')]), 0)
        self.assertTrue((self.root / 'cli/binding-receipt.json').is_file())


class BindingBoundaryTests(unittest.TestCase):
    def test_adapter_is_opt_in_and_free_of_sandbox_identity(self):
        source = (ROOT / 'scripts/pipeline/analytics/artifact_binding.py').read_text(encoding='utf-8')
        for value in ('712107929769', '1360616627', '178685987', '37806495087', 'alric', 'itau', 'boto3'):
            self.assertNotIn(value, source)
        for workflow in (ROOT / '.github/workflows').glob('*.yml'):
            self.assertNotIn('artifact_binding', workflow.read_text(encoding='utf-8'), workflow.name)

    def test_adapter_closure_needs_no_release_store_custody_or_sdk(self):
        code = '\n'.join((
            'import sys',
            'class Block:',
            '    def find_spec(self, name, path=None, target=None):',
            '        blocked = ("boto3", "botocore", "scripts.pipeline.release.release_store",',
            '                   "scripts.pipeline.release.evidence_custody", "scripts.pipeline.release.evidence_store",',
            '                   "scripts.pipeline.release.release_manifest", "scripts.pipeline.governance")',
            '        if name.startswith(blocked):',
            '            raise ImportError("blocked " + name)',
            'sys.meta_path.insert(0, Block())',
            'import scripts.pipeline.analytics.artifact_binding',
            'print("ok")'))
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True,
                                timeout=60)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'ok'), result.stderr)


if __name__ == '__main__':
    unittest.main()
