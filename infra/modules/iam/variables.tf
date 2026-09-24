variable "name_prefix" {
  description = "Naming prefix applied to IAM resource names."
  type        = string
}

variable "execution_role_name" {
  description = "IAM role name for AWS data jobs (Glue job + crawlers)."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
}

variable "enable_budget_guardrail" {
  description = "Whether to create the monthly AWS Budget (and its SNS alert topic, if an email is set)."
  type        = bool
}

variable "budget_limit_usd" {
  description = "Monthly AWS budget limit in USD. Only used when enable_budget_guardrail is true."
  type        = number
}

variable "budget_alert_email" {
  description = "Email address for budget alerts. Leave empty to skip SNS subscription creation."
  type        = string
}

variable "project_name" {
  description = "Project name, used as the budget cost filter tag value."
  type        = string
}

variable "tags" {
  description = "Common tags applied to all resources in this module."
  type        = map(string)
}
