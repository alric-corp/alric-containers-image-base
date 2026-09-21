"""No stable write is reachable until the entire tested pair is authorized."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
import io

import yaml

from scripts.pipeline.artifacts.oci_artifact import INDEX
from scripts.pipeline.release import promotion_batch as batch
from scripts.pipeline.release.verify_promotion_pairs import verify_completed_pair


ROOT = Path(__file__).resolve().parents[4]
PAIR = ['go1-26', 'go1-26-dev']
NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
REGISTRY = '123456789012.dkr.ecr.us-east-1.amazonaws.com'
SOURCE = 'alric-corp/alric-containers-image-base'
RUNTIME = 'sha256:' + 'a' * 64
DEV = 'sha256:' + 'b' * 64
OLD = 'sha256:' + 'c' * 64
TAG = '210926-0300-r123-a1'


def image(digest, tag=TAG, age=8, stable=False):
    return {'imageDigest': digest, 'imageTags': [tag] + (['stable'] if stable else []),
            'imagePushedAt': (NOW - timedelta(hours=age)).isoformat(),
            'imageManifestMediaType': INDEX}


class BatchAuthorizationTests(unittest.TestCase):
    def execute(self, requested=None, inventories=None, quarantine=None,
                trust_failure=None, scan_failure=None, write_failure=None,
                readback_mismatch=None, inventory_error=None):
        requested = requested or PAIR
        inventories = inventories if inventories is not None else {
            PAIR[0]: [image(RUNTIME)], PAIR[1]: [image(DEV)]}
        events, stable = [], {}
        for name, entries in inventories.items():
            prior = [entry['imageDigest'] for entry in entries if 'stable' in entry['imageTags']]
            if prior:
                stable[name] = prior[0]

        def framework(ref):
            return ref.split('/image-base-', 1)[1].split('@')[0]

        def inventory(repository):
            name = repository.removeprefix('image-base-')
            events.append(('inventory', name))
            if inventory_error == name:
                raise ValueError('ambiguous inventory')
            return {'imageDetails': inventories.get(name, [])}

        def trust(ref, repository, reports):
            name = framework(ref)
            events.append(('trust', name))
            self.assertEqual(repository, SOURCE)
            if trust_failure == name:
                raise ValueError('candidate signature or provenance rejected')

        def scan(mode, ref, reports):
            name = framework(ref)
            events.append(('scan', name))
            self.assertEqual(mode, 'remote')
            return int(scan_failure == name)

        def write(ref, digest):
            name = framework(ref)
            events.append(('write', name))
            if write_failure == name:
                raise subprocess.CalledProcessError(1, ['docker'])
            stable[name] = digest

        def read(command, **kwargs):
            repository = command[command.index('--repository-name') + 1]
            name = repository.removeprefix('image-base-')
            events.append(('readback', name))
            digest = OLD if readback_mismatch == name else stable.get(name)
            details = [] if digest is None else [{
                'repositoryName': repository, 'imageTags': ['stable'],
                'imageDigest': digest, 'imageManifestMediaType': INDEX}]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({'imageDetails': details}))

        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / 'reports'
            policy = Path(tmp) / 'quarantine.json'
            policy.write_text(json.dumps(quarantine or {}))
            with patch.object(batch, 'load_details', side_effect=inventory), \
                    patch.object(batch, 'verify_promotion', side_effect=trust), \
                    patch.object(batch, 'scan_images', side_effect=scan), \
                    patch.object(batch, 'write_stable', side_effect=write), \
                    patch.object(batch, 'report_unfixed_cves') as info, \
                    patch('scripts.pipeline.release.verify_stable.subprocess.run', side_effect=read):
                failure = None
                try:
                    batch.promote_batch(requested, REGISTRY, SOURCE, 6, 1, reports, policy, NOW)
                except batch.ERRORS as error:
                    failure = str(error)
            documents = {str(path.relative_to(reports)): json.loads(path.read_text())
                         for path in reports.rglob('*.json')}
            evidence = {name: documents.get(f'promotion-{name}-1/promotion-evidence.json')
                        for name in requested}
            return failure, events, evidence, documents, info.call_count

    def assert_no_writes(self, result):
        failure, events, evidence, _, _ = result
        self.assertTrue(failure)
        self.assertFalse(any(action == 'write' for action, _ in events), events)
        self.assertTrue(all(entry['promoted'] is False for entry in evidence.values()))

    def test_matching_pair_verifies_every_member_before_first_write_and_reads_both(self):
        failure, events, evidence, documents, info_count = self.execute(requested=list(reversed(PAIR)))
        self.assertIsNone(failure)
        first_write = next(index for index, entry in enumerate(events) if entry[0] == 'write')
        self.assertEqual([event for event in events[:first_write] if event[0] in ('trust', 'scan')],
                         [('trust', PAIR[0]), ('trust', PAIR[1]), ('scan', PAIR[0]), ('scan', PAIR[1])])
        self.assertEqual(events[first_write:], [('write', PAIR[0]), ('write', PAIR[1]),
                                               ('readback', PAIR[0]), ('readback', PAIR[1])])
        self.assertTrue(all(entry['promoted'] for entry in evidence.values()))
        self.assertEqual(verify_completed_pair(evidence[PAIR[0]], evidence[PAIR[1]])['status'], 'PAIR_BOUND')
        self.assertTrue(documents['promotion-batch.json']['promoted'])
        self.assertEqual(evidence[PAIR[0]]['pair_authorization'], evidence[PAIR[1]]['pair_authorization'])
        self.assertEqual(info_count, 2)

    def test_run_or_attempt_mismatch_rejected_before_writes(self):
        for tag in ('210926-0300-r456-a1', '210926-0300-r123-a2'):
            with self.subTest(tag=tag):
                result = self.execute(inventories={PAIR[0]: [image(RUNTIME)], PAIR[1]: [image(DEV, tag)]})
                self.assert_no_writes(result)
                self.assertIn('vêm de builds diferentes', result[0])

    def test_missing_runtime_missing_dev_and_dev_still_soaking_never_write(self):
        for inventories in ({PAIR[0]: [image(RUNTIME)]}, {PAIR[1]: [image(DEV)]},
                            {PAIR[0]: [image(RUNTIME)], PAIR[1]: [image(DEV, age=5)]}):
            with self.subTest(inventories=inventories):
                self.assert_no_writes(self.execute(inventories=inventories))

    def test_quarantined_pair_member_never_writes(self):
        for name, digest in zip(PAIR, (RUNTIME, DEV)):
            with self.subTest(name=name):
                self.assert_no_writes(self.execute(quarantine={
                    f'image-base-{name}': [{'digest': digest}]}))

    def test_signature_or_provenance_failure_on_either_member_never_writes(self):
        for name in PAIR:
            with self.subTest(name=name):
                self.assert_no_writes(self.execute(trust_failure=name))

    def test_blocking_scan_on_either_member_never_writes(self):
        for name in PAIR:
            with self.subTest(name=name):
                result = self.execute(scan_failure=name)
                self.assert_no_writes(result)
                self.assertEqual(result[4], 2)  # Informational reporting survives the blocking gate.

    def test_second_write_failure_preserves_prior_state_and_false_outcome_for_both(self):
        inventories = {PAIR[0]: [image(RUNTIME), image(OLD, '190926-0300-r100-a1', 48, True)],
                       PAIR[1]: [image(DEV), image(OLD, '190926-0300-r100-a1', 48, True)]}
        failure, events, evidence, documents, _ = self.execute(inventories=inventories,
                                                              write_failure=PAIR[1])
        self.assertTrue(failure)
        self.assertEqual(evidence[PAIR[0]]['write_status'], 'completed')
        self.assertEqual(evidence[PAIR[1]]['write_status'], 'failed')
        self.assertEqual(evidence[PAIR[0]]['stable_digest_observed'], RUNTIME)
        self.assertEqual(evidence[PAIR[1]]['stable_digest_observed'], OLD)
        self.assertTrue(all(entry['promoted'] is False for entry in evidence.values()))
        self.assertFalse(documents['promotion-batch.json']['promoted'])
        self.assertEqual(events[-2:], [('readback', PAIR[0]), ('readback', PAIR[1])])
        for name in PAIR:
            self.assertEqual(documents[f'promotion-{name}-1/ecr-before.json']['imageDetails'], inventories[name])

    def test_readback_mismatch_fails_pair_even_when_both_writes_succeeded(self):
        for name in PAIR:
            with self.subTest(name=name):
                failure, events, evidence, _, _ = self.execute(readback_mismatch=name)
                self.assertTrue(failure)
                self.assertEqual(sum(action == 'readback' for action, _ in events), 2)
                self.assertTrue(all(entry['promoted'] is False for entry in evidence.values()))
                with self.assertRaises(ValueError):
                    verify_completed_pair(evidence[PAIR[0]], evidence[PAIR[1]])

    def test_whole_pair_without_eligible_candidates_is_a_clean_no_write_skip(self):
        for inventories in ({}, {PAIR[0]: [image(RUNTIME, age=1)], PAIR[1]: [image(DEV, age=1)]}):
            with self.subTest(inventories=inventories):
                failure, events, evidence, documents, _ = self.execute(inventories=inventories)
                self.assertIsNone(failure)
                self.assertFalse(any(action == 'write' for action, _ in events))
                self.assertFalse(documents['promotion-batch.json']['promoted'])
                self.assertEqual(verify_completed_pair(evidence[PAIR[0]], evidence[PAIR[1]])['status'], 'PAIR_SKIPPED')

    def test_interpreted_frameworks_remain_independent_even_with_dev_suffix(self):
        requested = ['python3-13', 'nodejs22', 'nodejs22-dev']
        inventories = {name: [image(RUNTIME, f'210926-0300-r{100 + index}-a1')]
                       for index, name in enumerate(requested)}
        failure, _, evidence, documents, _ = self.execute(requested=requested, inventories=inventories)
        self.assertIsNone(failure)
        self.assertTrue(all(entry['promoted'] for entry in evidence.values()))
        self.assertEqual(documents['promotion-batch.json']['authorized_pairs'], [])

    def test_complete_initial_inventory_required(self):
        self.assert_no_writes(self.execute(inventory_error=PAIR[1]))


class UnprivilegedPlanTests(unittest.TestCase):
    def test_cli_plan_enforces_pairs_and_production_soak_without_aws(self):
        for frameworks, hours, expected in ((PAIR, '6', 0), ([PAIR[0]], '6', 1),
                                             ([PAIR[1]], '6', 1), (PAIR, '0', 1)):
            with self.subTest(frameworks=frameworks, hours=hours), \
                    patch.object(batch, 'load_details') as read, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(batch.main([json.dumps(frameworks), '--soak-hours', hours, '--plan']), expected)
                read.assert_not_called()

    def test_compiled_relationships_are_derived_from_catalog(self):
        for runtime in ('go1-26', 'go1-25', 'java21', 'java25', 'dotnet10'):
            with self.subTest(runtime=runtime):
                self.assertEqual(batch.promotion_units([runtime + '-dev', runtime], 6),
                                 [[runtime, runtime + '-dev']])

    def test_incomplete_pair_and_lower_soak_fail_before_aws(self):
        for frameworks, hours in (([PAIR[0]], 6), ([PAIR[1]], 6), (PAIR, 0), (PAIR, 5.99)):
            with self.subTest(frameworks=frameworks, hours=hours), patch.object(batch, 'load_details') as read:
                with self.assertRaises(ValueError):
                    batch.promote_batch(frameworks, REGISTRY, SOURCE, hours, 1,
                                        Path('unused'), Path('unused'))
                read.assert_not_called()

    def test_invalid_build_prefix_cannot_pass_run_suffix_binding(self):
        from scripts.pipeline.release.verify_promotion_pair import run_identity
        for tag in ('invalid-r123-a1', '990926-0300-r123-a1'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                run_identity(tag)


class PromotionWorkflowWiringTests(unittest.TestCase):
    def test_authorization_precedes_aws_and_orchestrator_owns_mutation(self):
        document = yaml.safe_load((ROOT / '.github/workflows/promote-stable.yml').read_text())
        job = document['jobs']['promote']
        steps = job['steps']
        names = [step['name'] for step in steps]
        validation = names.index('Validate workflow inputs before privileged operations')
        credentials = names.index('Configure AWS credentials (OIDC)')
        self.assertLess(validation, credentials)
        self.assertIn('--plan', steps[validation]['run'])
        self.assertIn('scripts.pipeline.catalog.validate_inputs', steps[validation]['run'])
        self.assertNotIn('strategy', job)
        self.assertFalse(job['concurrency']['cancel-in-progress'])
        self.assertIn("vars.STABLE_PROMOTION_AUTHORIZED == 'true'", job['if'])
        execution = steps[names.index('Authorize candidates and promote stable pairs')]
        self.assertIn('scripts.pipeline.release.promotion_batch', execution['run'])
        self.assertNotIn('continue-on-error', execution)
        self.assertNotIn('imagetools create', '\n'.join(step.get('run', '') for step in steps))
        self.assertIn('policies/release/promotion-quarantine.json', execution['run'])
        outcome = steps[names.index('Preserve promotion outcome')]
        self.assertIn('reports/promotion-*/promotion-evidence.json', outcome['with']['path'])
        self.assertIn('reports/promotion-batch.json', outcome['with']['path'])
        for name in ('verify-pair', 'summary'):
            download = next(step for step in document['jobs'][name]['steps']
                            if step['name'] == 'Download promotion evidence')
            self.assertEqual(download['with']['pattern'], 'promotion-*-${{ github.run_attempt }}')
            self.assertTrue(download['with']['merge-multiple'])
            self.assertEqual(download['with']['digest-mismatch'], 'error')
            self.assertEqual(download['with']['run-id'], '${{ github.run_id }}')


if __name__ == '__main__':
    unittest.main()
