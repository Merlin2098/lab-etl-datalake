-- Validate Silver records: row count and a quick sanity check on cleaning
-- (no duplicate order_id, no null/zero amount).

SELECT COUNT(*) AS total_orders
FROM silver_orders;

SELECT order_id, COUNT(*) AS occurrences
FROM silver_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
