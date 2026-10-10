"""Manual, bounded Athena caller. Imports and planning never initialize an SDK.

The catalog producer remains a proposal (execute=false). Only a separately
supplied authorization for the exact frozen SQL plan enables StartQueryExecution.
This module does not provision resources or change IAM.
"""
import argparse
import base64
from collections import Counter
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

from scripts.pipeline.analytics import poc, parquet
from scripts.pipeline.analytics.catalog import catalog_plan
from scripts.pipeline.analytics.demo import QUERIES
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError, check, hash_id
from scripts.pipeline.analytics.normalize import read_completed
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import read_snapshot, recover_snapshot
from scripts.pipeline.analytics.spdx import canonical, document, fields, read_local, sha256

CONFIG_KEYS = ('protocol_version', 'catalog', 'database', 'workgroup', 'table_prefix', 'results_prefix',
               'execution_limit', 'scan_cutoff_bytes', 'timeout_seconds', 'result_reuse',
               'manifest_sha256', 'manifest_version_id')
TERMINAL = ('SUCCEEDED', 'FAILED', 'CANCELLED')
PLAN_LIMIT = 4 * 1024 * 1024
RESULT_ROWS = 4096
RESULT_BYTES = 8 * 1024 * 1024
ATHENA_ACTIONS = ['athena:GetWorkGroup', 'athena:StartQueryExecution', 'athena:GetQueryExecution',
                  'athena:GetQueryResults', 'athena:StopQueryExecution']
GLUE_ACTIONS = ['glue:GetDatabase', 'glue:GetTable', 'glue:GetPartitions', 'glue:CreateTable']
TABLE_NAMES = ('sbom_observation_rows_v1', 'sbom_package_rows_v1', 'sbom_observations_v1',
               'sbom_packages_v1', 'sbom_inventory_v1')


def config(path):
    value = document(read_local(Path(path), 65536))
    fields(value, CONFIG_KEYS)
    check(type(value['protocol_version']) is int and value['protocol_version'] == 1, 'ATHENA_CONFIG_VERSION')
    check(value['catalog'] == 'AwsDataCatalog', 'ATHENA_DEFAULT_CATALOG_REQUIRED')
    for key in ('database', 'workgroup', 'table_prefix'):
        check(type(value[key]) is str and re.fullmatch('poc_[a-z0-9_]{1,32}', value[key]), 'ATHENA_POC_NAMESPACE_REQUIRED')
    check(value['results_prefix'] == 'query-results/poc-v1/', 'ATHENA_RESULTS_PREFIX_DIFFERS')
    for key, expected in (('execution_limit', 18), ('scan_cutoff_bytes', 104857600), ('timeout_seconds', 120)):
        check(type(value[key]) is int and value[key] == expected, 'ATHENA_LIMIT_DIFFERS')
    check(value['result_reuse'] is False, 'ATHENA_RESULT_REUSE_FORBIDDEN')
    hash_id(value['manifest_sha256'])
    check(type(value['manifest_version_id']) is str and 0 < len(value['manifest_version_id']) <= 1024,
          'ATHENA_REFERENCE_VERSION_REQUIRED')
    return value


def result_configuration(expected, settings):
    destination = expected['destination']
    return dict(OutputLocation='s3://' + destination['bucket'] + '/' + settings['results_prefix'],
                ExpectedBucketOwner=destination['expected_bucket_owner'],
                EncryptionConfiguration={'EncryptionOption': 'SSE_S3'})


def session_policy(expected, settings, *, execute):
    """Intersection with exact role grants; only five snapshot-prefixed Glue names.

    The session pattern saves STS plaintext space. The ROLE contract enumerates
    the five names exactly. No snapshot write, deletion, IAM, ECR or state access.
    """
    target = Destination(**expected['destination'])
    account = target.expected_bucket_owner
    bucket = 'arn:aws:s3:::' + target.bucket
    snapshot = target.snapshot_prefix(expected['snapshot_id'])
    glue = f'arn:aws:glue:{target.region}:{account}:'
    statements = [
        dict(Effect='Allow', Action=['sts:GetCallerIdentity'], Resource='*'),
        dict(Effect='Allow', Action=['s3:GetBucketLocation'], Resource=bucket),
        dict(Effect='Allow', Action=['s3:ListBucket'], Resource=bucket,
             Condition={'StringLike': {'s3:prefix': [snapshot + '*', settings['results_prefix'] + '*']}}),
        dict(Effect='Allow', Action=['s3:GetObject', 's3:GetObjectVersion'], Resource=bucket + '/' + snapshot + '*'),
        dict(Effect='Allow', Action=['s3:GetObject'] + (['s3:PutObject'] if execute else []),
             Resource=bucket + '/' + settings['results_prefix'] + '*'),
        dict(Effect='Allow', Action=ATHENA_ACTIONS if execute else ['athena:GetWorkGroup'],
             Resource=f'arn:aws:athena:{target.region}:{account}:workgroup/{settings["workgroup"]}'),
        dict(Effect='Allow', Action=GLUE_ACTIONS if execute else GLUE_ACTIONS[:-1], Resource=[
            glue + 'catalog', glue + 'database/' + settings['database'],
            glue + 'table/' + settings['database'] + '/' + settings['table_prefix'] + '_' + expected['snapshot_id'] + '_*']),
    ]
    value = dict(Version='2012-10-17', Statement=statements)
    check(len(json.dumps(value, separators=(',', ':'))) <= 2048, 'STS_SESSION_POLICY_TOO_LARGE')
    return value


def _sql_statements(text):
    # Only the reviewed repository DDL templates, not an arbitrary SQL parser.
    content = '\n'.join(line for line in text.splitlines() if not line.strip().startswith('--'))
    return [sql.strip() for sql in content.split(';') if sql.strip()]


def _literal(value):
    check(type(value) in (str, int), 'ATHENA_PARAMETER_TYPE')
    encoded = str(value) if type(value) is int else "'" + value.replace("'", "''") + "'"
    check(len(encoded) <= 1024, 'ATHENA_PARAMETER_LIMIT')
    return encoded


def _array_projection(sql):
    # GetQueryResults has string cells, no nested-value codec. SQL explicitly
    # encodes ONLY the two array columns as JSON. Row selection/joins are unchanged.
    names = ('comparison', 'package_spdx_id', 'left_name', 'left_version', 'left_purls', 'left_purpose',
             'right_name', 'right_version', 'right_purls', 'right_purpose')
    projection = ', '.join('json_format(CAST(' + n + ' AS JSON)) AS ' + n if n.endswith('_purls') else n for n in names)
    return 'SELECT ' + projection + '\nFROM (\n' + sql.rstrip().rstrip(';') + '\n) AS reported'


def _json_value(raw):
    # Reuse the strict JSON parser (which requires an object at its root) without
    # losing array/NULL values or accepting duplicate keys inside a struct.
    return document(b'{"value":' + raw.encode() + b'}', limit=RESULT_BYTES)['value']


