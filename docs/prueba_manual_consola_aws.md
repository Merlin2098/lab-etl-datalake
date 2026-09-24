# Guía de prueba manual — Solo consola de AWS (sin CLI)

Esta guía ejecuta y valida el pipeline Bronze → Silver → Gold
**exclusivamente desde la consola web de AWS** — ningún paso usa
terminal, AWS CLI, ni `aws s3`/`aws glue`/`aws athena`. Útil para
explorar el laboratorio de forma puramente visual, o para quien no tenga
la CLI configurada.

Requiere que la infraestructura ya esté desplegada (ver
[despliegue_infra_terraform.md](despliegue_infra_terraform.md) — ese paso
sí usa Terraform desde terminal, es la única excepción, ya que
`terraform apply` no tiene equivalente en consola).

Para saber los nombres exactos de tus recursos (bucket, Job, Crawlers,
etc.), pide a quien desplegó la infraestructura los valores de
`terraform output`, o revisa el archivo `infra/terraform.tfvars` para
identificar el prefijo (`project_name`, ej.
`lab-etl`) — con eso puedes ubicar cada recurso por nombre en
la consola sin ejecutar ningún comando.

## 1. Ubicar el bucket del data lake

1. Entra a la consola de AWS y busca el servicio **S3**.
2. En la lista de buckets, busca uno con el patrón
   `<project_name>-<account-id>-<data_lake_bucket_suffix>`
   (por ejemplo `lab-etl-123456789012-datalake`).
3. Ábrelo. Verás (o se crearán al ejecutar el pipeline) los siguientes
   prefijos (carpetas):
   - `bronze/orders/` — datos crudos.
   - `silver/orders/` — datos limpios (Parquet).
   - `gold/orders/` — datos agregados (Parquet, particionado).
   - `scripts/` — el script PySpark del Glue Job.
   - `athena-results/` — resultados de las queries de Athena.

## 2. Subir el dataset a Bronze

El dataset se sube directo dentro de `bronze/orders/`, sin ninguna
subcarpeta adicional. Si no tienes un dataset a mano, usa el archivo
`data/orders.csv` de este repositorio (descárgalo a tu computadora si
trabajas solo desde el navegador).

1. Dentro del bucket, entra a la carpeta `bronze/orders/`.
2. Haz clic en **Upload** (Cargar).
3. Arrastra o selecciona tu archivo CSV (ej. `orders.csv`).
4. Haz clic en **Upload** para confirmar la subida.
5. Verifica que el archivo aparece listado dentro de `bronze/orders/`.

## 3. Ejecutar el Glue Job

1. Busca el servicio **AWS Glue** en la consola.
2. En el menú lateral, bajo **Data Integration and ETL**, elige **Jobs**.
3. Busca el Job con el patrón `<project_name>-orders`
   (ej. `lab-etl-orders`) y haz clic en su nombre.
4. Arriba a la derecha, haz clic en **Run** (Ejecutar).
5. Ve a la pestaña **Runs** (Ejecuciones) del Job.
6. Observa la fila más reciente: el estado pasa de **Running** a
   **Succeeded** (o **Failed** si algo salió mal). Un run típico tarda
   entre 2 y 5 minutos — incluye el tiempo de arranque de los workers de
   Spark.
7. Si el estado es **Failed**, haz clic en la fila del run y luego en
   **CloudWatch logs** (o **Error logs**) para ver el detalle del error.

### Verificar el resultado en S3

1. Vuelve a **S3** → tu bucket.
2. Entra a `silver/orders/`. Debe haber uno o más archivos con extensión
   `.parquet`.
3. Entra a `gold/orders/`. En vez de archivos sueltos, verás carpetas
   anidadas con el patrón `year=.../month=.../day=.../`, y dentro de la
   última carpeta, el archivo `.parquet` correspondiente. Esa estructura
   de carpetas es la partición del dataset Gold.

## 4. Ejecutar los Crawlers (Silver y luego Gold)

El pipeline usa **dos crawlers separados** — uno para Silver, otro para
Gold — para que las tablas resultantes en el catálogo se llamen siempre
`silver_orders` y `gold_orders` de forma consistente.

1. En la consola de **AWS Glue**, en el menú lateral, bajo **Data
   Catalog**, elige **Crawlers**.
2. Busca el crawler con el patrón
   `<project_name>-silver-crawler` (ej.
   `lab-etl-silver-crawler`).
3. Selecciona su casilla y haz clic en **Run** (Ejecutar).
4. Espera a que la columna **Status** vuelva a **Ready** y la columna
   **Last run** muestre **Succeeded**. Normalmente tarda 1-2 minutos.
5. Repite los pasos 2-4 con el crawler
   `<project_name>-gold-crawler`.

> **¿Vas a subir y procesar un dataset adicional después de ya haber
> corrido el pipeline una vez?** No hace falta ningún paso extra en
> Athena: solo vuelve a ejecutar el Gold crawler
> (`<project_name>-gold-crawler`) como se indicó arriba — el crawler
> detecta y registra automáticamente las particiones nuevas de
> `gold/orders/` en el catálogo. Repite este paso 4 completo (Silver y
> Gold) cada vez que corras el Glue Job de nuevo.

### Verificar las tablas en el catálogo

