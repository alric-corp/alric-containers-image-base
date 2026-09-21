"""Authorize a complete stable promotion batch before the first tag write.

Selection, trust verification and blocking scans share one process: saved JSON
is audit evidence, never an authorization token for a later mutation phase.
ECR cannot atomically write two tags. A failed write/read-back leaves the whole
pair unpromoted in the evidence, including the original ECR state for recovery.
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
    batch = {'schema_version': 1, 'frameworks': frameworks, 'units': units,
             'evaluated_at': now.isoformat(), 'authorized_pairs': [],
             'prewrite_authorized': False, 'promoted': False}
    eligible = []

    def save():
        for name, entry in evidence.items():
            write_evidence(paths[name], entry)
        write_evidence(reports / 'promotion-batch.json', batch)

    save()
    try:
        # Take every repository's initial snapshot before selecting or writing.
        inventories = {}
        for name in ordered:
            document = load_details(evidence[name]['repository'])
            write_evidence(paths[name].parent / 'ecr-before.json', document)
            inventories[name] = document['imageDetails']
        for name in ordered:
            entry = evidence[name]
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
        save()

        # Missing, soaking or quarantined members cannot leave a writable half-pair.
        for unit in units:
            members = [evidence[name] for name in unit]
            if all(member['skipped'] for member in members):
                continue
            if any(member['skipped'] for member in members):
                raise ValueError(f'complete eligible pair required before stable writes: {unit}')
            if len(unit) == 2:
                binding = verify_pair(*members)
                batch['authorized_pairs'].append(binding)
                for member in members:
                    member['pair_authorization'] = binding
        save()

        # Existing verifiers and scanner policy remain authoritative for every
        # selected digest. No write occurs if either member fails either gate.
        for name in eligible:
            entry = evidence[name]
            verify_promotion(f"{entry['image']}@{entry['digest']}", repository, scans[name])
            entry['trust_verified'] = True
            save()
        for name in eligible:
            entry = evidence[name]
            if scan_images('remote', f"{entry['image']}@{entry['digest']}", scans[name]) != 0:
                raise ValueError(f'blocking promotion scan failed for {name}')
            entry['scan_passed'] = True
            save()
        batch['prewrite_authorized'] = True
        save()

        for unit in units:
            if all(evidence[name]['skipped'] for name in unit):
                continue
            failures = []
            # Canonical runtime then dev order, under the shared stable lock.
            for name in unit:
                entry = evidence[name]
                entry['write_status'] = 'started'
                save()
                try:
                    write_stable(entry['image'], entry['digest'])
                    entry['write_status'] = 'completed'
                except ERRORS as error:
                    entry.update(write_status='failed', write_error=str(error))
                    failures.append(f'{name} write: {error}')
                    break
                finally:
                    save()
            # Observe BOTH tags even after a failed second write. Observations
            # cannot turn a partially written pair into a successful promotion.
            for name in unit:
                entry = evidence[name]
                try:
                    verify_stable(entry['image'], entry['digest'], paths[name])
                except ERRORS as error:
                    failures.append(f'{name} read-back: {error}')
                finally:
                    evidence[name] = json.loads(paths[name].read_text())
            if len(unit) == 2:
                verify_pair(*(evidence[name] for name in unit))
            for name in unit:
                evidence[name] = record_outcome(evidence[name], not failures)
            save()
            if failures:
                raise ValueError('; '.join(failures))
        batch['promoted'] = bool(eligible) and all(evidence[name]['promoted'] for name in eligible)
        return batch
    except ERRORS as error:
        batch['error'] = str(error)
        for name in ordered:
            if not evidence[name]['promoted']:
                evidence[name]['error'] = str(error)
                evidence[name] = record_outcome(evidence[name], False, evidence[name]['skipped'])
        raise
    finally:
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
