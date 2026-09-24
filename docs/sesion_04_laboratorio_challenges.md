# Laboratorio --- ETL Serverless y Data Lake con AWS

**Sesión:** 04 --- Procesamiento ETL y Data Lake con AWS\
**Duración:** 1 hora\
**Modalidad:** Terraform + AWS Console + AWS CLI / SQL\
**Nivel:** AWS Data Engineer Associate

------------------------------------------------------------------------

# 1. Objetivos

Al finalizar el laboratorio, el alumno podrá:

-   Desplegar la infraestructura base mediante Terraform.
-   Identificar los componentes de un Data Lake en AWS.
-   Explorar S3, Glue Data Catalog, Glue Jobs, Athena y Lake Formation
    desde la consola.
-   Ejecutar un proceso ETL con AWS Glue.
-   Implementar una transformación Bronze → Silver → Gold.
-   Consultar los datos procesados con Athena.
-   Analizar cómo el particionamiento afecta las consultas.
-   Revisar conceptos básicos de gobierno con Lake Formation.
-   Resolver challenges basados en escenarios de AWS Data Engineer
    Associate.
-   Identificar cuándo una consulta federada puede ser una alternativa a
    un ETL.

------------------------------------------------------------------------

# 2. Arquitectura del laboratorio

``` text
                    Synthetic Data
                         │
                         ▼
                    S3 / Bronze
                         │
                         ▼
                   AWS Glue Job
                    PySpark ETL
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          S3 / Silver           S3 / Gold
              │                     │
              └──────────┬──────────┘
                         ▼
                 Glue Data Catalog
                         │
                         ▼
                      Athena
```

La infraestructura será creada mediante Terraform. Lake Formation no es
parte del despliegue de Terraform de este lab (ver
[ADR 0001](internal/adr/0001-remove-lake-formation.md)); se explora solo
manualmente por consola en la Parte 9, como ejercicio conceptual de
gobierno de datos.

------------------------------------------------------------------------

# 3. Caso de negocio

Una empresa de logística recibe diariamente información de pedidos.

Los datos contienen:

-   `order_id`
-   `customer_id`
-   `order_date`
-   `status`
-   `amount`
-   `city`
-   `carrier`

Los archivos iniciales representan datos **raw**.

El objetivo es construir un pequeño Data Lake:

``` text
Bronze → Silver → Gold
```

### Bronze

Conservar los datos originales.

### Silver

Limpiar y estandarizar:

-   tipos de datos
-   valores inválidos
-   columnas
-   nombres
-   registros duplicados

### Gold

Generar un dataset preparado para analytics.

------------------------------------------------------------------------

# 4. Requisitos

Antes del laboratorio:

-   AWS CLI configurado.
-   Credenciales AWS válidas.
-   Terraform instalado.
-   Git instalado.
-   Cuenta/región AWS definida.
-   Permisos suficientes para crear los recursos del laboratorio.

> Utilizar una cuenta o entorno de laboratorio controlado cuando sea
> posible.

------------------------------------------------------------------------

# 5. Estructura sugerida del proyecto

``` text
session-04/
│
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── iam.tf
│   ├── s3.tf
│   ├── glue.tf
│   ├── athena.tf
│   └── lakeformation.tf
│
├── glue/
│   └── transform.py
│
├── data/
│   └── orders.csv
│
└── queries/
    ├── 01_bronze.sql
    ├── 02_silver.sql
    └── 03_gold.sql
```

------------------------------------------------------------------------

# 6. Parte 1 --- Despliegue con Terraform

## Objetivo

Crear la infraestructura base mediante Infrastructure as Code.

### Recursos sugeridos

Terraform debe crear, como mínimo:

-   S3 bucket
-   estructura de prefijos Bronze/Silver/Gold
-   Glue Database
-   IAM Role para Glue
-   Glue Job
-   Athena Workgroup
-   configuración necesaria para Lake Formation

Opcional:

-   bucket/prefijo para Athena query results
-   CloudWatch Log Group
-   dataset sintético
-   recursos necesarios para un escenario de Federated Query

------------------------------------------------------------------------

## 6.1. Inicializar Terraform

``` bash
terraform init
```

------------------------------------------------------------------------

## 6.2. Revisar el plan

``` bash
terraform plan
```

