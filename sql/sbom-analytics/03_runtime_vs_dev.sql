-- Parameters: common repository/run/attempt/SHA/platform, then runtime framework/SPDX hash, then dev framework/SPDX hash.
-- SPDXIDs are document-local. This aligns reported IDs and compares name/version;
-- it does not assert global component equivalence or installation/dependency status.
WITH same_execution AS (
  SELECT * FROM sbom_inventory_v1
  WHERE repository = ? AND run_id = ? AND run_attempt = ? AND source_sha = ? AND document_platform = ?
), left_inventory AS (
  SELECT DISTINCT package_spdx_id, package_name, package_version, purls, primary_package_purpose FROM same_execution
  WHERE framework = ? AND sbom_sha256 = ?
), right_inventory AS (
  SELECT DISTINCT package_spdx_id, package_name, package_version, purls, primary_package_purpose FROM same_execution
  WHERE framework = ? AND sbom_sha256 = ?
)
SELECT CASE WHEN r.package_spdx_id IS NULL THEN 'ONLY_RUNTIME'
            WHEN l.package_name = r.package_name AND
                 (l.package_version = r.package_version OR (l.package_version IS NULL AND r.package_version IS NULL))
            THEN 'SAME_REPORTED_NAME_VERSION' ELSE 'CHANGED_REPORTED_NAME_VERSION' END AS comparison,
       l.package_spdx_id AS package_spdx_id,
       l.package_name AS left_name, l.package_version AS left_version, l.purls AS left_purls,
       l.primary_package_purpose AS left_purpose,
       r.package_name AS right_name, r.package_version AS right_version, r.purls AS right_purls,
       r.primary_package_purpose AS right_purpose
FROM left_inventory l LEFT JOIN right_inventory r ON l.package_spdx_id = r.package_spdx_id
UNION ALL
SELECT 'ONLY_DEV', r.package_spdx_id, NULL, NULL, NULL, NULL,
       r.package_name, r.package_version, r.purls, r.primary_package_purpose
FROM right_inventory r LEFT JOIN left_inventory l ON l.package_spdx_id = r.package_spdx_id
WHERE l.package_spdx_id IS NULL
ORDER BY package_spdx_id;
