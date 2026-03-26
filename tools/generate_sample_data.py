#!/usr/bin/env python3
"""
Sample Data Generator for SMCP Connectors
=========================================

Generates realistic sample datasets for testing SMCP connectors.
Supports multiple data domains and export formats (CSV, JSON, Parquet).

Available Datasets:
- E-commerce: customers, orders, products, reviews
- SaaS: users, subscriptions, usage_metrics, support_tickets
- IoT: devices, sensor_readings, alerts
- Financial: transactions, accounts, market_data
- HR: employees, departments, performance_reviews
"""

import csv
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Optional dependencies for enhanced data generation
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SampleDataGenerator:
    """Generate realistic sample data for testing SMCP connectors"""
    
    def __init__(self, seed: Optional[int] = None):
        """
        Initialize the data generator
        
        Args:
            seed: Random seed for reproducible data generation
        """
        if seed:
            random.seed(seed)
        
        # Sample data pools
        self.first_names = [
            "Alice", "Bob", "Carol", "David", "Eva", "Frank", "Grace", "Henry", "Ivy", "Jack",
            "Kate", "Liam", "Maya", "Noah", "Olivia", "Paul", "Quinn", "Rachel", "Sam", "Tina",
            "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zoe"
        ]
        
        self.last_names = [
            "Anderson", "Brown", "Chen", "Davis", "Evans", "Foster", "Garcia", "Harris", "Johnson", "Kim",
            "Lee", "Martin", "Nelson", "O'Connor", "Patel", "Quinn", "Rodriguez", "Smith", "Taylor", "Wilson"
        ]
        
        self.companies = [
            "TechCorp", "DataSystems", "CloudWorks", "InnovateIO", "StreamLine", "MetricsLab", 
            "AnalyticsPro", "ScaleOps", "DevFlow", "CodeBase", "ApiFirst", "MicroTech"
        ]
        
        self.cities = [
            "San Francisco", "New York", "London", "Berlin", "Tokyo", "Singapore", 
            "Toronto", "Sydney", "Mumbai", "São Paulo", "Amsterdam", "Stockholm"
        ]
        
        self.product_names = [
            "Widget Pro", "Data Analyzer", "Cloud Dashboard", "API Gateway", "Stream Processor",
            "Analytics Engine", "Security Scanner", "Performance Monitor", "Code Assistant", "Deploy Tool"
        ]
        
        self.departments = [
            "Engineering", "Product", "Sales", "Marketing", "Customer Success", "Operations",
            "Finance", "Human Resources", "Legal", "Design"
        ]
        
        self.device_types = [
            "Temperature Sensor", "Humidity Sensor", "Motion Detector", "Camera", "Light Sensor",
            "Pressure Gauge", "Flow Meter", "Air Quality Monitor", "GPS Tracker", "Accelerometer"
        ]
    
    def generate_ecommerce_data(self, num_customers: int = 1000, num_orders: int = 5000) -> Dict[str, List[Dict]]:
        """
        Generate e-commerce dataset
        
        Args:
            num_customers: Number of customers to generate
            num_orders: Number of orders to generate
            
        Returns:
            Dict containing customers, orders, products, and reviews datasets
        """
        logger.info(f"Generating e-commerce data: {num_customers} customers, {num_orders} orders")
        
        # Generate customers
        customers = []
        for i in range(num_customers):
            customer_id = f"cust_{i+1:06d}"
            customers.append({
                "customer_id": customer_id,
                "first_name": random.choice(self.first_names),
                "last_name": random.choice(self.last_names),
                "email": f"user{i+1}@example.com",
                "city": random.choice(self.cities),
                "registration_date": self._random_date(days_back=365*2),
                "lifetime_value": round(random.uniform(50, 5000), 2),
                "is_premium": random.choice([True, False]),
                "acquisition_channel": random.choice(["organic", "paid_search", "social", "referral", "email"])
            })
        
        # Generate products
        products = []
        for i in range(50):
            product_id = f"prod_{i+1:03d}"
            products.append({
                "product_id": product_id,
                "name": f"{random.choice(self.product_names)} {random.choice(['Basic', 'Pro', 'Enterprise'])}",
                "category": random.choice(["Software", "Hardware", "Services", "Accessories"]),
                "price": round(random.uniform(9.99, 999.99), 2),
                "cost": round(random.uniform(5.0, 500.0), 2),
                "in_stock": random.randint(0, 1000),
                "rating": round(random.uniform(3.0, 5.0), 1),
                "launch_date": self._random_date(days_back=365*3)
            })
        
        # Generate orders
        orders = []
        for i in range(num_orders):
            customer = random.choice(customers)
            product = random.choice(products)
            quantity = random.randint(1, 5)
            
            order_id = f"ord_{i+1:07d}"
            orders.append({
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "product_id": product["product_id"],
                "quantity": quantity,
                "unit_price": product["price"],
                "total_amount": round(quantity * product["price"], 2),
                "order_date": self._random_date(days_back=365),
                "status": random.choice(["pending", "shipped", "delivered", "cancelled"]),
                "shipping_cost": round(random.uniform(0, 25), 2),
                "payment_method": random.choice(["credit_card", "paypal", "bank_transfer", "crypto"])
            })
        
        # Generate reviews
        reviews = []
        for i in range(min(num_orders // 3, 1000)):  # ~33% of orders get reviews
            order = random.choice(orders)
            review_id = f"rev_{i+1:06d}"
            
            reviews.append({
                "review_id": review_id,
                "order_id": order["order_id"],
                "customer_id": order["customer_id"],
                "product_id": order["product_id"],
                "rating": random.randint(1, 5),
                "review_text": f"{'Great' if random.random() > 0.3 else 'Poor'} product experience",
                "review_date": self._random_date_after(order["order_date"], max_days=30),
                "verified_purchase": True,
                "helpful_votes": random.randint(0, 50)
            })
        
        return {
            "customers": customers,
            "orders": orders,
            "products": products,
            "reviews": reviews
        }
    
    def generate_saas_data(self, num_users: int = 500, num_usage_records: int = 10000) -> Dict[str, List[Dict]]:
        """
        Generate SaaS business dataset
        
        Args:
            num_users: Number of users to generate
            num_usage_records: Number of usage metric records
            
        Returns:
            Dict containing users, subscriptions, usage_metrics, and support_tickets
        """
        logger.info(f"Generating SaaS data: {num_users} users, {num_usage_records} usage records")
        
        # Generate users
        users = []
        for i in range(num_users):
            user_id = f"user_{i+1:06d}"
            users.append({
                "user_id": user_id,
                "email": f"user{i+1}@{random.choice(['startup', 'corp', 'tech'])}.com",
                "company": random.choice(self.companies),
                "role": random.choice(["Admin", "Developer", "Analyst", "Manager", "User"]),
                "signup_date": self._random_date(days_back=365*2),
                "last_active": self._random_date(days_back=30),
                "is_active": random.choice([True, True, True, False]),  # 75% active
                "plan": random.choice(["free", "basic", "pro", "enterprise"]),
                "monthly_spend": round(random.uniform(0, 500), 2)
            })
        
        # Generate subscriptions
        subscriptions = []
        for user in users:
            if user["plan"] != "free":
                sub_id = f"sub_{len(subscriptions)+1:06d}"
                start_date = user["signup_date"]
                
                subscriptions.append({
                    "subscription_id": sub_id,
                    "user_id": user["user_id"],
                    "plan": user["plan"],
                    "status": random.choice(["active", "active", "active", "cancelled", "paused"]),
                    "start_date": start_date,
                    "end_date": self._random_date_after(start_date, max_days=365) if random.random() < 0.2 else None,
                    "monthly_price": {"basic": 29, "pro": 99, "enterprise": 299}[user["plan"]],
                    "billing_cycle": random.choice(["monthly", "annual"]),
                    "auto_renew": random.choice([True, False])
                })
        
        # Generate usage metrics
        usage_metrics = []
        for i in range(num_usage_records):
            user = random.choice(users)
            metric_id = f"usage_{i+1:07d}"
            
            usage_metrics.append({
                "metric_id": metric_id,
                "user_id": user["user_id"],
                "date": self._random_date(days_back=90),
                "api_calls": random.randint(0, 10000),
                "data_processed_mb": round(random.uniform(0, 1000), 2),
                "active_time_minutes": random.randint(0, 480),  # 8 hours max
                "features_used": random.randint(1, 20),
                "error_rate": round(random.uniform(0, 0.05), 4),
                "response_time_ms": round(random.uniform(50, 2000), 1)
            })
        
        # Generate support tickets
        support_tickets = []
        for i in range(num_users // 4):  # 25% of users create tickets
            user = random.choice(users)
            ticket_id = f"ticket_{i+1:06d}"
            
            support_tickets.append({
                "ticket_id": ticket_id,
                "user_id": user["user_id"],
                "subject": random.choice([
                    "API Integration Issue", "Billing Question", "Feature Request", 
                    "Performance Problem", "Account Access", "Data Export"
                ]),
                "priority": random.choice(["low", "medium", "high", "urgent"]),
                "status": random.choice(["open", "in_progress", "resolved", "closed"]),
                "created_date": self._random_date(days_back=180),
                "resolved_date": self._random_date(days_back=150) if random.random() < 0.7 else None,
                "category": random.choice(["technical", "billing", "general", "feature"]),
                "satisfaction_score": random.randint(1, 5) if random.random() < 0.6 else None
            })
        
        return {
            "users": users,
            "subscriptions": subscriptions,
            "usage_metrics": usage_metrics,
            "support_tickets": support_tickets
        }
    
    def generate_iot_data(self, num_devices: int = 100, num_readings: int = 50000) -> Dict[str, List[Dict]]:
        """
        Generate IoT sensor dataset
        
        Args:
            num_devices: Number of IoT devices
            num_readings: Number of sensor readings
            
        Returns:
            Dict containing devices, sensor_readings, and alerts
        """
        logger.info(f"Generating IoT data: {num_devices} devices, {num_readings} readings")
        
        # Generate devices
        devices = []
        for i in range(num_devices):
            device_id = f"device_{i+1:05d}"
            devices.append({
                "device_id": device_id,
                "device_type": random.choice(self.device_types),
                "location": random.choice(self.cities),
                "building": f"Building {chr(65 + (i % 26))}",  # A, B, C, etc.
                "floor": random.randint(1, 10),
                "room": f"Room {random.randint(100, 999)}",
                "installed_date": self._random_date(days_back=365*2),
                "last_maintenance": self._random_date(days_back=90),
                "firmware_version": f"{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}",
                "is_active": random.choice([True, True, True, False]),  # 75% active
                "battery_level": round(random.uniform(10, 100), 1) if random.random() < 0.8 else None
            })
        
        # Generate sensor readings
        sensor_readings = []
        for i in range(num_readings):
            device = random.choice(devices)
            reading_id = f"reading_{i+1:07d}"
            
            # Generate realistic sensor values based on device type
            if "Temperature" in device["device_type"]:
                value = round(random.uniform(18, 28), 2)  # Celsius
                unit = "°C"
            elif "Humidity" in device["device_type"]:
                value = round(random.uniform(30, 80), 2)  # Percentage
                unit = "%"
            elif "Pressure" in device["device_type"]:
                value = round(random.uniform(1000, 1030), 2)  # hPa
                unit = "hPa"
            elif "Light" in device["device_type"]:
                value = round(random.uniform(0, 1000), 2)  # Lux
                unit = "lux"
            else:
                value = round(random.uniform(0, 100), 2)
                unit = "units"
            
            sensor_readings.append({
                "reading_id": reading_id,
                "device_id": device["device_id"],
                "timestamp": self._random_datetime(days_back=30),
                "value": value,
                "unit": unit,
                "quality_score": round(random.uniform(0.8, 1.0), 3),
                "is_anomaly": random.choice([False] * 95 + [True] * 5),  # 5% anomalies
                "processing_time_ms": round(random.uniform(10, 500), 1)
            })
        
        # Generate alerts
        alerts = []
        anomaly_readings = [r for r in sensor_readings if r["is_anomaly"]]
        
        for i, reading in enumerate(anomaly_readings[:200]):  # Max 200 alerts
            alert_id = f"alert_{i+1:06d}"
            
            alerts.append({
                "alert_id": alert_id,
                "device_id": reading["device_id"],
                "reading_id": reading["reading_id"],
                "alert_type": random.choice(["threshold_exceeded", "sensor_failure", "communication_lost", "battery_low"]),
                "severity": random.choice(["low", "medium", "high", "critical"]),
                "message": f"Anomaly detected: {reading['value']} {reading['unit']}",
                "timestamp": reading["timestamp"],
                "acknowledged": random.choice([True, False]),
                "resolved_timestamp": self._random_datetime_after(reading["timestamp"], max_hours=24) if random.random() < 0.7 else None
            })
        
        return {
            "devices": devices,
            "sensor_readings": sensor_readings,
            "alerts": alerts
        }
    
    def save_datasets(self, datasets: Dict[str, List[Dict]], output_dir: str, formats: List[str] = ["csv"]):
        """
        Save datasets to files in specified formats
        
        Args:
            datasets: Dictionary of dataset name -> records
            output_dir: Directory to save files
            formats: List of formats to save (csv, json, parquet)
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)
        
        for dataset_name, records in datasets.items():
            if not records:
                continue
                
            logger.info(f"Saving {dataset_name}: {len(records)} records")
            
            # Save as CSV
            if "csv" in formats:
                csv_path = output_path / f"{dataset_name}.csv"
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    if records:
                        writer = csv.DictWriter(f, fieldnames=records[0].keys())
                        writer.writeheader()
                        writer.writerows(records)
                logger.info(f"  Saved CSV: {csv_path}")
            
            # Save as JSON
            if "json" in formats:
                json_path = output_path / f"{dataset_name}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(records, f, indent=2, default=str)
                logger.info(f"  Saved JSON: {json_path}")
            
            # Save as Parquet (requires pandas and pyarrow)
            if "parquet" in formats and PANDAS_AVAILABLE and PYARROW_AVAILABLE:
                try:
                    df = pd.DataFrame(records)
                    parquet_path = output_path / f"{dataset_name}.parquet"
                    df.to_parquet(parquet_path, index=False)
                    logger.info(f"  Saved Parquet: {parquet_path}")
                except Exception as e:
                    logger.warning(f"  Could not save Parquet for {dataset_name}: {e}")
    
    def _random_date(self, days_back: int = 365) -> str:
        """Generate random date string"""
        start_date = datetime.now() - timedelta(days=days_back)
        random_days = random.randint(0, days_back)
        date = start_date + timedelta(days=random_days)
        return date.strftime("%Y-%m-%d")
    
    def _random_datetime(self, days_back: int = 365) -> str:
        """Generate random datetime string"""
        start_date = datetime.now() - timedelta(days=days_back)
        random_seconds = random.randint(0, days_back * 24 * 3600)
        dt = start_date + timedelta(seconds=random_seconds)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _random_date_after(self, start_date_str: str, max_days: int = 30) -> str:
        """Generate random date after given start date"""
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        random_days = random.randint(1, max_days)
        date = start_date + timedelta(days=random_days)
        return date.strftime("%Y-%m-%d")
    
    def _random_datetime_after(self, start_datetime_str: str, max_hours: int = 24) -> str:
        """Generate random datetime after given start datetime"""
        start_dt = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M:%S")
        random_seconds = random.randint(1, max_hours * 3600)
        dt = start_dt + timedelta(seconds=random_seconds)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    """Generate sample datasets and save to files"""
    generator = SampleDataGenerator(seed=42)  # Reproducible data
    
    output_dir = Path(__file__).parent.parent / "sample_data"
    
    # Generate different datasets
    print("🏪 Generating E-commerce Dataset...")
    ecommerce_data = generator.generate_ecommerce_data(num_customers=1000, num_orders=5000)
    generator.save_datasets(ecommerce_data, output_dir / "ecommerce", formats=["csv", "json"])
    
    print("\n💼 Generating SaaS Dataset...")
    saas_data = generator.generate_saas_data(num_users=500, num_usage_records=10000)
    generator.save_datasets(saas_data, output_dir / "saas", formats=["csv", "json"])
    
    print("\n🔌 Generating IoT Dataset...")
    iot_data = generator.generate_iot_data(num_devices=100, num_readings=20000)
    generator.save_datasets(iot_data, output_dir / "iot", formats=["csv", "json"])
    
    print(f"\n✅ Sample data generated successfully in {output_dir}")
    print("\n📊 Dataset Summary:")
    
    # Print summary
    all_datasets = [
        ("E-commerce", ecommerce_data),
        ("SaaS", saas_data),
        ("IoT", iot_data)
    ]
    
    for domain_name, datasets in all_datasets:
        print(f"\n{domain_name}:")
        for table_name, records in datasets.items():
            print(f"  • {table_name}: {len(records):,} records")


if __name__ == "__main__":
    main()