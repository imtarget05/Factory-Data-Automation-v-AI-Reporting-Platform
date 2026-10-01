using '../main.bicep'

param environment = 'prod'
param location = 'southeastasia'
param prefix = 'fact-prod'
param tenantId = '00000000-0000-0000-0000-000000000000'
param postgresAdminPassword = 'PlaceholderProdPassword123!'
param imageRepository = 'ghcr.io/imtarget05/factory-data-platform'
param imageTag = 'latest'
