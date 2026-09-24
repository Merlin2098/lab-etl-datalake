# Guía de prueba manual — Pipeline Bronze → Silver → Gold

Esta guía cubre cómo ejecutar y validar el pipeline **manualmente**, paso a
paso, después de haber desplegado la infraestructura (ver
[despliegue_infra_terraform.md](despliegue_infra_terraform.md)).

El pipeline no tiene disparador automático por evento — se ejecuta a
demanda, deliberadamente, para que cada paso se pueda observar por
separado en la consola de AWS Glue/Athena. Ver la nota al final sobre por
qué, y cómo se automatizaría más adelante.

Todos los pasos tienen dos vías: **Consola** (para explorar visualmente,
como pide el laboratorio) y **AWS CLI** (para repetir rápido). Usa la que
prefieras; los resultados son los mismos recursos reales. Si quieres una
guía que use **solo consola, sin absolutamente ningún comando de
terminal**, usa
[prueba_manual_consola_aws.md](prueba_manual_consola_aws.md) en su lugar.

## 0. Prerrequisitos

- Infraestructura ya desplegada (`terraform apply` completado).
- Credenciales cargadas en la shell (Git Bash):
  ```bash
  set -a
  source .env.credentials
  set +a
  ```
- Outputs de Terraform a mano:
  ```bash
  cd infra
  terraform output
  cd ..
  ```
  Los pasos siguientes usan estos nombres (ejemplo real de un despliegue
  con `project_name=lab-etl`):
  - `data_lake_bucket_name` → `lab-etl-<account-id>-datalake`
  - `glue_job_name` → `lab-etl-orders`
  - `glue_silver_crawler_name` → `lab-etl-silver-crawler`
  - `glue_gold_crawler_name` → `lab-etl-gold-crawler`
  - `glue_database_name` → `lab_etl_datalake_db`
  - `athena_workgroup_name` → `lab-etl-datalake`

## 1. Subir el dataset a Bronze

El dataset se carga directo dentro de `bronze/orders/`, sin ninguna
subcarpeta adicional. Un dataset con columnas distintas (otra entidad de
negocio, no otra corrida del mismo `orders`) necesita su propio
script/Job, no este mismo pipeline.

### Consola

1. Abre S3 → el bucket de `data_lake_bucket_name`.
2. Navega al prefijo `bronze/orders/`.
3. Sube el CSV dentro de esa carpeta.

### CLI

```bash
BUCKET=$(cd infra && terraform output -raw data_lake_bucket_name)
aws s3 cp data/orders.csv "s3://$BUCKET/bronze/orders/orders.csv"
```

El Glue Job lee todo `bronze/orders/` de una sola pasada.

### Generar un dataset distinto en cada corrida

