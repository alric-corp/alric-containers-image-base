import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from scripts.pipeline.runtime import retry_lab as lab
from scripts.pipeline.runtime import retry_lab_publish as publish

ROOT = Path(__file__).resolve().parents[4]
REVISION = 'b' * 40
RUN_ID = '55'
ROLE_ARN = 'arn:aws:iam::712107929769:role/github-actions-image-base-p102-lab'


def env(attempt='2', **overrides):
    base = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': lab.REPOSITORY,
            'GITHUB_REF': 'refs/heads/main', 'GITHUB_SHA': REVISION,
            'GITHUB_WORKFLOW_SHA': REVISION,
            'GITHUB_WORKFLOW_REF': f'{lab.REPOSITORY}/{lab.WORKFLOW}@refs/heads/main',
            'GITHUB_RUN_ID': RUN_ID, 'GITHUB_RUN_ATTEMPT': attempt,
            'LAB_AWS_REGION': publish.REGION, 'LAB_AWS_ROLE_ARN': ROLE_ARN,
            'LAB_ECR_REPOSITORY_RUNTIME': publish.REPOSITORIES['runtime'],
            'LAB_ECR_REPOSITORY_DEV': publish.REPOSITORIES['dev']}
    base.update(overrides)
    return base


def event():
    return {'inputs': {'confirmation': lab.CONFIRMATION, 'reviewed-sha': REVISION}}


def sha(seed):
    return 'sha256:' + hashlib.sha256(seed.encode()).hexdigest()


def platforms(seed):
    return {'linux/amd64': sha(seed + 'amd64'), 'linux/arm64': sha(seed + 'arm64')}


def make_gate(attempt=2, selected_attempt=1, reused=True, **overrides):
    gate = {
        'framework': 'go1-26', 'passed': True, 'repository': lab.REPOSITORY,
        'run_id': RUN_ID, 'run_attempt': attempt, 'revision': REVISION,
        'selected_artifact_id': 900, 'selected_artifact': 'runtime-go1-26-1',
        'selected_attempt': selected_attempt, 'index_digest': sha('runtime-index'),
        'platforms': platforms('runtime'), 'dev_index_digest': sha('dev-index'),
        'dev_platforms': platforms('dev'),
        'report_sha256': {'amd64': hashlib.sha256(b'amd64').hexdigest(),
                          'arm64': hashlib.sha256(b'arm64').hexdigest()},
        'latest_producer_job_id': 700, 'latest_producer_attempt': 1, 'reused': reused,
    }
    gate.update(overrides)
    return gate


def make_ctx(attempt=2):
    return lab.context(env(attempt=str(attempt)), event())


class TargetTests(unittest.TestCase):
    def test_exact_role_region_account_and_two_repositories_required(self):
        self.assertEqual(publish.ACCOUNT_ID, '712107929769')
        self.assertEqual(publish.REGION, 'us-east-1')
        self.assertEqual(publish.ROLE_ARN, ROLE_ARN)
        self.assertEqual(publish.REPOSITORIES, {'runtime': 'p102-lab-go1-26',
                                                'dev': 'p102-lab-go1-26-dev'})
        target = publish.resolve_target(env())
        self.assertEqual(target, {'account_id': '712107929769', 'region': 'us-east-1',
                                  'role_arn': ROLE_ARN,
                                  'repositories': {'runtime': 'p102-lab-go1-26',
                                                   'dev': 'p102-lab-go1-26-dev'}})

    def test_wrong_region_role_or_repository_fails_closed(self):
        cases = [
            {'LAB_AWS_REGION': 'us-west-2'},
            {'LAB_AWS_ROLE_ARN': 'arn:aws:iam::712107929769:role/github-actions-image-base'},
            {'LAB_AWS_ROLE_ARN': 'arn:aws:iam::999999999999:role/github-actions-image-base-p102-lab'},
            {'LAB_ECR_REPOSITORY_RUNTIME': 'image-base-go1-26'},
            {'LAB_ECR_REPOSITORY_DEV': 'image-base-go1-26-dev'},
            {'LAB_ECR_REPOSITORY_RUNTIME': 'p102-lab-go1-26-typo'},
            {'LAB_AWS_REGION': None}, {'LAB_AWS_ROLE_ARN': None},
            {'LAB_ECR_REPOSITORY_RUNTIME': None}, {'LAB_ECR_REPOSITORY_DEV': None},
        ]
        for override in cases:
            with self.subTest(override=override), self.assertRaises(ValueError):
                publish.resolve_target(env(**override))


