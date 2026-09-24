output "bucket_name" {
  description = "S3 bucket used for the Bronze/Silver/Gold medallion data lake."
  value       = aws_s3_bucket.data_lake.bucket
}

output "bucket_arn" {
  description = "ARN of the data lake bucket."
  value       = aws_s3_bucket.data_lake.arn
}

output "bronze_prefix" {
  description = "Logical Bronze prefix (raw orders data), no source= subfolder."
  value       = local.bronze_prefix
}

output "silver_prefix" {
  description = "Logical Silver prefix (cleaned Parquet)."
  value       = local.silver_prefix
}

output "gold_prefix" {
  description = "Logical Gold prefix (aggregated Parquet, partitioned by year/month/day)."
  value       = local.gold_prefix
}

output "temp_prefix" {
  description = "Logical prefix used as the Glue job's --TempDir."
  value       = local.temp_prefix
}

output "athena_results_prefix" {
  description = "Prefix where Athena writes query results."
  value       = local.athena_results_prefix
}

output "glue_script_s3_key" {
  description = "S3 key of the uploaded Glue transform script."
  value       = aws_s3_object.glue_transform_script.key
}