Por defecto, `scripts/generate_orders_dataset.py` genera un dataset
**nuevo en cada corrida** — sin necesidad de pasar ningún argumento
(sirve también al ejecutarlo directo desde el IDE, ej. "Run Python
File"): escribe automáticamente a `data/orders-<timestamp>.csv`, usando
ese mismo timestamp como seed, sin que tengas que calcular nada a mano.

```bash
BUCKET=$(cd infra && terraform output -raw data_lake_bucket_name)

# El script imprime "Wrote N rows (...) to <ruta>" — se captura la ruta
# directamente del output en vez de copiarla a mano (el timestamp real
# tiene resolución de microsegundos, ej. data/orders-20260923192821874530.csv).
OUT_FILE=$(uv run python scripts/generate_orders_dataset.py | sed -n 's/.* to //p')
echo "Generado: $OUT_FILE"

FILE_NAME=$(basename "$OUT_FILE")          # orders-<timestamp>.csv

aws s3 cp "$OUT_FILE" "s3://$BUCKET/bronze/orders/${FILE_NAME}"
```

Cada archivo se guarda en `data/` junto al dataset base — `data/` está en
`.gitignore`, así que estos archivos no se versionan, pero quedan en
disco para volver a subirlos sin regenerarlos. El nombre en S3 lleva el
mismo timestamp que el archivo local — no `orders.csv` fijo: el Glue Job
lee todos los archivos bajo `bronze/orders/` en una sola pasada, así que
un nombre fijo se sobrescribiría silenciosamente en cada corrida. El
timestamp tiene resolución de microsegundos precisamente para que dos
corridas separadas por menos de un segundo (típico al re-ejecutar rápido)
nunca colisionen; si de todos modos el archivo de salida ya existiera, el
script falla con `FileExistsError` en vez de sobrescribirlo
silenciosamente.

`tests/aws/test_datalake_e2e.py` depende de un `data/orders.csv` fijo y
determinista (seed 42, duplicados siempre en `ORD-0001`/`ORD-0007`). Para
(re)generar exactamente ese archivo, usa `--fixed` en vez de dejar el
default:

```bash
uv run python scripts/generate_orders_dataset.py --fixed
```

> **¿Vas a subir este dataset adicional después de ya haber corrido el
> pipeline al menos una vez?** El Glue Job creará particiones nuevas en
> `gold/orders/` (por fecha de procesamiento) que Athena no verá hasta que
> el catálogo se actualice. Sigue el resto de esta guía normalmente y,
> antes de consultar en la sección 4, revisa
> [reparar_particiones_athena.md](reparar_particiones_athena.md).

## 2. Ejecutar el Glue Job

### Consola

1. Abre AWS Glue → **Jobs**.
2. Selecciona el job (`glue_job_name`).
3. Clic en **Run**.
4. Ve a la pestaña **Runs** y observa el estado (`Running` →
   `Succeeded`/`Failed`). Un run típico tarda 2-5 minutos (incluye cold
   start de los workers Spark).
5. Si falla, abre **Logs** (CloudWatch) desde la misma pestaña —
   apuntan al log group `log_group_name`.

### CLI

```bash
JOB_NAME=$(cd infra && terraform output -raw glue_job_name)

# Disparar el run
RUN_ID=$(aws glue start-job-run --job-name "$JOB_NAME" --query 'JobRunId' --output text)
echo "Run ID: $RUN_ID"

# Ver estado (repetir hasta ver SUCCEEDED/FAILED)
aws glue get-job-run --job-name "$JOB_NAME" --run-id "$RUN_ID" --query 'JobRun.JobRunState' --output text
```

### Verificar el output en S3

```bash
aws s3 ls "s3://$BUCKET/silver/orders/" --recursive
aws s3 ls "s3://$BUCKET/gold/orders/" --recursive
```

Debes ver archivos `.parquet` en ambos prefijos, y en `gold/orders/` una
estructura de carpetas `year=.../month=.../day=.../` (partición
Hive-style).

## 3. Ejecutar los Crawlers (Silver y Gold por separado)

Silver y Gold usan **dos crawlers independientes** (no uno solo) para que
las tablas resultantes tengan nombres deterministas (`silver_orders`,
`gold_orders`) — ver la nota de diseño en
[despliegue_infra_terraform.md](despliegue_infra_terraform.md#insight--un-solo-crawler-con-dos-prefijos-produce-nombres-de-tabla-impredecibles).

### Consola

1. Abre AWS Glue → **Crawlers**.
2. Ejecuta `glue_silver_crawler_name`. Espera a que su estado vuelva a
   `Ready` (columna **Last run** debe decir `Succeeded`).
3. Ejecuta `glue_gold_crawler_name` de la misma forma.
4. Ve a **Databases** → tu database (`glue_database_name`) → **Tables** y
   confirma que existen `silver_orders` y `gold_orders`.

### CLI

```bash
SILVER_CRAWLER=$(cd infra && terraform output -raw glue_silver_crawler_name)
GOLD_CRAWLER=$(cd infra && terraform output -raw glue_gold_crawler_name)

aws glue start-crawler --name "$SILVER_CRAWLER"
# Poll hasta que vuelva a READY:
aws glue get-crawler --name "$SILVER_CRAWLER" --query 'Crawler.State' --output text

aws glue start-crawler --name "$GOLD_CRAWLER"
aws glue get-crawler --name "$GOLD_CRAWLER" --query 'Crawler.State' --output text

# Confirmar que las tablas quedaron catalogadas
DB=$(cd infra && terraform output -raw glue_database_name)
aws glue get-tables --database-name "$DB" --query 'TableList[*].Name' --output table
```

Debes ver exactamente `silver_orders` y `gold_orders` — no `orders` ni
sufijos con hash (si ves eso, el crawler viejo de una sola pasada sigue
activo; revisa que `terraform apply` haya aplicado el cambio a dos
crawlers).

## 4. Consultar con Athena

### Consola

1. Abre Athena → **Query editor**.
2. En **Data source**: `AwsDataCatalog`. En **Database**:
   `glue_database_name`. En **Workgroup** (arriba a la derecha):
   `athena_workgroup_name`.
3. Pega y ejecuta las queries de [src/queries/](../src/queries/):
   - `01_bronze.sql`
   - `02_silver.sql`
   - `03_gold.sql`

### CLI

```bash
WORKGROUP=$(cd infra && terraform output -raw athena_workgroup_name)
DB=$(cd infra && terraform output -raw glue_database_name)

QUERY_ID=$(aws athena start-query-execution \
  --query-string "SELECT COUNT(*) FROM silver_orders" \
  --query-execution-context "Database=$DB" \
  --work-group "$WORKGROUP" \
  --query 'QueryExecutionId' --output text)

# Esperar a que termine
aws athena get-query-execution --query-execution-id "$QUERY_ID" --query 'QueryExecution.Status.State' --output text

# Leer el resultado
aws athena get-query-results --query-execution-id "$QUERY_ID"
```

### Qué validar

- `silver_orders` tiene **menos filas** que `data/orders.csv` (42): la
  limpieza descartó `amount` inválido/vacío y la deduplicación por
  `order_id` eliminó los 2 duplicados intencionales
  (`ORD-0001`, `ORD-0007`).
- Ninguna fila de `silver_orders` tiene `order_id` duplicado ni `amount
  <= 0`.
- `gold_orders` reconcilia: la suma de `orders` por ciudad debe igualar el
  conteo total de `silver_orders`.
- El filtro por partición (`WHERE year = '2026' AND month = '9'`, con
  **comillas** — ver nota abajo) trae menos datos que
  `SELECT * FROM gold_orders` sin filtro: eso es partition pruning.

### Nota: las particiones son `string`, no `int`

El crawler cataloga las columnas de partición Hive-style (`year`,
`month`, `day`) como **`string`** por defecto. Si filtras con
`WHERE year = 2026` (sin comillas) obtendrás:

```
TYPE_MISMATCH: Cannot apply operator: varchar = integer
```

Usa siempre `WHERE year = '2026'` con comillas, tal como está en
`src/queries/03_gold.sql`.

### Si corriste el pipeline más de una vez (particiones nuevas)

Cada corrida adicional del Glue Job agrega una partición nueva a
`gold/orders/` (fecha de procesamiento distinta). Si después de una
segunda corrida una query filtrando por esa fecha nueva devuelve cero
filas — aunque el crawler ya se ejecutó antes —, repite el Gold crawler o
usa `MSCK REPAIR TABLE gold_orders` desde Athena; ver
[reparar_particiones_athena.md](reparar_particiones_athena.md) para el
comando exacto (CLI y consola).

## 5. Prueba automatizada equivalente

Todos los pasos anteriores están automatizados como una carga real (no un
smoke test) en
[tests/aws/test_datalake_e2e.py](../tests/aws/test_datalake_e2e.py), que
ejecuta exactamente esta misma secuencia contra AWS real y valida los
mismos criterios de la sección 4:

```bash
set -a
source .env.credentials
set +a
uv run python -m pytest tests/aws/test_datalake_e2e.py -m cloud -v -s
```

Tarda ~4-6 minutos y tiene costo real (Glue DPU-hours, datos escaneados
por Athena). Útil para confirmar rápido que un cambio en
`src/glue/transform.py` o en `infra/modules/glue/main.tf` no rompió el
pipeline, sin repetir los pasos manuales de consola.

## Nota sobre el disparo automático (fuera de alcance de este lab)

Este pipeline se ejecuta a demanda, no por evento, a propósito: el
objetivo pedagógico de la sesión es observar cada paso (Job, Crawler,
Athena) por separado en la consola, no una tubería opaca de punta a
punta.

El patrón estándar para disparar el Glue Job automáticamente cuando llega
un archivo nuevo a `bronze/orders/` es:

```text
S3 (PutObject) → EventBridge (notificación nativa del bucket)
              → EventBridge Rule (filtra por prefijo)
              → AWS Glue Trigger (type = EVENT)
              → Glue Job
```

Esto se puede construir **sin Lambda**, usando el recurso nativo
`aws_glue_trigger` con `type = "EVENT"` más una regla de EventBridge —
Lambda solo sería necesaria si se quisiera algo de lógica de validación
antes de disparar el job. Se deja fuera de esta infraestructura porque
Lambda (y EventBridge en profundidad) aún no se han cubierto en el curso;
es un candidato natural para una sesión posterior sobre automatización.
