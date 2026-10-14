-- DISTINCT removes identical records from overlapping completed batches.
-- LOCATION must contain only schema v1 / normalizer 1.0.0 output.
-- Conflicting rows for a logical key are an ingestion error, not a last-write-wins decision.

CREATE OR REPLACE VIEW sbom_observations_v1 AS
SELECT DISTINCT observation_id, sbom_sha256, predicate_digest, repository, source_sha, framework, image_repository, event, ref, image_index_digest, subject_digest, sbom_scope, document_namespace, spdx_version, normalizer_version, raw_spdx_path, integrity_check, subject_check, hosted_verification_status, cryptographic_authenticity, document_platform, source_path, source_timestamp, source_timestamp_origin, spdx_created, validation_record_sha256, validation_record_reference, publication_record_sha256, publication_record_reference, published_index_sha256, candidate_identity_sha256, candidate_identity_reference, hosted_verification_reference, validation_record_check, publication_record_check, candidate_identity_check, run_id, run_attempt, artifact_id, schema_version, package_count, relationship_count, publication_authority
FROM sbom_observation_rows_v1;

CREATE OR REPLACE VIEW sbom_packages_v1 AS
SELECT DISTINCT schema_version, normalizer_version, sbom_sha256, package_spdx_id, package_name, package_version, purls, external_references, license_declared, license_concluded, supplier, download_location, primary_package_purpose, is_document_subject
FROM sbom_package_rows_v1;

CREATE OR REPLACE VIEW sbom_inventory_v1 AS
SELECT o.observation_id, o.sbom_sha256, o.predicate_digest, o.repository, o.source_sha, o.framework, o.image_repository, o.event, o.ref, o.image_index_digest, o.subject_digest, o.sbom_scope, o.document_namespace, o.spdx_version, o.normalizer_version, o.raw_spdx_path, o.integrity_check, o.subject_check, o.hosted_verification_status, o.cryptographic_authenticity, o.document_platform, o.source_path, o.source_timestamp, o.source_timestamp_origin, o.spdx_created, o.validation_record_sha256, o.validation_record_reference, o.publication_record_sha256, o.publication_record_reference, o.published_index_sha256, o.candidate_identity_sha256, o.candidate_identity_reference, o.hosted_verification_reference, o.validation_record_check, o.publication_record_check, o.candidate_identity_check, o.run_id, o.run_attempt, o.artifact_id, o.schema_version, o.package_count, o.relationship_count, o.publication_authority, p.package_spdx_id, p.package_name, p.package_version, p.purls, p.external_references, p.license_declared, p.license_concluded, p.supplier, p.download_location, p.primary_package_purpose, p.is_document_subject
FROM sbom_observations_v1 o JOIN sbom_packages_v1 p ON o.sbom_sha256 = p.sbom_sha256
WHERE o.sbom_scope = 'platform' AND p.is_document_subject = false;