class RepositoryGuardTests(unittest.TestCase):
    def test_only_the_two_lab_repositories_are_allowlisted(self):
        publish.require_allowlisted_repository('p102-lab-go1-26')
        publish.require_allowlisted_repository('p102-lab-go1-26-dev')

    def test_operational_image_base_prefix_is_rejected(self):
        for name in ('image-base-go1-26', 'image-base-go1-26-dev', 'image-base-python3-14',
                    'image-base-'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                publish.require_allowlisted_repository(name)

    def test_stable_or_arbitrary_repository_names_are_rejected(self):
        for name in ('stable', 'latest', 'p102-lab', 'p102-lab-go1-26-extra', '', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                publish.require_allowlisted_repository(name)


class TagTests(unittest.TestCase):
    def test_tag_is_deterministic_for_the_same_run_and_attempt(self):
        self.assertEqual(publish.tag('55', 2), 'p1-02-lab-55-2')
        self.assertEqual(publish.tag('55', 2), publish.tag('55', 2))
        self.assertNotEqual(publish.tag('55', 1), publish.tag('55', 2))
        self.assertNotEqual(publish.tag('55', 2), publish.tag('56', 2))

    def test_tag_rejects_invalid_run_id_or_attempt(self):
        for run_id, attempt in (('55x', 2), ('-1', 2), ('0', 2), ('55', 3), ('55', 0), ('', 2)):
            with self.subTest(run_id=run_id, attempt=attempt), self.assertRaises(ValueError):
                publish.tag(run_id, attempt)

    def test_require_lab_tag_rejects_stable_latest_and_external_values(self):
        for value in ('stable', 'latest', 'p1-02-lab-55-1', 'p1-02-lab-99-2', 'anything',
                     'p1-02-lab-55-2 ', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                publish.require_lab_tag(value, '55', 2)
        publish.require_lab_tag('p1-02-lab-55-2', '55', 2)


class BindTests(unittest.TestCase):
    def test_attempt_two_with_reused_gate_binds_successfully(self):
        gate = make_gate(attempt=2, selected_attempt=1, reused=True)
        result = publish.bind(env(), event(), gate)
        self.assertEqual(result['context']['run_attempt'], 2)
        self.assertEqual(result['gate'], gate)
        self.assertEqual(result['tag'], f'p1-02-lab-{RUN_ID}-2')
        self.assertEqual(result['target']['repositories'],
                         {'runtime': 'p102-lab-go1-26', 'dev': 'p102-lab-go1-26-dev'})

    def test_attempt_one_can_never_publish(self):
        gate = make_gate(attempt=1, selected_attempt=1, reused=False)
        with self.assertRaises(ValueError):
            publish.bind(env(attempt='1'), event(), gate)

    def test_attempt_two_requires_reused_true(self):
        gate = make_gate(attempt=2, selected_attempt=1, reused=False)
        with self.assertRaises(ValueError):
            publish.bind(env(), event(), gate)

    def test_selected_attempt_must_be_one(self):
        gate = make_gate(attempt=2, selected_attempt=2, reused=True)
        gate['selected_artifact'] = 'runtime-go1-26-2'
        with self.assertRaises(ValueError):
            publish.bind(env(), event(), gate)

    def test_wrong_run_id_or_revision_fails(self):
        for override in ({'run_id': '999'}, {'revision': 'c' * 40}, {'repository': 'other/repo'}):
            gate = make_gate(**override)
            with self.subTest(override=override), self.assertRaises(ValueError):
                publish.bind(env(), event(), gate)

    def test_wrong_framework_fails(self):
        gate = make_gate(framework='go1-26-dev')
        with self.assertRaises(ValueError):
            publish.bind(env(), event(), gate)

    def test_missing_lab_variables_fail_before_binding_completes(self):
        gate = make_gate()
        with self.assertRaises(ValueError):
            publish.bind(env(LAB_AWS_ROLE_ARN=None), event(), gate)


class PreflightTests(unittest.TestCase):
    def test_immutable_repository_without_exclusions_passes(self):
        result = publish.preflight({'repositoryName': 'p102-lab-go1-26',
                                    'imageTagMutability': 'IMMUTABLE'}, 'p102-lab-go1-26')
        self.assertEqual(result['status'], 'PREFLIGHT_OK')

    def test_mutable_or_excluded_repository_aborts(self):
        cases = [
            {'repositoryName': 'p102-lab-go1-26', 'imageTagMutability': 'MUTABLE'},
            {'repositoryName': 'p102-lab-go1-26', 'imageTagMutability': 'IMMUTABLE_WITH_EXCLUSION',
             'imageTagMutabilityExclusionFilters': [{'filterType': 'WILDCARD', 'filter': 'stable'}]},
            {'repositoryName': 'p102-lab-go1-26', 'imageTagMutability': 'IMMUTABLE',
             'imageTagMutabilityExclusionFilters': [{'filterType': 'WILDCARD', 'filter': 'stable'}]},
            {'repositoryName': 'image-base-go1-26', 'imageTagMutability': 'IMMUTABLE'},
            {'repositoryName': 'p102-lab-go1-26-dev', 'imageTagMutability': 'IMMUTABLE'},
        ]
        for descriptor in cases:
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                publish.preflight(descriptor, 'p102-lab-go1-26')

    def test_preflight_never_targets_an_operational_repository(self):
        with self.assertRaises(ValueError):
            publish.preflight({'repositoryName': 'image-base-go1-26',
                               'imageTagMutability': 'IMMUTABLE'}, 'image-base-go1-26')


class RecordingRun:
    """Fake subprocess.run: records the command, never touches the network."""
    def __init__(self, stdout):
        self.stdout_text = stdout
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=self.stdout_text, stderr='')


class SelfVerificationIdentityTests(unittest.TestCase):
    IMAGE_REF = ('712107929769.dkr.ecr.us-east-1.amazonaws.com/p102-lab-go1-26@' + sha('x'))

    def test_signature_verification_uses_the_lab_workflow_identity(self):
        run = RecordingRun('[{"ok": true}]')
        result = publish.verify_signature(self.IMAGE_REF, run=run)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['certificate_identity'], publish.LAB_CERTIFICATE_IDENTITY)
        self.assertIn('--certificate-identity', run.calls[0])
        self.assertIn(publish.LAB_CERTIFICATE_IDENTITY, run.calls[0])
        self.assertNotIn('build-base-images.yml', ' '.join(run.calls[0]))

    def test_provenance_verification_uses_the_lab_workflow_as_signer(self):
        run = RecordingRun('[{"ok": true}]')
        result = publish.verify_provenance(self.IMAGE_REF, run=run)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['signer_workflow'], publish.LAB_WORKFLOW)
        self.assertIn('--signer-workflow', run.calls[0])
        self.assertIn(publish.LAB_WORKFLOW, run.calls[0])
        self.assertNotIn('build-base-images.yml', publish.LAB_WORKFLOW)

    def test_sbom_verification_uses_the_lab_workflow_identity(self):
        run = RecordingRun('{"payloadType": "application/vnd.in-toto+json"}')
        result = publish.verify_sbom(self.IMAGE_REF, run=run)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['certificate_identity'], publish.LAB_CERTIFICATE_IDENTITY)
        self.assertIn('verify-attestation', run.calls[0])

    def test_empty_verification_output_is_rejected(self):
        for verifier, stdout in ((publish.verify_signature, '[]'),
                                 (publish.verify_provenance, '[]'),
                                 (publish.verify_sbom, '')):
            with self.subTest(verifier=verifier.__name__), self.assertRaises(ValueError):
                verifier(self.IMAGE_REF, run=RecordingRun(stdout))

    def test_self_verification_never_targets_an_operational_repository(self):
        bad_ref = '712107929769.dkr.ecr.us-east-1.amazonaws.com/image-base-go1-26@' + sha('x')
        for verifier in (publish.verify_signature, publish.verify_provenance, publish.verify_sbom):
            with self.subTest(verifier=verifier.__name__), self.assertRaises(ValueError):
                verifier(bad_ref, run=RecordingRun('[{"ok": true}]'))


