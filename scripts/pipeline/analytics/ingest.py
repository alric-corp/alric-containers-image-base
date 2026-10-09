"""Offline plan CLI and JSON-reported ingestion with a caller-supplied client.

This module never initializes an SDK, reads corporate configuration or obtains
credentials. Production integration must supply an authorized low-level client.
"""
import argparse
from pathlib import Path
import os
import re
import sys
import tempfile

from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError, Limits, check
from scripts.pipeline.analytics.snapshot import prepare_snapshot, publish_snapshot, save_plan
from scripts.pipeline.analytics.spdx import canonical, document, fields, read_local


def _report_destination(path, protected_roots):
    path = Path(path)
    check(path.drive or re.match(r'[A-Za-z][A-Za-z0-9+.-]*:', str(path)) is None,
          'REPORT_PATH_INVALID', stage='DIAGNOSTIC')
    check(not path.is_symlink() and not path.is_dir(), 'REPORT_PATH_INVALID', stage='DIAGNOSTIC')
    resolved = path.resolve()
    for root in protected_roots:
        root = Path(root).resolve()
        check(resolved != root and root not in resolved.parents, 'REPORT_INSIDE_INPUT', stage='DIAGNOSTIC')
    # Also reject known batch/plan ancestors when the caller does not have
    # preparation paths (for example after restarting with a frozen plan).
    check(not any(((p / 'complete.json').is_file() and (p / 'reports/records.json').is_file())
                  or ((p / 'plan.json').is_file() and (p / 'batch').is_dir()) for p in resolved.parents),
          'REPORT_INSIDE_INPUT', stage='DIAGNOSTIC')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_report(result, path):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', prefix='.analytics-report-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(result) + b'\n')
        check(not path.is_symlink(), 'REPORT_PATH_INVALID', stage='DIAGNOSTIC')
        os.replace(temporary, path)
        temporary = None
        return result
    except Exception:
        return IngestionError('REPORT_WRITE_FAILED', stage='DIAGNOSTIC', retryable=True,
            observed={'operation_code':result['code']}).diagnostic(batch_id=result.get('batch_id'), snapshot_id=result.get('snapshot_id'))
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # The returned diagnostic still reports the write failure.


def publish_reported(plan, adapter, report, *, protected_roots=()):
    """Always return a JSON-safe outcome. Report failure never becomes success."""
    try:
        destination = _report_destination(report, protected_roots)
        result = publish_snapshot(plan, adapter)
    except Exception as error:
        failure = error if isinstance(error, IngestionError) else IngestionError('INGESTION_ERROR', stage='INGEST')
        result = failure.diagnostic(batch_id=plan.batch_id, snapshot_id=plan.snapshot_id)
        try:
            destination = _report_destination(report, protected_roots)
        except Exception:
            return result  # JSON is still returned, but no permitted report sink exists.
    return _write_report(result, destination)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise IngestionError('INVALID_ARGUMENTS', stage='ARGUMENTS', operation='ParseArguments')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _Parser(description=__doc__)
    parser.add_argument('--batch', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--plan-dir', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    # Recover the explicitly supplied report sink even on argument failures.
    report, protected = None, []
    for i, argument in enumerate(argv):
        if argument == '--report' and i + 1 < len(argv):
            report = Path(argv[i+1])
        elif argument.startswith('--report='):
            report = Path(argument.split('=',1)[1])
        for flag in ('--batch', '--plan-dir', '--config'):
            if argument == flag and i + 1 < len(argv):
                protected.append(Path(argv[i+1]))
            elif argument.startswith(flag + '='):
                protected.append(Path(argument.split('=',1)[1]))
    plan = None
    try:
        args = parser.parse_args(argv)
        protected = [args.batch, args.plan_dir, args.config]
        report = _report_destination(args.report, protected)
        check(args.plan_dir.resolve() != args.batch.resolve() and args.batch.resolve() not in args.plan_dir.resolve().parents
              and args.plan_dir.resolve() not in args.batch.resolve().parents, 'PLAN_OVERLAPS_BATCH', stage='FREEZE_PLAN')
        config = document(read_local(args.config, 4*1024*1024), limit=4*1024*1024)
        fields(config, ('protocol_version','destination'), ('limits',), 'ingestion configuration')
        check(type(config['protocol_version']) is int and config['protocol_version'] == 1, 'UNSUPPORTED_CONFIGURATION')
        target = Destination(**config['destination'])
        limits = Limits(**config.get('limits', {}))
        plan = prepare_snapshot(args.batch, target, limits)
        status = save_plan(plan, args.plan_dir)
        result = dict(diagnostic_version=1, status='SUCCESS', stage='FREEZE_PLAN', code='PLAN_' + status,
            batch_id=plan.batch_id, snapshot_id=plan.snapshot_id, operation='FreezePlan', object=None,
            expected=None, observed={'objects':len(plan.objects)}, complete=False, catalog_eligible=False,
            retryable=False, snapshot_status='NOT_UPLOADED', cloud_calls=0)
    except Exception as error:
        failure = error if isinstance(error, IngestionError) else IngestionError('PLANNING_ERROR', stage='PLAN')
        result = failure.diagnostic(batch_id=plan.batch_id if plan else None, snapshot_id=plan.snapshot_id if plan else None)
    if report is not None:
        try:
            result = _write_report(result, _report_destination(report, protected))
        except Exception:
            result = IngestionError('REPORT_PATH_INVALID', stage='DIAGNOSTIC',
                observed={'operation_code':result['code']}).diagnostic(batch_id=result.get('batch_id'),snapshot_id=result.get('snapshot_id'))
    print(canonical(result).decode())
    return 0 if result['status'] == 'SUCCESS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
