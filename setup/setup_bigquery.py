#!/usr/bin/env python3
"""
=============================================================================
Secure Customer Service Agent - BigQuery Setup
=============================================================================
Creates tables and loads sample data for the customer service agent.

Tables created:
  customer_service.customers  - Customer information (agent CAN access)
  customer_service.orders     - Order history (agent CAN access)
  customer_service.products   - Product catalog (agent CAN access)
  admin.audit_log            - Admin audit logs (agent CANNOT access)
=============================================================================
"""

import os
from google.cloud import bigquery

# Get project ID from environment or gcloud config
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
if not PROJECT_ID:
    import subprocess
    PROJECT_ID = subprocess.check_output(
        ["gcloud", "config", "get-value", "project"],
        text=True
    ).strip()

print(f"   Setting up BigQuery tables for project: {PROJECT_ID}")

client = bigquery.Client(project=PROJECT_ID)

# =============================================================================
# Table Schemas
# =============================================================================

CUSTOMERS_SCHEMA = [
    bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED",
                        description="Unique customer identifier"),
    bigquery.SchemaField("name", "STRING", mode="REQUIRED",
                        description="Customer full name"),
    bigquery.SchemaField("email", "STRING", mode="REQUIRED",
                        description="Customer email address"),
    bigquery.SchemaField("tier", "STRING", mode="REQUIRED",
                        description="Customer tier: Bronze, Silver, Gold, Platinum"),
    bigquery.SchemaField("created_date", "DATE", mode="REQUIRED",
                        description="Account creation date"),
    bigquery.SchemaField("phone", "STRING", mode="NULLABLE",
                        description="Customer phone number"),
]

ORDERS_SCHEMA = [
    bigquery.SchemaField("order_id", "STRING", mode="REQUIRED",
                        description="Unique order identifier"),
    bigquery.SchemaField("customer_id", "STRING", mode="REQUIRED",
                        description="Reference to customer"),
    bigquery.SchemaField("order_date", "DATE", mode="REQUIRED",
                        description="Date order was placed"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED",
                        description="Order status: pending, processing, shipped, delivered, cancelled"),
    bigquery.SchemaField("total_amount", "FLOAT64", mode="REQUIRED",
                        description="Total order amount in USD"),
    bigquery.SchemaField("shipping_address", "STRING", mode="NULLABLE",
                        description="Shipping address"),
    bigquery.SchemaField("tracking_number", "STRING", mode="NULLABLE",
                        description="Shipping tracking number"),
    bigquery.SchemaField("items", "STRING", mode="NULLABLE",
                        description="JSON array of order items"),
]

PRODUCTS_SCHEMA = [
    bigquery.SchemaField("product_id", "STRING", mode="REQUIRED",
                        description="Unique product identifier"),
    bigquery.SchemaField("name", "STRING", mode="REQUIRED",
                        description="Product name"),
    bigquery.SchemaField("category", "STRING", mode="REQUIRED",
                        description="Product category"),
    bigquery.SchemaField("price", "FLOAT64", mode="REQUIRED",
                        description="Product price in USD"),
    bigquery.SchemaField("in_stock", "BOOLEAN", mode="REQUIRED",
                        description="Whether product is in stock"),
    bigquery.SchemaField("description", "STRING", mode="NULLABLE",
                        description="Product description"),
]

AUDIT_LOG_SCHEMA = [
    bigquery.SchemaField("log_id", "STRING", mode="REQUIRED",
                        description="Unique log entry identifier"),
    bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED",
                        description="When the event occurred"),
    bigquery.SchemaField("admin_user", "STRING", mode="REQUIRED",
                        description="Admin user who performed action"),
    bigquery.SchemaField("action", "STRING", mode="REQUIRED",
                        description="Action performed"),
    bigquery.SchemaField("target_resource", "STRING", mode="NULLABLE",
                        description="Resource affected"),
    bigquery.SchemaField("ip_address", "STRING", mode="NULLABLE",
                        description="IP address of admin"),
    bigquery.SchemaField("details", "STRING", mode="NULLABLE",
                        description="Additional details in JSON format"),
]

# =============================================================================
# Sample Data
# =============================================================================

