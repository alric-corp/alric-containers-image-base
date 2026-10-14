-- Parameter: exact component name. Historical observations/homonyms do not multiply images.
WITH containing_images AS (
  SELECT DISTINCT image_repository, image_index_digest, subject_digest, document_platform, package_version
  FROM sbom_inventory_v1 WHERE package_name = ?
)
SELECT package_version, COUNT(*) AS distinct_image_platforms
FROM containing_images GROUP BY package_version ORDER BY package_version;
