@description('Location for application resources')
param location string

@description('Resource name prefix')
param prefix string

@description('Subnet ID for ACA environment')
param acaSubnetId string

@description('Log Analytics Workspace ID')
param logAnalyticsWorkspaceId string

@description('Application Insights Connection String')
@secure()
param appInsightsConnectionString string

@description('Container image tag')
param imageTag string = 'latest'

@description('Container image repository')
param imageRepository string = 'mcr.microsoft.com/azuredocs/aci-helloworld'

@description('Minimum replicas')
param minReplicas int = 1

@description('Maximum replicas')
param maxReplicas int = 5

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-aca-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2023-09-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2023-09-01').primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
  }
}

resource factoryApiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'factory-api'
          image: '${imageRepository}:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
            {
              name: 'PORT'
              value: '8000'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 15
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output environmentId string = containerAppEnv.id
output appId string = factoryApiApp.id
output appFqdn string = factoryApiApp.properties.configuration.ingress.fqdn
