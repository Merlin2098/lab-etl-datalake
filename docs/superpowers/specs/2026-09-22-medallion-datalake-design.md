# Diseño — Data Lake Medallion (Bronze/Silver/Gold) en AWS con Terraform

**Fecha:** 2026-09-22
**Estado:** Implementado
**Basado en:** `docs/sesion_04_laboratorio_challenges.md`

> Nota post-implementación: `glue/` y `queries/` se movieron a
> `src/glue/` y `src/queries/` para mantener todo el código de la
> aplicación bajo `src/`. El resto del contenido original de `src/`
> (job de ejemplo genérico: `config/`, `contracts/`, `jobs/`,
> `transformations/`) fue eliminado a pedido explícito del usuario.
>
> Nota post-implementación 2: se eliminó el bucket `aws_s3_bucket.artifacts`
> (y sus recursos asociados: versioning, encryption, public access block,
> `aws_s3_object.artifact_bundle`, la policy `artifact_access`, y las
> variables/outputs correspondientes) de `infra/main.tf`. Ese bucket era un
> patrón genérico heredado del template para desplegar un `.zip` de código
> (vía `scripts/package.py`), sin ningún consumidor en el flujo del data
> lake — bloqueaba `terraform plan` porque exigía que el `.zip` local ya
> existiera (`filemd5()` sobre un archivo inexistente). El código de Glue
> se sube al bucket `data_lake` (`s3_datalake.tf`,
> `aws_s3_object.glue_transform_script`), no a un bucket de artifacts
> separado.
>
> Nota post-implementación 3: `apply` falló dos veces en
> `aws_lakeformation_permissions.data_job_execution_location` con
> `AccessDeniedException: Resource does not exist or requester is not
> authorized`. El primer intento de fix (`time_sleep` de 30s entre
> `aws_lakeformation_resource` y los `aws_lakeformation_permissions`,
> ver `lakeformation.tf`) no resolvió el segundo fallo — la causa raíz no
> era propagación, sino que **ningún principal estaba registrado como Data
> Lake Administrator** en la cuenta: Lake Formation exige al menos un
> admin registrado antes de aceptar cualquier `GrantPermissions`, sin
> importar cuánto se espere. Se agregó
> `aws_lakeformation_data_lake_settings.this` con
> `admins = [data.aws_caller_identity.current.arn]` (la identidad que
> ejecuta `terraform apply`), con `aws_lakeformation_resource.data_lake`
> dependiendo de él. El `time_sleep` se mantiene porque ambos problemas
> son reales y no mutuamente excluyentes. Nota: `aws_caller_identity.arn`
> solo es válido como admin si el principal es un usuario o rol IAM
> directo — si en el futuro se usa un rol asumido vía STS, se debe
> registrar el ARN del rol, no el del assumed-role de la sesión.
>
> Nota post-implementación 4: se generó `tests/aws/test_datalake_e2e.py`
> (reemplaza `test_datalake_infra.py`, eliminado) — un test de carga real,
> no un smoke test: sube `data/orders.csv` a Bronze, ejecuta el Glue Job
> real, ejecuta los Crawlers reales, y valida con queries Athena reales
> que Silver deduplicó/limpió correctamente y que Gold reconcilia con
> Silver. La primera corrida E2E expuso un bug real de diseño en
> `glue.tf`: `aws_glue_crawler.silver_gold_crawler` usaba un único crawler
> con dos `s3_target` (`silver/orders/`, `gold/orders/`). Como ambas rutas
> terminan en el mismo último segmento de path (`orders/`), Glue catalogó
> la primera como tabla `orders` y, al chocar el nombre con la segunda,
> le agregó un sufijo hash aleatorio
> (`orders_a3ff0d60bfd57bd73ce9c9c262ad5729`) en vez de un nombre legible
> y estable. Se reemplazó por dos crawlers separados,
> `aws_glue_crawler.silver_crawler` y `aws_glue_crawler.gold_crawler`,
> cada uno con `table_prefix` (`silver_`, `gold_`) para garantizar nombres
> deterministas (`silver_orders`, `gold_orders`) en cada corrida. El
> output `glue_crawler_name` se dividió en `glue_silver_crawler_name` y
> `glue_gold_crawler_name`. El Glue Job y el primer crawler ya habían sido
> validados exitosamente en AWS real antes de este fix (run
> `jr_8b8d421a7fe0f4a6db8ffa8fd4d6621944d3d3167b141e560b85db9d5299fe05`,
> `SUCCEEDED`); el fallo fue únicamente de nomenclatura del catálogo, no
> del pipeline de datos en sí.
>
> Nota post-implementación 5: se agregó soporte para múltiples orígenes
> con el mismo esquema de `orders` (ej. distintas tiendas/canales) vía una
> partición Hive-style `source=<nombre>/` bajo `bronze/orders/`, en lugar
> de duplicar Job/Crawlers por origen. `src/glue/transform.py` ahora lee
> Bronze con `basePath` explícito (para que Spark reconozca `source=` como
> columna, no como segmento literal del path), agrega un fallback
> `source="default"` cuando no hay partición (compatibilidad con el
> flujo anterior, que subía el CSV directo a `bronze/orders/orders.csv`),
> y particiona tanto Silver (`partitionBy("source")`) como Gold
> (`partitionBy("source", "year", "month", "day")`, con `source` también
> agregado al `groupBy`). No se tocó `infra/`: el mismo Job y los mismos
> dos Crawlers siguen sirviendo, porque la partición vive dentro de los
> prefijos ya existentes. Un dataset con columnas distintas (otra entidad
> de negocio, no otro origen del mismo esquema) sigue necesitando su
> propio script/Job — esto no lo resuelve. `tests/aws/test_datalake_e2e.py`
> se actualizó para subir bajo `source=lab/` y validar la nueva partición
> en el output de Gold; `src/queries/03_gold.sql` y
> `docs/prueba_manual_pipeline.md` se actualizaron con el nuevo patrón.
>
> Nota post-implementación 6: al validar el cambio anterior contra AWS
> real aparecieron dos problemas adicionales, ninguno de diseño del
> pipeline en sí:
>
> 1. **Archivo huérfano en Bronze.** Quedaba `bronze/orders/orders.csv`
>    (de una corrida previa a la partición `source=`) junto al nuevo
>    `bronze/orders/source=lab/orders.csv`. Con `basePath` apuntando al
>    prefijo padre, Spark leyó ambos; el archivo sin partición produce
>    `source = NULL` para esas filas en vez de un error. Se agregó
>    `F.coalesce(F.col("source"), F.lit("default"))` en
>    `src/glue/transform.py` para que una mezcla de archivos
>    particionados/no particionados nunca deje `source` nulo — no alcanza
>    con limpiar los datos una vez, el código debe ser robusto ante esa
>    mezcla porque es fácil de reproducir por accidente.
> 2. **Migración de esquema de particiones sobre una tabla ya
>    catalogada.** Con Bronze limpio, el Glue Job sí escribió Gold
>    particionado correctamente por `source/year/month/day`, pero el Gold
>    Crawler falló: `InvalidInputException: Trying to change
>    partitionColumn name from: year to new partitionColumn name: source.
>    Change of partitionColumn names is not allowed.` La tabla
>    `gold_orders` ya existía en el catálogo con el esquema de partición
>    anterior (`year, month, day`); Glue no permite que un crawler cambie
>    el nombre/orden de las columnas de partición de una tabla existente.
>    Se resolvió borrando `gold_orders` y `silver_orders` del catálogo
>    (`aws glue delete-table`) antes de re-crawlear — esto es solo
>    metadata, no borra los datos en S3. De paso se limpiaron también
>    `orders` y `orders_a3ff0d60bfd57bd73ce9c9c262ad5729`, tablas
>    huérfanas del incidente del crawler único (nota 4) que nunca se
>    habían borrado. Documentado como procedimiento en
>    `docs/despliegue_infra_terraform.md` — cualquier cambio futuro al
>    esquema de particiones de Silver/Gold requiere este mismo paso
>    manual, Terraform no lo gestiona (el schema de la tabla lo escribe el
>    Crawler, no `aws_glue_catalog_database`).
>
> Tras aplicar ambos fixes y limpiar el catálogo, el pipeline completo con
> soporte multi-source se validó de punta a punta contra AWS real:
> `tests/aws/test_datalake_e2e.py::test_pipeline_end_to_end PASSED` (310s).
>
> Nota post-implementación 7: se agregó la flag `--timestamped` a
> `scripts/generate_orders_dataset.py` para generar un dataset distinto en
> cada corrida (útil para subir varios archivos al pipeline, cada uno
> como su propio `source=`). Con `--timestamped`, escribe a
> `data/orders-<timestamp>.csv` usando el timestamp como seed
> automáticamente, sin que el usuario tenga que calcular ni un seed ni
> una ruta a mano.
>
> Nota post-implementación 8: se invirtió el default de la flag anterior.
> El pedido explícito era que ejecutar el script sin ningún argumento
> (incluyendo "Run Python File" desde un IDE, sin pasar por la CLI)
> genere directamente un dataset con timestamp — no el fijo. Se reemplazó
> `--timestamped` por `--fixed` con el sentido invertido: sin argumentos,
> el script ahora escribe `data/orders-<timestamp>.csv` (antes requería
> `--timestamped` explícito); `--fixed` regenera el `data/orders.csv`
> determinista con seed 42 que usa `tests/aws/test_datalake_e2e.py`
> (antes era el comportamiento por defecto). Se verificó que
> `--fixed` sigue produciendo exactamente las mismas 42 filas y los
> mismos duplicados (`ORD-0001`, `ORD-0007`) que antes de este cambio —
> el test E2E no se ve afectado, solo cambia qué hace falta pasar
> explícitamente para regenerar ese archivo.
>
> Nota post-implementación 9: al validar el cambio anterior corriendo el
> script varias veces en sucesión rápida, se encontró que el timestamp
> `%Y%m%d%H%M%S` (resolución de segundo) colisionaba entre corridas
> separadas por menos de un segundo — típico al re-ejecutar rápido desde
> un IDE. La segunda corrida sobrescribía silenciosamente el archivo de
> la primera, exactamente el problema que este mecanismo debía evitar
> (confirmado reproduciendo la colisión: dos `Wrote 42 rows ... to
> data/orders-20260923192821.csv` con el mismo nombre, el segundo
> pisando al primero). Se cambió el formato a
> `%Y%m%d%H%M%S%f` (microsegundos) y se agregó una salvaguarda explícita:
> si el archivo de salida ya existe, el script falla con
> `FileExistsError` en vez de sobrescribir. Verificado corriendo el
> script 5 veces seguidas sin pausa: 5 archivos con nombres y contenido
> (hash MD5) distintos, sin colisiones. `--fixed` no usa timestamp
> (siempre `data/orders.csv`), así que no le aplica esta salvaguarda —
> ahí sí se espera sobrescribir el archivo fijo en cada regeneración.