CUSTOMERS_DATA = [
    {
        "customer_id": "CUST-001",
        "name": "Alice Johnson",
        "email": "alice.johnson@email.com",
        "tier": "Gold",
        "created_date": "2023-01-15",
        "phone": "+1-555-0101",
    },
    {
        "customer_id": "CUST-002",
        "name": "Bob Smith",
        "email": "bob.smith@email.com",
        "tier": "Silver",
        "created_date": "2023-03-22",
        "phone": "+1-555-0102",
    },
    {
        "customer_id": "CUST-003",
        "name": "Carol Williams",
        "email": "carol.w@email.com",
        "tier": "Platinum",
        "created_date": "2022-06-10",
        "phone": "+1-555-0103",
    },
    {
        "customer_id": "CUST-004",
        "name": "David Brown",
        "email": "david.brown@email.com",
        "tier": "Bronze",
        "created_date": "2024-01-05",
        "phone": None,
    },
    {
        "customer_id": "CUST-005",
        "name": "Eva Martinez",
        "email": "eva.m@email.com",
        "tier": "Gold",
        "created_date": "2023-08-20",
        "phone": "+1-555-0105",
    },
]

ORDERS_DATA = [
    {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "2024-12-15",
        "status": "shipped",
        "total_amount": 129.99,
        "shipping_address": "123 Main St, Los Angeles, CA 90001",
        "tracking_number": "1Z999AA10123456784",
        "items": '[{"product_id": "PROD-001", "quantity": 1}, {"product_id": "PROD-003", "quantity": 2}]',
    },
    {
        "order_id": "ORD-002",
        "customer_id": "CUST-001",
        "order_date": "2024-12-20",
        "status": "processing",
        "total_amount": 79.50,
        "shipping_address": "123 Main St, Los Angeles, CA 90001",
        "tracking_number": None,
        "items": '[{"product_id": "PROD-002", "quantity": 3}]',
    },
    {
        "order_id": "ORD-003",
        "customer_id": "CUST-002",
        "order_date": "2024-12-18",
        "status": "delivered",
        "total_amount": 249.99,
        "shipping_address": "456 Oak Ave, San Francisco, CA 94102",
        "tracking_number": "1Z999AA10123456785",
        "items": '[{"product_id": "PROD-004", "quantity": 1}]',
    },
    {
        "order_id": "ORD-004",
        "customer_id": "CUST-003",
        "order_date": "2024-12-22",
        "status": "pending",
        "total_amount": 599.00,
        "shipping_address": "789 Pine Rd, Seattle, WA 98101",
        "tracking_number": None,
        "items": '[{"product_id": "PROD-005", "quantity": 1}, {"product_id": "PROD-001", "quantity": 2}]',
    },
    {
        "order_id": "ORD-005",
        "customer_id": "CUST-004",
        "order_date": "2024-12-10",
        "status": "cancelled",
        "total_amount": 45.00,
        "shipping_address": "321 Elm St, Denver, CO 80201",
        "tracking_number": None,
        "items": '[{"product_id": "PROD-002", "quantity": 2}]',
    },
    {
        "order_id": "ORD-006",
        "customer_id": "CUST-005",
        "order_date": "2024-12-25",
        "status": "processing",
        "total_amount": 189.99,
        "shipping_address": "555 Maple Dr, Austin, TX 78701",
        "tracking_number": None,
        "items": '[{"product_id": "PROD-003", "quantity": 1}, {"product_id": "PROD-004", "quantity": 1}]',
    },
]

PRODUCTS_DATA = [
    {
        "product_id": "PROD-001",
        "name": "Wireless Bluetooth Headphones",
        "category": "Electronics",
        "price": 59.99,
        "in_stock": True,
        "description": "Premium wireless headphones with 30-hour battery life and noise cancellation.",
    },
    {
        "product_id": "PROD-002",
        "name": "Organic Green Tea (50 bags)",
        "category": "Food & Beverage",
        "price": 15.00,
        "in_stock": True,
        "description": "Premium organic green tea sourced from Japan.",
    },
    {
        "product_id": "PROD-003",
        "name": "Yoga Mat - Premium",
        "category": "Sports & Fitness",
        "price": 35.00,
        "in_stock": True,
        "description": "Extra thick, non-slip yoga mat with carrying strap.",
    },
    {
        "product_id": "PROD-004",
        "name": "Smart Watch Pro",
        "category": "Electronics",
        "price": 249.99,
        "in_stock": False,
        "description": "Advanced smartwatch with health monitoring and GPS.",
    },
    {
        "product_id": "PROD-005",
        "name": "Ergonomic Office Chair",
        "category": "Furniture",
        "price": 399.00,
        "in_stock": True,
        "description": "Fully adjustable ergonomic chair with lumbar support.",
    },
]