def build_plan(proposal, inspection, batch, expected, settings, round_id):
    """Freeze requests/expectations from recovered bytes and versioned templates."""
    check(type(round_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}', round_id), 'ATHENA_ROUND_ID_INVALID')
    check(proposal['execute'] is False and proposal['snapshot_id'] == expected['snapshot_id']
          and proposal['batch_id'] == expected['batch_id'], 'ATHENA_CATALOG_PLAN_DIFFERS')
    data = read_completed(batch)
    names = proposal['table_names']
    statements = []

    def add(name, kind, sql, parameters=(), expected_rows=None, json_columns=()):
        check(sql.count('?') == len(parameters), 'ATHENA_PARAMETER_COUNT')
        statements.append(dict(id=name, kind=kind, sql=sql, sql_sha256=sha256(sql.encode()),
                               parameters=[_literal(p) for p in parameters], expected_rows=expected_rows,
                               json_columns=list(json_columns)))

    tables = _sql_statements(proposal['ddl'])
    views = _sql_statements(proposal['views'])
    check(len(tables) == 2 and len(views) == 3, 'ATHENA_DDL_TEMPLATE_COUNT')
    for number, sql in enumerate(tables):
        check(sql.startswith('CREATE EXTERNAL TABLE IF NOT EXISTS '), 'ATHENA_DDL_TEMPLATE_DIFFERS')
        add('table-' + str(number), 'DDL', sql.replace('CREATE EXTERNAL TABLE IF NOT EXISTS ', 'CREATE EXTERNAL TABLE ', 1))
    for number, sql in enumerate(views):
        check(sql.startswith('CREATE OR REPLACE VIEW '), 'ATHENA_DDL_TEMPLATE_DIFFERS')
        add('view-' + str(number), 'DDL', sql.replace('CREATE OR REPLACE VIEW ', 'CREATE VIEW ', 1))
    for name in QUERIES:
        query = inspection['local_queries']['queries'][name]
        sql, rows, codecs = proposal['queries'][name + '.sql'], query['rows'], []
        if name in ('03_runtime_vs_dev', '04_compare_digests'):
            sql = _array_projection(sql)
            codecs = ['left_purls', 'right_purls']
            rows = [{k: (_json_value(v) if k in codecs and v is not None else v)
                     for k, v in row.items()} for row in rows]
        add(name, 'SELECT', sql, query['parameters'], rows, codecs)
    obs, pkg, inv = (names[k] for k in ('sbom_observation_rows_v1', 'sbom_package_rows_v1', 'sbom_inventory_v1'))
    add('count_observations', 'SELECT', 'SELECT COUNT(*) AS observation_count FROM ' + obs,
        expected_rows=[{'observation_count': len(data['observations'])}])
    add('count_packages', 'SELECT', 'SELECT COUNT(*) AS package_record_count FROM ' + pkg,
        expected_rows=[{'package_record_count': len(data['packages'])}])
    counts = [{k: row[k] for k in ('framework', 'document_platform', 'component_records')}
              for row in inspection['local_queries']['component_counts']]
    add('inventory_counts', 'SELECT', 'SELECT framework, document_platform, COUNT(*) AS component_records FROM ' + inv
        + ' GROUP BY framework, document_platform ORDER BY framework, document_platform', expected_rows=counts)
    nullable = {'total': len(data['packages'])}
    for column, prefix in (('purls', 'purls'), ('external_references', 'references')):
        nullable[prefix + '_null'] = sum(p[column] is None for p in data['packages'])
        nullable[prefix + '_empty'] = sum(p[column] == [] for p in data['packages'])
    add('null_empty_arrays', 'SELECT', 'SELECT COUNT(*) AS total, '
        'SUM(CASE WHEN purls IS NULL THEN 1 ELSE 0 END) AS purls_null, '
        'SUM(CASE WHEN cardinality(purls)=0 THEN 1 ELSE 0 END) AS purls_empty, '
        'SUM(CASE WHEN external_references IS NULL THEN 1 ELSE 0 END) AS references_null, '
        'SUM(CASE WHEN cardinality(external_references)=0 THEN 1 ELSE 0 END) AS references_empty FROM ' + pkg,
        expected_rows=[nullable])
    add('nested_types', 'SELECT', 'SELECT typeof(purls) AS purls_type, typeof(external_references) AS references_type FROM '
        + pkg + ' LIMIT 1', expected_rows=[dict(purls_type='array(varchar)', references_type=
        'array(row(reference_category varchar, reference_type varchar, reference_locator varchar, comment varchar))')])
    reference_fields = ['reference_category', 'reference_type', 'reference_locator', 'comment']
    encoded_refs = 'json_format(CAST(transform(external_references, r -> map(ARRAY[' + ','.join(
        "'" + k + "'" for k in reference_fields) + '], ARRAY[' + ','.join('r.' + k for k in reference_fields) + '])) AS JSON))'
    nested_rows = [{k: row[k] for k in ('sbom_sha256', 'package_spdx_id', 'purls', 'external_references',
                                      'license_declared', 'license_concluded')} for row in data['packages']]
    add('nested_values', 'SELECT', 'SELECT sbom_sha256, package_spdx_id, json_format(CAST(purls AS JSON)) AS purls, '
        + encoded_refs + ' AS external_references, license_declared, license_concluded FROM ' + pkg,
        expected_rows=nested_rows, json_columns=['purls', 'external_references'])
    add('describe_observations', 'DESCRIBE', 'DESCRIBE ' + obs)
    add('describe_packages', 'DESCRIBE', 'DESCRIBE ' + pkg)
    check(Counter(s['kind'] for s in statements) == {'DDL': 5, 'SELECT': 11, 'DESCRIBE': 2}, 'ATHENA_BUDGET_DIFFERS')
    value = dict(protocol_version=1, round_id=round_id, snapshot_id=expected['snapshot_id'], batch_id=expected['batch_id'],
                 catalog=settings['catalog'], database=settings['database'], workgroup=settings['workgroup'],
                 result_configuration=result_configuration(expected, settings), execution_limit=18,
                 scan_cutoff_bytes=settings['scan_cutoff_bytes'], timeout_seconds=settings['timeout_seconds'],
                 manifest_sha256=settings['manifest_sha256'], manifest_version_id=settings['manifest_version_id'],
                 result_reuse=False, table_names=names, statements=statements)
    raw = canonical(value)
    check(len(raw) <= PLAN_LIMIT, 'ATHENA_PLAN_LIMIT')
    return raw


def request(statement, plan):
    value = dict(QueryString=statement['sql'], WorkGroup=plan['workgroup'],
                 QueryExecutionContext=dict(Catalog=plan['catalog'], Database=plan['database']),
                 ResultConfiguration=plan['result_configuration'],
                 ResultReuseConfiguration={'ResultReuseByAgeConfiguration': {'Enabled': False}})
    if statement['parameters']:
        value['ExecutionParameters'] = statement['parameters']
    # Token covers ALL service request fields and the externally selected round.
    value['ClientRequestToken'] = sha256(canonical(dict(round_id=plan['round_id'], statement_id=statement['id'], request=value)))
    return value


def _service_call(client, operation, **kwargs):
    try:
        return getattr(client, operation)(**kwargs)
    except Exception as error:
        code = poc.service_code(error)
        uncertain = isinstance(error, (TimeoutError, OSError, ConnectionError)) or code in (
            'ReadTimeoutError', 'ConnectTimeoutError', 'ConnectionClosedError', 'EndpointConnectionError',
            'InternalServerException')
        raise IngestionError('ATHENA_START_OUTCOME_UNKNOWN' if uncertain and operation=='start_query_execution'
                             else 'ATHENA_SERVICE_ERROR', stage='ATHENA', operation=operation,
                             observed={'service_code': code}, retryable=uncertain) from error


def _cell(value, column, json_columns):
    check(type(value) is dict and set(value) <= {'VarCharValue'}, 'ATHENA_CELL_INVALID')
    if 'VarCharValue' not in value:
        return None
    raw = value['VarCharValue']
    check(type(raw) is str, 'ATHENA_CELL_INVALID')
    if column['Name'] in json_columns:
        check(column['Type'] in ('varchar', 'string'), 'ATHENA_JSON_RESULT_TYPE_DIFFERS')
        return _json_value(raw)
    kind = column['Type']
    if kind in ('tinyint', 'smallint', 'integer', 'int', 'bigint'):
        check(re.fullmatch('-?[0-9]+', raw), 'ATHENA_INTEGER_INVALID')
        return int(raw)
    if kind == 'boolean':
        check(raw in ('true', 'false'), 'ATHENA_BOOLEAN_INVALID')
        return raw == 'true'
    # DESCRIBE and other strings are recorded literally, including empty strings.
    check(kind in ('varchar', 'string', 'char'), 'ATHENA_UNEXPECTED_RESULT_TYPE')
    return raw


def query_results(client, execution_id, *, kind, json_columns=()):
    pages, rows, columns, tokens, total = [], [], None, set(), 0
    args = dict(QueryExecutionId=execution_id, MaxResults=1000)
    for page_number in range(16):
        response = _service_call(client, 'get_query_results', **args)
        total += len(canonical(response))
        check(total <= RESULT_BYTES, 'ATHENA_RESULT_BYTES_LIMIT')
        result = response['ResultSet']
        metadata = result['ResultSetMetadata']['ColumnInfo']
        check(type(metadata) is list and metadata and len(metadata) <= 128
              and len({c['Name'] for c in metadata}) == len(metadata), 'ATHENA_COLUMNS_INVALID')
        check(columns is None or columns == metadata, 'ATHENA_COLUMNS_CHANGED')
        columns = metadata
        raw_rows = result.get('Rows', [])
        check(type(raw_rows) is list and len(raw_rows) <= 1000, 'ATHENA_ROWS_INVALID')
        pages.append(response)
        if page_number == 0 and kind == 'SELECT':
            # SELECT result sets have the column label row. DESCRIBE has Hive
            # output and is preserved without guessing whether it has a header.
            check(raw_rows and raw_rows[0].get('Data') == [{'VarCharValue': c.get('Label', c['Name'])} for c in columns],
                  'ATHENA_HEADER_DIFFERS')
            raw_rows = raw_rows[1:]
        for row in raw_rows:
            cells = row.get('Data')
            check(type(cells) is list and len(cells) == len(columns), 'ATHENA_ROW_WIDTH_DIFFERS')
            rows.append({c['Name']: _cell(v, c, json_columns) for c, v in zip(columns, cells)})
            check(len(rows) <= RESULT_ROWS, 'ATHENA_RESULT_ROW_LIMIT')
        token = response.get('NextToken')
        if token is None:
            return dict(columns=columns, rows=rows, pages=pages)
        check(type(token) is str and token and len(token) <= 4096 and token not in tokens, 'ATHENA_RESULT_TOKEN_INVALID')
        tokens.add(token)
        args['NextToken'] = token
    raise IngestionError('ATHENA_RESULT_PAGE_LIMIT')


def execution_tokens(sql):
    """Lexical equality, not SQL equivalence. Only ASCII whitespace is ignored.

    Case, numbers, punctuation, quoted tokens and comments remain exact. In
    particular a line comment retains its terminating newline: deleting it can
    turn the following code into a comment. Unsupported syntax fails closed.
    This deliberately does not use the limited view grammar below.
    """
    check(type(sql) is str and 0 < len(sql.encode()) <= 262144, 'ATHENA_SQL_REPRESENTATION_UNSUPPORTED')
    tokens, position = [], 0
    while position < len(sql):
        start, char = position, sql[position]
        if char in ' \t\r\n\f':
            position += 1
            continue
        if sql.startswith('--', position):
            end = sql.find('\n', position)
            position = len(sql) if end < 0 else end + 1
        elif sql.startswith('/*', position):
            end = sql.find('*/', position + 2)
            check(end >= 0 and '/*' not in sql[position+2:end], 'ATHENA_SQL_REPRESENTATION_UNSUPPORTED')
            position = end + 2
        elif char in ("'", '"', '`'):
            position += 1
            while position < len(sql):
                check(sql[position] != '\\', 'ATHENA_SQL_REPRESENTATION_UNSUPPORTED')
                if sql[position] == char:
                    position += 1
                    if position < len(sql) and sql[position] == char:
                        position += 1
                        continue
                    break
                position += 1
            else:
                raise IngestionError('ATHENA_SQL_REPRESENTATION_UNSUPPORTED')
        elif re.match('[A-Za-z_]', char):
            position += 1
            while position < len(sql) and re.match('[A-Za-z_0-9]', sql[position]):
                position += 1
        elif char in '0123456789':
            match = re.match(r'[0-9]+(?:\.[0-9]+)?', sql[position:])
            position += len(match[0])
            check(position == len(sql) or not re.match('[A-Za-z_]', sql[position]),
                  'ATHENA_SQL_REPRESENTATION_UNSUPPORTED')
        elif sql[position:position+2] in ('<>', '<=', '>=', '!=', '->', '||'):
            position += 2
        elif char in '.,()[]<>=+-*/%?:;':
            position += 1
        else:
            raise IngestionError('ATHENA_SQL_REPRESENTATION_UNSUPPORTED', stage='RECONCILE',
                                 observed={'offset': position, 'sql_sha256': sha256(sql.encode())})
        tokens.append(sql[start:position])
    return tokens


def _safe_execution(value):
    # Preserve the explanatory response BEFORE rejecting identity. No SDK
    # headers, credentials, signed URLs or unrestricted error strings are saved.
    kept = {k: value[k] for k in ('QueryExecutionId', 'Query', 'WorkGroup', 'QueryExecutionContext',
                                'ExecutionParameters', 'EngineVersion') if k in value}
    status, stats = value.get('Status'), value.get('Statistics')
    kept['Status'] = {k: v for k, v in status.items() if k in ('State', 'SubmissionDateTime', 'CompletionDateTime')} if type(status) is dict else None
    kept['Statistics'] = {k: v for k, v in stats.items() if k in ('DataScannedInBytes', 'ResultReuseInformation')
                          or k.endswith('TimeInMillis')} if type(stats) is dict else None
    result = dict(value.get('ResultConfiguration') or {})
    location = result.get('OutputLocation')
    if type(location) is str and (not location.startswith('s3://') or '?' in location or '#' in location):
        result['OutputLocation'] = {'redacted_sha256': sha256(location.encode())}
    kept['ResultConfiguration'] = result
    return json_safe(kept)


def _execution(client, query_id, submission, *, observation=None):
    value = _service_call(client, 'get_query_execution', QueryExecutionId=query_id)['QueryExecution']
    check(type(value) is dict, 'ATHENA_EXECUTION_RESPONSE_INVALID')
    comparison = dict(sql_rule='EXACT_TOKENS_ASCII_WHITESPACE_ONLY',
                      catalog_rule='AWS_DEFAULT_CATALOG_CASE_ONLY',
                      execution_parameters='RETURNED' if 'ExecutionParameters' in value else 'NOT_RETURNED',
                      request_sql_sha256=sha256(submission['QueryString'].encode()),
                      observed_sql_sha256=sha256(value['Query'].encode()) if type(value.get('Query')) is str else None)
    if observation:
        observation(_safe_execution(value), comparison)

    def same(field, wanted, got):
        check(wanted == got, 'ATHENA_EXECUTION_IDENTITY_DIFFERS', stage='RECONCILE', key=query_id,
              expected={'field': field, 'sha256': sha256(canonical(wanted))},
              observed={'field': field, 'sha256': sha256(canonical(got)), 'comparison': comparison})

    same('QueryExecutionId', query_id, value.get('QueryExecutionId'))
    same('WorkGroup', submission['WorkGroup'], value.get('WorkGroup'))
    wanted_tokens = execution_tokens(submission['QueryString'])
    observed_tokens = execution_tokens(value.get('Query'))
    # Directional response-only exception: one lexical final terminator omitted.
    # Quoted/comment tokens containing ';' are intact; another statement,
    # intermediate delimiter, final comment or added terminator cannot match.
    if wanted_tokens[-1:] == [';'] and wanted_tokens.count(';') == 1 and observed_tokens == wanted_tokens[:-1]:
        comparison['sql_rule'] = 'TRAILING_TERMINATOR_OMITTED'
        if observation:
            observation(_safe_execution(value), comparison)
    else:
        same('Query.tokens', wanted_tokens, observed_tokens)
    context = value.get('QueryExecutionContext')
    check(type(context) is dict and set(context) == {'Catalog', 'Database'}, 'ATHENA_EXECUTION_CONTEXT_INVALID')
    same('Database', submission['QueryExecutionContext']['Database'], context['Database'])
    catalog = context['Catalog']
    wanted = submission['QueryExecutionContext']['Catalog']
    same('Catalog', wanted, 'AwsDataCatalog' if wanted == 'AwsDataCatalog' and catalog == 'awsdatacatalog' else catalog)
    if 'ExecutionParameters' in value:
        check(type(value['ExecutionParameters']) is list and all(type(p) is str for p in value['ExecutionParameters']),
              'ATHENA_EXECUTION_IDENTITY_DIFFERS', observed={'field': 'ExecutionParameters', 'comparison': comparison})
        same('ExecutionParameters', submission.get('ExecutionParameters', []), value['ExecutionParameters'])
    # Absence is not evidence of changed parameters. Exact request/token bindings
    # are checked independently by validate_journal; results are compared later.
    return value


def validate_journal(raw, journal, authorization_reference):
    """Validate the whole prefix before any service call, including an uncertain start."""
    plan = document(raw, limit=PLAN_LIMIT)
    plan_fields = {'protocol_version', 'round_id', 'snapshot_id', 'batch_id', 'catalog', 'database', 'workgroup',
                   'result_configuration', 'execution_limit', 'scan_cutoff_bytes', 'timeout_seconds', 'manifest_sha256',
                   'manifest_version_id', 'result_reuse', 'table_names', 'statements'}
    check(set(plan) == plan_fields and type(plan['protocol_version']) is int and plan['protocol_version'] == 1
          and type(plan['statements']) is list and all(type(s) is dict and set(s) == {
              'id', 'kind', 'sql', 'sql_sha256', 'parameters', 'expected_rows', 'json_columns'} for s in plan['statements']),
          'ATHENA_PLAN_SCHEMA_INVALID')
    ids = ['table-0', 'table-1', 'view-0', 'view-1', 'view-2'] + list(QUERIES) + [
        'count_observations', 'count_packages', 'inventory_counts', 'null_empty_arrays', 'nested_types',
        'nested_values', 'describe_observations', 'describe_packages']
    check(type(plan.get('execution_limit')) is int and plan['execution_limit'] == 18
          and [s['id'] for s in plan['statements']] == ids
          and Counter(s['kind'] for s in plan['statements']) == {'DDL': 5, 'SELECT': 11, 'DESCRIBE': 2}
          and all(type(s['sql']) is str and s['sql_sha256'] == sha256(s['sql'].encode())
                  and type(s['parameters']) is list and all(type(p) is str for p in s['parameters'])
                  for s in plan['statements']), 'ATHENA_BUDGET_DIFFERS')
    check(type(journal) is dict and set(journal) == {'protocol_version', 'plan_sha256', 'authorization_reference', 'executions'}
          and type(journal['protocol_version']) is int and journal['protocol_version'] == 1
          and journal['plan_sha256'] == sha256(raw) and journal['authorization_reference'] == authorization_reference
          and type(journal['executions']) is dict, 'ATHENA_JOURNAL_CONFLICT')
    entries = journal['executions']
    check(set(entries) == set(ids[:len(entries)]), 'ATHENA_JOURNAL_SEQUENCE_INVALID')
    query_ids = set()
    optional = {'execution', 'remote_observation', 'identity_comparison', 'timing', 'data_scanned_bytes',
                'results', 'cancellation_observation', 'start_attempts', 'recorded_get_attempts'}
    for number, statement in enumerate(plan['statements'][:len(entries)]):
        entry = entries[statement['id']]
        check(type(entry) is dict and {'request', 'submitted_at', 'state', 'query_id'} <= set(entry)
              and set(entry) <= {'request', 'submitted_at', 'state', 'query_id'} | optional
              and canonical(entry['request']) == canonical(request(statement, plan))
              and type(entry['submitted_at']) in (int, float) and math.isfinite(entry['submitted_at'])
              and entry['submitted_at'] >= 0, 'ATHENA_JOURNAL_CONFLICT')
        check(entry['state'] in ('PREPARED', 'SUBMITTED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'VERIFIED',
                                'FAILED', 'CANCELLED', 'TIMED_OUT'), 'ATHENA_JOURNAL_CONFLICT')
        check(number == len(entries)-1 or entry['state'] == 'VERIFIED', 'ATHENA_JOURNAL_SEQUENCE_INVALID')
        query_id = entry['query_id']
        check((query_id is None and entry['state'] == 'PREPARED') or
              (type(query_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', query_id)
               and query_id not in query_ids and entry['state'] != 'PREPARED'), 'ATHENA_JOURNAL_QUERY_ID_INVALID')
        if query_id is not None:
            query_ids.add(query_id)
        if 'start_attempts' in entry:
            check(type(entry['start_attempts']) is int and entry['start_attempts'] > 0, 'ATHENA_JOURNAL_CONFLICT')
        if 'recorded_get_attempts' in entry:
            check(type(entry['recorded_get_attempts']) is int and entry['recorded_get_attempts'] > 0, 'ATHENA_JOURNAL_CONFLICT')
        if entry['state'] == 'VERIFIED':
            check(type(entry.get('data_scanned_bytes')) is int and entry['data_scanned_bytes'] >= 0
                  and entry.get('execution', {}).get('QueryExecutionId') == query_id
                  and entry['execution'].get('Status', {}).get('State') == 'SUCCEEDED', 'ATHENA_JOURNAL_CONFLICT')
    return plan


def _epoch(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        check(isinstance(parsed, datetime) and parsed.tzinfo is not None and parsed.utcoffset() is not None,
              'ATHENA_TIMING_INVALID')
        result = parsed.timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError) as error:
        raise IngestionError('ATHENA_TIMING_INVALID') from error
    check(math.isfinite(result), 'ATHENA_TIMING_INVALID')
    return result


def _terminal_timing(value, entry, now, timeout):
    status, stats = value['Status'], value.get('Statistics', {})
    check(type(status) is dict and type(stats) is dict, 'ATHENA_TIMING_INVALID')
    check('SubmissionDateTime' in status and 'CompletionDateTime' in status
          and 'TotalExecutionTimeInMillis' in stats, 'ATHENA_TIMING_INCONCLUSIVE')
    start, end = _epoch(status['SubmissionDateTime']), _epoch(status['CompletionDateTime'])
    total = stats['TotalExecutionTimeInMillis']
    check(type(total) is int and total >= 0 and entry['submitted_at'] <= start <= end <= now,
          'ATHENA_TIMING_INVALID')
    # Timestamp rounding and integer millisecond statistics may differ by <=1 ms.
    check(abs((end-start)*1000-total) <= 1.001, 'ATHENA_TIMING_INVALID')
    for name, duration in stats.items():
        if name.endswith('TimeInMillis'):
            check(type(duration) is int and 0 <= duration <= total, 'ATHENA_TIMING_INVALID')
    return dict(aws_duration_seconds=end-start, total_execution_time_ms=total,
                engine_execution_time_ms=stats.get('EngineExecutionTimeInMillis'),
                submission_to_completion_seconds=end-entry['submitted_at'],
                observation_delay_seconds=now-end, original_deadline=entry['submitted_at']+timeout,
                within_deadline=total < timeout*1000 and end-entry['submitted_at'] < timeout)


def _verify_execution(value, plan, *, kind):
    result = value['ResultConfiguration']
    desired = plan['result_configuration']
    # Athena appends the execution-specific output filename/directory.
    check(type(result.get('OutputLocation')) is str and result['OutputLocation'].startswith(desired['OutputLocation'])
          and result.get('ExpectedBucketOwner') == desired['ExpectedBucketOwner']
          and result.get('EncryptionConfiguration') == desired['EncryptionConfiguration'], 'ATHENA_EFFECTIVE_RESULTS_DIFFERS')
    check(value.get('EngineVersion', {}).get('EffectiveEngineVersion') == 'Athena engine version 3', 'ATHENA_ENGINE_DIFFERS')
    stats = value.get('Statistics', {})
    reused = stats.get('ResultReuseInformation', {}).get('ReusedPreviousResult')
    check(reused is False if kind == 'SELECT' else reused in (None, False), 'ATHENA_RESULT_REUSE_INCONCLUSIVE')
    scanned = stats.get('DataScannedInBytes')
    check(type(scanned) is int and 0 <= scanned <= plan['scan_cutoff_bytes'], 'ATHENA_SCANNED_BYTES_DIFFERS')
    return scanned


def execute_plan(raw, client, journal_path, *, authorized_sha256, authorization_reference,
                 clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
    """No cloud client construction. Journal is persisted BEFORE every submission.

    A retry/restart reuses each frozen token. Unknown outcomes never get a fresh
    token. A failure/timeout interrupts the sequence; it is not an approval.
    """
    check(type(raw) is bytes and sha256(raw) == hash_id(authorized_sha256)
          and type(authorization_reference) is str and re.fullmatch('[A-Za-z0-9:/._# -]{1,200}', authorization_reference),
          'ATHENA_EXPLICIT_AUTHORIZATION_REQUIRED', stage='AUTHORIZE')
    path = Path(journal_path)
    journal = document(read_local(path, 16 * 1024 * 1024), limit=16 * 1024 * 1024) if path.exists() else dict(
        protocol_version=1, plan_sha256=sha256(raw), authorization_reference=authorization_reference, executions={})
    plan = validate_journal(raw, journal, authorization_reference)
    calls = dict(get_query_execution=0, start_query_execution=0, new_starts=0, idempotent_retransmissions=0)
    historical_reserved = len(journal['executions'])
    for statement in plan['statements']:
        submission = request(statement, plan)
        entry = journal['executions'].get(statement['id'])
        new = entry is None
        if entry is None:
            entry = dict(request=submission, submitted_at=clock(), state='PREPARED', query_id=None)
            journal['executions'][statement['id']] = entry
        check(entry['request'] == submission, 'ATHENA_JOURNAL_CONFLICT')
        poc.write_json(path, json_safe(journal))
        if entry.get('state') in ('FAILED', 'CANCELLED', 'TIMED_OUT'):
            raise IngestionError('ATHENA_PRIOR_EXECUTION_FAILED', stage='ATHENA', key=entry['query_id'])
        if entry['query_id'] is None:
            entry['start_attempts'] = entry.get('start_attempts', 0) + 1
            poc.write_json(path, json_safe(journal))
            calls['start_query_execution'] += 1
            calls['new_starts' if new else 'idempotent_retransmissions'] += 1
            response = _service_call(client, 'start_query_execution', **submission)
            query_id = response.get('QueryExecutionId')
            check(type(query_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', query_id), 'ATHENA_QUERY_ID_INVALID')
            check(query_id not in [e['query_id'] for e in journal['executions'].values() if e is not entry],
                  'ATHENA_JOURNAL_QUERY_ID_INVALID')
            entry.update(query_id=query_id, state='SUBMITTED')
            poc.write_json(path, json_safe(journal))
        query_id = entry['query_id']
        anchor, age = monotonic(), clock() - entry['submitted_at']
        check(math.isfinite(age) and age >= 0, 'ATHENA_CLOCK_INVALID')

        def preserve(observed, comparison):
            entry.update(remote_observation=observed, identity_comparison=comparison)
            poc.write_json(path, json_safe(journal))

        try:
            while True:
                calls['get_query_execution'] += 1
                entry['recorded_get_attempts'] = entry.get('recorded_get_attempts', 0) + 1
                poc.write_json(path, json_safe(journal))
                value = _execution(client, query_id, submission, observation=preserve)
                state = value['Status']['State']
                check(state in TERMINAL + ('QUEUED', 'RUNNING'), 'ATHENA_STATE_INVALID')
                entry.update(state=state, execution=value)
                poc.write_json(path, json_safe(journal))
                if state in TERMINAL:
                    check(state == 'SUCCEEDED', 'ATHENA_QUERY_FAILED', stage='ATHENA', key=query_id,
                          observed={'state':state, 'athena_error':value['Status'].get('AthenaError')})
                    entry['timing'] = _terminal_timing(value, entry, clock(), plan['timeout_seconds'])
                    if not entry['timing']['within_deadline']:
                        entry['state'] = 'TIMED_OUT'
                        poc.write_json(path, json_safe(journal))
                        raise IngestionError('ATHENA_QUERY_TIMEOUT', stage='ATHENA', key=query_id,
                                             observed=entry['timing'])
                    break
                # Active queries keep the ORIGINAL deadline. Monotonic elapsed
                # prevents a wall-clock adjustment from granting more time.
                elapsed = max(clock() - entry['submitted_at'], age + monotonic() - anchor)
                check(math.isfinite(elapsed) and elapsed >= 0, 'ATHENA_CLOCK_INVALID')
                if elapsed >= plan['timeout_seconds']:
                    entry['state'] = 'TIMED_OUT'
                    poc.write_json(path, json_safe(journal))
                    _service_call(client, 'stop_query_execution', QueryExecutionId=query_id)
                    calls['get_query_execution'] += 1
                    entry['recorded_get_attempts'] += 1
                    entry['cancellation_observation'] = _execution(client, query_id, submission, observation=preserve)
                    poc.write_json(path, json_safe(journal))
                    raise IngestionError('ATHENA_QUERY_TIMEOUT', stage='ATHENA', key=query_id)
                sleep(min(2, max(0, plan['timeout_seconds'] - elapsed)))
            entry['data_scanned_bytes'] = _verify_execution(value, plan, kind=statement['kind'])
            if statement['kind'] != 'DDL':
                result = query_results(client, query_id, kind=statement['kind'], json_columns=statement['json_columns'])
                entry['results'] = result
                poc.write_json(path, json_safe(journal))  # Preserve mismatching rows too.
                if statement['expected_rows'] is not None:
                    check(Counter(canonical(r) for r in result['rows']) == Counter(canonical(r) for r in statement['expected_rows']),
                          'ATHENA_RESULTS_DIFFER', stage='COMPARE', key=query_id,
                          expected=len(statement['expected_rows']), observed=len(result['rows']))
                else:
                    check(result['rows'], 'ATHENA_DESCRIBE_EMPTY')
            entry['state'] = 'VERIFIED'
            poc.write_json(path, json_safe(journal))
        except Exception:
            poc.write_json(path, json_safe(journal))
            raise
    return dict(status='SUCCESS', code='ATHENA_RESULTS_VERIFIED', sql_plan_sha256=sha256(raw),
                query_executions=len(journal['executions']), total_data_scanned_bytes=sum(
                e['data_scanned_bytes'] for e in journal['executions'].values()),
                query_ids={s['id']:journal['executions'][s['id']]['query_id'] for s in plan['statements']},
                api_calls=calls, distinct_query_execution_ids=len({e['query_id'] for e in journal['executions'].values()}),
                historically_reserved_requests=historical_reserved,
                authorized_round_budget=18, remaining_unreserved_executions=18-len(journal['executions']),
                empty_array_from_parquet='NOT_EXERCISED', cryptographic_authenticity='NOT_REVALIDATED', publication_authority=False)


def _get_table(client, account, database, name):
    try:
        return client.get_table(CatalogId=account, DatabaseName=database, Name=name)['Table']
    except Exception as error:
        if poc.service_code(error) == 'EntityNotFoundException':
            return None
        raise IngestionError('GLUE_READ_ERROR', stage='CATALOG', operation='GetTable', key=name,
                             observed={'service_code':poc.service_code(error)}) from error


def _view_tokens(sql):
    """Compare ONLY the simple v1 views despite Athena's SQL pretty printing.

    v1 uses a column list, FROM/JOIN, equalities and AND, no functions or OR.
    Parentheses/optional AS cannot change precedence in that grammar. Literals
    stay exact; different columns, tables, predicates or operators still differ.
    This is not a general SQL semantic equivalence checker.
    """
    check(type(sql) is str and len(sql.encode()) <= 65536, 'GLUE_VIEW_SQL_LIMIT')
    pattern = re.compile(r'''\s+|--[^\n]*(?:\n|$)|/\*.*?\*/|'(?:''|[^'])*'|"[a-zA-Z_][a-zA-Z_0-9]*"|[a-zA-Z_][a-zA-Z_0-9]*|[.,=();]''', re.S)
    tokens, position = [], 0
    while position < len(sql):
        match = pattern.match(sql, position)
        check(match is not None, 'GLUE_VIEW_SQL_UNSUPPORTED')
        token = match[0]; position = match.end()
        if token == '(' and tokens and re.fullmatch('[a-z_][a-z_0-9]*', tokens[-1]):
            check(tokens[-1] in ('select','where','and','on'), 'GLUE_VIEW_SQL_UNSUPPORTED')
        if token.startswith('"'):
            check(token.strip('"').lower() not in ('select','distinct','from','join','on','where','and','false','true','as'),
                  'GLUE_VIEW_SQL_UNSUPPORTED')
        if token.isspace() or token.startswith(('--','/*')) or token in ('(',')') or token.upper()=='AS':
            continue
        tokens.append(token if token.startswith("'") else token.strip('"').lower())
    if tokens and tokens[-1]==';':
        tokens.pop()
    check(';' not in tokens and not any(t in tokens for t in ('or','union','with','group','limit')), 'GLUE_VIEW_SQL_UNSUPPORTED')
    return tokens


def resource_readback(athena, glue, expected, settings, proposal, journal=None, *, require_complete=False,
                      journal_path=None, plan_raw=None, authorization_reference=None):
    """No create/adopt/update. Existing names require this exact round's journal."""
    account = expected['destination']['expected_bucket_owner']
    calls = dict(get_query_execution=0, idempotent_retransmissions=0)
    group = _service_call(athena, 'get_work_group', WorkGroup=settings['workgroup'])['WorkGroup']
    configuration = group['Configuration']
    check(group['Name'] == settings['workgroup'] and group['State'] == 'ENABLED'
          and configuration.get('EnforceWorkGroupConfiguration') is True
          and configuration.get('BytesScannedCutoffPerQuery') == settings['scan_cutoff_bytes']
          and configuration.get('PublishCloudWatchMetricsEnabled') is False
          and configuration.get('RequesterPaysEnabled') is False
          and configuration.get('EngineVersion', {}).get('SelectedEngineVersion') == 'Athena engine version 3'
          and configuration.get('ResultConfiguration') == result_configuration(expected, settings), 'ATHENA_WORKGROUP_DIFFERS')
    try:
        db = glue.get_database(CatalogId=account, Name=settings['database'])['Database']
    except Exception as error:
        raise IngestionError('GLUE_DATABASE_READ_ERROR', stage='CATALOG', operation='GetDatabase',
                             observed={'service_code':poc.service_code(error)}) from error
    # CatalogId is explicit in every request; optional response fields, when
    # present, must match it. Missing optional metadata is not another catalog.
    check(db.get('Name') == settings['database'] and db.get('CatalogId', account) == account, 'GLUE_DATABASE_IDENTITY_DIFFERS')
    if journal_path is not None and journal:
        check(plan_raw is not None and authorization_reference, 'ATHENA_JOURNAL_VALIDATION_REQUIRED')
        validate_journal(plan_raw, journal, authorization_reference)
        # Reconcile a lost response only AFTER live workgroup/database checks.
        # Caller has already matched every saved request to the authorized plan.
        for entry in journal['executions'].values():
            if entry['query_id'] is None:
                entry['start_attempts'] = entry.get('start_attempts', 0) + 1
                poc.write_json(journal_path, json_safe(journal))
                calls['idempotent_retransmissions'] += 1
                response = _service_call(athena, 'start_query_execution', **entry['request'])
                query_id = response.get('QueryExecutionId')
                check(type(query_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', query_id), 'ATHENA_QUERY_ID_INVALID')
                check(query_id not in [e['query_id'] for e in journal['executions'].values() if e is not entry],
                      'ATHENA_JOURNAL_QUERY_ID_INVALID')
                entry.update(query_id=query_id, state='SUBMITTED')
                poc.write_json(journal_path, json_safe(journal))
    existing = {}
    for number, table_name in enumerate(TABLE_NAMES):
        qualified = proposal['table_names'][table_name]
        name = qualified.split('.')[1]
        table = _get_table(glue, account, settings['database'], name)
        if table is None:
            check(not require_complete, 'ATHENA_CATALOG_INCOMPLETE', stage='CATALOG', key=name)
            continue
        key = ('table-' + str(number)) if number < 2 else ('view-' + str(number-2))
        entry = (journal or {}).get('executions', {}).get(key)
        check(entry is not None and entry.get('query_id'), 'ATHENA_CATALOG_NAME_CONFLICT', stage='CATALOG', key=name)
        def preserve(observed, comparison):
            entry.update(remote_observation=observed, identity_comparison=comparison)
            if journal_path is not None:
                poc.write_json(journal_path, json_safe(journal))

        calls['get_query_execution'] += 1
        entry['recorded_get_attempts'] = entry.get('recorded_get_attempts', 0) + 1
        if journal_path is not None:
            poc.write_json(journal_path, json_safe(journal))
        observed = _execution(athena, entry['query_id'], entry['request'], observation=preserve)
        check(observed['Status']['State'] == 'SUCCEEDED', 'ATHENA_CATALOG_OWNERSHIP_INCONCLUSIVE', key=name)
        check(table.get('Name') == name and table.get('DatabaseName') == settings['database']
              and table.get('CatalogId', account) == account, 'GLUE_TABLE_IDENTITY_DIFFERS')
        if number < 2:
            table_kind = ('observations', 'packages')[number]
            location_rule = location_readback(proposal['locations']['sbom_' + table_kind], table['StorageDescriptor']['Location'])
            wanted = [(c['name'], c['type']) for c in parquet.definition()['tables'][table_kind]]
            types = dict(string='string', int32='int', int64='bigint', boolean='boolean', strings='array<string>',
                         references='array<struct<reference_category:string,reference_type:string,reference_locator:string,comment:string>>')
            columns = table['StorageDescriptor']['Columns']
            check(type(columns) is list and table.get('PartitionKeys',[]) == [], 'GLUE_COLUMNS_CONFLICT')
            check(table['TableType'] == 'EXTERNAL_TABLE' and [dict(Name=c.get('Name'),Type=c.get('Type')) for c in columns] ==
                  [dict(Name=name, Type=types[kind]) for name, kind in wanted], 'GLUE_COLUMNS_CONFLICT')
            descriptor = table['StorageDescriptor']
            check(descriptor.get('InputFormat') == 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat'
                  and descriptor.get('OutputFormat') == 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat'
                  and type(descriptor.get('SerdeInfo')) is dict
                  and descriptor.get('SerdeInfo', {}).get('SerializationLibrary') ==
                  'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe', 'GLUE_FORMAT_CONFLICT')
            # Keep both representations; this is not an S3 object-byte comparison.
            table = dict(table, location_comparison=location_rule)
        else:
            check(table.get('TableType') == 'VIRTUAL_VIEW' and type(table.get('ViewOriginalText')) is str,
                  'GLUE_VIEW_CONFLICT')
            # Ordinary Athena views encode the original SELECT in Presto JSON.
            # Unknown representations fail closed; a same-name view is not enough.
            encoded = re.fullmatch(r'/\* Presto View: ([A-Za-z0-9+/=]+) \*/', table['ViewOriginalText'])
            check(encoded is not None, 'GLUE_VIEW_REPRESENTATION_UNSUPPORTED')
            view = document(base64.b64decode(encoded[1], validate=True), limit=PLAN_LIMIT)
            original_sql = entry['request']['QueryString'].split(' AS\n', 1)
            check(len(original_sql) == 2 and _view_tokens(view.get('originalSql')) == _view_tokens(original_sql[1])
                  and view.get('catalog') in (settings['catalog'], settings['catalog'].lower())
                  and view.get('schema') == settings['database'],
                  'GLUE_VIEW_CONFLICT')
        existing[name] = table
    return dict(workgroup=group, database=db, existing_objects=existing, api_calls=calls)


def location_readback(expected, observed):
    """Only Glue's observed omission of ONE terminal slash is equivalent."""
    safe_observed = observed if type(observed) is str and observed.startswith('s3://') and '?' not in observed and '#' not in observed else (
        {'sha256': sha256(canonical(observed))})
    context = dict(expected=expected, observed=safe_observed)
    for uri in (expected, observed):
        check(type(uri) is str, 'GLUE_LOCATION_CONFLICT', **context)
        parsed = urlsplit(uri)
        check(parsed.scheme == 's3' and re.fullmatch('[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', parsed.netloc)
              and not parsed.query and not parsed.fragment and '%' not in uri and '\\' not in uri
              and '//' not in parsed.path and all(p not in ('.', '..') for p in parsed.path.split('/')),
              'GLUE_LOCATION_CONFLICT', **context)
    check(expected.endswith('/') and '/snapshots/' in expected
          and re.search(r'/snapshots/[0-9a-f]{64}/analytics/sbom_(?:observations|packages)/$', expected)
          and observed in (expected, expected[:-1]), 'GLUE_LOCATION_CONFLICT',
          **context)
    return dict(expected=expected, observed=observed, rule='EXACT_OR_ONE_FINAL_SLASH_OMITTED')


def snapshot_fingerprint(verified):
    manifest = document(verified.manifest.body)
    return dict(manifest_sha256=verified.manifest.sha256, manifest_version_id=verified.manifest_version,
                files=manifest['files'], object_count=len(verified.plan.objects)+1)


def run(s3, sts, athena, glue, expected, settings, session_name, round_id, reports, output, *,
        authorized_sha256=None, authorization_reference=None):
    reports = Path(reports)
    reports.mkdir(parents=True, exist_ok=True)
    check(reports.resolve() != Path(output).resolve() and Path(output).resolve() not in reports.resolve().parents, 'REPORT_INSIDE_INPUT')
    observed = poc.identity(sts, expected, session_name)
    poc.write_json(reports/'identity.json', observed)
    adapter = S3Adapter(s3, Destination(**expected['destination']))
    verified = read_snapshot(adapter, expected['snapshot_id'])
    before = snapshot_fingerprint(verified)
    poc.write_json(reports/'snapshot-before.json', before)
    check(before['manifest_sha256'] == settings['manifest_sha256']
          and before['manifest_version_id'] == settings['manifest_version_id']
          and before['object_count'] == expected['payload_objects'] + 1, 'ATHENA_SNAPSHOT_REFERENCE_DIFFERS')
    recover_snapshot(adapter, expected['snapshot_id'], output)
    inspection = poc.inspect_recovered(output, expected)
    poc.write_json(reports/'recovered-inspection.json', inspection)
    proposal = catalog_plan(adapter, expected['snapshot_id'], database=settings['database'], table_prefix=settings['table_prefix'])
    poc.write_json(reports/'catalog-proposal.json', proposal)
    raw = build_plan(proposal, inspection, output, expected, settings, round_id)
    # Persist exact plan bytes, not a reserialization with acquisition timestamps.
    path = reports/'sql-plan.json'
    if path.exists():
        check(path.read_bytes() == raw, 'ATHENA_FROZEN_PLAN_CONFLICT')
    else:
        path.write_bytes(raw)
    result = dict(status='PROPOSED', code='ATHENA_PLAN_NOT_AUTHORIZED', execute=False, sql_plan_sha256=sha256(raw),
                  snapshot_id=expected['snapshot_id'], statements=18, identity=observed,
                  publication_authority=False, cryptographic_authenticity='NOT_REVALIDATED')
    if authorized_sha256 is None:
        return result
    check(sha256(raw) == authorized_sha256 and authorization_reference, 'ATHENA_EXPLICIT_AUTHORIZATION_REQUIRED')
    journal_path = reports/'execution-journal.json'
    journal = document(read_local(journal_path,16*1024*1024),limit=16*1024*1024) if journal_path.exists() else None
    if journal:
        validate_journal(raw, journal, authorization_reference)
    resource = resource_readback(athena, glue, expected, settings, proposal, journal, journal_path=journal_path,
                                 plan_raw=raw, authorization_reference=authorization_reference)
    before_calls = resource['api_calls']
    poc.write_json(reports/'resources-before.json', json_safe(resource))
    try:
        result = execute_plan(raw, athena, journal_path, authorized_sha256=authorized_sha256,
                              authorization_reference=authorization_reference)
        journal = document(read_local(journal_path,16*1024*1024),limit=16*1024*1024)
        resource = resource_readback(athena, glue, expected, settings, proposal, journal, require_complete=True,
                                     journal_path=journal_path, plan_raw=raw, authorization_reference=authorization_reference)
        result['resource_readback_api_calls'] = dict(before=before_calls, after=resource['api_calls'])
        poc.write_json(reports/'resources-after.json', json_safe(resource))
    except Exception as error:
        failure = error.diagnostic() if isinstance(error, IngestionError) else dict(status='ERROR',code=poc.service_code(error))
        poc.write_json(reports/'execution-failure.json', failure)
        raise
    finally:
        after = snapshot_fingerprint(read_snapshot(adapter, expected['snapshot_id']))
        poc.write_json(reports/'snapshot-after.json', after)
        check(before == after, 'ATHENA_SNAPSHOT_CHANGED', stage='FINAL_READBACK')
    result.update(snapshot_bytes_and_versions_unchanged=True, snapshot_id=expected['snapshot_id'],
                  raw_traceability=[dict(row, raw_s3_uri=adapter.destination.uri(expected['snapshot_id']) + row['raw_spdx_path'])
                                    for row in inspection['raw_traceability']], identity=observed)
    return result


def json_safe(value):
    # AWS resource descriptions contain datetimes. Result data/NULLs are handled
    # separately and never stringified through this helper.
    import datetime
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if type(value) is dict:
        return {k:json_safe(v) for k,v in value.items()}
    if type(value) is list:
        return [json_safe(v) for v in value]
    return value


def aws_clients(expected):
    s3, sts = poc.aws_clients(expected)  # Explicit temporary-environment boundary.
    # Reuse the exact pinned credentials/client configuration, no default profile.
    import boto3
    from botocore.config import Config
    session = boto3.Session(aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                           aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
                           aws_session_token=os.environ['AWS_SESSION_TOKEN'], region_name=expected['destination']['region'])
    options = Config(connect_timeout=5, read_timeout=10, retries={'total_max_attempts':1})
    return s3, sts, session.client('athena',config=options), session.client('glue',config=options)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = poc._Parser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--athena-config', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--session-name', required=True)
    parser.add_argument('--round-id', required=True)
    parser.add_argument('--authorized-plan-sha256')
    parser.add_argument('--authorization-reference')
    parser.add_argument('--resume-receipt', type=Path)
    try:
        args = parser.parse_args(argv)
    except (IngestionError, argparse.ArgumentError):
        result = dict(status='ERROR', code='ATHENA_ARGUMENTS_INVALID', stage='ARGUMENTS')
        def option(name):
            positions = [i for i, value in enumerate(argv) if value == name]
            return Path(argv[positions[0]+1]) if len(positions)==1 and positions[0]+1<len(argv) else None
        sink = option('--report')
        try:
            if sink:
                inputs = [option(x) for x in ('--config','--athena-config','--output')]
                check(all(sink.resolve()!=p.resolve() and p.resolve() not in sink.resolve().parents for p in inputs if p),
                      'REPORT_INSIDE_INPUT')
                poc.write_json(sink,result)
        except Exception:
            result = dict(status='ERROR',code='REPORT_WRITE_FAILED')
        print(json.dumps(result,sort_keys=True))
        return 1
    result = dict(status='ERROR', code='ATHENA_NOT_STARTED')
    expected = None
    try:
        protected = (args.config, args.athena_config, args.output)
        check(all(args.report.resolve() != p.resolve() and p.resolve() not in args.report.resolve().parents for p in protected),
              'REPORT_INSIDE_INPUT')
        check(args.report.name not in ('sql-plan.json','execution-journal.json','snapshot-before.json','snapshot-after.json',
                                      'catalog-proposal.json','identity.json','recovered-inspection.json','resources-before.json',
                                      'resources-after.json','execution-failure.json','resume-receipt.json','resume-diagnostic.json'),
              'REPORT_RESERVED_PATH')
        expected, settings = poc.config(args.config), config(args.athena_config)
        check(bool(args.authorized_plan_sha256) == bool(args.authorization_reference), 'ATHENA_EXPLICIT_AUTHORIZATION_REQUIRED')
        if args.authorized_plan_sha256:
            # Hosted execute cannot silently start with an empty journal. The
            # restore happens before OIDC; recheck its working bytes before any
            # AWS client or resource reconciliation can submit a request.
            from scripts.pipeline.analytics.athena_restore import validate_working_restore
            check(args.resume_receipt is not None, 'ATHENA_VERIFIED_RESTORE_REQUIRED')
            validate_working_restore(args.resume_receipt, args.report.parent, executor_sha=os.environ.get('GITHUB_SHA'),
                                     plan_sha256=args.authorized_plan_sha256, authorization_reference=args.authorization_reference,
                                     round_id=args.round_id, snapshot_id=expected['snapshot_id'])
        else:
            check(args.resume_receipt is None, 'ATHENA_PLAN_RESTORE_FORBIDDEN')
        clients = aws_clients(expected)
        result = run(*clients, expected, settings, args.session_name, args.round_id, args.report.parent, args.output,
                     authorized_sha256=args.authorized_plan_sha256, authorization_reference=args.authorization_reference)
    except Exception as error:
        result = error.diagnostic() if isinstance(error, IngestionError) else dict(status='ERROR', code=poc.service_code(error))
    result.setdefault('stage', 'ATHENA_CALLER')
    result.update(diagnostic_version=1, round_id=args.round_id if re.fullmatch('[A-Za-z0-9_-]{1,64}',args.round_id) else None,
                  batch_id=expected['batch_id'] if expected else None, snapshot_id=expected['snapshot_id'] if expected else None,
                  executor_source_sha=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
                  run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), publication_authority=False,
                  cryptographic_authenticity='NOT_REVALIDATED')
    try:
        poc.write_json(args.report, result)
    except Exception:
        result = dict(status='ERROR', code='REPORT_WRITE_FAILED')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('SUCCESS','PROPOSED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