## Contexto

El repo ya contiene un stack Terraform genérico (`infra/main.tf`) con un
bucket de artifacts, un rol IAM de ejecución para jobs (`data_job_execution`)
y un log group. No existe infraestructura de Data Lake: no hay bucket de
datos, Glue Database/Job/Crawler, Athena ni Lake Formation.

El laboratorio de la sesión 4 pide construir esa infraestructura con
Terraform y ejecutar un ETL Bronze → Silver → Gold sobre un dataset de
`orders`, para luego consultarlo con Athena y observar governance con Lake
Formation.

También existe un patrón de "job simple" (`job_config.yaml` +
`orders_to_curated.sql` + `orders_contract.json`) pensado para un dataset
curated de una sola capa. Ese patrón no encaja con un flujo medallion
multi-capa y se deja intacto como ejemplo independiente; el flujo nuevo no
lo reutiliza ni lo modifica.

## Alcance de esta tarea

Se entrega el **código** (Terraform + script PySpark + queries SQL +
dataset sintético) listo para que el usuario ejecute manualmente
`terraform init/plan/apply`, suba el dataset, corra el Glue Job y las
queries en Athena. Esta tarea **no** ejecuta `terraform apply`/`destroy` ni
corre nada contra AWS — eso queda para el usuario, según los approval
boundaries de `AGENTS.md`.

