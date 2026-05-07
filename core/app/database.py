"""
Configuración de conexiones a SQL Server y MongoDB.
"""

import os
import pyodbc
from pymongo import MongoClient


def get_sql_connection():
    """Obtiene conexión a SQL Server con AdventureWorksLT."""
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('SQL_SERVER_HOST', 'sqlserver')},{os.getenv('SQL_SERVER_PORT', '1433')};"
        f"DATABASE={os.getenv('SQL_SERVER_DB', 'AdventureWorksLT')};"
        f"UID={os.getenv('SQL_SERVER_USER', 'sa')};"
        f"PWD={os.getenv('SQL_SERVER_PASSWORD', 'AdventureWorks2024!')};"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def get_mongo_client():
    """Obtiene cliente MongoDB."""
    host = os.getenv('MONGO_HOST', 'mongodb')
    port = os.getenv('MONGO_PORT', '27017')
    user = os.getenv('MONGO_USER', 'admin')
    password = os.getenv('MONGO_PASSWORD', 'MongoAdmin2024!')
    
    uri = f"mongodb://{user}:{password}@{host}:{port}/?authSource=admin"
    return MongoClient(uri)


def get_mongo_db():
    """Obtiene la base de datos MongoDB destino."""
    client = get_mongo_client()
    db_name = os.getenv('MONGO_DB', 'adventureworks_nosql')
    return client[db_name]
