using '../main.bicep'

param environment = 'dev'
param location = 'southeastasia'
param prefix = 'fact-dev'
param tenantId = '00000000-0000-0000-0000-000000000000'
param postgresAdminPassword = 'PlaceholderDevPassword123!'
param imageRepository = 'ghcr.io/imtarget05/factory-data-platform'
param imageTag = 'latest'
