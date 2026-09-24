# ADR 0001: Remove AWS Lake Formation from the lab stack

## Status

Accepted

## Context

Lake Formation was used to register the data lake S3 bucket and grant the
Glue execution role access to it, as a teaching example of fine-grained data
lake governance.

In practice it has caused repeated `terraform destroy` failures:

* `DeregisterResource` fails with `InvalidInputException: Must manually
  delete service-linked role to deregister last S3 location` — Lake
  Formation refuses to deregister the last S3 location while the
  account-level service-linked role (`AWSServiceRoleForLakeFormationDataAccess`)
  still exists, and that role is not managed by Terraform, so it must be
  deleted out-of-band via the AWS CLI/IAM console before every destroy.
* This makes the lab's teardown workflow unreliable for students, who are
  expected to be able to `terraform destroy` cleanly without manual AWS CLI
  intervention.

The Glue execution role (`aws_iam_role.data_job_execution` in
[`infra/main.tf`](../../../infra/main.tf)) does not rely on Lake Formation
grants for its S3/Glue Catalog access — that access is already granted
directly through IAM policies (`AWSGlueServiceRole` attachment plus the
CloudWatch logs inline policy). Lake Formation's `ALL` database grant and
`DATA_LOCATION_ACCESS` grant in
[`infra/lakeformation.tf`](../../../infra/lakeformation.tf) are redundant
with those IAM permissions for this lab's scope, which does not exercise
column/row-level Lake Formation permissions.

## Decision

Remove Lake Formation from the Terraform stack:

* Delete [`infra/lakeformation.tf`](../../../infra/lakeformation.tf)
  entirely (`aws_lakeformation_data_lake_settings`,
  `aws_lakeformation_resource`, `time_sleep` propagation resource, and both
  `aws_lakeformation_permissions` grants).
* Data access for the Glue execution role continues to be governed purely by
  IAM (already in place, no changes needed there).
* The manual Lake Formation exercise (restricting an Analyst role to
  Gold-only) referenced in
  `docs/sesion_04_laboratorio_challenges.md`, Parte 9, remains a
  console-only, optional exercise and is unaffected by this change — it was
  never backed by Terraform-managed resources.

## Consequences

* `terraform destroy` no longer requires manually deleting the Lake
  Formation service-linked role first; teardown becomes fully
  Terraform-driven again.
* The lab no longer demonstrates Lake Formation registration/grants via
  Terraform. Fine-grained data lake governance is out of scope for this
  lab's IaC; it can be reintroduced later as a separate, explicitly-scoped
  exercise if needed.
* Any pre-existing deployed environment must have its Lake Formation
  resources destroyed (following the manual service-linked-role deletion
  workaround one last time) before or during the `terraform destroy` that
  removes them from state, since Terraform will otherwise try to manage
  resources no longer present in code.