class GateLayoutBindingTests(unittest.TestCase):
    """F1: the OCI lab-publish revalidated must be proven equal, by digest, to
    the one lab-retry's gate approved — validated-oci-* is overwrite:true."""

    def setUp(self):
        self.gate = make_gate()

    def test_matching_digests_bind_successfully(self):
        result = publish.require_gate_layout_binding(
            self.gate, self.gate['index_digest'], self.gate['dev_index_digest'])
        self.assertEqual(result['status'], 'LAYOUT_BOUND_TO_GATE')
        self.assertEqual(result['gate_index_digest'], self.gate['index_digest'])
        self.assertEqual(result['gate_dev_index_digest'], self.gate['dev_index_digest'])
        self.assertEqual(result['verified_runtime_digest'], self.gate['index_digest'])
        self.assertEqual(result['verified_dev_digest'], self.gate['dev_index_digest'])

    def test_runtime_mismatch_fails_before_aws(self):
        # Simulates validated-oci-go1-26 having been overwritten with a
        # different, internally-consistent candidate since the gate ran.
        with self.assertRaises(ValueError):
            publish.require_gate_layout_binding(
                self.gate, sha('SUBSTITUTED-runtime'), self.gate['dev_index_digest'])

    def test_dev_mismatch_fails_before_aws(self):
        with self.assertRaises(ValueError):
            publish.require_gate_layout_binding(
                self.gate, self.gate['index_digest'], sha('SUBSTITUTED-dev'))

    def test_runtime_and_dev_swapped_fails(self):
        with self.assertRaises(ValueError):
            publish.require_gate_layout_binding(
                self.gate, self.gate['dev_index_digest'], self.gate['index_digest'])

    def test_gate_missing_digests_fails(self):
        broken = dict(self.gate)
        del broken['index_digest']
        with self.assertRaises(KeyError):
            publish.require_gate_layout_binding(
                broken, self.gate['index_digest'], self.gate['dev_index_digest'])

    def test_malformed_verified_digest_fails(self):
        for bad in ('not-a-real-digest', '', None, True, 'sha256:short',
                   self.gate['index_digest'].upper()):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                publish.require_gate_layout_binding(
                    self.gate, bad, self.gate['dev_index_digest'])


