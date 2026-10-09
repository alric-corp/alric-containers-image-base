"""Render an isolated POC catalog proposal only after remote snapshot read-back."""
from pathlib import Path
import re

from scripts.pipeline.analytics.ingestion_types import check
from scripts.pipeline.analytics.snapshot import read_snapshot

SQL = Path(__file__).resolve().parents[3] / 'sql/sbom-analytics'


def catalog_plan(adapter, snapshot_id, *, database, table_prefix):
    # These names are external decisions; no default database or active names.
    for name in (database, table_prefix):
        check(type(name) is str and re.fullmatch('poc_[a-z0-9_]{1,32}', name), 'ISOLATED_POC_NAMESPACE_REQUIRED', stage='CATALOG')
    verified = read_snapshot(adapter, snapshot_id)
    plan = verified.plan
    names = ('sbom_observation_rows_v1','sbom_package_rows_v1','sbom_observations_v1','sbom_packages_v1','sbom_inventory_v1')
    mappings = {name: database + '.' + table_prefix + '_' + snapshot_id + '_' + name for name in names}

    def namespaced(sql):
        return re.sub(r'\b(' + '|'.join(names) + r')\b', lambda m:mappings[m[0]], sql)

    ddl = namespaced((SQL / 'tables.sql').read_text())
    locations = {}
    for table in ('observations','packages'):
        path = 'analytics/sbom_' + table + '/'
        members = [o.path for o in plan.objects if o.path.startswith(path)]
        check(members == [path + 'part-00000.parquet'], 'CATALOG_FILE_SET_DIFFERS', stage='CATALOG')
        uri = plan.destination.uri(snapshot_id) + path
        original = 's3://<ANALYTICS_BUCKET>/<DATASET_PREFIX>/analytics/schema=v1/normalizer=1.0.0/sbom_' + table + '/'
        check(ddl.count(original) == 1, 'CATALOG_TEMPLATE_DIFFERS', stage='CATALOG')
        ddl = ddl.replace(original, uri)
        locations['sbom_' + table] = uri
    queries = {p.name:namespaced(p.read_text()) for p in sorted(SQL.glob('0*.sql'))}
    return dict(protocol_version=1, snapshot_id=snapshot_id, batch_id=plan.batch_id,
        catalog_eligible=True, execute=False, database=database, table_names=mappings,
        locations=locations, raw_root_uri=plan.destination.uri(snapshot_id), ddl=ddl,
        views=namespaced((SQL / 'views.sql').read_text()), queries=queries,
        selection='EXPLICIT_CLOSED_SNAPSHOT', existing_tables_changed=False,
        external_namespace_confirmation_required=True, tables_transaction='NOT_PROVIDED',
        authentication='NOT_REVALIDATED', publication_authority=False)
