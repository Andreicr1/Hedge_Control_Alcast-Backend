targetScope = 'resourceGroup'

@description('Base app name used to derive Azure Front Door resource names.')
@minLength(1)
param appName string = 'alcast-hc'

@description('Deployment environment name (dev|staging|prod).')
@minLength(1)
param environment string = 'dev'

@description('Azure Front Door endpoint origin hostname for the API (e.g. <app>.<hash>.<region>.azurecontainerapps.io).')
@minLength(1)
param backendOriginHost string

@description('Azure Static Web Apps default hostname (e.g. <name>.azurestaticapps.net).')
@minLength(1)
param frontendOriginHost string

@description('Optional tags applied to resources.')
param tags object = {
  app: appName
  env: environment
}

var suffix = toLower(uniqueString(subscription().id, resourceGroup().id, appName, environment))

var afdProfileName = toLower(take(replace('${appName}-${environment}-afd-${suffix}', '_', '-'), 90))
var afdEndpointName = toLower(take(replace('${appName}-${environment}-edge', '_', '-'), 60))

var afdOriginGroupApiName = 'og-api'
var afdOriginGroupWebName = 'og-web'
var afdRuleSetName = 'rs-strip-api'

// Azure Front Door (Standard) to unify routing under a single domain:
// - /api/* -> backend (with rewrite stripping /api)
// - /*     -> Static Web App
module frontDoor 'br/public:avm/res/cdn/profile:0.12.1' = {
  name: 'afd'
  params: {
    name: afdProfileName
    location: 'global'
    sku: 'Standard_AzureFrontDoor'
    tags: tags
    originGroups: [
      {
        name: afdOriginGroupApiName
        healthProbeSettings: {
          probeIntervalInSeconds: 60
          probePath: '/health'
          probeProtocol: 'Https'
          probeRequestType: 'GET'
        }
        loadBalancingSettings: {
          additionalLatencyInMilliseconds: 50
          sampleSize: 4
          successfulSamplesRequired: 3
        }
        origins: [
          {
            name: 'api'
            hostName: backendOriginHost
            enabledState: 'Enabled'
            enforceCertificateNameCheck: true
            httpPort: 80
            httpsPort: 443
            priority: 1
            weight: 1000
          }
        ]
      }
      {
        name: afdOriginGroupWebName
        healthProbeSettings: {
          probeIntervalInSeconds: 120
          probePath: '/'
          probeProtocol: 'Https'
          probeRequestType: 'GET'
        }
        loadBalancingSettings: {
          additionalLatencyInMilliseconds: 50
          sampleSize: 4
          successfulSamplesRequired: 3
        }
        origins: [
          {
            name: 'web'
            hostName: frontendOriginHost
            enabledState: 'Enabled'
            enforceCertificateNameCheck: true
            httpPort: 80
            httpsPort: 443
            priority: 1
            weight: 1000
          }
        ]
      }
    ]
    ruleSets: [
      {
        name: afdRuleSetName
        rules: [
          {
            name: 'StripApiPrefix'
            order: 1
            actions: [
              {
                name: 'UrlRewrite'
                parameters: {
                  typeName: 'DeliveryRuleUrlRewriteActionParameters'
                  sourcePattern: '/api/*'
                  destination: '/'
                  preserveUnmatchedPath: true
                }
              }
            ]
          }
        ]
      }
    ]
    afdEndpoints: [
      {
        name: afdEndpointName
        enabledState: 'Enabled'
        routes: [
          {
            name: 'route-api'
            originGroupName: afdOriginGroupApiName
            patternsToMatch: [
              '/api/*'
            ]
            supportedProtocols: [
              'Https'
            ]
            forwardingProtocol: 'HttpsOnly'
            httpsRedirect: 'Enabled'
            linkToDefaultDomain: 'Enabled'
            enabledState: 'Enabled'
            ruleSets: [
              {
                name: afdRuleSetName
              }
            ]
          }
          {
            name: 'route-web'
            originGroupName: afdOriginGroupWebName
            patternsToMatch: [
              '/*'
            ]
            supportedProtocols: [
              'Https'
            ]
            forwardingProtocol: 'HttpsOnly'
            httpsRedirect: 'Enabled'
            linkToDefaultDomain: 'Enabled'
            enabledState: 'Enabled'
          }
        ]
      }
    ]
  }
}

@description('Azure Front Door endpoint hostname (use this as the single entry point for the app).')
output frontDoorHostname string = frontDoor.outputs.frontDoorEndpointHostNames[0]
