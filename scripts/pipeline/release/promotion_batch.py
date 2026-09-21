"""Authorize independent promotion units behind a global pre-write barrier.

Selection, trust verification and blocking scans share one process: saved JSON
is audit evidence, never an authorization token for a later mutation phase.
ECR cannot atomically write two tags. A failed write/read-back leaves the whole
pair unpromoted in the evidence, including the original ECR state for recovery.
A failed compiled pair or interpreted singleton does not block unrelated units.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from scripts.pipeline.artifacts.image_reference import require_digest_reference
from scripts.pipeline.artifacts.scan_images import scan_images
from scripts.pipeline.catalog.validate_inputs import validate
from scripts.pipeline.release.find_promotion_candidate import (
    is_build_tag, load_quarantined_digests, select_candidate, skip_reason,
    stable_state, write_evidence,
)
from scripts.pipeline.release.report_unfixed_cves import report_unfixed_cves
from scripts.pipeline.release.verify_promotion import verify_promotion
from scripts.pipeline.release.verify_promotion_pair import verify_pair
from scripts.pipeline.release.verify_stable import unique_object, verify_stable
from scripts.pipeline.runtime.runtime_images import ROOT, publication_contract

MINIMUM_SOAK_HOURS = 6
ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError)


def promotion_units(frameworks, soak_hours):
    """Resolve compiled pairs and interpreted singletons before AWS access."""
    catalog = {path.stem for path in (ROOT / 'frameworks').glob('*.yaml')}
    validate(json.dumps(frameworks), catalog, soak_hours)
    if not math.isfinite(soak_hours) or soak_hours < MINIMUM_SOAK_HOURS:
        raise ValueError('production promotion requires at least 6 hours of real soak')
    units, seen = [], set()
    for framework in frameworks:
        resolution = publication_contract(framework, frameworks)
        runtime = resolution['runtime_framework']
        if runtime in seen:
            continue
        seen.add(runtime)
        units.append([runtime, resolution['dev_framework']]
                     if resolution['dev_framework'] else [runtime])
    return units


def load_details(repository):
    raw = subprocess.run(
        ['aws', 'ecr', 'describe-images', '--repository-name', repository,
         '--output', 'json', '--no-cli-pager'], check=True, capture_output=True,
        text=True, timeout=60).stdout
    response = json.loads(raw, object_pairs_hook=unique_object)
    if (not isinstance(response, dict) or response.get('nextToken')
            or not isinstance(response.get('imageDetails'), list)
            or any(not isinstance(entry, dict) for entry in response['imageDetails'])):
        raise ValueError('complete ECR image inventory required before stable authorization')
    return response


def write_stable(image, digest):
    require_digest_reference(f'{image}@{digest}')
    subprocess.run(['docker', 'buildx', 'imagetools', 'create', '--tag',
                    f'{image}:stable', f'{image}@{digest}'], check=True, timeout=120)


def record_outcome(evidence, write_succeeded, skipped=False):
    """A successful write alone can never be reported as a promotion."""
    result = dict(evidence)
    result.setdefault('candidate_digest', result.get('digest'))
    result.setdefault('stable_digest_observed', None)
    result.setdefault('read_back_status', 'not_run')
    result['skipped'] = skipped
    result['promoted'] = bool(
        write_succeeded and not skipped and result['read_back_status'] == 'confirmed'
        and result['candidate_digest'] and result['candidate_digest'] == result.get('digest')
        and result['stable_digest_observed'] == result['candidate_digest'])
    if not result['promoted'] and not skipped:
        result['reason'] = ('promotion not completed: '
                            + (result.get('read_back_error') or result.get('error')
                               or result.get('reason') or 'candidate was not evaluated'))
    return result


def promote_batch(frameworks, registry, repository, soak_hours, attempt, reports,
                  quarantine, now=None):
    units = promotion_units(frameworks, soak_hours)
    if not re.fullmatch(r'[1-9][0-9]*', str(attempt)):
        raise ValueError('promotion run attempt must be a positive integer')
    if not isinstance(registry, str) or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?', registry):
        raise ValueError('registry must be a hostname without a path')
    now = now or datetime.now(timezone.utc)
    reports = Path(reports)
    ordered = [framework for unit in units for framework in unit]
    paths = {name: reports / f'promotion-{name}-{attempt}' / 'promotion-evidence.json'
             for name in ordered}
    scans = {name: reports / f'promotion-scans-{name}-{attempt}' for name in ordered}
    evidence = {name: {
        'repository': f'image-base-{name}', 'soak_hours': soak_hours,
        'evaluated_at': now.isoformat(), 'promoted': False, 'skipped': False,
        'candidate_digest': None, 'stable_digest_observed': None,
        'read_back_status': 'not_run', 'write_status': 'not_run',
        'reason': 'candidate not yet evaluated',
    } for name in ordered}
    unit_results = [{'frameworks': unit, 'status': 'PENDING', 'phase': 'inventory',
                     'prewrite_authorized': False, 'promoted': False, 'errors': []}
                    for unit in units]
    owner = {name: unit for unit in unit_results for name in unit['frameworks']}
    batch = {'schema_version': 1, 'frameworks': frameworks, 'units': units,
             'evaluated_at': now.isoformat(), 'authorized_pairs': [],
             'unit_results': unit_results, 'authorized_units': [],
             'failed_units': [], 'skipped_units': [],
             'prewrite_barrier_complete': False,
             'prewrite_authorized': False, 'promoted': False}
    eligible = []

    def fail(unit, phase, error, framework=None):
        # Failure belongs to the atomic authorization unit, not the whole
        # batch. A compiled pair shares the failure; unrelated units do not.
        unit['status'] = 'FAILED'
        unit['phase'] = phase
        unit['promoted'] = False
        unit['errors'].append({'phase': phase, 'framework': framework, 'message': str(error)})
        message = '; '.join(item['message'] for item in unit['errors'])
        for name in unit['frameworks']:
            evidence[name]['error'] = message
            evidence[name]['promoted'] = False

    def save():
        batch['authorized_units'] = [unit['frameworks'] for unit in unit_results
                                     if unit['status'] == 'AUTHORIZED']
        batch['failed_units'] = [unit['frameworks'] for unit in unit_results
                                if unit['status'] == 'FAILED']
        batch['skipped_units'] = [unit['frameworks'] for unit in unit_results
                                 if unit['status'] == 'SKIPPED']
        # These are batch summaries, never the authority to mutate an
        # individual unit. Mixed success/failure remains a failed batch.
        batch['prewrite_authorized'] = bool(
            batch['prewrite_barrier_complete'] and batch['authorized_units']
            and not batch['failed_units'])
        batch['promoted'] = bool(
            batch['authorized_units'] and not batch['failed_units']
            and all(unit['promoted'] for unit in unit_results
                    if unit['status'] == 'AUTHORIZED'))
        for name, entry in evidence.items():
            unit = owner[name]
            entry.update(unit_frameworks=unit['frameworks'], unit_status=unit['status'],
                         unit_prewrite_authorized=unit['prewrite_authorized'])
            write_evidence(paths[name], entry)
        write_evidence(reports / 'promotion-batch.json', batch)

    save()
    try:
        # Global inventory phase: snapshot all repositories before selection.
        # A failed inventory disqualifies its unit while preserving other units.
        inventories = {}
        for name in ordered:
            try:
                document = load_details(evidence[name]['repository'])
                write_evidence(paths[name].parent / 'ecr-before.json', document)
                inventories[name] = document['imageDetails']
            except ERRORS as error:
                fail(owner[name], 'inventory', error, name)
        save()

        # Global selection phase. Original ECR timestamps, quarantine policy
        # and candidate ordering remain authoritative within each repository.
        for unit in unit_results:
            if unit['status'] == 'FAILED':
                continue
            unit['phase'] = 'selection'
            for name in unit['frameworks']:
                entry = evidence[name]
                try:
                    details = inventories[name]
                    quarantined = load_quarantined_digests(str(quarantine), entry['repository'])
                    selected = select_candidate(details, soak_hours, now, quarantined)
                    entry.update(stable_state(details, now))
                    if selected is None:
                        entry.update(skipped=True, reason=skip_reason(details, soak_hours, now, quarantined))
                        continue
                    pushed_at, tag, digest = selected
                    image = f"{registry}/{entry['repository']}"
                    require_digest_reference(f'{image}@{digest}')
                    if not is_build_tag(tag):
                        raise ValueError('candidate must have a valid immutable build tag')
                    entry.update(image=image, tag=tag, digest=digest, candidate_digest=digest,
                                 candidate_pushed_at=pushed_at.isoformat(), reason='eligible candidate')
                    eligible.append(name)
                except ERRORS as error:
                    fail(unit, 'selection', error, name)
                    break
        save()

        # Global pair authorization phase: incomplete eligible pairs cannot
        # leave a writable half-pair, but do not suppress unrelated runtimes.
        for unit in unit_results:
            if unit['status'] == 'FAILED':
                continue
            unit['phase'] = 'pair_authorization'
            members = [evidence[name] for name in unit['frameworks']]
            if all(member['skipped'] for member in members):
                unit.update(status='SKIPPED', phase='complete')
                continue
            try:
                if any(member['skipped'] for member in members):
                    raise ValueError('complete eligible pair required before stable writes: '
                                     + str(unit['frameworks']))
                if len(members) == 2:
                    binding = verify_pair(*members)
                    batch['authorized_pairs'].append(binding)
                    for member in members:
                        member['pair_authorization'] = binding
            except ERRORS as error:
                fail(unit, 'pair_authorization', error)
        save()

        # All trust evaluations finish before the scan phase; all scans finish
        # before the first mutation. Failure stays local to its compiled pair
        # or interpreted singleton. No persisted boolean grants authorization.
        for unit in unit_results:
            if unit['status'] != 'PENDING':
                continue
            unit['phase'] = 'trust'
            for name in unit['frameworks']:
                entry = evidence[name]
                try:
                    verify_promotion(f"{entry['image']}@{entry['digest']}", repository, scans[name])
                    entry['trust_verified'] = True
                except ERRORS as error:
                    fail(unit, 'trust', error, name)
                    break
            save()
        for unit in unit_results:
            if unit['status'] != 'PENDING':
                continue
            unit['phase'] = 'scan'
            for name in unit['frameworks']:
                entry = evidence[name]
                try:
                    if scan_images('remote', f"{entry['image']}@{entry['digest']}", scans[name]) != 0:
                        raise ValueError(f'blocking promotion scan failed for {name}')
                    entry['scan_passed'] = True
                except ERRORS as error:
                    fail(unit, 'scan', error, name)
                    break
            if unit['status'] != 'FAILED':
                unit.update(status='AUTHORIZED', phase='prewrite_authorized', prewrite_authorized=True)
            save()
        batch['prewrite_barrier_complete'] = True
        save()

        for unit in unit_results:
            if unit['status'] != 'AUTHORIZED':
                continue
            # Canonical runtime then dev order, under the shared stable lock.
            # A failed write stops this pair's remaining writes, not later units.
            unit['phase'] = 'write'
            for name in unit['frameworks']:
                entry = evidence[name]
                entry['write_status'] = 'started'
                save()
                try:
                    write_stable(entry['image'], entry['digest'])
                    entry['write_status'] = 'completed'
                except ERRORS as error:
                    entry.update(write_status='failed', write_error=str(error))
                    fail(unit, 'write', error, name)
                    break
                finally:
                    save()
            # Observe BOTH tags even after a failed second write. Observations
            # cannot turn a partially written pair into a successful promotion.
            if unit['status'] != 'FAILED':
                unit['phase'] = 'readback'
            for name in unit['frameworks']:
                entry = evidence[name]
                try:
                    verify_stable(entry['image'], entry['digest'], paths[name])
                except ERRORS as error:
                    fail(unit, 'readback', error, name)
                finally:
                    try:
                        refreshed = json.loads(paths[name].read_text())
                        if not isinstance(refreshed, dict):
                            raise ValueError('stable read-back evidence must be an object')
                        evidence[name] = refreshed
                    except ERRORS as error:
                        fail(unit, 'readback', error, name)
            if len(unit['frameworks']) == 2:
                try:
                    verify_pair(*(evidence[name] for name in unit['frameworks']))
                except ERRORS as error:
                    fail(unit, 'final_pair', error)
            for name in unit['frameworks']:
                evidence[name] = record_outcome(evidence[name], unit['status'] != 'FAILED')
            if unit['status'] != 'FAILED':
                if all(evidence[name]['promoted'] for name in unit['frameworks']):
                    unit.update(phase='complete', promoted=True)
                else:
                    fail(unit, 'readback', 'every unit member must confirm its stable digest')
            save()

        # Preserve successful unrelated outcomes, then fail the overall run so
        # a rejected or partially mutated unit cannot disappear from reporting.
        if batch['failed_units']:
            batch['error'] = '; '.join(
                f"{','.join(unit['frameworks'])}: "
                + '; '.join(error['message'] for error in unit['errors'])
                for unit in unit_results if unit['status'] == 'FAILED')
            raise ValueError(batch['error'])
        return batch
    finally:
        # Error fields are scoped to the failed unit, including both members
        # of a partial pair. A successful unrelated unit is never overwritten.
        for unit in unit_results:
            if unit['status'] == 'FAILED':
                message = '; '.join(error['message'] for error in unit['errors'])
                for name in unit['frameworks']:
                    evidence[name]['error'] = message
                    evidence[name] = record_outcome(evidence[name], False, evidence[name]['skipped'])
        save()
        # Informational CVEs retain visibility even after a blocking failure.
        # They never confer authorization and never hide the blocking result.
        for name in eligible:
            entry = evidence[name]
            try:
                report_unfixed_cves('remote', f"{entry['image']}@{entry['digest']}", scans[name])
            except ERRORS as error:
                write_evidence(scans[name] / 'unfixed-cves-summary.json', {
                    'target': f"{entry['image']}@{entry['digest']}",
                    'architectures': {arch: {'error': str(error)} for arch in ('amd64', 'arm64')},
                })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frameworks', help='JSON array of requested catalog frameworks')
    parser.add_argument('--soak-hours', type=float, default=MINIMUM_SOAK_HOURS)
    parser.add_argument('--plan', action='store_true', help='validate pair scope without AWS access')
    parser.add_argument('--registry')
    parser.add_argument('--repository')
    parser.add_argument('--attempt')
    parser.add_argument('--reports', type=Path, default=Path('reports'))
    parser.add_argument('--quarantine', type=Path, default=Path('policies/release/promotion-quarantine.json'))
    args = parser.parse_args(argv)
    try:
        frameworks = json.loads(args.frameworks)
        if args.plan:
            print(json.dumps({'units': promotion_units(frameworks, args.soak_hours)}))
        else:
            result = promote_batch(frameworks, args.registry, args.repository, args.soak_hours,
                                   args.attempt, args.reports, args.quarantine)
            print(json.dumps(result, indent=2))
    except ERRORS as error:
        print(f'stable promotion blocked: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
