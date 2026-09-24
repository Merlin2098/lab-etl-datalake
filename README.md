# Laboratorio ETL Serverless y Data Lake con AWS

Implementación en código (Terraform + PySpark + SQL) del laboratorio de
la sesión 4 del bootcamp de Data Engineering:
[docs/sesion_04_laboratorio_challenges.md](docs/sesion_04_laboratorio_challenges.md).

Construye un Data Lake medallion (**Bronze → Silver → Gold**) sobre datos
de pedidos (`orders`), desplegado con Terraform, procesado con AWS Glue
(PySpark), catalogado con Glue Crawlers, y consultado con Athena.

```text
data/orders.csv (o cualquier CSV con el mismo esquema)
        │
        ▼ (subida manual a S3)
Bronze  s3://<bucket>/bronze/orders/source=<origen>/
        │
        ▼
   AWS Glue Job (PySpark, src/glue/transform.py)
        │
   ┌────┴────┐
   ▼         ▼
Silver      Gold
(parquet,   (parquet, particionado
particionado source/year/month/day)
por source)
   │         │
   └────┬────┘
        ▼
  Glue Crawlers (uno por capa) → Glue Data Catalog
        │
        ▼
     Athena (queries en src/queries/)
```

## Por dónde empezar

Si es tu primera vez en este repo, sigue este orden:

1. **Lee el enunciado del laboratorio**:
   [docs/sesion_04_laboratorio_challenges.md](docs/sesion_04_laboratorio_challenges.md)
   — contiene el caso de negocio, los conceptos (Bronze/Silver/Gold, Glue
   Crawler vs Job, partition pruning, Lake Formation, Athena Federated
   Query) y los challenges que debes poder responder al final.
2. **Despliega la infraestructura**:
   [docs/despliegue_infra_terraform.md](docs/despliegue_infra_terraform.md)
   — paso a paso de `terraform init/plan/apply`, incluyendo los problemas
   reales (eventual consistency de IAM, nombres de tabla del Crawler) que
   se encontraron construyendo este stack y cómo se resolvieron.
3. **Ejecuta el pipeline manualmente**:
   [docs/prueba_manual_pipeline.md](docs/prueba_manual_pipeline.md) —
   sube el dataset, corre el Glue Job, corre los Crawlers, consulta con
   Athena. Cubre consola y AWS CLI para cada paso.
4. **Repite los challenges del laboratorio** contra tu propio despliegue
   para verificar que entiendes cada componente, no solo que "funcionó".

## Qué hay en este repo

| Ruta | Qué es |
|---|---|
| `infra/` | Terraform: S3 (data lake), Glue (database, job, crawlers), Athena (workgroup), IAM, CloudWatch. |
| `src/glue/transform.py` | Script PySpark del Glue Job: limpia y deduplica Bronze → Silver, agrega Silver → Gold. |
| `src/queries/` | Queries SQL de referencia para Athena (`01_bronze.sql`, `02_silver.sql`, `03_gold.sql`). |
| `data/orders.csv` | Dataset sintético de ejemplo (pedidos), con duplicados y valores inválidos a propósito. |
| `scripts/generate_orders_dataset.py` | Por defecto genera un dataset nuevo por corrida (`data/orders-<timestamp>.csv`); `--fixed` regenera el `data/orders.csv` determinista. |
| `tests/aws/test_datalake_e2e.py` | Test de carga real (no un smoke test): ejecuta el pipeline completo contra AWS real y valida los resultados. |
| `docs/` | Guías de despliegue, prueba manual, y el spec de diseño con el historial de decisiones e incidentes reales. |

## El dataset: `orders`

Columnas: `order_id, customer_id, order_date, status, amount, city,
carrier`. El CSV de ejemplo tiene 40 filas base + 2 duplicados
intencionales (mismo `order_id`, fecha posterior — simula un pedido
re-enviado) y algunos `amount` inválidos/vacíos, para que el paso Silver
tenga limpieza real que hacer, no solo un passthrough.

