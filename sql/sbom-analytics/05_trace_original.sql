-- Parameter: observation_id from a selected result/context. No tag or latest-run inference.
SELECT observation_id, repository, run_id, run_attempt, source_sha, framework, event, ref,
       image_index_digest, subject_digest, document_platform, sbom_sha256, predicate_digest,
       raw_spdx_path, artifact_id, source_path, source_timestamp, source_timestamp_origin,
       validation_record_reference, publication_record_reference, candidate_identity_reference,
       integrity_check, subject_check, hosted_verification_status, cryptographic_authenticity
FROM sbom_observations_v1 WHERE observation_id = ?;