El alumno debe identificar:

-   recursos S3
-   roles IAM
-   Glue resources
-   Athena resources
-   Lake Formation resources

------------------------------------------------------------------------

## 6.3. Aplicar infraestructura

``` bash
terraform apply
```

Confirmar el despliegue.

------------------------------------------------------------------------

# 7. Parte 2 --- Exploración por consola

## Objetivo

Relacionar los recursos creados mediante IaC con los servicios visibles
en AWS Console.

------------------------------------------------------------------------

## 7.1. Amazon S3

Revisar:

-   bucket
-   prefijos
-   objetos
-   Bronze
-   Silver
-   Gold
-   ubicación de los datos

Responder:

> ¿Dónde están físicamente los datos?

**Respuesta esperada:** Amazon S3.

------------------------------------------------------------------------

## 7.2. AWS Glue

Revisar:

### Data Catalog

-   Databases
-   Tables
-   Schema
-   Location
-   Partitions

### Jobs

-   Job name
-   IAM Role
-   Glue version
-   Worker configuration
-   Script location
-   Job parameters
-   Bookmarks

Responder:

> ¿Dónde están los datos y dónde está almacenada la metadata?

------------------------------------------------------------------------

## 7.3. Amazon Athena

Revisar:

-   Workgroup
-   Data source
-   Catalog
-   Database
-   Tables
-   Query editor
-   Query results

Responder:

> ¿Athena almacena los datos consultados?

**Respuesta:** No. Consulta datos almacenados en fuentes compatibles; en
el escenario principal, los datos permanecen en S3.

------------------------------------------------------------------------

## 7.4. Lake Formation

Revisar:

-   Data Catalog
-   Data locations
-   Databases
-   Tables
-   Permissions

Identificar:

``` text
S3 Location
    ↓
Lake Formation
    ↓
Catalog / Permissions
```

------------------------------------------------------------------------

# 8. Parte 3 --- Ejecutar el ETL

## 8.1. Dataset Bronze

Subir el dataset inicial a:

``` text
s3://<bucket>/bronze/orders/
```

Los datos representan la fuente original.

------------------------------------------------------------------------

## 8.2. Ejecutar Glue Job

Desde AWS Console:

1.  Abrir AWS Glue.
2.  Ir a Jobs.
3.  Seleccionar el Job.
4.  Ejecutar.
5.  Revisar el estado.
6.  Abrir los logs si existen errores.
7.  Confirmar que el Job finalizó correctamente.

Flujo:

``` text
Bronze
  ↓
Glue Job
  ↓
Silver
```

------------------------------------------------------------------------

# 9. Parte 4 --- Catalogar los datos

Ejecutar o revisar el Crawler correspondiente.

Objetivo:

``` text
S3 Silver
    ↓
Crawler
    ↓
Glue Data Catalog
```

Verificar:

-   database
-   table
-   columns
-   types
-   location
-   partitions

------------------------------------------------------------------------

# 10. Parte 5 --- Consultar con Athena

## Query 1 --- Validar registros

``` sql
SELECT *
FROM silver_orders
LIMIT 10;
```

------------------------------------------------------------------------

## Query 2 --- Contar registros

``` sql
SELECT COUNT(*) AS total_orders
FROM silver_orders;
```

------------------------------------------------------------------------

## Query 3 --- Agregación

``` sql
SELECT
    city,
    COUNT(*) AS orders,
    SUM(amount) AS revenue
FROM silver_orders
GROUP BY city
ORDER BY revenue DESC;
```

------------------------------------------------------------------------

# 11. Parte 6 --- Bronze → Silver → Gold

El objetivo final será producir:

``` text
Bronze
   ↓
Silver
   ↓
Gold
```

### Silver

Debe contener:

-   datos limpios
-   tipos correctos
-   registros válidos
-   estructura consistente

### Gold

Debe contener información orientada a analytics.

Ejemplo:

``` text
city
orders
revenue
average_order_value
```

------------------------------------------------------------------------

# 12. Parte 7 --- Particionamiento

La tabla Gold debe utilizar una estrategia de particionamiento.

Ejemplo:

``` text
gold/orders/
    year=2026/
        month=09/
            day=23/
                data.parquet
```

Analizar:

