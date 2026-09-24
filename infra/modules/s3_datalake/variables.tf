variable "name_prefix" {
  description = "Naming prefix applied to the bucket name."
  type        = string
}

variable "account_id" {
  description = "AWS account ID, used to keep the generated bucket name globally unique."
  type        = string
}

variable "bucket_suffix" {
  description = "Suffix appended to the generated data lake bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Whether Terraform may destroy the data lake bucket even when it contains objects."
  type        = bool
}

variable "glue_script_path" {
  description = "Local path to the Glue ETL script uploaded to the scripts/ prefix."
  type        = string
}

variable "data_job_execution_role_name" {
  description = "Name of the IAM role (from the iam module) that needs read/write/list access to this bucket. The inline policy is declared here, not in the iam module, because the bucket ARN is only known in this module."
  type        = string
}

variable "tags" {
  description = "Common tags applied to all resources in this module."
  type        = map(string)
}
