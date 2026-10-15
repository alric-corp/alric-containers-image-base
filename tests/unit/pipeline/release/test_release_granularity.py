"""Characterization of the integrated release granularity (audit G16).

M13 isolates candidate publication per framework, but the release is the
whole run-attempt manifest: approval, holds, watermarks, policy scope and
stable writes act on every member together. With today's one-unit DEV/HOM
scope this is the intended contract; with a multi-unit scope one unit would
block unrelated units. These tests pin that coupling and the invariants any
reviewed unit isolation must keep (never split a manifest or a pair). They
neither endorse nor implement isolation.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.release import lifecycle as flow
from scripts.pipeline.release import release_manifest as model
from tests.unit.pipeline.consumer_apps.support import digest, good_result
from tests.unit.pipeline.release import test_release_manifest as publications
from tests.unit.pipeline.release.test_lifecycle import MemoryStore

CLOCK = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
GO = ['go1-26', 'go1-26-dev']
PYTHON = ['python3-13']
ROOT = Path(__file__).resolve().parents[4]


def two_unit_manifest(run=20000, state='DEV_STABLE'):
    """A valid manifest holding two independent units: the Go pair and Python 3.13."""
    images = {}
    for name in GO + PYTHON:
        platforms = {f'linux/{arch}': digest(name + arch) for arch in ('amd64', 'arm64')}
        images[name] = dict(digest=digest(name), platforms=platforms, tag=f'131026-1200-r{run}-a1',
                            sboms=[dict(subject=subject, predicate_digest=digest('SBOM'))
                                   for subject in [digest(name), *platforms.values()]])
    manifest = dict(schema_version=1, release_id=f'r{run}-a1', run_id=run, attempt=1, source_sha='a' * 40,
                    repository=model.configuration()['repository'], branch='develop',
                    source_registry=model.registry('DEV'), units=[GO, PYTHON], images=images,
                    consumer_results={}, state=state)
    approved = (CLOCK - timedelta(hours=7)).isoformat()
    if state == 'DEV_STABLE':
        manifest.update(dev_stable_at=approved, dev_readback={n: i['digest'] for n, i in images.items()})
    else:
        manifest.update(dev_validated_at=approved)
    for unit in manifest['units']:
        for arch in ('amd64', 'arm64'):
            result = good_result(unit[0], arch)
            result['source_run_id'] = run
            for role, name in zip(('runtime', 'dev'), unit):
                result[role + '_image_ref'] = f'{manifest["source_registry"]}/image-base-{name}@{images[name]["digest"]}'
            manifest['consumer_results'][f'{unit[0]}-{arch}'] = result
    return manifest


def scope(frameworks, environment='HOM'):
    return dict(schema_version=1, enabled=True, frameworks=frameworks, soak_hours=0 if environment == 'DEV' else 6)


class SelectionCouplingTests(unittest.TestCase):
    def setUp(self):
        clock = patch.object(flow, 'now', return_value=CLOCK)
        clock.start()
        self.addCleanup(clock.stop)

    def select(self, manifest, states, frameworks=GO + PYTHON, environment='HOM'):
        with patch.object(flow, 'promotion_policy', return_value=scope(frameworks, environment)):
            return flow.choose([manifest], states, 0 if environment == 'DEV' else 6, CLOCK, environment=environment)

    def test_a_held_unit_blocks_an_unrelated_unit_of_the_same_manifest(self):
        for environment, state in (('HOM', 'DEV_STABLE'), ('DEV', 'DEV_VALIDATED')):
            with self.subTest(environment=environment):
                manifest = two_unit_manifest(state=state)
                self.assertEqual(self.select(manifest, {}, environment=environment), manifest)
                held = {'python3-13': {'hold': True, 'high_watermark': [1, 1]}}
                self.assertIsNone(self.select(manifest, held, environment=environment))

    def test_a_newer_watermark_on_one_unit_blocks_the_whole_manifest(self):
        manifest = two_unit_manifest()
        newer = {'python3-13': {'hold': False, 'high_watermark': [manifest['run_id'] + 1, 1]}}
        self.assertIsNone(self.select(manifest, newer))

    def test_a_one_unit_scope_never_splits_a_multi_unit_manifest(self):
        self.assertIsNone(self.select(two_unit_manifest(), {}, frameworks=GO))
        self.assertIsNone(self.select(two_unit_manifest(), {}, frameworks=PYTHON))


class WriteCouplingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        for target in (patch.dict(os.environ, GITHUB_RUN_ID='777', GITHUB_RUN_ATTEMPT='1'),
                       patch.object(flow, 'now', return_value=CLOCK)):
            target.start()
            self.addCleanup(target.stop)

    def test_one_unit_write_failure_holds_every_unit_without_success_receipt(self):
        manifest, store = two_unit_manifest(), MemoryStore()

        def write(manifest, name, environment, reports):
            if name == 'python3-13':
                raise ValueError('ECR put-image failed')

        with patch.object(flow, 'write_stable', side_effect=write), \
                patch.object(flow, 'stable_digest', return_value=None), self.assertRaises(ValueError):
            flow.publish_states(store, manifest, {name: None for name in manifest['images']}, 'HOM',
                                Path(self.temporary.name))
        self.assertTrue(all(store.records[f'state/{name}.json']['hold'] for name in GO + PYTHON))
        self.assertFalse(any(key.startswith('promoted/') or key.endswith('/completed.json') for key in store.records))


class ApprovalRecordTests(unittest.TestCase):
    def setUp(self):
        fixture = publications.ManifestTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    def test_a_missing_unit_fails_the_batch_while_a_complete_unit_subset_is_valid_v1(self):
        shutil.rmtree(self.fixture.root / 'publication-python3-13-1')

        def create(frameworks):
            return model.from_publications(self.fixture.root, frameworks, self.fixture.run, 1, self.fixture.revision)

        with self.assertRaises(FileNotFoundError):
            create(self.fixture.frameworks)
        subset = create([name for name in self.fixture.frameworks if name != 'python3-13'])
        self.assertEqual((len(subset['images']), len(subset['units'])), (15, 8))
        self.assertEqual(model.validate(json.loads(model.canonical(subset))), subset)
        with self.assertRaisesRegex(ValueError, 'complete'):
            create([name for name in self.fixture.frameworks if name not in ('python3-13', 'go1-26-dev')])


class WorkflowCouplingTests(unittest.TestCase):
    def test_publication_is_isolated_per_leg_but_dev_approval_needs_every_leg(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/build-base-images.yml').read_text())['jobs']
        self.assertTrue(jobs['build-push']['if'].startswith('always() &&'))
        self.assertEqual(set(jobs['dev-stable']['needs']), {'validate', 'runtime-contract', 'build-push'})
        # No status function: GitHub applies success() to every needed job, so
        # one failed matrix leg skips the DEV approval of the whole batch.
        self.assertFalse(any(name + '(' in jobs['dev-stable']['if']
                             for name in ('always', 'success', 'failure', 'cancelled')))


if __name__ == '__main__':
    unittest.main()
