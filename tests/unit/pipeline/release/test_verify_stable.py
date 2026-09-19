from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tests.helpers.subprocess_env import bash_command, python3_test_environment, windows_native_stub
from scripts.pipeline.artifacts.oci_artifact import INDEX, MANIFEST
from scripts.pipeline.release.verify_publication import verify_publication
from scripts.pipeline.release.verify_stable import main


ROOT = Path(__file__).resolve().parents[4]
REPOSITORY = 'image-base-go1-26'
IMAGE = '123456789012.dkr.ecr.us-east-1.amazonaws.com/' + REPOSITORY
PLATFORMS = {'linux/amd64': 'sha256:' + '1' * 64, 'linux/arm64': 'sha256:' + '2' * 64}
RAW_INDEX = json.dumps({'schemaVersion': 2, 'mediaType': INDEX, 'manifests': [
    {'mediaType': MANIFEST, 'digest': digest,
     'platform': dict(zip(('os', 'architecture'), platform.split('/')))}
    for platform, digest in PLATFORMS.items()
]}).encode()
CANDIDATE = 'sha256:' + hashlib.sha256(RAW_INDEX).hexdigest()
OTHER = 'sha256:' + 'b' * 64


def promotion_steps():
    return yaml.safe_load((ROOT / '.github/workflows/promote-stable.yml').read_text())['jobs']['promote']['steps']


def selected_evidence():
    return {'repository': REPOSITORY, 'image': IMAGE, 'digest': CANDIDATE,
            'candidate_digest': CANDIDATE, 'tag': '130926-0000-r1-a1',
            'stable_digest': OTHER, 'stable_age_hours': 24, 'soak_hours': 6,
            'promoted': False, 'read_back_status': 'not_run', 'stable_digest_observed': None}


def registry_response(**overrides):
    return {'imageDetails': [{'repositoryName': REPOSITORY, 'imageTags': ['stable'],
                             'imageDigest': CANDIDATE, 'imageManifestMediaType': INDEX, **overrides}]}