class DigestFormatTests(unittest.TestCase):
    """F2: digest_equal must reject well-matched-but-malformed strings."""

    def test_valid_matching_sha256_passes(self):
        value = sha('ok')
        self.assertTrue(publish.digest_equal(
            {'validated_digest': value, 'copied_digest': value, 'remote_digest': value}))

    def test_equal_but_malformed_values_are_rejected(self):
        for bad in ('not-a-real-digest', 'sha256:' + 'a' * 63, 'sha256:' + 'A' * 64,
                   'sha512:' + 'a' * 128, '', None, True, ' ' + sha('padded') + ' ',
                   sha('trailing') + '\n'):
            publication = {'validated_digest': bad, 'copied_digest': bad, 'remote_digest': bad}
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                publish.digest_equal(publication)

    def test_unequal_valid_digests_are_rejected(self):
        publication = {'validated_digest': sha('a'), 'copied_digest': sha('a'),
                       'remote_digest': sha('b')}
        self.assertFalse(publish.digest_equal(publication))


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.gate = make_gate()
        self.binding = publish.bind(env(), event(), self.gate)
        self.layout_binding = publish.require_gate_layout_binding(
            self.gate, self.gate['index_digest'], self.gate['dev_index_digest'])
        digest = self.gate['index_digest']
        dev_digest = self.gate['dev_index_digest']
        self.runtime_publication = {'validated_digest': digest, 'copied_digest': digest,
                                    'remote_digest': digest}
        self.dev_publication = {'validated_digest': dev_digest, 'copied_digest': dev_digest,
                                'remote_digest': dev_digest}
        self.signature = {'certificate_identity': publish.LAB_CERTIFICATE_IDENTITY,
                          'status': 'VERIFIED'}
        self.provenance = {'signer_workflow': publish.LAB_WORKFLOW, 'status': 'VERIFIED'}
        self.sbom = {'certificate_identity': publish.LAB_CERTIFICATE_IDENTITY, 'status': 'VERIFIED'}

    def finalize(self, **overrides):
        args = dict(binding=self.binding, layout_binding=self.layout_binding,
                   runtime_publication=self.runtime_publication,
                   dev_publication=self.dev_publication, runtime_signature=self.signature,
                   dev_signature=self.signature, runtime_provenance=self.provenance,
                   dev_provenance=self.provenance, runtime_sbom=self.sbom, dev_sbom=self.sbom)
        args.update(overrides)
        return publish.finalize(**args)

    def test_pass_only_when_everything_mandatory_holds(self):
        result = self.finalize()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['stable_touched'], False)
        self.assertEqual(result['tag'], f'p1-02-lab-{RUN_ID}-2')
        self.assertEqual(result['repositories'], {'runtime': 'p102-lab-go1-26',
                                                   'dev': 'p102-lab-go1-26-dev'})
        self.assertEqual(result['runtime']['gate_digest'], self.gate['index_digest'])
        self.assertEqual(result['runtime']['verified_digest'], self.gate['index_digest'])
        self.assertEqual(result['dev']['gate_digest'], self.gate['dev_index_digest'])
        self.assertEqual(result['dev']['verified_digest'], self.gate['dev_index_digest'])

    def test_runtime_dev_digest_mismatch_fails(self):
        broken = dict(self.dev_publication, remote_digest=sha('tampered'))
        with self.assertRaises(ValueError):
            self.finalize(dev_publication=broken)
        broken_runtime = dict(self.runtime_publication, copied_digest=sha('tampered'))
        with self.assertRaises(ValueError):
            self.finalize(runtime_publication=broken_runtime)

    def test_publication_internally_consistent_but_divergent_from_gate_fails(self):
        # copied_digest/remote_digest agree with validated_digest, but none of
        # them is the digest the gate actually approved — the overwrite:true
        # substitution scenario, expressed at the publication-metadata layer.
        substituted = sha('SUBSTITUTED-DIFFERENT-runtime-index')
        broken = {'validated_digest': substituted, 'copied_digest': substituted,
                 'remote_digest': substituted}
        with self.assertRaises(ValueError):
            self.finalize(runtime_publication=broken)

    def test_layout_binding_referencing_a_different_gate_fails(self):
        other_gate = make_gate(index_digest=sha('other-runtime'))
        mismatched_binding = publish.require_gate_layout_binding(
            other_gate, other_gate['index_digest'], other_gate['dev_index_digest'])
        with self.assertRaises(ValueError):
            self.finalize(layout_binding=mismatched_binding)

    def test_missing_layout_binding_fails(self):
        with self.assertRaises((ValueError, AttributeError)):
            self.finalize(layout_binding={})

    def test_runtime_and_dev_publication_swapped_fails(self):
        with self.assertRaises(ValueError):
            self.finalize(runtime_publication=self.dev_publication,
                          dev_publication=self.runtime_publication)

    def test_gate_without_index_digests_fails_bind_before_finalize_is_reached(self):
        broken_gate = dict(self.gate)
        del broken_gate['dev_index_digest']
        with self.assertRaises((KeyError, ValueError)):
            publish.require_gate_layout_binding(
                broken_gate, broken_gate['index_digest'], self.gate['dev_index_digest'])

    def test_missing_or_wrong_identity_signature_fails(self):
        with self.assertRaises(ValueError):
            self.finalize(runtime_signature={'certificate_identity': 'https://github.com/'
                                             'alric-corp/alric-containers-image-base/'
                                             '.github/workflows/build-base-images.yml'
                                             '@refs/heads/main', 'status': 'VERIFIED'})
        with self.assertRaises(ValueError):
            self.finalize(dev_signature={'certificate_identity': publish.LAB_CERTIFICATE_IDENTITY,
                                         'status': 'FAILED'})

    def test_missing_or_wrong_provenance_signer_fails(self):
        with self.assertRaises(ValueError):
            self.finalize(runtime_provenance={'signer_workflow': f'{lab.REPOSITORY}/'
                                              '.github/workflows/build-base-images.yml',
                                              'status': 'VERIFIED'})

    def test_missing_or_wrong_sbom_identity_fails(self):
        with self.assertRaises(ValueError):
            self.finalize(dev_sbom={'certificate_identity': 'not-the-lab-identity',
                                    'status': 'VERIFIED'})

    def test_tag_cannot_be_stable_or_external(self):
        tampered = dict(self.binding, tag='stable')
        with self.assertRaises(ValueError):
            self.finalize(binding=tampered)
        tampered = dict(self.binding, tag='p1-02-lab-999-2')
        with self.assertRaises(ValueError):
            self.finalize(binding=tampered)


