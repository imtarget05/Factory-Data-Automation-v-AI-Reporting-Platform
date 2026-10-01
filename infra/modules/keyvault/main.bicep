@description('Location for Key Vault resources')
param location string

@description('Key Vault name (3-24 characters, globally unique)')
param vaultName string

@description('Azure AD tenant ID')
param tenantId string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

output vaultId string = keyVault.id
output vaultName string = keyVault.name
output vaultUri string = keyVault.properties.vaultUri