def record_outcome(directory, promoted, skipped='false'):
    recorder = next(step for step in promotion_steps() if step['name'] == 'Record promotion outcome')
    base_env = {**os.environ, 'PROMOTED': promoted, 'SKIPPED': skipped,
                'REASON': 'candidato elegível'}
    with python3_test_environment(base_env) as env:
        result = subprocess.run(bash_command('-c', recorder['run']), cwd=directory,
                                env=env, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads((Path(directory) / 'reports/promotion-evidence.json').read_text())


class StableReadBackTests(unittest.TestCase):
    def run_readback(self, raw=None, error=None, initial=None, candidate=CANDIDATE):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reports/promotion-evidence.json'
            path.parent.mkdir()
            path.write_text(json.dumps(initial if initial is not None else selected_evidence()))

            def registry(*args, **kwargs):
                pending = json.loads(path.read_text())
                self.assertFalse(pending['promoted'])
                self.assertEqual(pending['read_back_status'], 'failed')
                self.assertIsNone(pending['stable_digest_observed'])
                if error is not None:
                    raise error
                return subprocess.CompletedProcess(args[0], 0, stdout=raw)

            with patch('sys.argv', ['verify_stable', IMAGE, candidate, '--evidence', str(path)]), \
                    patch('scripts.pipeline.release.verify_stable.subprocess.run', side_effect=registry) as run, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                code = main()
            self.assertFalse(json.loads(path.read_text())['promoted'])
            final = record_outcome(directory, 'true' if code == 0 else 'false')
            self.assertNotIn('Traceback', stderr.getvalue())
            return code, final, run, stderr.getvalue()

    def assert_failed(self, raw=None, error=None, status='failed', **kwargs):
        code, evidence, run, message = self.run_readback(raw, error, **kwargs)
        self.assertNotEqual(code, 0)
        self.assertFalse(evidence['promoted'])
        self.assertEqual(evidence['read_back_status'], status)
        self.assertTrue(message)
        return evidence, run

    def test_success_uses_the_published_index_identity_and_records_both_digests(self):
        publication = verify_publication({'digest': CANDIDATE, 'platforms': PLATFORMS},
                                         CANDIDATE, RAW_INDEX, IMAGE + '@' + CANDIDATE)
        code, evidence, run, _ = self.run_readback(json.dumps(registry_response()))
        self.assertEqual(code, 0)
        self.assertTrue(evidence['promoted'])
        self.assertEqual(evidence['read_back_status'], 'confirmed')
        self.assertEqual(evidence['candidate_digest'], publication['remote_digest'])
        self.assertEqual(evidence['stable_digest_observed'], CANDIDATE)
        self.assertNotIn(CANDIDATE, PLATFORMS.values())
        self.assertEqual(evidence['stable_digest'], OTHER)  # Previous observation preserved.
        self.assertEqual(evidence['soak_hours'], 6)
        run.assert_called_once_with(
            ['aws', 'ecr', 'describe-images', '--repository-name', REPOSITORY,
             '--image-ids', 'imageTag=stable', '--output', 'json', '--no-cli-pager'],
            check=True, capture_output=True, text=True, timeout=60)

    def test_digest_mismatch_fails_even_after_successful_tag_write(self):
        evidence, _ = self.assert_failed(json.dumps(registry_response(imageDigest=OTHER)), status='mismatch')
        self.assertEqual(evidence['candidate_digest'], CANDIDATE)
        self.assertEqual(evidence['stable_digest_observed'], OTHER)
        self.assertIn('leitura de volta não bate', evidence['reason'])

    def test_cli_process_exits_nonzero_on_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reports/promotion-evidence.json'
            path.parent.mkdir()
            path.write_text(json.dumps(selected_evidence()))
            aws = Path(directory) / 'aws'
            aws.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_ECR_RESPONSE"\n')
            aws.chmod(0o755)
            native_env = windows_native_stub(directory, 'aws', stdout_env='TEST_ECR_RESPONSE')
            result = subprocess.run(
                [sys.executable, '-B', '-m', 'scripts.pipeline.release.verify_stable',
                 IMAGE, CANDIDATE, '--evidence', str(path)], cwd=ROOT,
                env={**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'],
                     'TEST_ECR_RESPONSE': json.dumps(registry_response(imageDigest=OTHER)),
                     **native_env},
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            evidence = record_outcome(directory, 'false')
            self.assertFalse(evidence['promoted'])
            self.assertEqual(evidence['read_back_status'], 'mismatch')
            self.assertEqual(evidence['stable_digest_observed'], OTHER)

    def test_missing_stable_fails(self):
        self.assert_failed(json.dumps({'imageDetails': []}))
        self.assert_failed(error=subprocess.CalledProcessError(
            254, ['aws'], stderr='ImageNotFoundException'))

    def test_registry_failure_timeout_or_unavailable_cli_fails(self):
        for error in (subprocess.CalledProcessError(255, ['aws'], stderr='AccessDeniedException'),
                      subprocess.TimeoutExpired(['aws'], 60), FileNotFoundError('aws')):
            with self.subTest(error=error):
                evidence, _ = self.assert_failed(error=error)
                self.assertIsNone(evidence['stable_digest_observed'])

    def test_empty_malformed_or_wrong_shape_response_fails(self):
        for raw in ('', ' ', 'not json', 'null', '[]', '{}', '{"imageDetails":null}',
                    '{"imageDetails":{}}', '{"imageDetails":[null]}'):
            with self.subTest(raw=raw):
                self.assert_failed(raw)

    def test_invalid_or_missing_digest_fails(self):
        for digest in ('', None, [], 123, 'sha256:', 'sha256:' + 'a' * 63,
                       'sha256:' + 'A' * 64, 'sha256:' + 'a' * 65, CANDIDATE + '\n'):
            with self.subTest(digest=digest):
                self.assert_failed(json.dumps(registry_response(imageDigest=digest)))
        response = registry_response()
        del response['imageDetails'][0]['imageDigest']
        self.assert_failed(json.dumps(response))

    def test_ambiguous_response_fails_including_identical_duplicates(self):
        response = registry_response()
        entry = response['imageDetails'][0]
        for raw in (json.dumps({'imageDetails': [entry, entry]}),
                    json.dumps(dict(response, nextToken='more-results')),
                    '{"imageDetails": [], ' + json.dumps(response)[1:],
                    json.dumps(response).replace('"imageDigest":', '"imageDigest":"' + OTHER + '","imageDigest":')):
            with self.subTest(raw=raw):
                self.assert_failed(raw)

    def test_wrong_repository_tag_or_platform_manifest_fails(self):
        for overrides in ({'repositoryName': 'another-repository'}, {'imageTags': []},
                          {'imageTags': 'stable'}, {'imageTags': ['stable', 'stable']},
                          {'imageTags': [None, 'stable']}, {'imageManifestMediaType': MANIFEST},
                          {'imageManifestMediaType': None}):
            with self.subTest(overrides=overrides):
                self.assert_failed(json.dumps(registry_response(**overrides)))

    def test_legacy_multiarch_list_remains_compatible(self):
        code, evidence, _, _ = self.run_readback(json.dumps(registry_response(
            imageManifestMediaType='application/vnd.docker.distribution.manifest.list.v2+json')))
        self.assertEqual(code, 0)
        self.assertTrue(evidence['promoted'])

    def test_changed_candidate_or_invalid_expected_digest_fails_before_aws(self):
        for candidate in (OTHER, '', 'sha256:bad'):
            with self.subTest(candidate=candidate):
                _, run = self.assert_failed(candidate=candidate)
                run.assert_not_called()

    def test_previous_confirmation_is_cleared_before_new_read_back(self):
        stale = dict(selected_evidence(), read_back_status='confirmed', promoted=True,
                     stable_digest_observed=CANDIDATE)
        self.assert_failed(error=subprocess.TimeoutExpired(['aws'], 60), initial=stale)


class PromotionOutcomeTests(unittest.TestCase):
    def test_write_success_alone_cannot_mark_promoted(self):
        for status, observed in (('not_run', None), ('failed', None), ('mismatch', OTHER),
                                 ('confirmed', OTHER), ('confirmed', None)):
            with self.subTest(status=status, observed=observed), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'reports/promotion-evidence.json'
                path.parent.mkdir()
                path.write_text(json.dumps(dict(selected_evidence(), promoted=True,
                                               read_back_status=status, stable_digest_observed=observed)))
                evidence = record_outcome(directory, 'true')
                self.assertFalse(evidence['promoted'])

    def test_failed_step_outcome_or_skip_overrides_matching_evidence(self):
        for promoted, skipped in (('false', 'false'), ('true', 'true')):
            with self.subTest(promoted=promoted, skipped=skipped), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'reports/promotion-evidence.json'
                path.parent.mkdir()
                path.write_text(json.dumps(dict(selected_evidence(), read_back_status='confirmed',
                                               stable_digest_observed=CANDIDATE)))
                self.assertFalse(record_outcome(directory, promoted, skipped)['promoted'])

    def test_no_selection_or_skipped_candidate_records_not_run(self):
        for skipped in ('', 'true'):
            with self.subTest(skipped=skipped), tempfile.TemporaryDirectory() as directory:
                evidence = record_outcome(directory, 'false', skipped)
                self.assertFalse(evidence['promoted'])
                self.assertEqual(evidence['read_back_status'], 'not_run')
                self.assertIsNone(evidence['candidate_digest'])
                self.assertIsNone(evidence['stable_digest_observed'])

    def test_workflow_requires_verification_scan_write_then_readback_before_outcome(self):
        steps = promotion_steps()
        by_name = {step['name']: i for i, step in enumerate(steps)}
        sequence = [by_name[name] for name in (
            'Find promotion candidate (soak window)', 'Verify candidate platforms, signature and provenance',
            'Re-scan both architectures before promotion', 'Promote to stable',
            'Confirm stable via independent ECR read-back', 'Record promotion outcome', 'Preserve promotion outcome')]
        self.assertEqual(sequence, sorted(sequence))
        readback = steps[sequence[4]]
        self.assertEqual(readback['id'], 'readback')
        self.assertEqual(readback['if'], "steps.candidate.outputs.skip == 'false'")
        self.assertNotIn('continue-on-error', readback)
        self.assertIn('scripts.pipeline.release.verify_stable "$IMAGE" "$DIGEST"', readback['run'])
        self.assertEqual(readback['env'], {
            'IMAGE': '${{ steps.candidate.outputs.image }}', 'DIGEST': '${{ steps.candidate.outputs.digest }}'})
        recorder = steps[sequence[5]]
        self.assertEqual(recorder['env']['PROMOTED'],
                         "${{ steps.promote.outcome == 'success' && steps.readback.outcome == 'success' }}")
        self.assertEqual(recorder['if'], '${{ !cancelled() }}')
        self.assertEqual(steps[sequence[6]]['if'], '${{ !cancelled() }}')


class RecoveryReadBackRegressionTests(unittest.TestCase):
    def test_existing_recovery_readback_success_mismatch_missing_and_error(self):
        steps = yaml.safe_load((ROOT / '.github/workflows/recover-stable.yml').read_text())['jobs']['recover']['steps']
        step = next(step for step in steps if step['name'] == 'Confirm stable via independent read-back')
        for observed, code, success in ((CANDIDATE, 0, True), (OTHER, 0, False),
                                        ('', 0, False), ('None', 0, False), ('', 254, False)):
            with self.subTest(observed=observed, code=code), tempfile.TemporaryDirectory() as directory:
                aws = Path(directory) / 'aws'
                aws.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_OBSERVED"\nexit "$TEST_AWS_EXIT"\n')
                aws.chmod(0o755)
                result = subprocess.run(bash_command('-c', step['run']), capture_output=True, text=True,
                                        env={**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'],
                                             'FRAMEWORK': 'go1-26', 'DIGEST': CANDIDATE,
                                             'TEST_OBSERVED': observed, 'TEST_AWS_EXIT': str(code)})
                self.assertEqual(result.returncode == 0, success, result.stderr)


if __name__ == '__main__':
    unittest.main()