``` sql
SELECT *
FROM gold_orders
WHERE year = 2026
  AND month = 9
  AND day = 23;
```

Comparar conceptualmente con:

``` sql
SELECT *
FROM gold_orders;
```

### Pregunta

¿Por qué la primera consulta puede procesar menos datos?

**Concepto esperado:**

Partition pruning.

------------------------------------------------------------------------

# 13. Parte 8 --- Optimización de Athena

Analizar estas dos consultas:

### Consulta A

``` sql
SELECT *
FROM gold_orders;
```

### Consulta B

``` sql
SELECT
    order_id,
    amount
FROM gold_orders
WHERE year = 2026
  AND month = 9;
```

Discutir:

-   columnas seleccionadas
-   particiones
-   formato Parquet
-   cantidad de datos procesados
-   costo

------------------------------------------------------------------------

# 14. Parte 9 --- Lake Formation

## Objetivo

Observar cómo el gobierno del Data Lake puede separar acceso a datos.

Escenario:

``` text
Data Engineer
    ↓
Bronze / Silver / Gold

Data Analyst
    ↓
Gold
```

Revisar en Lake Formation:

-   Database permissions
-   Table permissions
-   Data location permissions

------------------------------------------------------------------------

## Actividad

Identificar:

1.  Qué principal tiene permisos.
2.  Sobre qué recurso.
3.  Qué acciones puede realizar.
4.  Qué recurso debería restringirse para un Analyst.

No es necesario construir un modelo completo de gobierno empresarial.

El objetivo es comprender la relación:

``` text
Principal
   ↓
Lake Formation Permission
   ↓
Catalog Resource
   ↓
Underlying Data
```

------------------------------------------------------------------------

# 15. Parte 10 --- Athena Federated Query

## Concepto

Supongamos que:

``` text
orders → S3

customers → DynamoDB
```

Queremos consultar ambas fuentes.

Una posibilidad:

``` text
DynamoDB
    ↓
ETL
    ↓
S3
    ↓
Athena
```

Otra posibilidad, para determinados escenarios:

``` text
             Athena
             /     \
           S3     DynamoDB
```

utilizando Athena Federated Query y el conector correspondiente.

------------------------------------------------------------------------

## Actividad conceptual

Identificar:

-   fuente de datos
-   conector
-   mecanismo de acceso
-   necesidad de credenciales/secretos
-   ubicación de spill cuando aplique

> No se requiere implementar un conector federado completo si la
> infraestructura de la cuenta no está preparada para ello. El objetivo
> mínimo es comprender el patrón arquitectónico y reconocerlo en
> escenarios DEA.

------------------------------------------------------------------------

# 16. Challenge 1 --- Medallion

## Escenario

El equipo está almacenando archivos CSV originales en S3 y actualmente
los sobrescribe después de limpiarlos.

### Pregunta

¿Qué problema genera esta estrategia y cómo la corregirías utilizando
Medallion Architecture?

### Resultado esperado

Proponer:

``` text
Raw/Bronze
    ↓
Silver
    ↓
Gold
```

manteniendo los datos originales.

------------------------------------------------------------------------

# 17. Challenge 2 --- Crawler vs Job

## Escenario

Una tabla nueva aparece diariamente en S3.

El equipo quiere detectar automáticamente:

-   schema
-   columnas
-   particiones
-   ubicación

### Pregunta

¿Utilizarías un Glue Job o un Glue Crawler?

Explica por qué.

### Resultado esperado

**Glue Crawler**, porque el requerimiento principal es
descubrimiento/catalogación de metadata.

------------------------------------------------------------------------

# 18. Challenge 3 --- Optimización Athena

## Escenario

Una consulta Athena procesa 300 GB.

El usuario solamente necesita:

-   `order_id`
-   `amount`

para:

``` text
year = 2026
month = 9
day = 23
```

### Reto

Propón al menos tres acciones para reducir los datos procesados.

### Posibles soluciones

-   utilizar Parquet
-   seleccionar únicamente columnas necesarias
-   particionar por dimensiones de consulta
-   filtrar por particiones
-   evitar `SELECT *`

------------------------------------------------------------------------

# 19. Challenge 4 --- Incremental ETL

## Escenario

El pipeline recibe diariamente archivos nuevos.

Actualmente el Glue Job procesa todo el histórico cada vez que se
ejecuta.

