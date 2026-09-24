variable "name_prefix" {
  description = "Naming prefix applied to the workgroup name."
  type        = string
}

variable "data_lake_bucket_name" {
  description = "S3 bucket where Athena writes query results."
  type        = string
}

variable "athena_results_prefix" {
  description = "Prefix within the data lake bucket used for Athena query results."
  type        = string
}

variable "tags" {
  description = "Common tags applied to all resources in this module."
  type        = map(string)
}
