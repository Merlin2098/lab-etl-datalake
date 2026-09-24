resource "aws_glue_catalog_database" "datalake_db" {
  name = replace("${var.name_prefix}_datalake_db", "-", "_")
}

resource "aws_glue_job" "orders_medallion" {
  name              = "${var.name_prefix}-orders"
  role_arn          = var.execution_role_arn
  glue_version      = "4.0"
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.job_timeout_minutes
  tags              = var.tags

  command {
    name            = "glueetl"
    script_location = "s3://${var.data_lake_bucket_name}/${var.glue_script_s3_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--BRONZE_PATH"                      = "s3://${var.data_lake_bucket_name}/${var.bronze_prefix}"
    "--SILVER_PATH"                      = "s3://${var.data_lake_bucket_name}/${var.silver_prefix}"
    "--GOLD_PATH"                        = "s3://${var.data_lake_bucket_name}/${var.gold_prefix}"
    "--TempDir"                          = "s3://${var.data_lake_bucket_name}/${var.temp_prefix}"
    "--continuous-log-logGroup"          = var.log_group_name
    "--enable-continuous-cloudwatch-log" = "true"
  }
}

# Two separate crawlers, not one crawler with two s3_target blocks: both
# Silver and Gold prefixes end in the same last path segment (.../orders/),
# so a single crawler names the first table "orders" and resolves the name
# collision on the second by appending a random hash suffix
# (e.g. "orders_a3ff0d60..."), which is neither readable nor stable across
# runs. table_prefix on separate crawlers makes the resulting table names
# deterministic: silver_orders and gold_orders.
resource "aws_glue_crawler" "silver_crawler" {
  name          = "${var.name_prefix}-silver-crawler"
  role          = var.execution_role_arn
  database_name = aws_glue_catalog_database.datalake_db.name
  table_prefix  = "silver_"
  tags          = var.tags

  s3_target {
    path = "s3://${var.data_lake_bucket_name}/${var.silver_prefix}"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}

resource "aws_glue_crawler" "gold_crawler" {
  name          = "${var.name_prefix}-gold-crawler"
  role          = var.execution_role_arn
  database_name = aws_glue_catalog_database.datalake_db.name
  table_prefix  = "gold_"
  tags          = var.tags

  s3_target {
    path = "s3://${var.data_lake_bucket_name}/${var.gold_prefix}"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}
