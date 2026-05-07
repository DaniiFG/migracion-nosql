#!/bin/bash

# Iniciar SQL Server en background
/opt/mssql/bin/sqlservr &

# Esperar a que SQL Server esté listo
echo "Esperando a que SQL Server inicie..."
sleep 15

# Intentar conectarse hasta que funcione
for i in {1..30}; do
    /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "SELECT 1" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "SQL Server está listo!"
        break
    fi
    echo "Esperando SQL Server... intento $i"
    sleep 2
done

# Verificar si la base de datos ya existe
DB_EXISTS=$(/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "SELECT COUNT(*) FROM sys.databases WHERE name = 'AdventureWorksLT'" -h -1 -W 2>/dev/null | head -1 | tr -d '[:space:]')

if [ "$DB_EXISTS" != "1" ]; then
    echo "Restaurando base de datos AdventureWorksLT..."
    /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -i /var/opt/mssql/restore-db.sql
    echo "Base de datos restaurada exitosamente!"
else
    echo "La base de datos AdventureWorksLT ya existe. Saltando restauración."
fi

# Mantener el proceso en primer plano
wait
