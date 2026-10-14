-- PROPOSED ONLY. Replace placeholders; this repository does not create AWS tables.
-- Each LOCATION contains only completed-batch Parquet files for this pinned projection.
-- No partitions are justified by the current six-document sample.

CREATE EXTERNAL TABLE IF NOT EXISTS sbom_observation_rows_v1 (
  observation_id string,
  sbom_sha256 string,
  predicate_digest string,
  repository string,
  source_sha string,
  framework string,
  image_repository string,
  event string,
  ref string,
  image_index_digest string,
  subject_digest string,
  sbom_scope string,
  document_namespace string,
  spdx_version string,
  normalizer_version string,
  raw_spdx_path string,
  integrity_check string,
  subject_check string,
  hosted_verification_status string,
  cryptographic_authenticity string,
  document_platform string,
  source_path string,
  source_timestamp string,
  source_timestamp_origin string,
  spdx_created string,
  validation_record_sha256 string,
  validation_record_reference string,
  publication_record_sha256 string,
  publication_record_reference string,
  published_index_sha256 string,
  candidate_identity_sha256 string,
  candidate_identity_reference string,
  hosted_verification_reference string,
  validation_record_check string,
  publication_record_check string,
  candidate_identity_check string,
  run_id bigint,
  run_attempt bigint,
  artifact_id bigint,
  schema_version int,
  package_count int,
  relationship_count int,
  publication_authority boolean
)
STORED AS PARQUET
LOCATION 's3://<ANALYTICS_BUCKET>/<DATASET_PREFIX>/analytics/schema=v1/normalizer=1.0.0/sbom_observations/'
;

CREATE EXTERNAL TABLE IF NOT EXISTS sbom_package_rows_v1 (
  schema_version int,
  normalizer_version string,
  sbom_sha256 string,
  package_spdx_id string,
  package_name string,
  package_version string,
  purls array<string>,
  external_references array<struct<reference_category:string,reference_type:string,reference_locator:string,comment:string>>,
  license_declared string,
  license_concluded string,
  supplier string,
  download_location string,
  primary_package_purpose string,
  is_document_subject boolean
)
STORED AS PARQUET
LOCATION 's3://<ANALYTICS_BUCKET>/<DATASET_PREFIX>/analytics/schema=v1/normalizer=1.0.0/sbom_packages/'
;
