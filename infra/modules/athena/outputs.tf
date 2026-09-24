output "workgroup_name" {
  description = "Athena workgroup configured for the data lake, with results written to the data lake bucket."
  value       = aws_athena_workgroup.datalake.name
}
