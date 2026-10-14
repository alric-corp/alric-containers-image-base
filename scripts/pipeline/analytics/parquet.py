"""Explicit v1 Arrow types. No schema inference, SDK client or remote URI."""
import json
from pathlib import Path

from scripts.pipeline.analytics.spdx import NORMALIZER_VERSION, SCHEMA_VERSION, require

SCHEMA_PATH = Path(__file__).resolve().parents[3] / 'schemas/sbom-analytics/v1.json'


def definition():
    return json.loads(SCHEMA_PATH.read_bytes())


def arrow_schema(table):
    import pyarrow as pa
    types = {'string': pa.string(), 'int32': pa.int32(), 'int64': pa.int64(), 'boolean': pa.bool_()}
    types['strings'] = pa.list_(pa.field('element', pa.string(), nullable=False))
    types['references'] = pa.list_(pa.field('element', pa.struct([
        pa.field('reference_category', pa.string(), nullable=False),
        pa.field('reference_type', pa.string(), nullable=False),
        pa.field('reference_locator', pa.string(), nullable=False),
        pa.field('comment', pa.string(), nullable=True)]), nullable=False))
    spec = definition()
    require(spec['schema_version'] == SCHEMA_VERSION and spec['normalizer_version'] == NORMALIZER_VERSION,
            'unsupported analytical schema definition')
    return pa.schema([pa.field(f['name'], types[f['type']], nullable=f['nullable']) for f in spec['tables'][table]],
        metadata={b'sbom_analytics_schema_version': str(SCHEMA_VERSION).encode(),
                  b'normalizer_version': NORMALIZER_VERSION.encode()})


def write(path, table, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = arrow_schema(table)
    names = set(schema.names)
    require(all(set(row) == names for row in rows), 'record columns differ from explicit schema')
    for row in rows:
        require(all(field.nullable or row[field.name] is not None for field in schema), 'required column is null')
    data = pa.Table.from_pylist(rows, schema=schema)
    data.validate(full=True)
    pq.write_table(data, Path(path), version='2.6', compression='snappy',
                   use_compliant_nested_type=True, row_group_size=65536)
    require(read(path, table) == rows, 'Parquet round-trip differs from normalized records')
    return pa.__version__


def read(path, table):
    import pyarrow.parquet as pq
    path = Path(path)
    require(not path.is_symlink() and path.is_file(), 'regular local Parquet required')
    # ParquetFile avoids dataset/partition/filesystem inference.
    data = pq.ParquetFile(path).read()
    require(data.schema.equals(arrow_schema(table), check_metadata=True), 'Parquet schema differs from v1')
    data.validate(full=True)
    return data.to_pylist()
