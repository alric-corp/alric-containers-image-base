"""The requested batch must reach the real certificate matrix and strict gate."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from tests.helpers.subprocess_env import bash_command, python3_test_environment


ROOT = Path(__file__).resolve().parents[4]


def workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


class ImageTrustWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.trust = workflow('image-trust.yml')
        self.jobs = self.trust['jobs']

    def test_caller_forwards_one_requested_batch_to_both_validation_gates(self):
        caller = workflow('validate-base-images.yml')
        triggers = caller.get('on', caller.get(True))
        self.assertTrue(triggers['workflow_call']['inputs']['frameworks']['required'])
        for job in ('image-trust', 'validate'):
            self.assertEqual(caller['jobs'][job]['with']['frameworks'], '${{ inputs.frameworks }}')
            self.assertEqual(caller['jobs'][job]['needs'], 'wolfi-trust')
        self.assertEqual(caller['jobs']['image-trust']['uses'], './.github/workflows/image-trust.yml')
        self.assertEqual(caller['jobs']['image-trust']['with'], {'frameworks': '${{ inputs.frameworks }}'})
        self.assertEqual(triggers['workflow_call']['outputs']['image-trust-result']['value'],
                         '${{ jobs.image-trust.outputs.result }}')

    def test_matrix_is_only_the_successful_planners_output(self):
        triggers = self.trust.get('on', self.trust.get(True))
        self.assertEqual(set(triggers), {'workflow_call'})
        self.assertEqual(triggers['workflow_call']['inputs']['frameworks']['type'], 'string')
        self.assertIs(triggers['workflow_call']['inputs']['frameworks']['required'], True)
        self.assertNotIn('default', triggers['workflow_call']['inputs']['frameworks'])
        step = next(s for s in self.jobs['plan']['steps'] if s.get('id') == 'plan')
        self.assertEqual(step['env'], {'FRAMEWORKS': '${{ inputs.frameworks }}'})
        self.assertIn('python3 -B -m scripts.pipeline.runtime.trust_plan', step['run'])
        self.assertNotIn('${{', step['run'])
        self.assertEqual(self.jobs['plan']['outputs']['fixtures'], '${{ steps.plan.outputs.fixtures }}')
        self.assertEqual(self.jobs['trust']['needs'], 'plan')
        self.assertEqual(self.jobs['trust']['strategy']['matrix'],
                         {'framework': '${{ fromJSON(needs.plan.outputs.fixtures) }}'})
        self.assertFalse(self.jobs['trust']['strategy']['fail-fast'])

    def test_real_plan_step_emits_only_go_and_rejects_invalid_batch_before_output(self):
        script = next(s['run'] for s in self.jobs['plan']['steps'] if s.get('id') == 'plan')
        for raw, success in (('["go1-26","go1-26-dev"]', True), ('[]', False),
                             ('["java21-dev"]', False), ('["unknown"]', False), ('{', False)):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'github-output'
                env = dict(os.environ, FRAMEWORKS=raw, GITHUB_OUTPUT=str(output))
                with python3_test_environment(env) as effective:
                    result = subprocess.run(bash_command('-c', script), cwd=ROOT, env=effective,
                                            capture_output=True, text=True, timeout=30)
                if success:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(output.read_text().removeprefix('fixtures=')), ['go1-26'])
                    self.assertIn('TRUST_MATRIX=', result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertNotIn('TRUST_MATRIX=', result.stdout)

    def test_gate_cannot_pass_failed_skipped_or_cancelled_plan_or_matrix(self):
        gate = self.jobs['image-trust-gate']
        self.assertEqual(gate['needs'], ['plan', 'trust'])
        self.assertEqual(gate['if'], 'always()')
        step = next(s for s in gate['steps'] if s.get('id') == 'require')
        self.assertEqual(step['env']['PLAN_RESULT'], '${{ needs.plan.result }}')
        self.assertEqual(step['env']['TRUST_RESULT'], '${{ needs.trust.result }}')
        for planned, trusted in (('success', 'success'), ('failure', 'success'),
                                 ('skipped', 'success'), ('cancelled', 'success'),
                                 ('success', 'failure'), ('success', 'skipped'),
                                 ('success', 'cancelled'), ('failure', 'skipped')):
            with self.subTest(plan=planned, trust=trusted), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                output = directory / 'output'
                env = dict(os.environ, PLAN_RESULT=planned, TRUST_RESULT=trusted,
                           GITHUB_OUTPUT=str(output), REVISION='a' * 40, ATTEMPT='1', RUN_ID='42')
                with python3_test_environment(env) as effective:
                    result = subprocess.run(bash_command('-c', step['run']), cwd=directory,
                                            env=effective, capture_output=True, text=True, timeout=30)
                if planned == trusted == 'success':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text(), 'result=success\n')
                    self.assertTrue(json.loads((directory / 'image-trust-gate.json').read_text())['passed'])
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse((directory / 'image-trust-gate.json').exists())

    def test_security_execution_and_evidence_contract_remain_intact(self):
        self.assertEqual(self.trust['permissions'], {'contents': 'read'})
        for job in self.jobs.values():
            self.assertNotIn('continue-on-error', job)
            self.assertNotIn('permissions', job)
            for step in job['steps']:
                if step.get('uses', '').startswith('actions/checkout@'):
                    self.assertFalse(step['with']['persist-credentials'])
                if 'uses' in step:
                    self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')
        trust = self.jobs['trust']
        self.assertEqual(trust['timeout-minutes'], 20)
        self.assertEqual(self.jobs['image-trust-gate']['timeout-minutes'], 5)
        emulation = next(s for s in trust['steps'] if s.get('uses', '').startswith('docker/setup-qemu-action@'))
        self.assertEqual(emulation['uses'], 'docker/setup-qemu-action@99012661954931238ded8c8b007157a8430204e1')
        self.assertEqual(emulation['with']['platforms'], 'arm64')
        exercise = next(s for s in trust['steps'] if 'certificate_contract.py' in s.get('run', ''))
        self.assertEqual(exercise['run'], 'python3 -B tests/runtime/certificate_contract.py "$FRAMEWORK"')
        self.assertEqual(exercise['env'], {'FRAMEWORK': '${{ matrix.framework }}'})
        self.assertNotIn('if', exercise)
        for job in ('trust', 'image-trust-gate'):
            upload = next(s for s in self.jobs[job]['steps'] if s.get('uses', '').startswith('actions/upload-artifact@'))
            self.assertEqual(upload['with']['retention-days'], 30)
            self.assertEqual(upload['with']['if-no-files-found'], 'error')

    def test_publication_still_requires_actual_trust_result(self):
        publisher = workflow('build-base-images.yml')['jobs']['build-push']
        step = next(s for s in publisher['steps'] if s.get('name') == 'Require successful default trust integration')
        self.assertEqual(step['env']['TRUST_RESULT'], '${{ needs.validate.outputs.image-trust-result }}')
        self.assertIn('test "$TRUST_RESULT" = success', step['run'])

    def test_hosted_regression_calls_only_the_real_go_certificate_gate(self):
        proof = workflow('image-trust-scope.yml')
        self.assertEqual(set(proof.get('on', proof.get(True))), {'pull_request'})
        self.assertEqual(proof['permissions'], {'contents': 'read'})
        self.assertEqual(len(proof['jobs']), 1)
        job = next(iter(proof['jobs'].values()))
        self.assertEqual(job['uses'], './.github/workflows/image-trust.yml')
        self.assertEqual(json.loads(job['with']['frameworks']), ['go1-26', 'go1-26-dev'])
