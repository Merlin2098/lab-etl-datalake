data "aws_iam_policy_document" "data_lake_access" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.data_lake.arn}/*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }
}

resource "aws_iam_role_policy" "data_lake_access" {
  name   = "${local.name_prefix}-data-lake-access"
  role   = aws_iam_role.data_job_execution.id
  policy = data.aws_iam_policy_document.data_lake_access.json
}

resource "aws_glue_catalog_database" "datalake_db" {
  name = replace("${local.name_prefix}_datalake_db", "-", "_")
}

resource "aws_glue_job" "orders_medallion" {
  name              = "${local.name_prefix}-orders-medallion"
  role_arn          = aws_iam_role.data_job_execution.arn
  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_job_timeout_minutes
  tags              = local.common_tags

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/${local.glue_scripts_prefix}transform.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--BRONZE_PATH"                      = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_lake_bronze_prefix}"
    "--SILVER_PATH"                      = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_lake_silver_prefix}"
    "--GOLD_PATH"                        = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_lake_gold_prefix}"
    "--continuous-log-logGroup"          = aws_cloudwatch_log_group.data_jobs.name
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
  name          = "${local.name_prefix}-silver-crawler"
  role          = aws_iam_role.data_job_execution.arn
  database_name = aws_glue_catalog_database.datalake_db.name
  table_prefix  = "silver_"
  tags          = local.common_tags

  s3_target {
    path = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_lake_silver_prefix}"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}

resource "aws_glue_crawler" "gold_crawler" {
  name          = "${local.name_prefix}-gold-crawler"
  role          = aws_iam_role.data_job_execution.arn
  database_name = aws_glue_catalog_database.datalake_db.name
  table_prefix  = "gold_"
  tags          = local.common_tags

  s3_target {
    path = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_lake_gold_prefix}"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }
}
