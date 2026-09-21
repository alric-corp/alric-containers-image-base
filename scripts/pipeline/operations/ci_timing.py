#!/usr/bin/env python3
"""Break down what actually determines a workflow run's wall-clock duration.

Uses real run/job data from `gh api` -- no synthetic timing. A job's own
`created_at` -> `started_at` gap is only a clean proxy for runner-queue wait
when that job has no `needs` and is not itself serialized by a concurrency
group. The Actions API does not expose `needs` or concurrency-group
membership at read time, so the caller must say which jobs in this run are
known (from reading the workflow YAML) to be dependent/serialized --
otherwise their wait gets folded into "runner queue" and overstates it.

A single run says nothing about a trend: aggregate reports median and p90
across several runs. Comparing runs across time also isn't apples-to-apples
by itself -- the same commit can resolve different Wolfi packages at
different times, so treat cross-run comparisons as directional, not exact,
unless commit/tools/cache condition are also controlled for.
"""
import argparse
from datetime import datetime
import json
import statistics
import subprocess
import sys

REQUIRED_CHECKS = ('Unit & integration tests', 'Repository & workflow lint')


def gh_api(path):
    output = subprocess.run(['gh', 'api', path], check=True, capture_output=True, text=True).stdout
    return json.loads(output)


def _parse(timestamp):
    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))


def _seconds(start, end):
    if not start or not end:
        return None
    return (_parse(end) - _parse(start)).total_seconds()


def job_breakdown(job, dependent, serialized):
    # A `skipped` job's timestamps don't represent real waiting or running
    # time -- GitHub can even report completed_at slightly before
    # started_at for one, which would otherwise show up as a negative
    # duration. Report it as no data, not a bogus number.
    skipped = job.get('conclusion') == 'skipped'
    steps = [] if skipped else [
        {'name': step['name'], 'seconds': _seconds(step['started_at'], step['completed_at'])}
        for step in job.get('steps') or []
        if step.get('started_at') and step.get('completed_at')
    ]
    steps.sort(key=lambda step: -step['seconds'])
    return {
        'job': job['name'],
        'conclusion': job.get('conclusion'),
        'dependent': job['name'] in dependent,
        'serialized': job['name'] in serialized,
        'queued_seconds': None if skipped else _seconds(job['created_at'], job['started_at']),
        'duration_seconds': None if skipped else _seconds(job['started_at'], job['completed_at']),
        'steps': steps,
    }


def required_checks_seconds(run, jobs, required):
    completions = [_parse(job['completed_at']) for job in jobs
                   if job['name'] in required and job.get('completed_at')]
    missing = sorted(required - {job['name'] for job in jobs})
    if missing or len(completions) < len(required):
        return {'seconds': None, 'missing': missing}
    return {'seconds': (max(completions) - _parse(run['created_at'])).total_seconds(), 'missing': []}


def breakdown(run, jobs, dependent=(), serialized=(), required=REQUIRED_CHECKS):
    dependent, serialized, required = set(dependent), set(serialized), set(required)
    return {
        'run_id': run['id'],
        'event': run.get('event'),
        'head_branch': run.get('head_branch'),
        'total_seconds': _seconds(run['created_at'], run.get('updated_at')),
        'required_checks': required_checks_seconds(run, jobs, required),
        'jobs': [job_breakdown(job, dependent, serialized) for job in jobs],
    }


def _percentile(values, fraction):
    """Nearest-rank percentile; no interpolation, so it never invents a
    value outside the observed samples -- appropriate for a handful of
    real runs, not a statistically large population."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return {'median': statistics.median(values), 'p90': _percentile(values, 0.9),
            'min': min(values), 'max': max(values), 'n': len(values)}


def aggregate(breakdowns):
    if not breakdowns:
        raise ValueError('aggregate requires at least one run breakdown')
    jobs_by_name, steps_by_key = {}, {}
    for entry in breakdowns:
        for job in entry['jobs']:
            jobs_by_name.setdefault(job['job'], {'dependent': job['dependent'],
                                                  'serialized': job['serialized'],
                                                  'queued': [], 'duration': []})
            jobs_by_name[job['job']]['queued'].append(job['queued_seconds'])
            jobs_by_name[job['job']]['duration'].append(job['duration_seconds'])
            for step in job['steps']:
                key = (job['job'], step['name'])
                steps_by_key.setdefault(key, []).append(step['seconds'])
    job_stats = {
        name: {'dependent': info['dependent'], 'serialized': info['serialized'],
               'queued_seconds': _stats(info['queued']), 'duration_seconds': _stats(info['duration'])}
        for name, info in jobs_by_name.items()
    }
    step_stats = [{'job': job, 'step': step, **_stats(seconds)}
                  for (job, step), seconds in steps_by_key.items() if _stats(seconds)]
    step_stats.sort(key=lambda entry: -entry['median'])
    return {
        'runs': len(breakdowns),
        'total_seconds': _stats([entry['total_seconds'] for entry in breakdowns]),
        'required_checks_seconds': _stats([entry['required_checks']['seconds'] for entry in breakdowns]),
        'jobs': job_stats,
        'dominant_steps': step_stats[:5],
    }


def fetch_breakdown(repo, run_id, dependent, serialized, required):
    run = gh_api(f'repos/{repo}/actions/runs/{run_id}')
    jobs = gh_api(f'repos/{repo}/actions/runs/{run_id}/jobs')['jobs']
    return breakdown(run, jobs, dependent, serialized, required)


def _csv(value):
    return [item for item in (value or '').split(',') if item]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', help='owner/repo')
    parser.add_argument('run_ids', nargs='+', type=int)
    parser.add_argument('--dependent', default='',
                         help='comma-separated job display names known to have `needs`')
    parser.add_argument('--serialized', default='',
                         help='comma-separated job display names known to run in a concurrency group')
    parser.add_argument('--required', default=','.join(REQUIRED_CHECKS),
                         help='comma-separated required-check display names; '
                              'use test,lint-workflows for historical runs')
    args = parser.parse_args()
    dependent, serialized, required = _csv(args.dependent), _csv(args.serialized), _csv(args.required)
    breakdowns = [fetch_breakdown(args.repo, run_id, dependent, serialized, required)
                  for run_id in args.run_ids]
    if len(breakdowns) == 1:
        print(json.dumps(breakdowns[0], indent=2))
    else:
        print(json.dumps(aggregate(breakdowns), indent=2))


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        raise SystemExit(error.returncode)
