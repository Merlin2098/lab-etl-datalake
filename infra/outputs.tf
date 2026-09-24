output "data_job_execution_role_arn" {
  description = "IAM role ARN for Glue or other batch data jobs."
  value       = module.iam.execution_role_arn
}

output "log_group_name" {
  description = "CloudWatch log group name for data jobs."
  value       = module.iam.log_group_name
}

output "log_group_arn" {
  description = "CloudWatch log group ARN for data jobs."
  value       = module.iam.log_group_arn
}

output "budget_name" {
  description = "AWS Budget name for monthly cost governance. Empty string when enable_budget_guardrail is false."
  value       = module.iam.budget_name
}

output "budget_alert_sns_arn" {
  description = "SNS topic ARN for budget alerts. Empty string when the guardrail is disabled or no alert email is configured."
  value       = module.iam.budget_alert_sns_arn
}

output "data_lake_bucket_name" {
  description = "S3 bucket used for the Bronze/Silver/Gold medallion data lake."
  value       = module.s3_datalake.bucket_name
}

output "data_lake_bucket_arn" {
  description = "ARN of the data lake bucket."
  value       = module.s3_datalake.bucket_arn
}

output "glue_database_name" {
  description = "Glue Data Catalog database holding the bronze/silver/gold tables."
  value       = module.glue.database_name
}

output "glue_job_name" {
  description = "Glue job that runs the Bronze -> Silver -> Gold medallion ETL."
  value       = module.glue.job_name
}

output "glue_silver_crawler_name" {
  description = "Glue crawler that catalogs the Silver prefix as silver_orders."
  value       = module.glue.silver_crawler_name
}

output "glue_gold_crawler_name" {
  description = "Glue crawler that catalogs the Gold prefix as gold_orders."
  value       = module.glue.gold_crawler_name
}

output "athena_workgroup_name" {
  description = "Athena workgroup configured for the data lake, with results written to the data lake bucket."
  value       = module.athena.workgroup_name
}
