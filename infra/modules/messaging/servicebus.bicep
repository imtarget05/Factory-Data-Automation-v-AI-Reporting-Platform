@description('Location for messaging resources')
param location string

@description('Service Bus namespace name')
param namespaceName string

@description('Service Bus SKU tier')
param skuName string = 'Standard'

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: namespaceName
  location: location
  sku: {
    name: skuName
    tier: skuName
  }
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource telemetryQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'factory-telemetry-inbox'
  properties: {
    requiresDuplicateDetection: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 10
    defaultMessageTimeToLive: 'P14D'
    lockDuration: 'PT1M'
  }
}

output namespaceId string = serviceBusNamespace.id
output namespaceName string = serviceBusNamespace.name
output queueName string = telemetryQueue.name
output serviceBusEndpoint string = serviceBusNamespace.properties.serviceBusEndpoint
