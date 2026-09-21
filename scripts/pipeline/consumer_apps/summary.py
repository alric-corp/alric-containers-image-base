"""Aggregate all eighteen consumer executions without hiding missing evidence."""
import argparse
import json
from pathlib import Path

from scripts.pipeline.consumer_apps.model import ARCHITECTURES, SCENARIOS, validate_inventory
from scripts.pipeline.consumer_apps.runner import validate_result


def summarize(inventory, directory, download_result='success'):
    validate_inventory(inventory)
    expected = {f'{item["framework"]}-{arch}' for item in SCENARIOS for arch in ARCHITECTURES}
    observed = {key: [] for key in expected}
    errors = [] if download_result == 'success' else ['result artifact download/integrity verification failed']
    for path in sorted(Path(directory).rglob('*.json')):
        if path.stem not in expected:
            # Logs and build metadata are not execution results. A document
            # claiming the execution schema under an unknown name is rejected.
            if not any(part.endswith('-logs') for part in path.parts):
                errors.append(f'unexpected result document: {path.name}')
            continue
        observed[path.stem].append(path)
    results = {}
    for name, paths in observed.items():
        if len(paths) != 1:
            results[name] = {'status': 'FAIL', 'error': f'expected one result, found {len(paths)}'}
            continue
        try:
            result = json.loads(paths[0].read_text())
            if name != result.get('framework', '') + '-' + result.get('platform', '').removeprefix('linux/'):
                raise ValueError('result filename differs from execution identity')
            if result.get('status') == 'FAIL':
                raise ValueError(result.get('error') or 'application execution failed without a diagnostic')
            validate_result(result, inventory)
            results[name] = result
        except (ValueError, KeyError, TypeError, OSError) as error:
            results[name] = {'status': 'FAIL', 'error': str(error)}
    passed = sum(result['status'] == 'PASS' for result in results.values())
    summary = {key: inventory[key] for key in ('source_run_id', 'source_run_attempt', 'source_sha')}
    summary.update(schema_version=1, application_scenarios=9, base_artifacts_expected=16,
                   consumer_executions_expected=18, consumer_executions_passed=passed,
                   status='PASS' if passed == 18 and not errors else 'FAIL', results=results, errors=errors)
    lines = ['# Consumer application certification', '',
             f'Source run: {inventory["source_run_id"]}, attempt {inventory["source_run_attempt"]}; '
             f'revision `{inventory["source_sha"]}`.', '',
             f'Actual HTTP executions passed: **{passed}/18**. Overall: **{summary["status"]}**.', '',
             '| Framework | amd64 | arm64 | Build stage | Runtime | Health | Security |',
             '|---|---|---|---|---|---|---|']
    for item in SCENARIOS:
        statuses = [results[f'{item["framework"]}-{arch}']['status'] for arch in ARCHITECTURES]
        overall = 'PASS' if statuses == ['PASS', 'PASS'] else 'FAIL'
        build = overall if item['dev_framework'] else 'N/A'
        lines.append(f'| {item["framework"]} | {statuses[0]} | {statuses[1]} | {build} | '
                     f'{overall} | {overall} | {overall} |')
    failures = [f'{key}: {value["error"]}' for key, value in results.items() if value['status'] != 'PASS'] + errors
    if failures:
        lines.extend(['', 'Failures:', ''])
        lines.extend('- ' + failure.replace('\n', ' ').replace('|', '/') for failure in failures)
    return summary, '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--markdown', type=Path, required=True)
    parser.add_argument('--download-result', required=True,
                        choices=('success', 'failure', 'skipped', 'cancelled'))
    args = parser.parse_args()
    summary, markdown = summarize(json.loads(args.inventory.read_text()), args.results, args.download_result)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2) + '\n')
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown)
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
