-- SILVER: published professional fee-for-service dollar rates. One row for each price.
-- Input view: bronze_published_rates.
--
-- The query keeps: CPT and HCPCS codes, the 'ffs' arrangement, the professional and 'both'
-- billing classes, and the negotiated types that are dollar amounts ('negotiated',
-- 'fee schedule', 'derived').
-- The query removes: 'percentage' rates (a percent of billed charges, not dollars), 'per diem'
-- rates (facility rates), capitation and bundles, rates of zero or less, and incorrect NPIs.
-- TIN: The query keeps only EIN values as a TIN. If a provider uses its SSN then the file gives
-- the NPI as the TIN (BCBSTX guide 3.2). That value never matches a 9-digit customer TIN.
-- BCBS Texas writes each EIN with a dash, for example 76-0221050. The query removes the dash.
CREATE OR REPLACE TABLE silver_published_rates AS
SELECT DISTINCT
    upper(trim(payer_id))                                        AS payer_id,
    trim(npi)                                                    AS npi,
    CASE WHEN lower(trim(tin_type)) = 'ein'
         THEN regexp_replace(tin_value, '[^0-9]', '', 'g') ELSE '' END AS tin,
    upper(trim(billing_code))                                    AS cpt,
    upper(replace(coalesce(modifiers, ''), ' ', ''))             AS modifier,
    coalesce(trim(place_of_service), '')                         AS place_of_service,
    lower(trim(negotiated_type))                                 AS negotiated_type,
    CAST(negotiated_rate AS DOUBLE)                              AS rate,
    TRY_CAST(nullif(trim(expiration_date), '') AS DATE)          AS expiration_date,
    source_file
FROM bronze_published_rates
WHERE upper(trim(billing_code_type)) IN ('CPT', 'HCPCS')
  AND lower(trim(negotiation_arrangement)) = 'ffs'
  AND lower(trim(billing_class)) IN ('professional', 'both')
  AND lower(trim(negotiated_type)) IN ('negotiated', 'fee schedule', 'derived')
  AND negotiated_rate > 0
  AND regexp_full_match(trim(npi), '\d{10}');
