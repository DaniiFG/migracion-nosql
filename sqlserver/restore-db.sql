-- Restaurar AdventureWorksLT2022 desde backup
RESTORE DATABASE [AdventureWorksLT]
FROM DISK = N'/var/opt/mssql/backup/AdventureWorksLT2022.bak'
WITH 
    MOVE N'AdventureWorksLT2022_Data' TO N'/var/opt/mssql/data/AdventureWorksLT2022.mdf',
    MOVE N'AdventureWorksLT2022_log' TO N'/var/opt/mssql/data/AdventureWorksLT2022_log.ldf',
    REPLACE,
    RECOVERY;
GO

-- Verificar la restauración
USE AdventureWorksLT;
GO

SELECT 'Tablas restauradas:' AS Info;
SELECT TABLE_SCHEMA, TABLE_NAME 
FROM INFORMATION_SCHEMA.TABLES 
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;
GO

SELECT 'Total de registros por tabla:' AS Info;
SELECT 
    s.name AS SchemaName,
    t.name AS TableName,
    SUM(p.rows) AS RowCount
FROM sys.tables t
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
INNER JOIN sys.partitions p ON t.object_id = p.object_id
WHERE p.index_id IN (0, 1)
GROUP BY s.name, t.name
ORDER BY s.name, t.name;
GO
