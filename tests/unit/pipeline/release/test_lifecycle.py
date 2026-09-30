"""Safety boundaries for exact release selection and cross-account mutations."""
import base64
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.pipeline.release import lifecycle as flow
from scripts.pipeline.release import release_manifest as model
from scripts.pipeline.release import release_trust as trust
from scripts.pipeline.release.release_store import Store
from scripts.pipeline.runtime.runtime_images import publication_contract
from tests.unit.pipeline.consumer_apps.support import digest, good_result

CLOCK = datetime(2026, 9, 30, 20, tzinfo=timezone.utc)
PAIR = ['go1-26', 'go1-26-dev']


def manifest(run=12345, age=7):
    images = {}
    for name in PAIR:
        platforms = {f'linux/{arch}': digest(name + arch) for arch in ('amd64', 'arm64')}
        image_digest = digest(name)
        images[name] = dict(digest=image_digest, platforms=platforms,
            tag=f'300926-0000-r{run}-a1', sboms=[dict(subject=d, predicate_digest=digest('SBOM'))
                for d in [image_digest, *platforms.values()]])
    m = dict(schema_version=1, release_id=f'r{run}-a1', run_id=run, attempt=1,
        source_sha='a' * 40, repository=model.configuration()['repository'], branch='develop',
        source_registry=model.registry('DEV'), units=[PAIR], images=images,
        state='DEV_STABLE', dev_stable_at=(CLOCK-timedelta(hours=age)).isoformat(),
        dev_readback={name: item['digest'] for name, item in images.items()}, consumer_results={})
    for arch in ('amd64', 'arm64'):
        result = good_result(architecture=arch)
        result['source_run_id'] = run
        for role, name in [('runtime', PAIR[0]), ('dev', PAIR[1])]:
            result[role+'_image_ref'] = f'{m["source_registry"]}/image-base-{name}@{images[name]["digest"]}'
        m['consumer_results'][f'go1-26-{arch}'] = result
    return m


class MemoryStore:
    def __init__(self, records=None):
        self.records = copy.deepcopy(records or {})
        self.writes = []

    def get(self, key, optional=False):
        if key not in self.records:
            if optional:
                return None
            raise ValueError('missing record: '+key)
        return copy.deepcopy(self.records[key])

    def put(self, key, value, immutable=False):
        if immutable and key in self.records and self.records[key] != value:
            raise ValueError('immutable record conflict')
        self.records[key] = copy.deepcopy(value)
        self.writes.append(key)

    def keys(self, prefix):
        return [key for key in self.records if key.startswith(prefix)]


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(flow, 'now', return_value=CLOCK)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_A_is_selected_while_newer_B_has_not_completed_its_own_soak(self):
        a, b = manifest(), manifest(12346, 1)
        self.assertEqual(flow.choose([a, b], {}, 6, CLOCK)['release_id'], a['release_id'])

    def test_soak_begins_at_dev_approval_and_cannot_be_shortened(self):
        self.assertIsNone(flow.choose([manifest(age=5.99)], {}, 6, CLOCK))
        self.assertIsNotNone(flow.choose([manifest(age=6)], {}, 6, CLOCK))
        for hours in (0, -1, 5.9, float('nan'), float('inf')):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                flow.choose([manifest()], {}, hours, CLOCK)

    def test_unapproved_or_incomplete_consumer_results_never_authorize(self):
        for mutate in (lambda m: m.update(state='CANDIDATE'),
                       lambda m: m['consumer_results'].pop('go1-26-arm64'),
                       lambda m: m['consumer_results'].update({'go1-26-arm64': m['consumer_results']['go1-26-amd64']}),
                       lambda m: m['consumer_results']['go1-26-amd64'].update(runtime_digest=digest('other')),
                       lambda m: m['dev_readback'].update({'go1-26': digest('other')})):
            m = manifest(); mutate(m)
            with self.assertRaises(ValueError):
                flow.choose([m], {}, 6, CLOCK)

    def test_partial_pair_wrong_source_and_ambiguous_identity_are_rejected(self):
        for mutate in (lambda m: m['images'].pop('go1-26-dev'),
                       lambda m: m.update(source_registry=model.registry('HOM')),
                       lambda m: m.update(branch='main'),
                       lambda m: m.update(run_id=True),
                       lambda m: m['images']['go1-26'].update(tag='300926-0000-r12345-a2'),
                       lambda m: m['images']['go1-26']['sboms'].pop()):
            m = manifest(); mutate(m)
            with self.assertRaises(ValueError):
                model.validate(m)

    def test_recovery_hold_and_monotonic_high_watermark(self):
        m = manifest()
        states = {name: {'hold': True, 'high_watermark': [12346, 1]} for name in PAIR}
        self.assertIsNone(flow.choose([m], states, 6, CLOCK, m['release_id'], True))
        n = manifest(12347)
        self.assertIsNone(flow.choose([n], states, 6, CLOCK))
        self.assertEqual(flow.choose([n], states, 6, CLOCK, n['release_id'], True), n)
        with self.assertRaises(ValueError):
            flow.choose([n], states, 6, CLOCK, resume=True)

    def test_already_promoted_is_an_idempotent_skip(self):
        m = manifest()
        states = {n: {'release_id': m['release_id'], 'digest': i['digest'], 'hold': False,
                      'high_watermark': [m['run_id'], 1]} for n, i in m['images'].items()}
        self.assertIsNone(flow.choose([m], states, 6, CLOCK))

    def test_release_units_cover_node_companions_and_full_catalog(self):
        self.assertEqual(model.release_units(['nodejs22-dev', 'nodejs22']), [['nodejs22', 'nodejs22-dev']])
        self.assertEqual(len(model.release_units(list(model.CATALOG))), 9)
        with self.assertRaises(ValueError):
            model.release_units(['nodejs22-dev'])


class MutationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.reports = Path(self.directory.name)
        self.m = manifest()
        self.env = patch.dict(os.environ, GITHUB_RUN_ID='555', GITHUB_RUN_ATTEMPT='1')
        self.env.start(); self.addCleanup(self.env.stop)
        self.clock = patch.object(flow, 'now', return_value=CLOCK)
        self.clock.start(); self.addCleanup(self.clock.stop)

    def states(self):
        return {name: None for name in PAIR}

    def test_second_tag_failure_leaves_all_members_held_without_success_receipt(self):
        store = MemoryStore()
        with patch.object(flow, 'write_stable', side_effect=[None, ValueError('write failed')]), \
             patch.object(flow, 'stable_digest', return_value=None) as readback, self.assertRaises(ValueError):
            flow.publish_states(store, self.m, self.states(), 'HOM', self.reports)
        self.assertEqual(readback.call_count, 4)
        self.assertFalse(any(k.startswith('promoted/') for k in store.records))
        self.assertTrue(all(store.records[f'state/{n}.json']['hold'] for n in PAIR))
        self.assertEqual(json.loads((self.reports/'release-outcome.json').read_text())['status'], 'FAIL')

    def test_all_holds_are_durable_before_first_write(self):
        store = MemoryStore()
        def write(*args):
            self.assertTrue(all(store.records[f'state/{n}.json']['hold'] for n in PAIR))
        with patch.object(flow, 'write_stable', side_effect=write), \
             patch.object(flow, 'stable_digest', side_effect=[None, None]+[self.m['images'][n]['digest'] for n in PAIR]):
            flow.publish_states(store, self.m, self.states(), 'HOM', self.reports)
        self.assertTrue(all(not store.records[f'state/{n}.json']['hold'] for n in PAIR))
        self.assertEqual(store.records['promoted/'+self.m['release_id']+'.json']['manifest_digest'],
                         model.checksum(self.m))

    def test_final_readback_failure_never_marks_promoted(self):
        store = MemoryStore()
        with patch.object(flow, 'write_stable'), patch.object(flow, 'stable_digest', return_value=digest('wrong')), \
             self.assertRaises(ValueError):
            flow.publish_states(store, self.m, self.states(), 'HOM', self.reports)
        self.assertFalse(any(k.startswith('promoted/') for k in store.records))

    def test_recovery_keeps_holds_and_preserves_newest_seen_release(self):
        before = {n: {'high_watermark': [99999, 2]} for n in PAIR}
        store = MemoryStore()
        with patch.object(flow, 'write_stable'), \
             patch.object(flow, 'stable_digest', side_effect=[None, None]+[self.m['images'][n]['digest'] for n in PAIR]):
            flow.publish_states(store, self.m, before, 'HOM', self.reports, recovery=True, reason='regression')
        for name in PAIR:
            state = store.records[f'state/{name}.json']
            self.assertTrue(state['hold'])
            self.assertEqual(state['high_watermark'], [99999, 2])

    def test_copy_trust_and_scan_failures_cannot_move_any_stable_tag(self):
        for failure in ('source-trust', 'scan', 'copy', 'target-trust'):
            source = MemoryStore({flow.manifest_key(self.m['release_id']): self.m})
            target = MemoryStore()
            args = SimpleNamespace(release=self.m['release_id'], soak_hours=6, resume=False, reports=self.reports)
            events = []
            def verify(m, name, registry, directory):
                events.append(('verify', registry, name))
                if failure == 'source-trust' or (failure == 'target-trust' and registry == model.registry('HOM')):
                    raise ValueError('trust failed')
            def copy_artifact(*args):
                events.append(('copy',))
                if failure == 'copy':
                    raise ValueError('missing layer')
            with self.subTest(failure=failure), patch.object(flow, 'Store', side_effect=[source, target]), \
                 patch.object(flow, 'validate_destination'), patch.object(flow, 'verify_image', side_effect=verify), \
                 patch.object(flow, 'scan_images', return_value=1 if failure=='scan' else 0), \
                 patch.object(flow, 'copy_image', side_effect=copy_artifact), patch.object(flow, 'read_index'), \
                 patch.object(flow, 'publish_states') as publish, self.assertRaises(ValueError):
                flow.promote_hom(args)
            publish.assert_not_called()
            if failure == 'target-trust':
                self.assertEqual(sum(e[0]=='copy' for e in events), 2)

    def test_recovery_requires_successful_prior_hom_promotion(self):
        target = MemoryStore({flow.manifest_key(self.m['release_id']): self.m})
        args = SimpleNamespace(release=self.m['release_id'], reason='rollback', reports=self.reports)
        with patch.object(flow, 'Store', return_value=target), patch.object(flow, 'write_stable') as write, \
             self.assertRaises(ValueError):
            flow.recover_hom(args)
        write.assert_not_called()

    def test_stable_write_uses_exact_original_manifest_and_checks_remote_digest(self):
        with patch.object(flow, 'read_index'), patch.object(flow, 'aws') as aws, \
             patch.object(flow, 'stable_digest', return_value=digest('unexpected')), self.assertRaises(ValueError):
            flow.write_stable(self.m, PAIR[0], 'HOM', self.reports)
        self.assertIn('--image-digest', aws.call_args.args)
        self.assertIn(self.m['images'][PAIR[0]]['digest'], aws.call_args.args)


