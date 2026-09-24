variable "name_prefix" {
  description = "Naming prefix applied to Glue resource names."
  type        = string
}

variable "execution_role_arn" {
  description = "IAM role ARN used by the Glue job and crawlers."
  type        = string
}

variable "data_lake_bucket_name" {
  description = "S3 bucket backing the data lake (script location, bronze/silver/gold/temp paths)."
  type        = string
}

variable "glue_script_s3_key" {
  description = "S3 key of the Glue transform script within the data lake bucket."
  type        = string
}

variable "bronze_prefix" {
  description = "Logical Bronze prefix (raw orders data, no source= subfolder)."
  type        = string
}

variable "silver_prefix" {
  description = "Logical Silver prefix (cleaned Parquet)."
  type        = string
}

variable "gold_prefix" {
  description = "Logical Gold prefix (aggregated Parquet, partitioned by year/month/day)."
  type        = string
}

variable "temp_prefix" {
  description = "Logical prefix used as the Glue job's --TempDir."
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group name for continuous logging."
  type        = string
}

variable "worker_type" {
  description = "Glue job worker type (e.g. G.1X, G.2X)."
  type        = string
}

variable "number_of_workers" {
  description = "Number of Glue workers allocated to the medallion ETL job."
  type        = number
}

variable "job_timeout_minutes" {
  description = "Glue job timeout in minutes."
  type        = number
}

variable "tags" {
  description = "Common tags applied to all resources in this module."
  type        = map(string)
}
