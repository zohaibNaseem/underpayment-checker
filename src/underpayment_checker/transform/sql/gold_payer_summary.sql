-- GOLD: one row for each payer.
-- The totals agree with gold_payment_gaps. The tests check this.
CREATE OR REPLACE TABLE gold_payer_summary AS
SELECT
    payer_id,
    count(*)                                                        AS rows_checked,
    count(*) FILTER (WHERE status = 'UNDERPAID')                    AS rows_underpaid,
    count(*) FILTER (WHERE status = 'NO_PUBLISHED_RATE')            AS rows_without_rate,
    coalesce(sum(line_count) FILTER (WHERE status = 'UNDERPAID'), 0) AS lines_underpaid,
    round(coalesce(sum(gap_usd) FILTER (WHERE status = 'UNDERPAID'), 0), 2) AS total_gap_usd,
    round(coalesce(sum(gap_usd) FILTER (WHERE status = 'UNDERPAID' AND confidence = 'HIGH'), 0), 2)
                                                                    AS high_confidence_gap_usd
FROM gold_payment_gaps
GROUP BY payer_id
ORDER BY total_gap_usd DESC;