## Arquitectura

```text
data/orders.csv (sintético)
        │
        ▼ (subida manual por el usuario)
S3: <bucket>/bronze/orders/
        │
        ▼
   AWS Glue Job (PySpark, glue/transform.py)
        │
   ┌────┴────┐
   ▼         ▼
Silver      Gold
(parquet)  (parquet, particionado year/month/day)
   │         │
   └────┬────┘
        ▼
  Glue Crawler → Glue Data Catalog (datalake_db)
        │
        ▼
  Lake Formation (registro del bucket + permisos sobre datalake_db)
        │
        ▼
     Athena (workgroup dedicado, queries en queries/)
```

## Componentes Terraform (nuevos archivos en `infra/`)

Los archivos existentes (`main.tf`, `variables.tf`, `outputs.tf`,
`providers.tf`) se mantienen; solo se agregan variables/outputs nuevos
donde haga falta. Se agregan:

### `infra/s3_datalake.tf`

- `aws_s3_bucket` `data_lake`: bucket privado nuevo, nombrado con el mismo
  `local.name_prefix` que ya usa `main.tf` (ej.
  `${local.name_prefix}-${account_id}-datalake`).
- `aws_s3_bucket_public_access_block`, `aws_s3_bucket_server_side_encryption_configuration`:
  mismos defaults de seguridad que el bucket de artifacts.