### Pregunta

¿Qué mecanismo de Glue puede ayudar a implementar procesamiento
incremental en escenarios compatibles?

### Resultado esperado

**Job Bookmarks.**

El alumno debe explicar que su utilidad depende del origen y patrón de
procesamiento.

------------------------------------------------------------------------

# 20. Challenge 5 --- Data Governance

## Escenario

La organización tiene:

``` text
Bronze → información raw
Silver → datos procesados
Gold   → datos para analistas
```

El equipo quiere:

``` text
Data Engineer → Bronze + Silver + Gold
Analyst       → Gold
```

### Pregunta

¿Qué servicio utilizarías para implementar gobierno y permisos sobre el
Data Lake?

### Resultado esperado

**AWS Lake Formation.**

El alumno debe diferenciarlo de IAM:

-   IAM → permisos sobre recursos AWS.
-   Lake Formation → gobierno/permisos sobre datos del Data Lake.

------------------------------------------------------------------------

# 21. Challenge 6 --- Federated Query

## Escenario

Una empresa tiene:

``` text
Ventas → S3
Clientes → DynamoDB
```

El equipo de analytics necesita realizar una consulta puntual combinando
ambas fuentes.

### Pregunta

¿Qué capacidad de Athena investigarías antes de construir un pipeline
ETL adicional?

### Resultado esperado

**Athena Federated Query.**

------------------------------------------------------------------------

# 22. Challenge 7 --- Arquitectura

## Reto final

Construye mentalmente la arquitectura para:

> "Una empresa recibe datos diariamente, necesita conservar los
> originales, limpiarlos, transformarlos a Parquet, consultarlos con
> SQL, controlar el acceso de los analistas y ocasionalmente consultar
> una fuente operacional externa."

Selecciona los servicios:

-   S3
-   Glue Data Catalog
-   Glue Crawler
-   Glue Job
-   Athena
-   Lake Formation
-   Athena Federated Query

### Arquitectura esperada

``` text
                   DATA SOURCES
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
            S3              External Source
             │                     │
             ▼                     ▼
      Bronze / Raw          Federated Query
             │                     │
             ▼                     │
        Glue Job                   │
             │                     │
       ┌─────┴─────┐               │
       ▼           ▼               │
    Silver       Gold              │
       │           │               │
       └─────┬─────┴───────────────┘
             ▼
      Glue Data Catalog
             │
             ▼
      Lake Formation
             │
             ▼
          Athena
```

------------------------------------------------------------------------

# 23. Checklist final

Antes de terminar, el alumno debe poder responder:

### S3

-   ¿Dónde viven físicamente los datos?

### Glue Data Catalog

-   ¿Qué almacena?
-   ¿Qué diferencia existe entre database y table?

### Crawler

-   ¿Para qué sirve?
-   ¿Qué diferencia existe con un ETL Job?

### Glue Job

-   ¿Qué ejecuta?
-   ¿Qué papel tiene Spark?
-   ¿Qué son Job Bookmarks?

### Medallion

-   ¿Qué representa Bronze?
-   ¿Qué representa Silver?
-   ¿Qué representa Gold?

### S3 / Parquet

-   ¿Por qué utilizar Parquet?
-   ¿Qué problema resuelve el particionamiento?

### Athena

-   ¿Cómo consulta datos en S3?
-   ¿Qué significa schema-on-read?
-   ¿Cómo reducir datos procesados?

### Lake Formation

-   ¿Qué problema resuelve?
-   ¿Cómo se diferencia de IAM?
-   ¿Qué significa gobernar un Data Lake?

### Federated Query

-   ¿Para qué sirve?
-   ¿Cuándo podría utilizarse en lugar de mover previamente los datos?

------------------------------------------------------------------------

# 24. Resultado final del laboratorio

El alumno debe terminar con una arquitectura funcional:

``` text
Terraform
    │
    ▼
AWS Infrastructure
    │
    ├── S3
    ├── Glue Catalog
    ├── Glue Job
    ├── Athena
    └── Lake Formation
          │
          ▼
     Data Lake
          │
          ▼
Bronze → Silver → Gold
          │
          ▼
        Athena
```

Y debe ser capaz de explicar **por qué existe cada componente**, no
solamente identificarlo en la consola.
