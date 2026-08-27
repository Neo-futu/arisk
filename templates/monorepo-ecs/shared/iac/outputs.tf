output "rds_endpoint" {
  value = aws_db_instance.main.address
}

output "rds_resource_id" {
  value = aws_db_instance.main.resource_id
}

output "rds_sg_id" {
  value = aws_security_group.rds.id
}
