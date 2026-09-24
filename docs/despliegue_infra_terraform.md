# Guía de despliegue — Infraestructura Terraform del Data Lake

Esta guía cubre el despliegue manual de la infraestructura definida en
`infra/` para el laboratorio de la sesión 4 (ver
[sesion_04_laboratorio_challenges.md](sesion_04_laboratorio_challenges.md)
y el [diseño del data lake](superpowers/specs/2026-09-22-medallion-datalake-design.md)).

No se automatiza `terraform apply`/`destroy` desde ningún agente ni script:
estos comandos se ejecutan manualmente, siguiendo los approval boundaries
de [AGENTS.md](../AGENTS.md).

## 1. Prerrequisitos

- Terraform >= 1.6.0 instalado.
- AWS CLI configurado o credenciales disponibles (ver sección 2).
- Permisos suficientes en la cuenta/rol AWS para crear: S3, IAM, Glue,
  Athena, CloudWatch Logs, SNS/Budgets (si se habilita el guardrail de
  presupuesto).
- Usar una cuenta o entorno de laboratorio controlado.

## 2. Configurar credenciales

Este proyecto usa un archivo `.env.credentials` (no versionado) para
pruebas locales con boto3 (`tests/aws/`). Para Terraform, las credenciales
se resuelven por los mecanismos estándar del proveedor AWS: variables de
entorno, perfil de AWS CLI (`~/.aws/credentials`), o rol asumido.

```bash
cp .env.example .env.credentials
# editar .env.credentials con credenciales reales — nunca commitear este archivo
```

Terraform (proveedor AWS) no lee `.env.credentials` automáticamente — solo
resuelve credenciales vía variables de entorno, perfil de AWS CLI, o rol
asumido. Para reutilizar el mismo `.env.credentials` con Terraform, carga
sus variables en el entorno de la shell antes de correr cualquier comando
`terraform`, usando Git Bash:

```bash
set -a
source .env.credentials
set +a
```

- `set -a` marca como exportadas todas las variables definidas a partir de
  ese punto (incluye las que trae `source .env.credentials`).
- `set +a` desactiva el auto-export inmediatamente después, para no dejar
  ninguna variable adicional exportada por accidente en el resto de la
  sesión de shell.
- Verifica que cargó correctamente sin imprimir el secreto:
  `echo ${AWS_ACCESS_KEY_ID:+set}` debe mostrar `set`.

Repite este `source` en cada sesión nueva de Git Bash (las variables no
persisten entre terminales). Alternativamente, usa un perfil de AWS CLI
(`aws configure`) si prefieres no depender de este archivo para Terraform.

**Nunca** pegues credenciales directamente en archivos `.tf`, `.tfvars` o
en este repositorio, y nunca las envíes a servicios externos.

## 3. Configurar variables de Terraform

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Revisa y ajusta `terraform.tfvars` según tu entorno. Variables relevantes
para el data lake:

| Variable                           | Default           | Descripción                                                                              |
| ---------------------------------- | ----------------- | ----------------------------------------------------------------------------------------- |
| `project_name`                   | `data-platform` | Prefijo usado en el nombre de todos los recursos.                                         |
| `environment`                    | `dev`           | Ambiente de despliegue.                                                                   |
| `aws_region`                     | `us-east-1`     | Región AWS.                                                                              |
| `data_lake_bucket_suffix`        | `datalake`      | Sufijo del bucket S3 del data lake (Bronze/Silver/Gold).                                  |
| `data_lake_bucket_force_destroy` | `true`          | Permite`terraform destroy` aunque el bucket tenga objetos. Mantener `true` en un lab. |
| `glue_worker_type`               | `G.1X`          | Tipo de worker del Glue Job.                                                              |
| `glue_number_of_workers`         | `2`             | Cantidad de workers del Glue Job.                                                         |
| `glue_job_timeout_minutes`       | `15`            | Timeout del Glue Job.                                                                     |
| `enable_budget_guardrail`        | `false`         | Crea un AWS Budget mensual + alerta SNS. Opcional para el lab.                            |

No existe un bucket de "artifacts" separado: todo el código (script de
Glue, queries de referencia) vive en `src/` y se sube al mismo bucket del
data lake (ver sección 8). No es necesario generar ningún paquete `.zip`
local antes de `terraform plan`.

No es necesario un backend remoto para un lab de una sola persona; el
estado se guarda localmente (`terraform.tfstate`, no versionado). Si
prefieres backend remoto S3, revisa `backend.tf.example`.

## 4. Inicializar Terraform

Antes de cualquier comando `terraform`, en la misma sesión de Git Bash,
carga las credenciales (ver sección 2):

```bash
set -a
source ../.env.credentials
set +a
```

Luego:

```bash
terraform init
```

Esto descarga el provider `hashicorp/aws` (~> 5.0) y genera
`.terraform.lock.hcl` (si no existe ya, versionado en el repo).

## 5. Revisar el plan

```bash
terraform plan
```

Identifica en el output:

- **S3**: bucket del data lake (`s3_datalake.tf`), con sus configuraciones
  de encriptación y bloqueo de acceso público.
- **IAM**: el rol `data_job_execution` (usado por el Glue Job y el
  Crawler) y sus políticas inline.
- **Glue**: `aws_glue_catalog_database`, `aws_glue_job`, y dos crawlers
  separados (`aws_glue_crawler.silver_crawler`,
  `aws_glue_crawler.gold_crawler`) en `glue.tf`.
- **Athena**: `aws_athena_workgroup` (`athena.tf`).

