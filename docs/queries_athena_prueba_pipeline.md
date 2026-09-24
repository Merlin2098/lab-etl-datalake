# Queries de Athena para probar el pipeline

Consultas SQL listas para pegar en el **Query editor** de Amazon Athena y
validar que el pipeline Bronze → Silver → Gold funcionó correctamente.
Organizadas por propósito: existencia de datos, calidad de Silver,
agregaciones de Gold, y particionamiento.

## Antes de empezar

En el editor de Athena, configura:

- **Data source**: `AwsDataCatalog`
- **Database**: la base con el patrón `<project_name>_datalake_db`
  (ej. `lab_etl_datalake_db`)
- **Workgroup** (arriba a la derecha): `<project_name>-datalake`
  (ej. `lab-etl-datalake`)

Esquema real de las tablas (confirmado contra el catálogo desplegado):

**`silver_orders`**

| Columna | Tipo |
|---|---|
| `order_id` | string |
| `customer_id` | string |
| `order_date` | date |
| `status` | string |
| `amount` | decimal(18,2) |
| `city` | string |
| `carrier` | string |

**`gold_orders`**

| Columna | Tipo |
|---|---|
| `city` | string |
| `orders` | bigint |
| `revenue` | decimal(28,2) |
| `average_order_value` | decimal(22,6) |
| `year` (partición) | string |
| `month` (partición) | string |
| `day` (partición) | string |

**Importante:** `year`, `month` y `day` son columnas de partición de tipo
`string`, aunque parezcan numéricas. Compáralas siempre con literales
entre comillas simples (`WHERE year = '2026'`), nunca sin comillas — de
lo contrario Athena responde
`TYPE_MISMATCH: Cannot apply operator: varchar = integer`.

---

## 1. Existencia y volumen de datos

### 1.1 — Confirmar que Silver tiene datos

```sql
SELECT COUNT(*) AS total_rows
FROM silver_orders;
```

### 1.2 — Confirmar que Gold tiene datos

```sql
SELECT COUNT(*) AS total_rows
FROM gold_orders;
```

### 1.3 — Ver una muestra de Silver

```sql
SELECT *
FROM silver_orders
LIMIT 10;
```

### 1.4 — Ver una muestra de Gold

```sql
SELECT *
FROM gold_orders
LIMIT 10;
```

---

## 2. Calidad de datos en Silver (validar que la limpieza funcionó)

### 2.1 — No debe haber `order_id` duplicados

```sql
SELECT order_id, COUNT(*) AS occurrences
FROM silver_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
```

**Resultado esperado: 0 filas.** Si aparece alguna fila, la deduplicación
del Glue Job no funcionó.

### 2.2 — No debe haber `amount` inválido (nulo o menor/igual a cero)

```sql
SELECT COUNT(*) AS invalid_amount_rows
FROM silver_orders
WHERE amount IS NULL OR amount <= 0;
```

**Resultado esperado: 0.**

### 2.3 — No debe haber `order_id` vacío o nulo

```sql
SELECT COUNT(*) AS invalid_id_rows
FROM silver_orders
WHERE order_id IS NULL OR order_id = '';
```

**Resultado esperado: 0.**

### 2.4 — El `status` debe estar normalizado (todo en mayúsculas)

```sql
SELECT DISTINCT status
FROM silver_orders;
```

**Resultado esperado:** solo valores en mayúsculas (`COMPLETE`,
`PENDING`, `CANCELLED`), nunca mezcla de casing (`complete`, `Complete`,
`COMPLETE` no deberían coexistir).

### 2.5 — Verificar que Silver tiene menos filas que Bronze

Compara el resultado de `1.1` contra el número de filas de tu CSV
original en `bronze/orders/`. Silver debe tener **menos** filas: la
limpieza descartó registros inválidos y la deduplicación eliminó
duplicados. Si Silver tiene el mismo número de filas que Bronze, la
limpieza no se ejecutó (o el dataset de origen ya estaba perfectamente
limpio, lo cual es sospechoso con el dataset de ejemplo de este repo).

---

## 3. Agregaciones en Gold

### 3.1 — Ranking de ciudades por ingresos