- Sin versioning por defecto (regla de AGENTS.md: no habilitar salvo pedido
  explícito).
- No se crean objetos de prefijo "carpeta" — Bronze/Silver/Gold son rutas
  lógicas (`bronze/orders/`, `silver/orders/`, `gold/orders/`) que el Glue
  Job crea al escribir. El prefijo `athena-results/` en el mismo bucket
  sirve como destino de resultados de Athena (evita crear un segundo
  bucket).

### `infra/glue.tf`

- `aws_glue_catalog_database` `datalake_db`: una sola database para las 3
  tablas (`bronze_orders`, `silver_orders`, `gold_orders`), más simple que
  3 databases separadas.
- `aws_glue_job` `orders_medallion`: PySpark (Glue 4.0), script apuntando a
  `glue/transform.py` subido a un prefijo `scripts/` del bucket data lake,
  usa `aws_iam_role.data_job_execution` (rol existente, extendido — ver
  IAM abajo). Parámetros del job (`--BRONZE_PATH`, `--SILVER_PATH`,
  `--GOLD_PATH`) pasados vía `default_arguments`, no hardcodeados en el
  script. `--job-bookmark-option: job-bookmark-enable`.
- `aws_glue_crawler` `silver_gold_crawler`: apunta a los prefijos
  Silver y Gold del bucket, target de `datalake_db`. Se ejecuta después del
  Glue Job (manual, vía consola, según el flujo del lab).
- CloudWatch log group ya existe (`aws_cloudwatch_log_group.data_jobs` en
  `main.tf`); el Glue Job reusa ese log group.

### `infra/athena.tf`

- `aws_athena_workgroup` `datalake`: `result_configuration.output_location`
  apunta a `s3://<data_lake_bucket>/athena-results/`. Enforce workgroup
  configuration = true (evita que las queries ignoren esta config).

### `infra/lakeformation.tf`

- `aws_lakeformation_resource`: registra el bucket data lake en Lake
  Formation.
- `aws_lakeformation_permissions`: otorga al rol `data_job_execution`
  permisos `ALL` sobre `datalake_db` (las 3 tablas). No se crea un rol
  Analyst separado en código — la restricción Analyst→Gold se documenta
  conceptualmente en el propio spec/comentarios de este archivo, para que
  el usuario la reproduzca manualmente en consola si quiere completar esa
  parte del lab.

