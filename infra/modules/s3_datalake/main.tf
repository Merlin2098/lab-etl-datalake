locals {
  bucket_name = "${var.name_prefix}-${var.account_id}-${var.bucket_suffix}"

  # Logical medallion prefixes. No placeholder objects are created for
  # bronze/silver/gold/temp — the Glue job creates the actual paths when
  # it reads/writes/spills to them.
  bronze_prefix         = "bronze/orders/"
  silver_prefix         = "silver/orders/"
  gold_prefix           = "gold/orders/"
  temp_prefix           = "temp/"
  athena_results_prefix = "athena-results/"
  glue_scripts_prefix   = "scripts/"
}

resource "aws_s3_bucket" "data_lake" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "glue_transform_script" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "${local.glue_scripts_prefix}transform.py"
  source = var.glue_script_path
  etag   = filemd5(var.glue_script_path)
  tags   = var.tags
}

# Declared here (not in the iam module) because the bucket ARN is only
# known in this module — see AGENTS.md's IAM cross-module placement rule.
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
  name   = "${var.name_prefix}-data-lake-access"
  role   = var.data_job_execution_role_name
  policy = data.aws_iam_policy_document.data_lake_access.json
}
