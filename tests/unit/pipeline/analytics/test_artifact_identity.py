"""Contract tests for the single canonical producer-identity module.

Exercises the three tiers directly: what the saved artifact record can verify,
what it cannot (run attempt, producing workflow identity), and how an
explicitly supplied workflow-run record resolves the declared tier. These are
the shared negatives both artifact_binding.py and intake.py rely on.
"""
import unittest

from scripts.pipeline.analytics.artifact_identity import IdentityError, verify_identity

SHA = 'a' * 40


def declared(**changes):
    base = dict(framework='go1-26', artifact_id=11562328737, artifact_name='sbom-go1-26-1',
                repository_id=1360616627, run_id=37806495087, run_attempt=1, source_sha=SHA,
                ref='refs/heads/develop')
    base.update(changes)
    return base


def artifact_record(**changes):
    run = dict(id=37806495087, repository_id=1360616627, head_repository_id=1360616627,
               head_branch='develop', head_sha=SHA)
    run.update(changes.pop('workflow_run', {}))
    base = dict(id=11562328737, name='sbom-go1-26-1', size_in_bytes=18330,
                digest='sha256:' + 'd' * 64, workflow_run=run)
    base.update(changes)
    return base


def run_record(**changes):
    base = dict(id=37806495087, head_sha=SHA, run_attempt=1,
                path='.github/workflows/build-base-images.yml', name='Build base images', workflow_id=42)
    base.update(changes)
    return base


class VerifiedTierTests(unittest.TestCase):
    def test_matching_artifact_record_verifies_the_artifact_tier(self):
        identity = verify_identity(declared(), artifact_record())
        self.assertEqual(identity['verified']['artifact_id'], 'MATCHED')
        self.assertEqual(identity['verified']['run_id'], 'MATCHED')
        self.assertEqual(identity['verified']['source_sha'], 'MATCHED')
        self.assertEqual(identity['verified']['head_repository_id'], 'MATCHED')
        self.assertEqual(identity['verified']['head_branch'], 'MATCHED')

    def test_each_artifact_field_divergence_has_its_own_code(self):
        for change, code in (
                (dict(id=1), 'ARTIFACT_ID_DIFFERS'),
                (dict(name='sbom-go1-26-9'), 'ARTIFACT_NAME_DIFFERS'),
                (dict(workflow_run=dict(id=999)), 'ARTIFACT_RUN_DIFFERS'),
                (dict(workflow_run=dict(repository_id=999)), 'ARTIFACT_REPOSITORY_DIFFERS'),
                (dict(workflow_run=dict(head_sha='b' * 40)), 'ARTIFACT_SOURCE_DIFFERS'),
                (dict(workflow_run=dict(head_repository_id=999)), 'ARTIFACT_REPOSITORY_DIFFERS'),
                (dict(workflow_run=dict(head_branch='main')), 'ARTIFACT_BRANCH_DIFFERS')):
            with self.subTest(code=code):
                with self.assertRaises(IdentityError) as caught:
                    verify_identity(declared(), artifact_record(**change))
                self.assertEqual(caught.exception.code, code)

    def test_incomplete_record_is_refused(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(), dict(id=1))
        self.assertEqual(caught.exception.code, 'ARTIFACT_RECORD_INCOMPLETE')

    def test_name_must_carry_declared_attempt(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(artifact_name='sbom-go1-26-2'), artifact_record(name='sbom-go1-26-2'))
        self.assertEqual(caught.exception.code, 'ARTIFACT_ATTEMPT_DIFFERS')

    def test_absent_optional_record_fields_are_not_provided_not_failures(self):
        record = artifact_record()
        record['workflow_run'] = dict(id=37806495087, repository_id=1360616627, head_sha=SHA)
        identity = verify_identity(declared(), record)
        self.assertEqual(identity['verified']['head_repository_id'], 'NOT_PROVIDED')
        self.assertEqual(identity['verified']['head_branch'], 'NOT_PROVIDED')


class NotVerifiableTierTests(unittest.TestCase):
    def test_without_run_record_attempt_and_workflow_are_not_verifiable(self):
        identity = verify_identity(declared(), artifact_record())
        self.assertFalse(identity['producer_identity_verified'])
        self.assertEqual(identity['corporate_acceptance'], 'FORBIDDEN')
        self.assertEqual(identity['not_verifiable']['run_attempt'], 'NOT_VERIFIABLE_FROM_ARTIFACT_RECORD')
        self.assertEqual(identity['not_verifiable']['workflow_identity'], 'NOT_VERIFIABLE_FROM_ARTIFACT_RECORD')
        # The declared values are still recorded, just not claimed as verified.
        self.assertEqual(identity['declared']['run_attempt'], 1)

    def test_declared_attempt_name_alone_never_implies_corporate_acceptance(self):
        # Even a perfectly consistent artifact record keeps acceptance forbidden.
        identity = verify_identity(declared(), artifact_record())
        self.assertEqual(identity['corporate_acceptance'], 'FORBIDDEN')


class RunRecordResolutionTests(unittest.TestCase):
    def test_run_record_verifies_attempt_and_workflow_identity(self):
        identity = verify_identity(declared(workflow=dict(
            path='.github/workflows/build-base-images.yml', name='Build base images', workflow_id=42)),
            artifact_record(), run_record())
        self.assertTrue(identity['producer_identity_verified'])
        self.assertEqual(identity['corporate_acceptance'], 'ELIGIBLE')
        self.assertEqual(identity['verified']['run_attempt'], 'VERIFIED')
        self.assertEqual(identity['verified']['workflow_path'], 'VERIFIED')
        self.assertEqual(identity['not_verifiable'], {})

    def test_run_record_attempt_mismatch_is_refused(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(run_attempt=1, artifact_name='sbom-go1-26-1',
                                     workflow=dict(path='.github/workflows/build-base-images.yml')),
                            artifact_record(), run_record(run_attempt=2))
        self.assertEqual(caught.exception.code, 'RUN_ATTEMPT_DIFFERS')

    def test_run_record_workflow_path_mismatch_is_refused(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(workflow=dict(path='.github/workflows/build-base-images.yml')),
                            artifact_record(), run_record(path='.github/workflows/evil.yml'))
        self.assertEqual(caught.exception.code, 'WORKFLOW_IDENTITY_DIFFERS')

    def test_run_record_for_a_different_run_cannot_be_swapped_in(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(workflow=dict(path='.github/workflows/build-base-images.yml')),
                            artifact_record(), run_record(id=999))
        self.assertEqual(caught.exception.code, 'RUN_RECORD_RUN_DIFFERS')

    def test_run_record_without_declared_workflow_is_refused(self):
        with self.assertRaises(IdentityError) as caught:
            verify_identity(declared(), artifact_record(), run_record())
        self.assertEqual(caught.exception.code, 'WORKFLOW_IDENTITY_UNDECLARED')


if __name__ == '__main__':
    unittest.main()
