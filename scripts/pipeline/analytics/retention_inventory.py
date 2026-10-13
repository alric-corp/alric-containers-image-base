"""Read-only retention inventory and cost sensitivity of SBOM Analytics data, from saved exports.

Inputs are files an operator already exported (S3 ListObjectVersions or
ListObjectsV2 pages, Athena BatchGetQueryExecution or an execution journal).
Nothing is listed, deleted, expired or locked here. Prices and billing rules
come only from an explicit, sourced assumptions file; without one, cost is
NOT_ESTIMATED. A per-query scan cutoff is reported as a bound, never as a
budget, retention period or recovery guarantee.
"""
import argparse
import math
import os
from pathlib import Path
import re
import sys
import tempfile

from scripts.pipeline.analytics.spdx import canonical, document, fields, read_local, sha256

INPUT_LIMIT = 64 * 1024 * 1024
HASH = '[0-9a-f]{64}'
SNAPSHOT_FILES = (
    (r'raw/spdx/sha256=' + HASH + r'/document\.spdx\.json', 'RAW_SPDX'),
    (r'raw/records/sha256=' + HASH + r'/record\.json', 'BINDING_RECORDS'),
    (r'reports/(?:records|normalization)\.json', 'STRUCTURED_RECORDS'),
    (r'analytics/sbom_(?:observations|packages)/part-[0-9]{5}\.parquet', 'PARQUET'),
    (r'complete\.json|ingestion-manifest\.json', 'MANIFESTS'),
)
CATEGORIES = ('RAW_SPDX', 'BINDING_RECORDS', 'STRUCTURED_RECORDS', 'PARQUET', 'MANIFESTS', 'SMOKE_PROBES',
              'QUERY_RESULTS', 'QUERY_RESULT_METADATA', 'UNCLASSIFIED')
ASSUMPTION_KEYS = ('source', 'storage_usd_per_gib_month', 'athena_usd_per_tib_scanned', 'athena_minimum_mib_per_query',
                   'athena_rounding_mib', 'athena_billable_statement_types')


def classify(key, data_prefix, results_prefix):
    """Category of one S3 key under the configured analytics prefixes; unknown keys are never guessed."""
    snapshots = data_prefix.rstrip('/') + '/snapshots/'
    if key.startswith(snapshots + '_smoke_tests/'):
        return 'SMOKE_PROBES', None
    match = re.fullmatch(re.escape(snapshots) + '(' + HASH + ')/(.+)', key)
    if match:
        return next((c for pattern, c in SNAPSHOT_FILES if re.fullmatch(pattern, match[2])), 'UNCLASSIFIED'), match[1]
    if key.startswith(results_prefix) and '/' not in key[len(results_prefix):]:
        return ('QUERY_RESULT_METADATA' if key.endswith('.metadata') else 'QUERY_RESULTS'), None
    return 'UNCLASSIFIED', None


def _objects(listings):
    """(Key, VersionId) -> entry, across pages; a listing without versions cannot prove noncurrent bytes."""
    versions, markers, complete_versions = {}, {}, True
    for listing in listings:
        versioned = type(listing) is dict and ('Versions' in listing or 'DeleteMarkers' in listing)
        if type(listing) is not dict or (versioned and 'Contents' in listing):
            raise ValueError('listing must be one ListObjectVersions or ListObjectsV2 response')
        complete_versions &= versioned or 'Contents' not in listing  # An empty page proves nothing either way.
        for entry in (listing.get('Versions') if versioned else listing.get('Contents')) or []:
            if type(entry) is not dict or type(entry.get('Key')) is not str or type(entry.get('Size')) is not int or entry['Size'] < 0:
                raise ValueError('object entry requires Key and a non-negative Size')
            identity = (entry['Key'], entry.get('VersionId') if versioned else None)
            if identity in versions and versions[identity]['size'] != entry['Size']:
                raise ValueError('the same object version has two sizes')
            versions[identity] = dict(size=entry['Size'], latest=entry.get('IsLatest', True) if versioned else True)
        for entry in listing.get('DeleteMarkers') or []:
            markers[(entry.get('Key'), entry.get('VersionId'))] = entry.get('IsLatest', False)
    unversioned = {key for key, version in versions if version is None}
    if any(key in unversioned for key, version in versions if version is not None):
        raise ValueError('a key appears in both a versioned and an unversioned listing')
    return versions, markers, complete_versions