1. En el menú lateral de Glue, bajo **Data Catalog**, elige **Databases**.
2. Abre la base de datos con el patrón `<project_name>_datalake_db`
   (ej. `lab_etl_datalake_db`) — con guiones bajos, no guiones.
3. Haz clic en **Tables** (o en el contador de tablas de esa database).
4. Debes ver exactamente dos tablas: `silver_orders` y `gold_orders`.
   - Si en vez de eso ves una tabla llamada `orders` o con un sufijo
     extraño tipo `orders_a3ff0d60...`, significa que se usó un crawler
     antiguo de una sola pasada — vuelve a correr los dos crawlers por
     separado como se indicó arriba.
5. Haz clic en `gold_orders` y revisa la sección **Partitions** — debe
   listar particiones con el patrón `year=.../month=.../day=...`.

## 5. Consultar con Athena

1. Busca el servicio **Amazon Athena** en la consola.
2. Si es la primera vez que usas Athena en la cuenta, puede pedirte
   configurar una ubicación de resultados de consulta — esto ya está
   preconfigurado por Terraform (workgroup con el patrón
   `<project_name>-datalake`), así que solo debes
   seleccionarlo (ver siguiente paso).
3. Entra a **Query editor** (Editor de consultas).
4. En el panel superior derecho, en el selector **Workgroup**, elige el
   workgroup con el patrón `<project_name>-datalake`.
5. En el panel izquierdo:
   - **Data source**: `AwsDataCatalog`.
   - **Database**: la base `<project_name>_datalake_db`.
6. En el editor de consultas (panel central), escribe y ejecuta (botón
   **Run** o **Ejecutar**) cada una de las siguientes consultas, una a la
   vez:

### Consulta 1 — Contar filas en Silver

```sql
SELECT COUNT(*) AS total_orders
FROM silver_orders;
```

El resultado debe ser **menor** al número de filas de tu CSV original
(por ejemplo, si subiste 42 filas y hay 2 duplicados con `amount`
inválido, esperarías bastante menos de 42) — confirma que la limpieza y
deduplicación del Glue Job realmente se ejecutó, no un simple copiado.

### Consulta 2 — Verificar que no quedan duplicados

```sql
SELECT order_id, COUNT(*) AS occurrences
FROM silver_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Este resultado **debe salir vacío** (0 filas). Si aparece alguna fila,
algo falló en la deduplicación.

### Consulta 3 — Agregación por ciudad en Gold

```sql
SELECT city, SUM(orders) AS orders, SUM(revenue) AS revenue
FROM gold_orders
GROUP BY city
ORDER BY revenue DESC;
```

Debes ver una fila por `city`, con totales de pedidos e ingresos.

### Consulta 4 — Partition pruning (filtrar por partición)

```sql
SELECT city, revenue
FROM gold_orders
WHERE year = '2026'
  AND month = '9'
  AND day = '23';
```

**Importante:** `year`, `month` y `day` son columnas de tipo texto
(`string`), aunque parezcan números — deben ir entre comillas simples. Si
las escribes sin comillas (`WHERE year = 2026`), Athena responde con un
error de tipo:

```
TYPE_MISMATCH: Cannot apply operator: varchar = integer
```

Ajusta los valores de `year`/`month`/`day` según la fecha real de tus
datos (revisa la pestaña **Partitions** de la tabla `gold_orders`, vista
en el paso 4, para saber qué valores existen).

Compara mentalmente esta consulta (que solo lee una partición) contra:

```sql
SELECT *
FROM gold_orders;
```

La segunda consulta escanea **todas** las particiones — en el panel de
resultados de Athena, fíjate en el indicador **Data scanned** (Datos
escaneados) de cada consulta: la que filtra por partición debe reportar
un valor menor. Eso es *partition pruning* en acción.

## 6. Revisar los logs del Glue Job (si algo falla)

1. Ve a **AWS Glue** → **Jobs** → tu Job → pestaña **Runs**.
2. Haz clic en el run que falló.
3. Haz clic en **CloudWatch logs** (o el enlace equivalente al log
   stream).
4. Esto te lleva a **CloudWatch** → **Log groups**, dentro del grupo con
   el patrón `/aws/data-jobs/<project_name>`.
5. Revisa el stream más reciente para ver el traceback completo de
   Python/Spark.

## Checklist final

Al terminar, deberías poder confirmar visualmente, sin usar ningún
comando de terminal:

- [ ] El CSV subido aparece en `bronze/orders/` (S3).
- [ ] El Glue Job terminó en estado **Succeeded** (Glue → Jobs → Runs).
- [ ] Existen archivos `.parquet` en `silver/orders/` y `gold/orders/`
      (S3), y `gold/orders/` tiene subcarpetas de partición.
- [ ] Existen exactamente las tablas `silver_orders` y `gold_orders` en
      el Glue Data Catalog (Glue → Databases → Tables).
- [ ] Las 4 consultas de Athena de la sección 5 devuelven los resultados
      esperados.

## Referencias

- [despliegue_infra_terraform.md](despliegue_infra_terraform.md) —
  despliegue de la infraestructura (requiere Terraform/terminal, es la
  única excepción a "solo consola").
- [sesion_04_laboratorio_challenges.md](sesion_04_laboratorio_challenges.md)
  — enunciado completo del laboratorio.
