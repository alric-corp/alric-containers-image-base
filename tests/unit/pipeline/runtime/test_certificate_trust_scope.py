"""Regression against the actual certificate fixture build orchestration.

Unit tests intercept expensive tool calls; the PR also runs the real integration
gate on a hosted runner. Neither replaces the existing certificate contract.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.runtime import trust_plan
from tests.runtime import certificate_contract as fixture


class CertificateTrustScopeTests(unittest.TestCase):
    def test_go_requested_pair_reaches_only_its_two_real_fixture_build_calls(self):
        planned = trust_plan.plan('["go1-26", "go1-26-dev"]')
        self.assertEqual(planned, ['go1-26'])
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(fixture, 'ROOT', Path(temporary)), \
                patch.object(fixture, 'require_key'), \
                patch.object(fixture.shutil, 'copytree'), \
                patch.object(fixture.shutil, 'copy'), \
                patch.object(fixture, 'command', return_value='2026-09-20T00:00:00Z'), \
                patch.object(fixture, 'stage') as stage, \
                patch.object(fixture, 'verify', side_effect=[None, ValueError('test CA is not a release input')]) as verify, \
                patch.object(fixture.subprocess, 'run') as execute, \
                patch.object(fixture, 'run', return_value=0) as runtime, \
                patch.dict(os.environ, {'MELANGE_IMAGE': 'fixture-tool'}):
            for framework in planned:
                self.assertEqual(fixture.check(framework, Path(temporary) / 'reports'), 0)
            builds = [c.args[0] for c in execute.call_args_list
                      if 'scripts.pipeline.artifacts.build_image' in c.args[0]]
            self.assertEqual([args[4] for args in builds], ['go1-26', 'go1-26-dev'])
            self.assertEqual(len(builds), 2)
            self.assertTrue(all(args[6:] == ['--engine', 'docker', '--repository',
                                            'melange/packages', '--keyring',
                                            'melange/melange.rsa.pub'] for args in builds))
            ca_builds = [c.args[0] for c in execute.call_args_list
                         if 'image-base-ca-certificates.yaml' in c.args[0]]
            self.assertEqual({args[args.index('--arch') + 1] for args in ca_builds},
                             {'x86_64', 'aarch64'})
            self.assertTrue(stage.call_args.kwargs['allow_test'])
            self.assertEqual(verify.call_args_list[0].kwargs, {'allow_test': True})
            self.assertEqual(verify.call_args_list[1].kwargs, {})
            runtime.assert_called_once()
            self.assertEqual(runtime.call_args.args[0].name, 'go1-26.oci')
            self.assertEqual(runtime.call_args.args[3].name, 'go1-26-dev.oci')
            self.assertIn('baked_ca', runtime.call_args.kwargs)

    def test_full_batch_preserves_previous_families_and_covers_exact_requested_catalog(self):
        catalog = sorted(p.stem for p in (fixture.ROOT / 'frameworks').glob('*.yaml'))
        planned = trust_plan.plan(json.dumps(catalog))
        old_fixtures = {'python3-13', 'nodejs22', 'go1-26', 'java21', 'dotnet10'}
        self.assertTrue(old_fixtures <= set(planned))
        self.assertEqual(len(planned), 11)
        expanded = []
        for framework in planned:
            expanded.append(framework)
            if fixture.supported(framework) == 'compiled':
                expanded.append(framework + '-dev')
        self.assertEqual(sorted(expanded), catalog)
        self.assertEqual(len(expanded), len(set(expanded)))
