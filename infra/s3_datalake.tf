locals {
  data_lake_bucket_name = "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-${var.data_lake_bucket_suffix}"

  # Logical medallion prefixes. No placeholder objects are created for
  # these — the Glue job creates the actual paths when it writes output.
  data_lake_bronze_prefix = "bronze/orders/"
  data_lake_silver_prefix = "silver/orders/"
  data_lake_gold_prefix   = "gold/orders/"
  athena_results_prefix   = "athena-results/"
  glue_scripts_prefix     = "scripts/"
}

resource "aws_s3_bucket" "data_lake" {
  bucket        = local.data_lake_bucket_name
  force_destroy = var.data_lake_bucket_force_destroy
  tags          = local.common_tags
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
  source = "${path.module}/../src/glue/transform.py"
  etag   = filemd5("${path.module}/../src/glue/transform.py")
  tags   = local.common_tags
}