## 6. Aplicar infraestructura

```bash
terraform apply
```

Confirma escribiendo `yes` cuando Terraform lo solicite. **Este paso
requiere tu aprobación explícita** — ningún agente debe ejecutarlo por ti.

### Nota sobre condiciones de carrera (eventual consistency)

IAM es un servicio eventualmente consistente: es posible que el primer
`apply` falle de forma transitoria en recursos que dependen del rol IAM
recién creado (`aws_glue_job`, `aws_glue_crawler`), con errores como
`AccessDeniedException`, aunque el orden de creación en el grafo de
Terraform sea correcto.

**Esto no deja recursos huérfanos ni requiere `terraform import`.** Si el
`apply` falla así, simplemente vuelve a ejecutar:

```bash
terraform apply
```

El segundo intento normalmente tiene éxito porque para entonces IAM ya
propagó el cambio anterior.

### Insight — un solo crawler con dos prefijos produce nombres de tabla impredecibles

`glue.tf` usa **dos crawlers separados** (`silver_crawler`, `gold_crawler`),
no uno solo con dos `s3_target`. Durante las pruebas E2E, un crawler único
apuntando a `silver/orders/` y `gold/orders/` catalogó la primera ruta como
tabla `orders` y, al chocar el nombre con la segunda ruta (ambas terminan
en el mismo último segmento de path, `orders/`), Glue le agregó a la
segunda un sufijo hash aleatorio (`orders_a3ff0d60bfd57bd73ce9c9c262ad5729`)
en lugar de un nombre legible. Cada crawler separado usa `table_prefix`
(`silver_`, `gold_`) para que los nombres resultantes sean deterministas:
`silver_orders` y `gold_orders`, siempre, en cada corrida.

## 7. Revisar los outputs

```bash
terraform output
```

Outputs relevantes para explorar por consola (sección 7 del lab):

- `data_lake_bucket_name` — bucket S3 con los prefijos `bronze/`,
  `silver/`, `gold/`.
- `glue_database_name` — Glue Data Catalog database.
- `glue_job_name` — Glue Job del ETL medallion.
- `glue_silver_crawler_name` — Crawler que cataloga Silver como
  `silver_orders`.
- `glue_gold_crawler_name` — Crawler que cataloga Gold como `gold_orders`.
- `athena_workgroup_name` — Workgroup de Athena a seleccionar en el query
  editor.
- `data_job_execution_role_arn` — rol IAM usado por Glue.

## 8. Subir el dataset y ejecutar el ETL (pasos manuales, fuera de Terraform)

Ver la guía detallada en
[prueba_manual_pipeline.md](prueba_manual_pipeline.md) (consola + AWS
CLI) o en
[prueba_manual_consola_aws.md](prueba_manual_consola_aws.md) (solo
consola, sin ningún comando de terminal). Resumen:

1. Sube `data/orders.csv` a
   `s3://<data_lake_bucket_name>/bronze/orders/source=<nombre-origen>/`
   (vía consola o `aws s3 cp`) — la partición `source=` permite combinar
   varios orígenes con el mismo esquema en un solo pipeline (ver
   docstring de [src/glue/transform.py](../src/glue/transform.py)).
2. En la consola de AWS Glue, ejecuta el Job indicado en
   `glue_job_name`.
3. Verifica que el Job finalizó correctamente y revisa los logs en
   CloudWatch (`log_group_name`).
4. Ejecuta el Crawler de Silver (`glue_silver_crawler_name`) y luego el de
   Gold (`glue_gold_crawler_name`) para catalogarlos como `silver_orders` y
   `gold_orders`.
5. En Athena, selecciona el workgroup (`athena_workgroup_name`) y corre
   las queries de [src/queries/](../src/queries/)
   (`01_bronze.sql`, `02_silver.sql`, `03_gold.sql`).

### Insight — cambiar el esquema de particiones rompe el Crawler sobre una tabla existente

Si ya corriste el pipeline antes y luego cambias qué columnas particionan
Silver/Gold (por ejemplo, al agregar `source` como partición nueva), el
crawler puede fallar así:

```
InvalidInputException: Trying to change partitionColumn name from: year
to new partitionColumn name: source. Change of partitionColumn names is
not allowed.
```

Glue no permite renombrar ni reordenar las columnas de partición de una
tabla ya catalogada — solo agregar más particiones *dentro* del mismo
esquema. La solución es borrar la tabla vieja antes de volver a correr el
crawler, para que la recree desde cero con el nuevo esquema:

```bash
aws glue delete-table --database-name "$(cd infra && terraform output -raw glue_database_name)" --name gold_orders
aws glue delete-table --database-name "$(cd infra && terraform output -raw glue_database_name)" --name silver_orders
```

Esto es solo metadata del catálogo — no borra los datos en S3. Después de
borrar, vuelve a correr el Crawler correspondiente.

## 9. Destruir la infraestructura

Cuando termines el lab:

```bash
terraform destroy
```

**Requiere tu aprobación explícita.** Con `force_destroy = true`, Terraform
puede eliminar el bucket del data lake aunque contenga objetos (datos
Bronze/Silver/Gold, resultados de Athena, el script de Glue).

## Referencias

- [Diseño del data lake medallion](superpowers/specs/2026-09-22-medallion-datalake-design.md)
- [Documento del laboratorio (sesión 4)](sesion_04_laboratorio_challenges.md)
- [AGENTS.md](../AGENTS.md) — approval boundaries y guardrails de
  AWS/Terraform aplicados en este stack.
