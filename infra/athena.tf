resource "aws_athena_workgroup" "datalake" {
  name          = "${local.name_prefix}-datalake"
  force_destroy = true
  tags          = local.common_tags

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.bucket}/${local.athena_results_prefix}"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
