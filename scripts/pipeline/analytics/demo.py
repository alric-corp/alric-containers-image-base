"""Run proposed inventory queries locally with SQLite, never Athena.

Arrays/structs use JSON text in this demonstration only. It tests relational
selection, joins and counts, not Athena's Parquet reader or native nested types.
"""
import argparse
from collections import Counter
from pathlib import Path
import sqlite3
import sys

from scripts.pipeline.analytics import parquet
from scripts.pipeline.analytics.normalize import read_completed
from scripts.pipeline.analytics.spdx import canonical, digest, require

SQL = Path(__file__).resolve().parents[3] / 'sql/sbom-analytics'
QUERIES = ('01_find_images', '02_versions', '03_runtime_vs_dev', '04_compare_digests', '05_trace_original')


def open_database(batches):
    """Load validated complete batches; reject conflicting logical package keys."""
    database = sqlite3.connect(':memory:')
    database.row_factory = sqlite3.Row
    spec = parquet.definition()['tables']
    types = dict(string='TEXT', int32='INTEGER', int64='INTEGER', boolean='INTEGER', strings='TEXT', references='TEXT')
    seen = dict(observations={}, packages={})
    try:
        for table, columns in spec.items():
            definition = ', '.join('"' + c['name'] + '" ' + types[c['type']] for c in columns)
            database.execute('CREATE TABLE sbom_' + ('observation' if table == 'observations' else 'package')
                             + '_rows_v1 (' + definition + ')')
        for batch in batches:
            data = read_completed(batch)
            for table, columns in spec.items():
                rows = []
                for row in data[table]:
                    key = row['observation_id'] if table == 'observations' else (row['sbom_sha256'], row['package_spdx_id'])
                    require(key not in seen[table] or seen[table][key] == row, 'conflicting logical dataset key')
                    seen[table][key] = row
                    rows.append([canonical(row[c['name']]).decode() if c['type'] in ('strings', 'references')
                                 and row[c['name']] is not None else row[c['name']] for c in columns])
                name = 'sbom_' + ('observation' if table == 'observations' else 'package') + '_rows_v1'
                database.executemany('INSERT INTO ' + name + ' VALUES (' + ','.join('?' for _ in columns) + ')', rows)
        # SQLite has CREATE VIEW but not CREATE OR REPLACE VIEW. SELECTs are unchanged.
        database.executescript((SQL / 'views.sql').read_text().replace('CREATE OR REPLACE VIEW', 'CREATE VIEW'))
        return database
    except Exception:
        database.close()
        raise


def query(database, name, parameters):
    require(name in QUERIES, 'unknown proposed query')
    return [dict(row) for row in database.execute((SQL / (name + '.sql')).read_text(), parameters)]


def demonstrate(batch, *, component, runtime_framework, dev_framework, runtime_index, dev_index, platform):
    """Compare explicitly supplied indices, in one complete run/platform context."""
    digest(runtime_index, 'runtime index', oci=True)
    digest(dev_index, 'dev index', oci=True)
    require(platform in ('linux/amd64', 'linux/arm64'), 'unsupported document platform')
    database = open_database([batch])
    try:
        selected = []
        for framework, index in ((runtime_framework, runtime_index), (dev_framework, dev_index)):
            rows = list(database.execute('SELECT * FROM sbom_observations_v1 WHERE framework = ? '
                'AND image_index_digest = ? AND document_platform = ?', (framework, index, platform)))
            require(len(rows) == 1, 'explicit framework/index/platform must select one observation')
            selected.append(dict(rows[0]))
        left, right = selected
        identity = ('repository', 'run_id', 'run_attempt', 'source_sha', 'event', 'ref')
        require(all(left[k] == right[k] for k in identity), 'runtime/dev must belong to the same execution')
        context_keys = ('repository', 'run_id', 'run_attempt', 'source_sha', 'document_platform')
        parameters = {
            '01_find_images': (component,), '02_versions': (component,),
            '03_runtime_vs_dev': tuple(left[k] for k in context_keys) +
                (runtime_framework, left['sbom_sha256'], dev_framework, right['sbom_sha256']),
            '04_compare_digests': (platform, runtime_index, left['sbom_sha256'], dev_index, right['sbom_sha256']),
            '05_trace_original': (left['observation_id'],)}
        results = {name: dict(parameters=list(parameters[name]), rows=query(database, name, parameters[name])) for name in QUERIES}
        for name in ('03_runtime_vs_dev', '04_compare_digests'):
            results[name]['counts'] = dict(sorted(Counter(r['comparison'] for r in results[name]['rows']).items()))
        counts = [dict(r) for r in database.execute('SELECT framework, image_index_digest, document_platform, '
            'sbom_sha256, COUNT(*) AS component_records FROM sbom_inventory_v1 GROUP BY '
            'framework, image_index_digest, document_platform, sbom_sha256 ORDER BY framework, document_platform')]
        return dict(local_sql_engine='SQLite', sqlite_version=sqlite3.sqlite_version, athena_executed=False,
                    nested_type_representation='JSON text in SQLite only', component_counts=counts, queries=results)
    finally:
        database.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, required=True)
    for option in ('component', 'runtime-framework', 'dev-framework', 'runtime-index', 'dev-index'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), required=True)
    args = parser.parse_args(argv)
    try:
        result = demonstrate(**vars(args))
    except (OSError, ValueError, KeyError, TypeError, ImportError, sqlite3.Error) as error:
        print('SBOM SQL demonstration failed: ' + str(error), file=sys.stderr)
        return 1
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