class SigningIdentitiesUnchangedTests(unittest.TestCase):
    def test_signing_identities_policy_does_not_reference_the_lab_workflow(self):
        policy = (ROOT / 'policies/release/signing-identities.json').read_text()
        self.assertNotIn('partial-retry-lab.yml', policy)
        self.assertNotIn(publish.LAB_CERTIFICATE_IDENTITY, policy)

    def test_lab_identity_is_distinct_from_the_product_signer(self):
        self.assertNotIn('build-base-images.yml', publish.LAB_WORKFLOW)
        self.assertIn('partial-retry-lab.yml', publish.LAB_WORKFLOW)


class ProfileATests(unittest.TestCase):
    def test_module_never_calls_create_or_reconfigure_repository_apis(self):
        source = Path(publish.__file__).read_text()
        for forbidden in ('CreateRepository', 'PutImageTagMutability',
                         'PutImageScanningConfiguration', 'TagResource',
                         'create-repository', 'put-image-tag-mutability'):
            self.assertNotIn(forbidden, source)

    def test_no_ecr_write_action_string_appears_in_the_module(self):
        source = Path(publish.__file__).read_text()
        self.assertNotIn('ecr:*', source)


class DomainBoundaryTests(unittest.TestCase):
    def test_module_stays_within_the_runtime_domain_dependency_boundary(self):
        # runtime may depend on artifacts, never on release (see
        # test_repository_layout.DEPENDENCIES); digest read-back reuses
        # scripts.pipeline.release.verify_publication as its own workflow
        # step (mirroring build-base-images.yml), never as a cross-domain import.
        source = Path(publish.__file__).read_text()
        self.assertNotIn('scripts.pipeline.release', source)
        self.assertNotIn('scripts.pipeline.catalog', source)
        self.assertNotIn('scripts.pipeline.operations', source)


if __name__ == '__main__':
    unittest.main()
