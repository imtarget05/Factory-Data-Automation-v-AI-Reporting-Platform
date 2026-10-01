targetScope = 'resourceGroup'

@description('Deployment environment (dev, prod)')
@allowed([
  'dev'
  'prod'
])
param environment string = 'dev'

@description('Azure region for resources')
param location string = resourceGroup().location

@description('Resource name prefix')
@minLength(3)
@maxLength(16)
param prefix string = 'factory-${environment}'

@description('Azure AD tenant ID for Key Vault')
param tenantId string

@description('PostgreSQL administrator login password')
@secure()
param postgresAdminPassword string

@description('Application image repository')
param imageRepository string = 'mcr.microsoft.com/azuredocs/aci-helloworld'

@description('Application image tag')
param imageTag string = 'latest'

var storageAccountName = replace('${prefix}st', '-', '')
var keyVaultName = '${prefix}-kv'
var postgresServerName = '${prefix}-psql'
var serviceBusNamespaceName = '${prefix}-sb'

module network 'modules/network/vnet.bicep' = {
  name: 'network-deployment'
  params: {
    location: location
    prefix: prefix
  }
}

module storage 'modules/storage/blob.bicep' = {
  name: 'storage-deployment'
  params: {
    location: location
    storageAccountName: storageAccountName
    skuName: environment == 'prod' ? 'Standard_GRS' : 'Standard_LRS'
  }
}

module messaging 'modules/messaging/servicebus.bicep' = {
  name: 'messaging-deployment'
  params: {
    location: location
    namespaceName: serviceBusNamespaceName
    skuName: 'Standard'
  }
}

module database 'modules/database/postgres.bicep' = {
  name: 'database-deployment'
  params: {
    location: location
    serverName: postgresServerName
    administratorLoginPassword: postgresAdminPassword
    skuName: environment == 'prod' ? 'Standard_D2ds_v5' : 'Standard_B1ms'
    skuTier: environment == 'prod' ? 'GeneralPurpose' : 'Burstable'
  }
}

module keyvault 'modules/keyvault/main.bicep' = {
  name: 'keyvault-deployment'
  params: {
    location: location
    vaultName: keyVaultName
    tenantId: tenantId
  }
}

module observability 'modules/observability/main.bicep' = {
  name: 'observability-deployment'
  params: {
    location: location
    prefix: prefix
  }
}

module apps 'modules/apps/factory.bicep' = {
  name: 'apps-deployment'
  params: {
    location: location
    prefix: prefix
    acaSubnetId: network.outputs.acaSubnetId
    logAnalyticsWorkspaceId: observability.outputs.workspaceId
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    imageRepository: imageRepository
    imageTag: imageTag
    minReplicas: environment == 'prod' ? 2 : 1
    maxReplicas: environment == 'prod' ? 10 : 3
  }
}

output vnetId string = network.outputs.vnetId
output storageAccountId string = storage.outputs.storageAccountId
output storageAccountName string = storage.outputs.storageAccountName
output blobEndpoint string = storage.outputs.blobEndpoint
output serviceBusNamespaceId string = messaging.outputs.namespaceId
output serviceBusEndpoint string = messaging.outputs.serviceBusEndpoint
output postgresServerFqdn string = database.outputs.serverFqdn
output keyVaultUri string = keyvault.outputs.vaultUri
output appInsightsConnectionString string = observability.outputs.appInsightsConnectionString
output appFqdn string = apps.outputs.appFqdn
