data "aws_caller_identity" "current" {}

locals {
  name_prefix = lower(replace(var.project_name, "_", "-"))
  common_tags = merge(
    var.tags,
    {
      Project    = var.project_name
      Owner      = var.owner
      ManagedBy  = "Terraform"
      CostCenter = var.cost_center
    }
  )
}

module "iam" {
  source = "./modules/iam"

  name_prefix             = local.name_prefix
  execution_role_name     = var.execution_role_name
  log_retention_days      = var.log_retention_days
  enable_budget_guardrail = var.enable_budget_guardrail
  budget_limit_usd        = var.budget_limit_usd
  budget_alert_email      = var.budget_alert_email
  project_name            = var.project_name
  tags                    = local.common_tags
}

module "s3_datalake" {
  source = "./modules/s3_datalake"

  name_prefix                  = local.name_prefix
  account_id                   = data.aws_caller_identity.current.account_id
  bucket_suffix                = var.data_lake_bucket_suffix
  force_destroy                = var.data_lake_bucket_force_destroy
  glue_script_path             = "${path.module}/../src/glue/transform.py"
  data_job_execution_role_name = module.iam.execution_role_name
  tags                         = local.common_tags
}

module "glue" {
  source = "./modules/glue"

  name_prefix           = local.name_prefix
  execution_role_arn    = module.iam.execution_role_arn
  data_lake_bucket_name = module.s3_datalake.bucket_name
  glue_script_s3_key    = module.s3_datalake.glue_script_s3_key
  bronze_prefix         = module.s3_datalake.bronze_prefix
  silver_prefix         = module.s3_datalake.silver_prefix
  gold_prefix           = module.s3_datalake.gold_prefix
  temp_prefix           = module.s3_datalake.temp_prefix
  log_group_name        = module.iam.log_group_name
  worker_type           = var.glue_worker_type
  number_of_workers     = var.glue_number_of_workers
  job_timeout_minutes   = var.glue_job_timeout_minutes
  tags                  = local.common_tags
}

module "athena" {
  source = "./modules/athena"

  name_prefix           = local.name_prefix
  data_lake_bucket_name = module.s3_datalake.bucket_name
  athena_results_prefix = module.s3_datalake.athena_results_prefix
  tags                  = local.common_tags
}
