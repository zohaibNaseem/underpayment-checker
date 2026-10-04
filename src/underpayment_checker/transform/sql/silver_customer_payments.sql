-- SILVER: the customer payment totals with correct data types. One row for each uploaded row.
-- Input view: bronze_customer_payment_totals. The loader validated this data before.
CREATE OR REPLACE TABLE silver_customer_payments AS
SELECT
    row_number() OVER ()                                   AS payment_id,
    upper(trim(payer_id))                                  AS payer_id,
    trim(provider_npi)                                     AS npi,
    coalesce(trim(provider_tin), '')                       AS tin,
    upper(trim(cpt))                                       AS cpt,
    upper(coalesce(trim(modifier), ''))                    AS modifier,
    coalesce(trim(place_of_service), '')                   AS place_of_service,
    CAST(year AS INTEGER)                                  AS year,
    CAST(line_count AS INTEGER)                            AS line_count,
    CAST(total_allowed AS DOUBLE)                          AS total_allowed,
    TRY_CAST(nullif(trim(min_allowed), '') AS DOUBLE)      AS min_allowed,
    TRY_CAST(nullif(trim(max_allowed), '') AS DOUBLE)      AS max_allowed,
    record_source
FROM bronze_customer_payment_totals;
