output "database_name" {
  description = "Glue Data Catalog database holding the bronze/silver/gold tables."
  value       = aws_glue_catalog_database.datalake_db.name
}

output "job_name" {
  description = "Glue job that runs the Bronze -> Silver -> Gold medallion ETL."
  value       = aws_glue_job.orders_medallion.name
}

output "silver_crawler_name" {
  description = "Glue crawler that catalogs the Silver prefix as silver_orders."
  value       = aws_glue_crawler.silver_crawler.name
}

output "gold_crawler_name" {
  description = "Glue crawler that catalogs the Gold prefix as gold_orders."
  value       = aws_glue_crawler.gold_crawler.name
}