### IAM (extensión, no archivo nuevo)

- Se agrega un `aws_iam_role_policy` adicional (en `main.tf` o
  `glue.tf`, junto al recurso que conoce el ARN del bucket data lake —
  regla de colocación cruzada de AGENTS.md) dando a
  `data_job_execution` `s3:GetObject/PutObject/ListBucket` sobre el bucket
  data lake y sus prefijos.

### Variables/outputs nuevos

- Variables: nombre del bucket data lake (por sufijo, igual patrón que
  `artifact_bucket_suffix`), nombre de la Glue database, nombre del Glue
  Job/Crawler/Workgroup — todos con defaults razonables, sin hardcodear
  nombres de ambiente.
- Outputs: `data_lake_bucket_name`, `glue_database_name`, `glue_job_name`,
  `athena_workgroup_name` (para que el usuario los use al explorar por
  consola).

## Glue Job — `glue/transform.py`

Un solo script PySpark (Glue ETL job) con dos transformaciones
secuenciales, más simple que 3 jobs separados:

**Bronze → Silver:**
- Lee CSV crudo desde `bronze/orders/`.
- Castea tipos: `order_date` → date, `amount` → decimal.
- Descarta filas con `order_id` o `amount` nulos/inválidos.
- Deduplica por `order_id` (quedándose con el registro más reciente si hay
  duplicados).
- Normaliza `status` (trim + uppercase) y nombres de columnas.
- Escribe Parquet a `silver/orders/`.

**Silver → Gold:**
- Agrupa por `city` y por fecha derivada de `order_date`.
- Calcula `orders` (count), `revenue` (sum de `amount`),
  `average_order_value`.
- Escribe Parquet particionado por `year/month/day` a `gold/orders/`.

Las rutas S3 se reciben como job parameters (`--BRONZE_PATH`,
`--SILVER_PATH`, `--GOLD_PATH`), no hardcodeadas — cumple con
"configuration over hardcoding" de AGENTS.md.

## Dataset sintético — `data/orders.csv`

~40 filas con columnas `order_id, customer_id, order_date, status, amount,
city, carrier`. Incluye intencionalmente 2-3 `order_id` duplicados, algún
`amount` vacío/inválido y `status` con casing inconsistente, para que el
paso Silver tenga registros reales que limpiar/deduplicar.

## Queries de referencia — `queries/`

- `01_bronze.sql`: `SELECT * FROM bronze_orders LIMIT 10` (o silver, según
  la sección del lab).
- `02_silver.sql`: validación de registros + `COUNT(*)`.
- `03_gold.sql`: agregación por ciudad + comparación con/sin filtro de
  partición (para ilustrar partition pruning, Challenge de Parte 7/8).

Estas queries son para ejecutar manualmente en el editor de Athena, no se
invocan desde Terraform ni desde el Glue Job.

## Tests

Se genera `tests/aws/test_datalake_infra.py` (boto3), siguiendo el
guardrail de AGENTS.md de generar validaciones cuando se despliega
infraestructura AWS: valida (post-deploy, no bloqueante para el diseño)
que el bucket data lake, la Glue database y el Athena workgroup existen y
tienen la configuración esperada (encryption, public access block).

## Fuera de alcance

- No se automatiza la ejecución del Glue Job, Crawler ni las queries de
  Athena — son pasos manuales del lab (consola/CLI), según pide el propio
  documento del laboratorio.
- No se crea un rol IAM "Analyst" independiente ni se configuran permisos
  Lake Formation diferenciados por rol — se registra el bucket y se dan
  permisos al rol Data Engineer/Glue únicamente; la separación Analyst se
  deja como ejercicio manual en consola.
- No se implementa un conector de Athena Federated Query real (Parte 10
  del lab es conceptual, según el propio documento).
- `terraform apply`/`destroy` no se ejecutan como parte de esta tarea.