```sql
SELECT
    city,
    SUM(orders) AS total_orders,
    SUM(revenue) AS total_revenue
FROM gold_orders
GROUP BY city
ORDER BY total_revenue DESC;
```

### 3.3 — Reconciliación: Gold debe cuadrar con Silver

```sql
SELECT SUM(orders) AS gold_total_orders
FROM gold_orders;
```

Compara este resultado contra `1.1` (`COUNT(*)` de `silver_orders`).
**Deben ser iguales** — Gold es una agregación de Silver, no debe perder
ni inventar filas.

### 3.4 — Ticket promedio por ciudad

```sql
SELECT
    city,
    AVG(average_order_value) AS avg_ticket
FROM gold_orders
GROUP BY city
ORDER BY avg_ticket DESC;
```

---

## 4. Particionamiento y partition pruning

### 4.1 — Ver qué particiones existen realmente

```sql
SHOW PARTITIONS gold_orders;
```

Ejemplo de particiones reales generadas con el dataset de ejemplo de este
repo (datos de septiembre 2026):

```text
year=2026/month=9/day=1
year=2026/month=9/day=2
year=2026/month=9/day=3
...
```

Usa los valores que veas en tu propio `SHOW PARTITIONS` para las queries
siguientes — pueden variar según cuándo/qué dataset subiste.

### 4.2 — Filtrar por una partición específica

```sql
SELECT city, revenue
FROM gold_orders
WHERE year = '2026'
  AND month = '9'
  AND day = '6';
```

Ajusta `day` a un valor real de tu `SHOW PARTITIONS`.

### 4.3 — Comparar datos escaneados: con y sin partition pruning

Ejecuta ambas por separado y compara el indicador **Data scanned**
(esquina superior derecha del panel de resultados de Athena) de cada una:

**Consulta A — sin filtro de partición (escanea todo):**

```sql
SELECT *
FROM gold_orders;
```

**Consulta B — con filtro de partición + solo columnas necesarias:**

```sql
SELECT city, revenue
FROM gold_orders
WHERE year = '2026'
  AND month = '9';
```

La consulta B debe reportar **menos datos escaneados** que la A — esa
diferencia es *partition pruning* en acción: Athena solo lee los archivos
Parquet de las particiones que coinciden con el filtro, no el dataset
completo.

### 4.4 — Filtrar por mes completo (todas las particiones de día)

```sql
SELECT
    day,
    SUM(orders) AS orders,
    SUM(revenue) AS revenue
FROM gold_orders
WHERE year = '2026'
  AND month = '9'
GROUP BY day
ORDER BY CAST(day AS INTEGER);
```

---

## 5. Diagnóstico rápido si algo falla

### 5.1 — Confirmar que las tablas existen con los nombres esperados

```sql
SHOW TABLES;
```

Debes ver exactamente `silver_orders` y `gold_orders` — no `orders` ni un
nombre con sufijo hash (`orders_a3ff0d60...`). Si ves eso, el Crawler que
generó el catálogo no separó Silver y Gold en dos crawlers distintos; ver
el insight correspondiente en
[despliegue_infra_terraform.md](despliegue_infra_terraform.md).

### 5.2 — Ver el schema completo de una tabla

```sql
DESCRIBE silver_orders;
```

```sql
DESCRIBE gold_orders;
```

### 5.3 — Si una query falla con error de Lake Formation

Si cualquier query de este documento falla con un mensaje tipo
`Insufficient Lake Formation permission(s)`, el problema no es de Athena
ni de estas queries — es un residuo de permisos en el catálogo de Glue.
Ver la sección de troubleshooting en
[despliegue_infra_terraform.md](despliegue_infra_terraform.md) y usar
`scripts/audit_lakeformation.py` para diagnosticar.

---

## Referencias

- [prueba_manual_consola_aws.md](prueba_manual_consola_aws.md) — guía
  completa del pipeline por consola; estas queries son la sección 5 de
  esa guía, ampliada.
- [src/queries/](../src/queries/) — versión resumida de estas queries
  como archivos `.sql` sueltos (`01_bronze.sql`, `02_silver.sql`,
  `03_gold.sql`).
