FROM mcr.microsoft.com/mssql/server:2022-latest

# Cambiar a root para instalar dependencias
USER root

# Instalar herramientas necesarias
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*

# Crear directorio para backups
RUN mkdir -p /var/opt/mssql/backup && chown -R mssql:root /var/opt/mssql/backup

# Descargar AdventureWorksLT2022.bak directamente desde GitHub
RUN curl -L -o /var/opt/mssql/backup/AdventureWorksLT2022.bak \
    "https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorksLT2022.bak" && \
    chown mssql:root /var/opt/mssql/backup/AdventureWorksLT2022.bak

# Copiar script de inicialización
COPY setup.sh /var/opt/mssql/setup.sh
COPY restore-db.sql /var/opt/mssql/restore-db.sql

RUN chmod +x /var/opt/mssql/setup.sh

# Volver a usuario mssql
USER mssql

# Ejecutar SQL Server y luego el script de restauración
CMD /bin/bash /var/opt/mssql/setup.sh