AUDIT_LOG_DATA = [
    {
        "log_id": "LOG-001",
        "timestamp": "2024-12-20T10:30:00Z",
        "admin_user": "admin@company.com",
        "action": "USER_PERMISSION_CHANGED",
        "target_resource": "user:alice.johnson@email.com",
        "ip_address": "10.0.0.50",
        "details": '{"old_role": "viewer", "new_role": "editor"}',
    },
    {
        "log_id": "LOG-002",
        "timestamp": "2024-12-21T14:15:00Z",
        "admin_user": "superadmin@company.com",
        "action": "DATABASE_BACKUP_CREATED",
        "target_resource": "database:customer_service",
        "ip_address": "10.0.0.1",
        "details": '{"backup_size_gb": 2.5, "backup_location": "gs://backups/"}',
    },
    {
        "log_id": "LOG-003",
        "timestamp": "2024-12-22T09:00:00Z",
        "admin_user": "admin@company.com",
        "action": "API_KEY_ROTATED",
        "target_resource": "api_key:prod-key-001",
        "ip_address": "10.0.0.50",
        "details": '{"reason": "scheduled rotation"}',
    },
    {
        "log_id": "LOG-004",
        "timestamp": "2024-12-23T16:45:00Z",
        "admin_user": "security@company.com",
        "action": "SECURITY_ALERT_ACKNOWLEDGED",
        "target_resource": "alert:suspicious-login-attempt",
        "ip_address": "10.0.0.100",
        "details": '{"alert_severity": "high", "source_ip": "203.0.113.50"}',
    },
]


def create_table_if_not_exists(dataset_id: str, table_id: str, schema: list) -> bigquery.Table:
    """Create a table if it doesn't exist."""
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
    
    try:
        table = client.get_table(table_ref)
        print(f"   ✓ Table '{dataset_id}.{table_id}' already exists")
        return table
    except Exception:
        table = bigquery.Table(table_ref, schema=schema)
        table = client.create_table(table)
        print(f"   ✓ Created table '{dataset_id}.{table_id}'")
        return table


def load_data(dataset_id: str, table_id: str, data: list):
    """Load data into a table."""
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"
    
    # Check if table already has data
    query = f"SELECT COUNT(*) as count FROM `{table_ref}`"
    result = list(client.query(query).result())[0]
    
    if result.count > 0:
        print(f"   ✓ Table '{dataset_id}.{table_id}' already has {result.count} rows")
        return
    
    # Load data
    errors = client.insert_rows_json(table_ref, data)
    if errors:
        print(f"   ✗ Errors loading data into '{dataset_id}.{table_id}': {errors}")
    else:
        print(f"   ✓ Loaded {len(data)} rows into '{dataset_id}.{table_id}'")


def main():
    print("")
    
    # Create tables
    print("   Creating tables...")
    create_table_if_not_exists("customer_service", "customers", CUSTOMERS_SCHEMA)
    create_table_if_not_exists("customer_service", "orders", ORDERS_SCHEMA)
    create_table_if_not_exists("customer_service", "products", PRODUCTS_SCHEMA)
    create_table_if_not_exists("admin", "audit_log", AUDIT_LOG_SCHEMA)
    
    print("")
    print("   Loading sample data...")
    load_data("customer_service", "customers", CUSTOMERS_DATA)
    load_data("customer_service", "orders", ORDERS_DATA)
    load_data("customer_service", "products", PRODUCTS_DATA)
    load_data("admin", "audit_log", AUDIT_LOG_DATA)
    
    print("")
    print("   ✅ BigQuery setup complete!")


if __name__ == "__main__":
    main()
