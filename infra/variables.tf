variable "project_name" {
  description = "Project name used in AWS resource naming."
  type        = string
  default     = "lab-etl"
}

variable "owner" {
  description = "Owner tag applied to all managed resources."
  type        = string
  default     = "data-engineering"
}

variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
  default     = "us-east-1"
}

variable "execution_role_name" {
  description = "IAM role name for AWS data jobs."
  type        = string
  default     = "data-job-execution-role"
}

variable "tags" {
  description = "Additional tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "cost_center" {
  description = "Cost center tag for budget allocation and cost reporting."
  type        = string
  default     = "engineering"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days. Use 7 for demos and labs; set higher for production per compliance requirements."
  type        = number
  default     = 7
}

variable "enable_budget_guardrail" {
  description = "Whether to create the monthly AWS Budget (and its SNS alert topic, if an email is set). Off by default for student/demo use; enable for real deployments."
  type        = bool
  default     = false
}

variable "budget_limit_usd" {
  description = "Monthly AWS budget limit in USD. Alerts fire at 80% (actual) and 100% (forecasted). Only used when enable_budget_guardrail is true."
  type        = number
  default     = 25
}

variable "budget_alert_email" {
  description = "Email address for budget alerts. Leave empty to skip SNS subscription creation. Only used when enable_budget_guardrail is true."
  type        = string
  default     = ""
}

variable "data_lake_bucket_suffix" {
  description = "Suffix appended to the generated data lake bucket name."
  type        = string
  default     = "datalake"
}

variable "data_lake_bucket_force_destroy" {
  description = "Whether Terraform may destroy the data lake bucket even when it contains objects. Keep true for dev and sandbox environments."
  type        = bool
  default     = true
}

variable "glue_worker_type" {
  description = "Glue job worker type (e.g. G.1X, G.2X)."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Number of Glue workers allocated to the medallion ETL job."
  type        = number
  default     = 2
}

variable "glue_job_timeout_minutes" {
  description = "Glue job timeout in minutes."
  type        = number
  default     = 15
}
