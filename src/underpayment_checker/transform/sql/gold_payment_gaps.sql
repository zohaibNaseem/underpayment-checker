-- GOLD: the expected amount and the paid amount for each customer payment row.
--
-- Rules for a candidate published rate (written in Attempto Controlled English):
--   * A candidate rate has the same payer, the same NPI and the same code as the payment row.
--   * If the customer gives a TIN then the candidate rate has the same TIN.
--   * If the customer gives a place of service then the candidate rate has the same
--     place of service or has no place of service.
--   * A candidate rate has the same modifier as the payment row or has no modifier.
--     BCBS Texas publishes no rates by modifier (MRF guide 3.2). CMS requires GP, GO or GN on
--     therapy codes. Thus the rate without a modifier is the usual match.
--   * If a candidate rate with the same modifier exists then the query uses only that rate.
--   * A candidate rate does not expire before 1 January of the payment year.
--
-- The expected rate is the lowest candidate rate. Thus each flag is true for the least
-- favourable reading. The confidence is HIGH only if all candidates have one exact dollar rate.
-- The allowed amount is the insurer payment plus the patient share. Thus deductibles and
-- co-payments do not show as gaps. The thresholds come from DuckDB variables. Refer to
-- sql_pipeline_runner.py.
CREATE OR REPLACE TABLE gold_payment_gaps AS
WITH candidates AS (
    SELECT
        p.payment_id,
        r.rate,
        r.negotiated_type,
        r.source_file,
        (r.modifier <> '' AND r.modifier = p.modifier) AS exact_modifier
    FROM silver_customer_payments AS p
    JOIN silver_published_rates AS r
      ON r.payer_id = p.payer_id
     AND r.npi = p.npi
     AND r.cpt = p.cpt
     AND (p.tin = '' OR r.tin = p.tin)
     AND (p.place_of_service = '' OR r.place_of_service IN (p.place_of_service, ''))
     AND (r.modifier = '' OR r.modifier = p.modifier)
     AND (r.expiration_date IS NULL OR r.expiration_date >= make_date(p.year, 1, 1))
),
preferred AS (
    SELECT *
    FROM candidates
    QUALIFY exact_modifier = max(exact_modifier) OVER (PARTITION BY payment_id)
),
matched AS (
    SELECT
        payment_id,
        min(rate)                                                    AS expected_rate,
        max(rate)                                                    AS max_published_rate,
        count(DISTINCT rate)                                         AS distinct_rates,
        string_agg(DISTINCT negotiated_type, ',' ORDER BY negotiated_type) AS negotiated_types,
        bool_and(negotiated_type IN ('negotiated', 'fee schedule'))  AS all_exact_amounts,
        string_agg(DISTINCT source_file, ',' ORDER BY source_file)   AS source_files
    FROM preferred
    GROUP BY payment_id
)
SELECT
    p.payment_id,
    p.payer_id,
    p.npi,
    p.tin,
    p.cpt,
    p.modifier,
    p.place_of_service,
    p.year,
    p.line_count,
    p.total_allowed,
    p.min_allowed,
    m.expected_rate,
    m.max_published_rate,
    m.distinct_rates,
    m.negotiated_types,
    m.source_files,
    CASE
        WHEN m.payment_id IS NULL THEN NULL
        WHEN m.all_exact_amounts AND m.distinct_rates = 1 THEN 'HIGH'
        ELSE 'REVIEW'
    END                                                              AS confidence,
    round(m.expected_rate * p.line_count, 2)                         AS expected_allowed,
    round(m.expected_rate * p.line_count - p.total_allowed, 2)       AS gap_usd,
    round((m.expected_rate * p.line_count - p.total_allowed)
          / nullif(m.expected_rate * p.line_count, 0), 4)            AS gap_pct,
    coalesce(p.min_allowed < m.expected_rate, false)                 AS some_lines_below_rate,
    CASE
        WHEN m.payment_id IS NULL THEN 'NO_PUBLISHED_RATE'
        WHEN m.expected_rate * p.line_count - p.total_allowed > getvariable('gap_usd_threshold')
         AND (m.expected_rate * p.line_count - p.total_allowed)
             / nullif(m.expected_rate * p.line_count, 0) > getvariable('gap_pct_threshold')
            THEN 'UNDERPAID'
        ELSE 'OK'
    END                                                              AS status
FROM silver_customer_payments AS p
LEFT JOIN matched AS m USING (payment_id)
ORDER BY p.payment_id;