def inventory(listings, data_prefix, results_prefix):
    versions, markers, complete_versions = _objects(listings)
    categories = {c: dict(objects=0, versions=0, current_bytes=0, noncurrent_bytes=0) for c in CATEGORIES}
    snapshots, keys = {}, {}
    for (key, _), entry in sorted(versions.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        category, snapshot = classify(key, data_prefix, results_prefix)
        row = categories[category]
        row['versions'] += 1
        row['current_bytes' if entry['latest'] else 'noncurrent_bytes'] += entry['size']
        keys.setdefault(key, category)
        if snapshot:
            totals = snapshots.setdefault(snapshot, dict(versions=0, bytes=0))
            totals['versions'] += 1
            totals['bytes'] += entry['size']
    for key, category in keys.items():
        categories[category]['objects'] += 1
    return dict(categories=categories, snapshots=snapshots, delete_markers=len(markers),
                current_delete_markers=sum(1 for latest in markers.values() if latest),
                total_bytes_all_versions=sum(e['size'] for e in versions.values()),
                version_history='COMPLETE' if complete_versions else 'CURRENT_OBJECTS_ONLY',
                unclassified_keys=sorted(k for k, c in keys.items() if c == 'UNCLASSIFIED')[:50])


def _executions(documents):
    """Distinct query executions from BatchGetQueryExecution responses or execution journals.

    Started executions without a recorded response stay counted as unobserved, never as zero bytes.
    """
    executions, unobserved = {}, set()
    for value in documents:
        if type(value) is dict and type(value.get('QueryExecutions')) is list:
            found = value['QueryExecutions']
            unobserved.update(value.get('UnprocessedQueryExecutionIds') or ())
        elif type(value) is dict and type(value.get('executions')) is dict:
            found = [e['execution'] for e in value['executions'].values() if type(e.get('execution')) is dict]
            unobserved.update(e['query_id'] for e in value['executions'].values()
                              if type(e.get('execution')) is not dict and e.get('query_id'))
        else:
            raise ValueError('executions must be a BatchGetQueryExecution response or an execution journal')
        for execution in found:
            identity, statistics = execution.get('QueryExecutionId'), execution.get('Statistics') or {}
            scanned = statistics.get('DataScannedInBytes')
            if type(identity) is not str or type(scanned) is not int or scanned < 0:
                raise ValueError('execution requires an ID and integer DataScannedInBytes')
            row = dict(statement_type=execution.get('StatementType'),
                       state=(execution.get('Status') or {}).get('State'), scanned_bytes=scanned)
            known = executions.setdefault(identity, row)
            if known != row:  # Only a terminal record may replace a non-terminal one.
                terminal = ('SUCCEEDED', 'FAILED', 'CANCELLED')
                if known['state'] in terminal or row['state'] not in terminal:
                    raise ValueError('the same execution has two different records')
                executions[identity] = row
    return executions, sorted(unobserved - set(executions))


def athena(documents, assumptions=None, config=None):
    executions, unobserved = _executions(documents)
    by_type = {}
    for row in executions.values():
        totals = by_type.setdefault(str(row['statement_type']), dict(executions=0, scanned_bytes=0))
        totals['executions'] += 1
        totals['scanned_bytes'] += row['scanned_bytes']
    result = dict(executions=len(executions), by_statement_type=by_type, unobserved_executions=unobserved,
                  scanned_bytes=sum(r['scanned_bytes'] for r in executions.values()), billable_bytes=None, cost_usd=None)
    if assumptions and assumptions['athena_usd_per_tib_scanned'] is not None:
        unit, minimum = assumptions['athena_rounding_mib'] * 2**20, assumptions['athena_minimum_mib_per_query'] * 2**20
        billable = [max(math.ceil(r['scanned_bytes'] / unit) * unit, minimum) for r in executions.values()
                    if r['statement_type'] in assumptions['athena_billable_statement_types'] and r['state'] != 'FAILED']
        result.update(billable_bytes=sum(billable), cost_usd=sum(billable) / 2**40 * assumptions['athena_usd_per_tib_scanned'])
    if config:
        # A bound per authorized round under an enforced workgroup cutoff, not a monthly budget.
        result['per_round_scan_bound_bytes'] = config['execution_limit'] * config['scan_cutoff_bytes']
        result['per_query_scan_cutoff_bytes'] = config['scan_cutoff_bytes']
    return result


def load_assumptions(value):
    """Every price/rule is explicit and sourced; null means NOT_ESTIMATED, never a default."""
    fields(value, ASSUMPTION_KEYS, label='cost assumptions')
    if type(value['source']) is not str or not value['source'].strip():
        raise ValueError('cost assumptions require a source')
    for key in ASSUMPTION_KEYS[1:5]:
        if value[key] is not None and (type(value[key]) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0):
            raise ValueError(key + ' must be null or a non-negative number')
    if value['athena_usd_per_tib_scanned'] is not None and not (
            value['athena_rounding_mib'] and value['athena_minimum_mib_per_query'] is not None
            and type(value['athena_billable_statement_types']) is list):
        raise ValueError('an Athena price requires its rounding, minimum and billable statement types')
    return value


def report(listings, data_prefix, results_prefix, executions=(), assumptions=None, config=None, inputs=()):
    stored = inventory(listings, data_prefix, results_prefix)
    price = (assumptions or {}).get('storage_usd_per_gib_month')
    return dict(inventory_version=1, inputs=list(inputs), data_prefix=data_prefix, results_prefix=results_prefix,
                storage=dict(stored, monthly_storage_usd=None if price is None else
                             stored['total_bytes_all_versions'] / 2**30 * price),
                athena=athena(executions, assumptions, config) if executions else None,
                assumptions=assumptions, cost='ESTIMATED_FROM_ASSUMPTIONS' if assumptions else 'NOT_ESTIMATED',
                monthly_budget='NOT_DEFINED', retention_policy='NOT_DEFINED', recovery_guarantee='NOT_DEFINED',
                lifecycle_or_object_lock_changes=0, deletions=0, cloud_calls=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-prefix', required=True, help='snapshot data prefix, e.g. from policies/analytics/s3.json')
    parser.add_argument('--results-prefix', required=True, help='Athena results prefix, e.g. from policies/analytics/athena.json')
    parser.add_argument('--objects', type=Path, action='append', required=True, help='saved S3 listing page (repeatable)')
    parser.add_argument('--executions', type=Path, action='append', default=[], help='saved Athena executions or journal')
    parser.add_argument('--athena-config', type=Path, help='workgroup bounds: execution_limit and scan_cutoff_bytes')
    parser.add_argument('--assumptions', type=Path, help='sourced prices and billing rules; omitted means NOT_ESTIMATED')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    inputs = args.objects + args.executions + [p for p in (args.athena_config, args.assumptions) if p]
    try:
        if any(args.output.resolve() == p.resolve() for p in inputs):
            raise ValueError('output must not replace an input')
        load = lambda path: document(read_local(path, INPUT_LIMIT), limit=INPUT_LIMIT)
        config = None
        if args.athena_config:
            config = load(args.athena_config)
            if not all(type(config.get(k)) is int and config[k] > 0 for k in ('execution_limit', 'scan_cutoff_bytes')):
                raise ValueError('athena config requires positive execution_limit and scan_cutoff_bytes')
        result = report([load(p) for p in args.objects], args.data_prefix, args.results_prefix,
                        [load(p) for p in args.executions], load_assumptions(load(args.assumptions)) if args.assumptions else None,
                        config, [dict(path=p.name, sha256=sha256(read_local(p, INPUT_LIMIT))) for p in inputs])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix='.retention-', delete=False) as stream:
            stream.write(canonical(result) + b'\n')
        os.replace(stream.name, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('SBOM analytics retention inventory failed: ' + ' '.join(str(error).split())[:300], file=sys.stderr)
        return 1
    print(canonical(dict(output=str(args.output), cost=result['cost'], total_bytes=result['storage']['total_bytes_all_versions'],
                         version_history=result['storage']['version_history'])).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
