"""
Router para consultar datos de SQL Server (AdventureWorksLT).
Permite listar tablas, ver datos y ejecutar consultas.
"""

from fastapi import APIRouter, HTTPException, Query
import pandas as pd
from app.database import get_sql_connection

router = APIRouter()


@router.get("/tables")
async def list_tables():
    """Lista todas las tablas de AdventureWorksLT con su conteo de registros."""
    try:
        conn = get_sql_connection()
        query = """
            SELECT 
                s.name AS schema_name,
                t.name AS table_name,
                SUM(p.rows) AS row_count
            FROM sys.tables t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            INNER JOIN sys.partitions p ON t.object_id = p.object_id
            WHERE p.index_id IN (0, 1)
            GROUP BY s.name, t.name
            ORDER BY s.name, t.name
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        tables = df.to_dict(orient='records')
        total_rows = int(df['row_count'].sum())
        
        return {
            "total_tables": len(tables),
            "total_rows": total_rows,
            "tables": tables
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al conectar con SQL Server: {str(e)}")


@router.get("/table/{schema_name}/{table_name}")
async def get_table_data(
    schema_name: str, 
    table_name: str, 
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """Obtiene datos de una tabla específica de SQL Server."""
    try:
        conn = get_sql_connection()
        
        # Obtener total de filas
        count_query = f"SELECT COUNT(*) as total FROM [{schema_name}].[{table_name}]"
        total = pd.read_sql(count_query, conn)['total'].iloc[0]
        
        # Obtener datos paginados
        query = f"""
            SELECT * FROM [{schema_name}].[{table_name}]
            ORDER BY (SELECT NULL)
            OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Convertir tipos datetime a string para JSON
        for col in df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
            df[col] = df[col].astype(str)
        
        # Convertir bytes a string representable
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (bytes, bytearray)) else x)
        
        return {
            "schema": schema_name,
            "table": table_name,
            "total_rows": int(total),
            "offset": offset,
            "limit": limit,
            "columns": list(df.columns),
            "data": df.to_dict(orient='records')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener datos: {str(e)}")


@router.get("/schema/{schema_name}/{table_name}")
async def get_table_schema(schema_name: str, table_name: str):
    """Obtiene el esquema (columnas, tipos, FK) de una tabla SQL Server."""
    try:
        conn = get_sql_connection()
        
        # Columnas
        col_query = f"""
            SELECT 
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.CHARACTER_MAXIMUM_LENGTH,
                CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'YES' ELSE 'NO' END AS IS_PRIMARY_KEY
            FROM INFORMATION_SCHEMA.COLUMNS c
            LEFT JOIN (
                SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku 
                    ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA 
                AND c.TABLE_NAME = pk.TABLE_NAME 
                AND c.COLUMN_NAME = pk.COLUMN_NAME
            WHERE c.TABLE_SCHEMA = '{schema_name}' AND c.TABLE_NAME = '{table_name}'
            ORDER BY c.ORDINAL_POSITION
        """
        cols_df = pd.read_sql(col_query, conn)
        
        # Foreign Keys
        fk_query = f"""
            SELECT 
                fk.name AS fk_name,
                cp.name AS column_name,
                OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS ref_schema,
                OBJECT_NAME(fk.referenced_object_id) AS ref_table,
                cr.name AS ref_column
            FROM sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            INNER JOIN sys.columns cp ON fkc.parent_object_id = cp.object_id AND fkc.parent_column_id = cp.column_id
            INNER JOIN sys.columns cr ON fkc.referenced_object_id = cr.object_id AND fkc.referenced_column_id = cr.column_id
            WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = '{schema_name}'
            AND OBJECT_NAME(fk.parent_object_id) = '{table_name}'
        """
        fk_df = pd.read_sql(fk_query, conn)
        conn.close()
        
        return {
            "schema": schema_name,
            "table": table_name,
            "columns": cols_df.to_dict(orient='records'),
            "foreign_keys": fk_df.to_dict(orient='records')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener esquema: {str(e)}")


@router.get("/query")
async def execute_query(q: str = Query(..., description="Consulta SQL SELECT")):
    """Ejecuta una consulta SELECT en SQL Server (solo lectura)."""
    try:
        # Validación básica de seguridad
        q_upper = q.strip().upper()
        if not q_upper.startswith("SELECT"):
            raise HTTPException(status_code=400, detail="Solo se permiten consultas SELECT")
        
        forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "EXEC", "EXECUTE", "TRUNCATE"]
        for word in forbidden:
            if word in q_upper.split():
                raise HTTPException(status_code=400, detail=f"Operación '{word}' no permitida")
        
        conn = get_sql_connection()
        df = pd.read_sql(q, conn)
        conn.close()
        
        # Convertir tipos especiales
        for col in df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
            df[col] = df[col].astype(str)
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: str(x) if isinstance(x, (bytes, bytearray)) else x)
        
        return {
            "query": q,
            "row_count": len(df),
            "columns": list(df.columns),
            "data": df.to_dict(orient='records')
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en consulta SQL: {str(e)}")


@router.get("/relationships")
async def get_all_relationships():
    """Obtiene todas las relaciones (FK) de la base de datos."""
    try:
        conn = get_sql_connection()
        query = """
            SELECT 
                OBJECT_SCHEMA_NAME(fk.parent_object_id) AS parent_schema,
                OBJECT_NAME(fk.parent_object_id) AS parent_table,
                cp.name AS parent_column,
                OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS ref_schema,
                OBJECT_NAME(fk.referenced_object_id) AS ref_table,
                cr.name AS ref_column,
                fk.name AS fk_name
            FROM sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            INNER JOIN sys.columns cp ON fkc.parent_object_id = cp.object_id AND fkc.parent_column_id = cp.column_id
            INNER JOIN sys.columns cr ON fkc.referenced_object_id = cr.object_id AND fkc.referenced_column_id = cr.column_id
            ORDER BY parent_schema, parent_table
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        return {
            "total_relationships": len(df),
            "relationships": df.to_dict(orient='records')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener relaciones: {str(e)}")
