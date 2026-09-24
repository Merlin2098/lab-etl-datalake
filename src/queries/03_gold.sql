-- Gold aggregation by city.
SELECT
    city,
    SUM(orders) AS orders,
    SUM(revenue) AS revenue
FROM gold_orders
GROUP BY city
ORDER BY revenue DESC;

-- Partition pruning comparison (Parte 7/8 del laboratorio).
-- Consulta A: escanea todas las particiones.
SELECT *
FROM gold_orders;

-- Consulta B: filtra por partición + selecciona solo columnas necesarias.
-- Procesa menos datos gracias a partition pruning + columnar Parquet.
-- Nota: year/month/day son particiones Hive-style catalogadas como
-- string por el crawler (comportamiento por defecto), no como int — de ahí
-- los literales entre comillas.
SELECT
    city,
    revenue
FROM gold_orders
WHERE year = '2026'
  AND month = '9'
  AND day = '23';
