"""Source inventory security boundaries, using only synthetic AWS/GitHub data."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import stat
import unittest
from unittest.mock import patch
import zipfile

from scripts.pipeline.consumer_apps import inventory
from scripts.pipeline.consumer_apps.model import CATALOG
from scripts.pipeline.runtime import runtime_images

REPOSITORY = 'alric-corp/alric-containers-image-base'
REGISTRY = '123456789012.dkr.ecr.us-east-1.amazonaws.com'
RUN_ID = 12345
SHA = 'a' * 40


def encoded(value):
    return json.dumps(value).encode()


def digest(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as result:
        for name, raw in files.items():
            result.writestr(name, raw)
    return buffer.getvalue()


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.run = {'id': RUN_ID, 'run_attempt': 1, 'head_sha': SHA,
                    'head_branch': 'main', 'event': 'workflow_dispatch',
                    'path': '.github/workflows/catalog-certification.yml',
                    'status': 'completed', 'conclusion': 'success',
                    'repository': {'id': 42, 'full_name': REPOSITORY},
                    'head_repository': {'id': 42, 'full_name': REPOSITORY}}
        self.expected, self.remote, self.ecr, self.files, self.archives = {}, {}, {}, {}, {}
        self.arts, self.jobs = [], []
        self.contracts = runtime_images.plan(list(CATALOG))[0]
        for index, framework in enumerate(CATALOG):
            platforms = {f'linux/{arch}': digest(f'{framework}-{arch}'.encode())
                         for arch in ('amd64', 'arm64')}
            remote = {'schemaVersion': 2, 'mediaType': inventory.INDEX,
                      'manifests': [{'digest': value, 'platform': {
                          'os': 'linux', 'architecture': key.split('/')[1]}}
                          for key, value in platforms.items()]}
            raw = encoded(remote)
            self.remote[framework] = raw
            self.expected[framework] = {'digest': digest(raw), 'platforms': platforms}
            self.ecr[framework] = {'imageDetails': [{
                'registryId': '123456789012', 'repositoryName': f'image-base-{framework}',
                'imageDigest': digest(raw), 'imageTags': [f'210926-0422-r{RUN_ID}-a1'],
                'imagePushedAt': '2026-09-21T07:22:00+00:00',
                'imageManifestMediaType': inventory.INDEX}]}
            self.arts.append(self.artifact(100 + index, f'publication-{framework}-1'))
            self.jobs.append(self.job(200 + index, f'build-base-images / Build & push {framework}',
                                      [{'name': name, 'status': 'completed', 'conclusion': 'success'}
                                       for name in inventory.REQUIRED_STEPS]))
        for index, framework in enumerate(self.contracts):
            self.arts.append(self.artifact(1000 + index, f'runtime-{framework}-1'))
            self.jobs.append(self.job(2000 + index, f'Runtime {framework} (both architectures)'))
        for framework in CATALOG:
            expected = self.expected[framework]
            plan = runtime_images.publication_contract(framework, list(CATALOG))
            contract_index = self.contracts.index(plan['contract_framework'])
            runtime = self.expected[plan['runtime_framework']]
            dev = self.expected[plan['dev_framework']] if plan['dev_framework'] else None
            gate = {**plan, 'passed': True, 'run_id': str(RUN_ID), 'run_attempt': 1,
                    'selected_attempt': 1, 'revision': SHA, 'repository': REPOSITORY,
                    'index_digest': runtime['digest'], 'platforms': runtime['platforms'],
                    'dev_index_digest': dev['digest'] if dev else None,
                    'dev_platforms': dev['platforms'] if dev else None,
                    'selected_artifact_id': 1000 + contract_index,
                    'selected_artifact': f'runtime-{plan["contract_framework"]}-1',
                    'latest_producer_job_id': 2000 + contract_index,
                    'latest_producer_attempt': 1, 'reused': False}
            self.files[framework] = {
                'image.oci/validated-index.json': encoded(expected),
                'image.oci/build-inputs.json': encoded({'revision': SHA, 'annotations': {
                    'revision': SHA, 'source': f'https://github.com/{REPOSITORY}'}}),
                'published.digest': expected['digest'].encode(),
                'published-index.json': self.remote[framework],
                'publication-evidence.json': encoded({
                    'image_ref': f'{REGISTRY}/image-base-{framework}@{expected["digest"]}',
                    'validated_digest': expected['digest'], 'copied_digest': expected['digest'],
                    'remote_digest': expected['digest'], 'platforms': expected['platforms']}),
                'runtime-gate-result.json': encoded(gate)}
            self.repack(framework)

    def artifact(self, artifact_id, name):
        return {'id': artifact_id, 'name': name, 'expired': False,
                'size_in_bytes': 1, 'digest': 'sha256:' + 'b' * 64,
                'workflow_run': {'id': RUN_ID, 'head_sha': SHA, 'head_branch': 'main',
                                 'repository_id': 42, 'head_repository_id': 42}}

    def job(self, job_id, name, steps=None):
        return {'id': job_id, 'name': name, 'run_id': RUN_ID, 'run_attempt': 1,
                'head_sha': SHA, 'status': 'completed', 'conclusion': 'success',
                'steps': steps or []}

    def repack(self, framework):
        raw = archive(self.files[framework])
        self.archives[framework] = raw
        artifact = next(x for x in self.arts if x['name'] == f'publication-{framework}-1')
        artifact.update(size_in_bytes=len(raw), digest=digest(raw))

    def mutate(self, framework, filename, key, value):
        document = json.loads(self.files[framework][filename])
        document[key] = value
        self.files[framework][filename] = encoded(document)
        self.repack(framework)

    def build(self, artifact_pages=None, job_pages=None):
        return inventory.build_inventory(
            RUN_ID, REPOSITORY, REGISTRY, self.run,
            artifact_pages or {'total_count': len(self.arts), 'artifacts': self.arts},
            job_pages or {'total_count': len(self.jobs), 'jobs': self.jobs},
            self.archives, self.ecr, self.remote)

    def test_exact_catalog_resolves_all_remote_digest_references(self):
        result = self.build()
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(result['source_run_id'], RUN_ID)
        self.assertEqual(result['source_run_attempt'], 1)
        self.assertEqual(result['source_sha'], SHA)
        self.assertEqual(len(result['candidates']), 16)
        self.assertEqual(set(result['candidates']), set(CATALOG))
        for framework, candidate in result['candidates'].items():
            self.assertEqual(candidate['image_ref'],
                             f'{REGISTRY}/image-base-{framework}@{self.expected[framework]["digest"]}')
            self.assertEqual(set(candidate['platforms']), {'amd64', 'arm64'})
            self.assertEqual(candidate['functional_contract_status'], 'passed')

    def test_run_id_mismatch(self):
        self.run['id'] += 1
        with self.assertRaisesRegex(ValueError, 'run ID mismatch'):
            self.build()

    def test_wrong_source_revision_in_artifact(self):
        self.arts[0]['workflow_run']['head_sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'artifact run/revision'):
            self.build()

    def test_wrong_run_attempt_is_rejected(self):
        self.run['run_attempt'] = 2
        with self.assertRaisesRegex(ValueError, 'reruns are ambiguous'):
            self.build()

    def test_source_must_be_successful_manual_catalog_run_on_main(self):
        for key, value in (('conclusion', 'failure'), ('status', 'in_progress'),
                           ('event', 'push'), ('head_branch', 'topic'),
                           ('path', '.github/workflows/workflow.yml')):
            with self.subTest(key=key), patch.dict(self.run, {key: value}):
                with self.assertRaises(ValueError):
                    self.build()

    def test_source_repository_must_match(self):
        self.run['head_repository']['id'] = 55
        with self.assertRaisesRegex(ValueError, 'repository mismatch'):
            self.build()

    def test_missing_framework_rejected(self):
        self.arts.pop(0)
        with self.assertRaisesRegex(ValueError, 'missing framework'):
            self.build()

    def test_ambiguous_publication_artifacts_rejected(self):
        duplicate = deepcopy(self.arts[0])
        duplicate['id'] = 99999
        self.arts.append(duplicate)
        with self.assertRaisesRegex(ValueError, 'ambiguous publication'):
            self.build()

    def test_unknown_or_wrong_attempt_publication_rejected(self):
        for name in ('publication-ruby-1', 'publication-dotnet10-2'):
            with self.subTest(name=name), patch.dict(self.arts[0], name=name):
                with self.assertRaisesRegex(ValueError, 'unexpected publication'):
                    self.build()

    def test_complete_artifact_pagination_required(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.build(artifact_pages={'total_count': len(self.arts) + 1, 'artifacts': self.arts})

    def test_complete_job_pagination_required(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.build(job_pages={'total_count': len(self.jobs) + 1, 'jobs': self.jobs})

    def test_duplicate_publication_producer_rejected(self):
        duplicate = deepcopy(self.jobs[0])
        duplicate['id'] = 99999
        self.jobs.append(duplicate)
        with self.assertRaisesRegex(ValueError, 'ambiguous publication producer'):
            self.build()

    def test_failed_publication_producer_rejected(self):
        self.jobs[0]['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'producer did not succeed'):
            self.build()

    def test_skipped_actual_publication_gate_rejected_even_with_successful_job(self):
        self.jobs[0]['steps'][1]['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, 'prerequisite did not succeed'):
            self.build()

    def test_wrong_job_run_attempt_or_revision_rejected(self):
        for key, value in (('run_id', RUN_ID + 1), ('run_attempt', 2), ('head_sha', 'b' * 40)):
            with self.subTest(key=key), patch.dict(self.jobs[0], {key: value}):
                with self.assertRaisesRegex(ValueError, 'producer run/attempt/revision'):
                    self.build()

    def test_archive_digest_tampering_rejected(self):
        self.archives['go1-26'] = self.archives['go1-26'].replace(b'passed', b'failed', 1)
        with self.assertRaisesRegex(ValueError, 'ZIP digest mismatch'):
            self.build()

    def test_expired_artifact_rejected(self):
        self.arts[0]['expired'] = True
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.build()

    def test_unsafe_zip_paths_rejected(self):
        for filename in ('../secret', '/tmp/secret', 'dir\\secret', 'a/./b'):
            with self.subTest(filename=filename):
                files = {filename: b'test'}
                raw = archive(files)
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    inventory.archive_files(raw, {'size_in_bytes': len(raw), 'digest': digest(raw)})

    def test_duplicate_zip_entries_rejected(self):
        buffer = io.BytesIO()
        import warnings
        with warnings.catch_warnings(), zipfile.ZipFile(buffer, 'w') as result:
            warnings.simplefilter('ignore', UserWarning)
            result.writestr('same', b'1')
            result.writestr('same', b'2')
        raw = buffer.getvalue()
        with self.assertRaisesRegex(ValueError, 'duplicate publication ZIP'):
            inventory.archive_files(raw, {'size_in_bytes': len(raw), 'digest': digest(raw)})

    def test_wrong_publication_build_revision_rejected(self):
        self.mutate('go1-26', 'image.oci/build-inputs.json', 'revision', 'b' * 40)
        with self.assertRaisesRegex(ValueError, 'build revision'):
            self.build()

    def test_gate_failure_or_missing_same_run_binding_rejected(self):
        for key, value in (('passed', None), ('run_id', str(RUN_ID + 1)), ('run_attempt', 2),
                           ('selected_attempt', 2), ('revision', 'b' * 40)):
            with self.subTest(key=key):
                original = self.files['go1-26']['runtime-gate-result.json']
                self.mutate('go1-26', 'runtime-gate-result.json', key, value)
                with self.assertRaisesRegex(ValueError, 'gate run/attempt/revision/status'):
                    self.build()
                self.files['go1-26']['runtime-gate-result.json'] = original
                self.repack('go1-26')

    def test_compiled_dev_gate_uses_same_runtime_and_exact_pair(self):
        result = self.build()
        for framework in ('dotnet10', 'go1-25', 'go1-26', 'java21', 'java25'):
            self.assertEqual(result['candidates'][framework + '-dev']['functional_contract'], framework)

    def test_runtime_digest_mismatch_rejected(self):
        self.mutate('go1-26-dev', 'runtime-gate-result.json', 'index_digest', 'sha256:' + 'f' * 64)
        with self.assertRaisesRegex(ValueError, 'runtime digest/platform mismatch'):
            self.build()

    def test_dev_digest_mismatch_rejected(self):
        self.mutate('go1-26', 'runtime-gate-result.json', 'dev_index_digest', 'sha256:' + 'f' * 64)
        with self.assertRaisesRegex(ValueError, 'dev digest/platform mismatch'):
            self.build()

    def test_runtime_platform_mismatch_rejected(self):
        platforms = deepcopy(self.expected['go1-26']['platforms'])
        platforms['linux/arm64'] = 'sha256:' + 'f' * 64
        self.mutate('go1-26-dev', 'runtime-gate-result.json', 'platforms', platforms)
        with self.assertRaisesRegex(ValueError, 'runtime digest/platform mismatch'):
            self.build()

    def test_dev_platform_mismatch_rejected(self):
        platforms = deepcopy(self.expected['go1-26-dev']['platforms'])
        platforms['linux/arm64'] = 'sha256:' + 'f' * 64
        self.mutate('go1-26', 'runtime-gate-result.json', 'dev_platforms', platforms)
        with self.assertRaisesRegex(ValueError, 'dev digest/platform mismatch'):
            self.build()

    def test_failed_functional_producer_rejected(self):
        job = next(j for j in self.jobs if j['name'] == 'Runtime go1-26 (both architectures)')
        job['conclusion'] = 'failure'
        with self.assertRaisesRegex(ValueError, 'functional producer did not succeed'):
            self.build()

    def test_wrong_functional_artifact_id_rejected(self):
        self.mutate('go1-26', 'runtime-gate-result.json', 'selected_artifact_id', 99999)
        with self.assertRaisesRegex(ValueError, 'functional producer/artifact binding mismatch'):
            self.build()

    def test_ecr_digest_mismatch_rejected(self):
        self.ecr['go1-26']['imageDetails'][0]['imageDigest'] = 'sha256:' + 'f' * 64
        with self.assertRaisesRegex(ValueError, 'ECR digest differs'):
            self.build()

    def test_ecr_ambiguous_immutable_tag_rejected(self):
        detail = self.ecr['go1-26']['imageDetails'][0]
        detail['imageTags'].append(f'210926-0522-r{RUN_ID}-a1')
        with self.assertRaisesRegex(ValueError, 'ambiguous immutable source-run tag'):
            self.build()

    def test_ecr_absent_tag_or_wrong_attempt_rejected(self):
        self.ecr['go1-26']['imageDetails'][0]['imageTags'] = [f'210926-0422-r{RUN_ID}-a2']
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous immutable'):
            self.build()

    def test_wrong_ecr_repository_rejected(self):
        self.ecr['go1-26']['imageDetails'][0]['repositoryName'] = 'image-base-other'
        with self.assertRaisesRegex(ValueError, 'repository/account mismatch'):
            self.build()

    def test_remote_index_mismatch_rejected(self):
        self.remote['go1-26'] = self.remote['go1-25']
        with self.assertRaisesRegex(ValueError, 'published index differs'):
            self.build()

    def test_remote_index_requires_actual_two_platform_digest_match(self):
        raw = json.loads(self.remote['go1-26'])
        raw['manifests'].pop()
        self.remote['go1-26'] = encoded(raw)
        with self.assertRaises(ValueError):
            self.build()

    def test_registry_must_not_include_tag_path_or_override(self):
        for registry in ('example.com', REGISTRY + '/path', REGISTRY + ':tag', '--help'):
            with self.subTest(registry=registry), self.assertRaises(ValueError):
                inventory.registry_identity(registry)

    def test_unknown_source_run_cli_fails_without_inventory_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'candidate-inventory.json'
            with patch.object(inventory, 'gh_json', side_effect=ValueError('GitHub run not found')):
                result = inventory.main([str(RUN_ID), '--repository', REPOSITORY,
                                         '--registry', REGISTRY, '--output', str(output)])
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())

    def test_source_input_is_required_and_has_no_default(self):
        with self.assertRaises(SystemExit):
            inventory.main(['--repository', REPOSITORY, '--registry', REGISTRY, '--output', 'unused'])

    def test_unexpected_publication_producer_rejected(self):
        self.jobs.append(self.job(99999, 'build-base-images / Build & push ruby'))
        with self.assertRaisesRegex(ValueError, 'outside the exact catalog'):
            self.build()

    def test_zip_symlink_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as result:
            member = zipfile.ZipInfo('symlink')
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            result.writestr(member, '/tmp/target')
        raw = buffer.getvalue()
        with self.assertRaisesRegex(ValueError, 'unsafe publication ZIP'):
            inventory.archive_files(raw, {'size_in_bytes': len(raw), 'digest': digest(raw)})

    def test_ecr_partial_inventory_rejected(self):
        self.ecr['go1-26']['NextToken'] = 'next-page'
        with self.assertRaisesRegex(ValueError, 'pagination is incomplete'):
            self.build()

    def test_timezone_required_for_ecr_timestamp(self):
        self.ecr['go1-26']['imageDetails'][0]['imagePushedAt'] = '2026-09-21T07:22:00'
        with self.assertRaisesRegex(ValueError, 'must include its timezone'):
            self.build()

    def test_runtime_and_node_dev_have_distinct_source_contracts(self):
        result = self.build()
        for framework in ('nodejs22', 'nodejs22-dev', 'nodejs24', 'nodejs24-dev',
                          'python3-13', 'python3-14'):
            self.assertEqual(result['candidates'][framework]['functional_contract'], framework)

    def test_json_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON field'):
            inventory.json_document(b'{"digest":"a","digest":"b"}')


if __name__ == '__main__':
    unittest.main()