class StoreAndTrustTests(unittest.TestCase):
    def test_optional_access_denied_is_not_treated_as_no_release(self):
        for code, missing in [('NoSuchKey', True), ('AccessDenied', False), ('RequestTimeout', False)]:
            error = subprocess.CalledProcessError(1, ['aws'], stderr=f'An error occurred ({code})'.encode())
            with patch.object(Store, 'aws', side_effect=error):
                if missing:
                    self.assertIsNone(Store('DEV').get('key', optional=True))
                else:
                    with self.assertRaises(subprocess.CalledProcessError):
                        Store('DEV').get('key', optional=True)

    def test_changed_immutable_record_is_rejected(self):
        error = subprocess.CalledProcessError(1, ['aws'], stderr=b'(PreconditionFailed)')
        with patch.object(Store, 'aws', side_effect=error), patch.object(Store, 'get', return_value={'digest':'other'}), \
             self.assertRaises(ValueError):
            Store('DEV').put('releases/r1-a1/manifest.json', {'digest':'expected'}, immutable=True)

    def test_spdx_requires_verified_original_predicate_and_exact_subject(self):
        predicate = {'spdxVersion':'SPDX-2.3'}
        subject = digest('image')
        statement = {'predicateType':'https://spdx.dev/Document', 'predicate':predicate,
                     'subject':[{'digest':{'sha256':subject[7:]}}]}
        raw = json.dumps({'payload':base64.b64encode(json.dumps(statement).encode()).decode()}).encode()
        trust.verify_spdx(raw, {'subject':subject,'predicate_digest':model.checksum(predicate)})
        for expected in ({'subject':digest('other'),'predicate_digest':model.checksum(predicate)},
                         {'subject':subject,'predicate_digest':digest('tampered')}):
            with self.assertRaises(ValueError):
                trust.verify_spdx(raw, expected)

    def test_copy_includes_referrers_and_legacy_attachments_without_build(self):
        m=manifest()
        with patch.object(trust, 'command') as command:
            trust.copy_image(m, PAIR[0], model.registry('HOM'))
        oras, cosign = [call.args for call in command.call_args_list]
        self.assertEqual(oras[:3], ('oras','cp','--recursive'))
        self.assertEqual(cosign[:2], ('cosign','copy'))
        self.assertIn('@'+m['images'][PAIR[0]]['digest'], oras[3])
        self.assertNotIn(':stable', ' '.join(oras+cosign))


if __name__ == '__main__':
    unittest.main()
