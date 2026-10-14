-- Parameter: exact component name. One result per image/platform identity.
SELECT DISTINCT image_repository, image_index_digest, subject_digest, document_platform
FROM sbom_inventory_v1
WHERE package_name = ?
ORDER BY image_repository, image_index_digest, document_platform;
