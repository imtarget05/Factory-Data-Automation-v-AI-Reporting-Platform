@description('Location for PostgreSQL resources')
param location string

@description('PostgreSQL server name')
param serverName string

@description('Administrator login name')
param administratorLogin string = 'factoryadmin'

@description('Administrator login password')
@secure()
param administratorLoginPassword string

@description('PostgreSQL database name')
param databaseName string = 'factory_data'

@description('SKU name for PostgreSQL Flexible Server')
param skuName string = 'Standard_B1ms'

@description('SKU tier for PostgreSQL Flexible Server')
param skuTier string = 'Burstable'

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: serverName
  location: location
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: '16'
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorLoginPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource requireSecureTransport 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
  parent: postgresServer
  name: 'require_secure_transport'
  properties: {
    value: 'ON'
    source: 'user-override'
  }
}

resource factoryDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output serverId string = postgresServer.id
output serverFqdn string = postgresServer.properties.fullyQualifiedDomainName
output databaseName string = factoryDatabase.name
output adminUsername string = administratorLogin
