# Reparar particiones tras subir un nuevo dataset (MSCK REPAIR TABLE)

Esta guía aplica cuando **ya corriste el pipeline al menos una vez** (el
Glue Job creó `gold_orders` con sus particiones `year=.../month=.../day=...`,
y los crawlers ya catalogaron la tabla) y ahora quieres subir un dataset
adicional sin repetir todo el despliegue.

## El problema

`gold/orders/` está particionado Hive-style por fecha de procesamiento
(`year`, `month`, `day`). Cada vez que el Glue Job corre un día distinto,
escribe una carpeta de partición **nueva** en S3
(`gold/orders/year=2026/month=9/day=24/`, por ejemplo), pero el Glue Data
Catalog no se entera solo — Athena seguirá viendo únicamente las
particiones que ya conocía hasta que algo actualice el catálogo.

Sin ese paso, una query como:

```sql
SELECT * FROM gold_orders WHERE year = '2026' AND month = '9' AND day = '24'
```

devuelve **cero filas**, aunque los archivos `.parquet` ya existan en S3 —
la partición existe en el storage pero no en el catálogo.

## Dos formas de resolverlo

### Opción A — Re-ejecutar el Gold crawler (ya documentada)

`glue_gold_crawler_name` vuelve a escanear `gold/orders/` completo y
agrega cualquier partición nueva. Es la vía recomendada en
[prueba_manual_pipeline.md](prueba_manual_pipeline.md#3-ejecutar-los-crawlers-silver-y-gold-por-separado)
y [prueba_manual_consola_aws.md](prueba_manual_consola_aws.md) porque no
requiere saber SQL de DDL y reutiliza el mismo recurso que ya despliega
Terraform.

### Opción B — `MSCK REPAIR TABLE` desde Athena (más rápida, sin crawler)

Si no quieres esperar un run de crawler (1-2 minutos) y solo necesitas que
Athena reconozca las particiones nuevas ya presentes en S3, ejecuta
directamente en el **Query editor** de Athena (o vía CLI, ver abajo):

```sql
MSCK REPAIR TABLE gold_orders;
```

Esto le pide a Athena que escanee el prefijo S3 de la tabla, detecte
carpetas con el patrón `clave=valor` que no estén en el catálogo, y las
registre como particiones nuevas — sin tocar los datos, solo metadata.

> **Solo aplica a `gold_orders`.** `silver_orders` no está particionada
> (es una sola carpeta plana `silver/orders/`), así que no necesita
> reparación de particiones — un nuevo archivo ahí ya es visible para
> Athena en la siguiente query, sin ningún paso adicional.

## Comando CLI

```bash
WORKGROUP=$(cd infra && terraform output -raw athena_workgroup_name)
DB=$(cd infra && terraform output -raw glue_database_name)

QUERY_ID=$(aws athena start-query-execution \
  --query-string "MSCK REPAIR TABLE gold_orders" \
  --query-execution-context "Database=$DB" \
  --work-group "$WORKGROUP" \
  --query 'QueryExecutionId' --output text)

# Esperar a que termine (debe llegar a SUCCEEDED)
aws athena get-query-execution --query-execution-id "$QUERY_ID" --query 'QueryExecution.Status.State' --output text

# Ver qué particiones quedaron registradas
aws athena get-query-results --query-execution-id "$QUERY_ID"
```

Si el estado es `FAILED`, revisa `QueryExecution.Status.StateChangeReason`
con:

```bash
aws athena get-query-execution --query-execution-id "$QUERY_ID" --query 'QueryExecution.Status.StateChangeReason' --output text
```

## Verificar que la partición nueva quedó registrada

```bash
aws athena start-query-execution \
  --query-string "SHOW PARTITIONS gold_orders" \
  --query-execution-context "Database=$DB" \
  --work-group "$WORKGROUP" \
  --query 'QueryExecutionId' --output text
```

Consulta el resultado con `aws athena get-query-results` como en el paso
anterior — debe listar la carpeta `year=.../month=.../day=.../` que
acabas de subir, junto con las que ya existían.

## Cuándo usar cada opción

| Situación | Usa |
|---|---|
| Quieres seguir el flujo pedagógico del lab, viendo el Crawler correr en consola | Re-ejecutar `glue_gold_crawler_name` (Opción A) |
| Ya sabes que solo cambió la partición, quieres la vía más rápida sin abrir Glue | `MSCK REPAIR TABLE` desde Athena (Opción B) |
| Subiste un archivo a `silver/orders/` únicamente | Ninguna — Silver no está particionada, no hace falta reparar nada |