Por defecto, `scripts/generate_orders_dataset.py` genera un dataset
**nuevo en cada corrida** (sin necesidad de pasar ningún argumento —
sirve también al ejecutarlo directo desde el IDE):

```bash
uv run python scripts/generate_orders_dataset.py
# → escribe a data/orders-<timestamp>.csv, listo para subir a su propio source=
```

Para regenerar el `data/orders.csv` **fijo y determinista** que usa el
test E2E (`tests/aws/test_datalake_e2e.py`), usa `--fixed`:

```bash
uv run python scripts/generate_orders_dataset.py --fixed
```

También puedes crear una variante puntual con más filas u otro seed:

```bash
uv run python scripts/generate_orders_dataset.py --rows 100 --seed 7 --out data/orders_grande.csv
```

## Múltiples orígenes con el mismo esquema

El pipeline soporta más de una fuente de datos (ej. distintas tiendas o
canales) siempre que compartan el **mismo esquema** de columnas, mediante
una partición Hive-style `source=<nombre>/` en Bronze:

```bash
aws s3 cp data/orders.csv "s3://<bucket>/bronze/orders/source=tienda_a/orders.csv"
aws s3 cp otro_origen.csv "s3://<bucket>/bronze/orders/source=tienda_b/orders.csv"
```

Un solo Glue Job procesa ambos orígenes en la misma corrida; `source`
queda como columna en Silver y como partición en Gold (`WHERE source =
'tienda_a'`). Si subes el CSV directo a `bronze/orders/orders.csv`, sin
`source=`, el job asigna `source = "default"` automáticamente — no rompe
el flujo simple de un solo origen.

**Un dataset con columnas distintas** (otra entidad de negocio, como
`customers` en vez de otra fuente de `orders`) **no encaja aquí** —
necesitaría su propio script PySpark y su propio Glue Job, no una
partición. Ver el docstring de
[src/glue/transform.py](src/glue/transform.py) para el detalle técnico.

## Probar que todo funciona

Después de desplegar la infraestructura (ver guía de despliegue), puedes
validar el pipeline completo de dos formas:

**Manual, paso a paso** (recomendado para aprender qué hace cada
servicio): sigue
[docs/prueba_manual_pipeline.md](docs/prueba_manual_pipeline.md).

**Automatizado** (más rápido para confirmar que un cambio no rompió
nada):

```bash
set -a
source .env.credentials
set +a
uv run python -m pytest tests/aws/test_datalake_e2e.py -m cloud -v -s
```

Este test sube el dataset real, corre el Glue Job real, corre los
Crawlers reales, y valida con queries Athena reales que Silver deduplicó
correctamente y que Gold reconcilia con Silver — no es un smoke test, es
una ejecución real con costo real (Glue DPU-hours, datos escaneados por
Athena). Tarda ~4-6 minutos.

## Convenciones del proyecto

Este repo sigue el contrato definido en [AGENTS.md](AGENTS.md): Terraform
separado por servicio en `infra/`, SQL separado de Python, configuración
sobre hardcoding, y aprobación explícita antes de cualquier `terraform
apply`/`destroy` real. Para dependencias Python se usa
[`uv`](https://docs.astral.sh/uv/) (`uv sync` para instalar, `uv run`
para ejecutar).

## Historial de diseño e incidentes reales

[docs/superpowers/specs/2026-09-22-medallion-datalake-design.md](docs/superpowers/specs/2026-09-22-medallion-datalake-design.md)
documenta no solo el diseño original, sino los problemas reales que
aparecieron al desplegar contra AWS real (condiciones de carrera en Lake
Formation, colisión de nombres de tabla en el Crawler, tipos de columna
de partición, migración de esquema de particiones) y cómo se
diagnosticaron y resolvieron — útil como referencia de troubleshooting
más allá de este laboratorio específico.
