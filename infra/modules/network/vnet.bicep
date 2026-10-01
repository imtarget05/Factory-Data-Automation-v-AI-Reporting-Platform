@description('Location for network resources')
param location string

@description('Resource name prefix')
param prefix string

@description('VNet address space prefix')
param addressPrefix string = '10.2.0.0/16'

resource networkSecurityGroup 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${prefix}-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPSInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: '${prefix}-vnet'
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
    subnets: [
      {
        name: 'snet-infra'
        properties: {
          addressPrefix: '10.2.0.0/24'
          networkSecurityGroup: {
            id: networkSecurityGroup.id
          }
        }
      }
      {
        name: 'snet-aca'
        properties: {
          addressPrefix: '10.2.2.0/23'
          delegations: [
            {
              name: 'aca-delegation'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-pe'
        properties: {
          addressPrefix: '10.2.4.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output vnetId string = virtualNetwork.id
output vnetName string = virtualNetwork.name
output acaSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetwork.name, 'snet-aca')
output peSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', virtualNetwork.name, 'snet-pe')
