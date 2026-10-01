"""DEV approval, exact-artifact HOM promotion, and recovery without rebuilding.

One destination-wide Actions concurrency lock surrounds each invocation.
S3 stores immutable manifests/receipts and conservative per-image holds.
ECR has no multi-repository transaction: incomplete writes retain holds and
never produce a successful release receipt.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from scripts.pipeline.artifacts.scan_images import scan_images
from scripts.pipeline.consumer_apps.inventory import json_document, require
from scripts.pipeline.consumer_apps.runner import execute, validate_result
from scripts.pipeline.release.find_promotion_candidate import load_quarantined_digests
from scripts.pipeline.release.release_manifest import (
    RELEASE_ID, checksum, configuration, consumer_inventory, from_publications,
    registry, release_units, timestamp, validate,
)
from scripts.pipeline.release.release_store import Store, command
from scripts.pipeline.release.release_trust import copy_image, read_index, verify_image
from scripts.pipeline.release.validate_ecr_repository import validate_repository as validate_ecr

ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)


def now():
    return datetime.now(timezone.utc)


def save(path, document):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, indent=2, allow_nan=False) + '\n')


def manifest_key(release_id):
    require(RELEASE_ID.fullmatch(release_id), 'release must be an exact r<RUN_ID>-a<ATTEMPT>')
    return f'releases/{release_id}/manifest.json'


def aws(environment, *args):
    return command('aws', *args, '--region', configuration()[environment]['region'], '--no-cli-pager')


def validate_destination(manifest, environment):
    cfg = configuration()[environment]
    identity = json_document(aws(environment, 'sts', 'get-caller-identity'))
    require(identity['Account'] == cfg['account_id'], 'wrong destination AWS account')
    for framework in manifest['images']:
        name = f'image-base-{framework}'
        description = json_document(aws(environment, 'ecr', 'describe-repositories',
                                        '--repository-names', name))
        validate_ecr(description, name, cfg['account_id'], cfg['region'])


def stable_digest(environment, framework):
    try:
        response = json_document(aws(environment, 'ecr', 'describe-images',
                                      '--repository-name', f'image-base-{framework}',
                                      '--image-ids', 'imageTag=stable'))
    except subprocess.CalledProcessError as error:
        if b'(ImageNotFoundException)' in (error.stderr or b''):
            return None
        raise
    entries = response['imageDetails']
    require(len(entries) == 1 and 'stable' in entries[0]['imageTags'], 'ambiguous stable read-back')
    return entries[0]['imageDigest']


def write_stable(manifest, framework, environment, reports):
    item = manifest['images'][framework]
    image = f'{registry(environment)}/image-base-{framework}'
    directory = Path(reports) / framework
    read_index(image + '@' + item['digest'], item, directory)
    try:
        aws(environment, 'ecr', 'put-image', '--repository-name', f'image-base-{framework}',
            '--image-tag', 'stable', '--image-digest', item['digest'],
            '--image-manifest', 'file://' + str((directory / 'index.json').resolve()))
    except subprocess.CalledProcessError as error:
        if b'(ImageAlreadyExistsException)' not in (error.stderr or b''):
            raise
    require(stable_digest(environment, framework) == item['digest'], 'stable digest read-back mismatch')
    read_index(image + ':stable', item, directory / 'stable-readback')


def verify_approved(manifest):
    validate(manifest)
    require(manifest['state'] == 'DEV_STABLE', 'release has no DEV stable approval')
    require(timestamp(manifest['dev_stable_at']) <= now(), 'DEV approval timestamp is in the future')
    inventory = consumer_inventory(manifest)
    expected = {f'{unit[0]}-{arch}' for unit in manifest['units'] for arch in ('amd64', 'arm64')}
    require(set(manifest['consumer_results']) == expected, 'consumer coverage is incomplete')
    for key, result in manifest['consumer_results'].items():
        require(key == result['framework'] + '-' + result['platform'].removeprefix('linux/'),
                'consumer result is filed under another framework or architecture')
        validate_result(result, inventory)
    require(manifest['dev_readback'] == {f: i['digest'] for f, i in manifest['images'].items()},
            'DEV stable read-back did not confirm the whole release')
    return manifest


def ordering(manifest):
    return manifest['run_id'], manifest['attempt']


def choose(manifests, states, soak_hours, clock, requested=None, resume=False):
    """Selection consumes immutable approvals; it never resolves DEV:stable."""
    minimum = configuration()['minimum_soak_hours']
    require(math.isfinite(soak_hours) and soak_hours >= minimum, 'minimum soak is six hours')
    require(not resume or requested, 'resuming automation requires an explicit release')
    eligible = []
    for manifest in manifests:
        verify_approved(manifest)
        if requested and manifest['release_id'] != requested:
            continue
        if timestamp(manifest['dev_stable_at']) + timedelta(hours=soak_hours) > clock:
            continue
        accepted, changed = True, False
        for name, image in manifest['images'].items():
            state = states.get(name) or {}
            if state.get('hold') and not resume:
                accepted = False
            current_order = tuple(state.get('high_watermark', [0, 0]))
            if ordering(manifest) < current_order:
                accepted = False
            changed |= (state.get('release_id') != manifest['release_id']
                        or state.get('digest') != image['digest'] or state.get('hold', False))
        if accepted and changed:
            eligible.append(manifest)
    return max(eligible, key=ordering) if eligible else None


def publish_states(store, manifest, before, environment, reports, *, recovery=False, reason=''):
    """All pre-write checks must finish before this function is called."""
    receipt = dict(schema_version=1, release_id=manifest['release_id'],
                   manifest_digest=checksum(manifest), environment=environment,
                   action='recovery' if recovery else 'promotion', reason=reason,
                   actor=os.environ.get('GITHUB_ACTOR', ''),
                   run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                   started_at=now().isoformat(), before=before, writes={}, status='IN_PROGRESS',
                   observed_before={name: stable_digest(environment, name) for name in manifest['images']})
    if not recovery:
        for name, previous in before.items():
            if previous and not previous.get('hold'):
                require(receipt['observed_before'][name] == previous['digest'],
                        'stable changed outside the Factory; reconcile the destination first')
    event_key = f'events/r{receipt["run_id"]}-a{receipt["attempt"]}'
    # Persist every hold before ANY tag write. A killed runner leaves an
    # operator-visible pause, including when one member of a pair was written.
    for name, item in manifest['images'].items():
        store.put(f'state/{name}.json', dict(before[name] or {}, hold=True,
                  pending_release=manifest['release_id'], reason=reason or 'stable write in progress'))
    store.put(event_key + '/started.json', receipt, immutable=True)
    try:
        for name, item in manifest['images'].items():
            write_stable(manifest, name, environment, reports)
            receipt['writes'][name] = item['digest']
        # Independent final read of all members, after the last write.
        for name, item in manifest['images'].items():
            require(stable_digest(environment, name) == item['digest'], 'final pair read-back mismatch')
        receipt.update(status='PASS', completed_at=now().isoformat())
        store.put(event_key + '/completed.json', receipt, immutable=True)
        if environment == 'HOM' and not recovery:
            store.put(f'promoted/{manifest["release_id"]}.json', {
                'manifest_digest': checksum(manifest), 'digests': receipt['writes']}, immutable=True)
        for name, item in manifest['images'].items():
            previous = before[name] or {}
            watermark = max(tuple(previous.get('high_watermark', [0, 0])), ordering(manifest))
            store.put(f'state/{name}.json', dict(release_id=manifest['release_id'], digest=item['digest'],
                      high_watermark=list(watermark), hold=recovery, reason=reason,
                      event_key=event_key, updated_at=receipt['completed_at']))
        return receipt
    except ERRORS as error:
        receipt.update(status='FAIL', error=str(error), completed_at=now().isoformat())
        receipt['observed_after_failure'] = {}
        for name in manifest['images']:
            try:
                receipt['observed_after_failure'][name] = stable_digest(environment, name)
            except ERRORS as observation_error:
                receipt['observed_after_failure'][name] = {'error': str(observation_error)}
        # Also re-hold members whose state write succeeded before a later state
        # operation failed. Registry/metadata failures never authorize a retry.
        for name in manifest['images']:
            try:
                store.put(f'state/{name}.json', dict(before[name] or {}, hold=True,
                          pending_release=manifest['release_id'], reason='incomplete stable operation'))
            except ERRORS:
                pass
        try:
            store.put(event_key + '/failed.json', receipt, immutable=True)
        except ERRORS:
            pass  # Local artifact and persistent holds retain the original failure.
        raise
    finally:
        save(Path(reports) / 'release-outcome.json', receipt)


def approve_dev(args):
    manifest = from_publications(args.evidence, json.loads(args.frameworks),
                                 os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'],
                                 os.environ['GITHUB_SHA'])
    store = Store('DEV')
    existing = store.get(manifest_key(manifest['release_id']), optional=True)
    if existing:
        verify_approved(existing)
        require(all(existing[key] == value for key, value in manifest.items()),
                'release approval already binds different content')
        return existing
    validate_destination(manifest, 'DEV')
    inventory = consumer_inventory(manifest)
    manifest['consumer_results'] = {}
    for name in manifest['images']:
        verify_image(manifest, name, registry('DEV'), args.reports / 'trust' / name)
    for unit in manifest['units']:
        for arch in ('amd64', 'arm64'):
            result = execute(inventory, unit[0], arch, args.reports / 'consumers')
            validate_result(result, inventory)
            manifest['consumer_results'][f'{unit[0]}-{arch}'] = result
    before = {name: store.get(f'state/{name}.json', optional=True) for name in manifest['images']}
    require(all(not value or not value.get('hold') for value in before.values()),
            'DEV stable has an incomplete operation; reconcile before releasing another candidate')
    publish_states(store, manifest, before, 'DEV', args.reports)
    manifest.update(state='DEV_STABLE', dev_stable_at=now().isoformat(),
                    dev_readback={name: item['digest'] for name, item in manifest['images'].items()})
    verify_approved(manifest)
    # Only this final immutable record makes a release visible to HOM selection.
    store.put(manifest_key(manifest['release_id']), manifest, immutable=True)
    save(args.reports / 'release-manifest.json', manifest)
    return manifest


def promote_hom(args):
    source, target = Store('DEV'), Store('HOM')
    if args.release:
        manifests = [source.get(manifest_key(args.release))]
    else:
        manifests = [source.get(key) for key in source.keys('releases/') if key.endswith('/manifest.json')]
    names = {name for manifest in manifests for name in validate(manifest)['images']}
    states = {name: target.get(f'state/{name}.json', optional=True) for name in names}
    manifest = choose(manifests, states, args.soak_hours, now(), args.release, args.resume)
    if manifest is None:
        require(not args.release, 'requested release is held, superseded, already promoted, or still in soak')
        save(args.reports / 'release-outcome.json', {'status': 'SKIPPED', 'reason': 'no eligible DEV release'})
        health_evidence(args.reports, names, None, False)
        return
    # A failed later pre-write gate must remain visible to operational health.
    health_evidence(args.reports, manifest['images'], manifest, False)
    validate_destination(manifest, 'HOM')
    for name, item in manifest['images'].items():
        require(item['digest'] not in load_quarantined_digests(
            'policies/release/promotion-quarantine.json', f'image-base-{name}'), 'digest is quarantined')
        verify_image(manifest, name, registry('DEV'), args.reports / 'source-trust' / name)
        require(scan_images('remote', f'{registry("DEV")}/image-base-{name}@{item["digest"]}',
                            args.reports / 'scans' / name) == 0, 'blocking promotion re-scan failed')
    # Copy the whole manifest and verify the whole destination before stable.
    for name in manifest['images']:
        copy_image(manifest, name, registry('HOM'))
    for name, item in manifest['images'].items():
        read_index(f'{registry("HOM")}/image-base-{name}:{item["tag"]}', item,
                   args.reports / 'target-tags' / name)
        verify_image(manifest, name, registry('HOM'), args.reports / 'target-trust' / name)
    target.put(manifest_key(manifest['release_id']), manifest, immutable=True)
    before = {name: states[name] for name in manifest['images']}
    publish_states(target, manifest, before, 'HOM', args.reports)
    health_evidence(args.reports, manifest['images'], manifest, True)
    save(args.reports / 'release-manifest.json', manifest)


def health_evidence(reports, frameworks, manifest, promoted):
    """Keep the existing small, per-framework operational metrics contract."""
    if not frameworks:
        return
    units = release_units(sorted(frameworks))
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    root = reports / 'health'
    save(root / 'promotion-batch.json', dict(schema_version=1, frameworks=sorted(frameworks),
         units=units, prewrite_authorized=promoted, promoted=promoted))
    for unit in units:
        binding = None if len(unit) == 1 or not manifest else dict(status='PAIR_BOUND',
            runtime_digest=manifest['images'][unit[0]]['digest'], dev_digest=manifest['images'][unit[1]]['digest'])
        for name in unit:
            digest = manifest['images'][name]['digest'] if manifest else None
            save(root / f'promotion-{name}-{attempt}' / 'promotion-evidence.json', dict(
                repository=f'image-base-{name}', environment='HOM', promoted=promoted,
                skipped=manifest is None, candidate_digest=digest, digest=digest,
                stable_digest_observed=digest if promoted else None,
                read_back_status='confirmed' if promoted else 'not_run', pair_authorization=binding))


def recover_hom(args):
    require(args.reason and args.reason.strip(), 'recovery requires an operational reason')
    target = Store('HOM')
    manifest = verify_approved(target.get(manifest_key(args.release)))
    receipt = target.get(f'promoted/{args.release}.json')
    require(receipt == {'manifest_digest': checksum(manifest),
                       'digests': {n: i['digest'] for n, i in manifest['images'].items()}},
            'recovery target has never completed HOM promotion')
    validate_destination(manifest, 'HOM')
    for name, item in manifest['images'].items():
        verify_image(manifest, name, registry('HOM'), args.reports / 'target-trust' / name)
        require(scan_images('remote', f'{registry("HOM")}/image-base-{name}@{item["digest"]}',
                            args.reports / 'scans' / name) == 0, 'blocking recovery re-scan failed')
    before = {name: target.get(f'state/{name}.json', optional=True) for name in manifest['images']}
    publish_states(target, manifest, before, 'HOM', args.reports, recovery=True, reason=args.reason)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('approve-dev', 'promote-hom', 'recover-hom'))
    parser.add_argument('--frameworks')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--release')
    parser.add_argument('--soak-hours', type=float)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--reason')
    parser.add_argument('--reports', type=Path, default=Path('reports/release'))
    args = parser.parse_args(argv)
    try:
        if args.soak_hours is None:
            args.soak_hours = configuration()['minimum_soak_hours']
        if args.operation == 'promote-hom':
            require(configuration()['promotion_authorized'], 'HOM promotion is disabled in pipeline config')
        if args.release:
            manifest_key(args.release)
        if args.resume:
            require(args.operation == 'promote-hom' and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch',
                    'only an explicit manual promotion can resume automation')
        {'approve-dev': approve_dev, 'promote-hom': promote_hom, 'recover-hom': recover_hom}[args.operation](args)
    except ERRORS as error:
        # Do not print captured CLI output: the log needs a bounded diagnostic.
        if not (args.reports / 'release-outcome.json').exists():
            save(args.reports / 'release-outcome.json', {'status': 'FAIL', 'error': str(error)})
        print(f'release lifecycle blocked: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
