-- Run manually in the Athena query editor after the Silver and Gold
-- crawlers have cataloged the tables. Requires a Bronze table cataloged
-- separately (this lab catalogs Silver/Gold via
-- aws_glue_crawler.silver_crawler and aws_glue_crawler.gold_crawler;
-- cataloging Bronze as its own table is an optional manual step).

SELECT *
FROM silver_orders
LIMIT 10;
