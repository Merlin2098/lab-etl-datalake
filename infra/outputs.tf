output "data_job_execution_role_arn" {
  description = "IAM role ARN for Glue or other batch data jobs."
  value       = aws_iam_role.data_job_execution.arn
}

output "log_group_name" {
  description = "CloudWatch log group name for data jobs."
  value       = aws_cloudwatch_log_group.data_jobs.name
}

output "log_group_arn" {
  description = "CloudWatch log group ARN for data jobs."
  value       = aws_cloudwatch_log_group.data_jobs.arn
}

output "budget_name" {
  description = "AWS Budget name for monthly cost governance. Empty string when enable_budget_guardrail is false."
  value       = var.enable_budget_guardrail ? aws_budgets_budget.monthly[0].name : ""
}

output "budget_alert_sns_arn" {
  description = "SNS topic ARN for budget alerts. Empty string when the guardrail is disabled or no alert email is configured."
  value       = var.enable_budget_guardrail && var.budget_alert_email != "" ? aws_sns_topic.budget_alerts[0].arn : ""
}

output "data_lake_bucket_name" {
  description = "S3 bucket used for the Bronze/Silver/Gold medallion data lake."
  value       = aws_s3_bucket.data_lake.bucket
}

output "data_lake_bucket_arn" {
  description = "ARN of the data lake bucket."
  value       = aws_s3_bucket.data_lake.arn
}

output "glue_database_name" {
  description = "Glue Data Catalog database holding the bronze/silver/gold tables."
  value       = aws_glue_catalog_database.datalake_db.name
}

output "glue_job_name" {
  description = "Glue job that runs the Bronze -> Silver -> Gold medallion ETL."
  value       = aws_glue_job.orders_medallion.name
}

output "glue_silver_crawler_name" {
  description = "Glue crawler that catalogs the Silver prefix as silver_orders."
  value       = aws_glue_crawler.silver_crawler.name
}

output "glue_gold_crawler_name" {
  description = "Glue crawler that catalogs the Gold prefix as gold_orders."
  value       = aws_glue_crawler.gold_crawler.name
}

output "athena_workgroup_name" {
  description = "Athena workgroup configured for the data lake, with results written to the data lake bucket."
  value       = aws_athena_workgroup.datalake.name
}
