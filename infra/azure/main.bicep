targetScope = 'resourceGroup'

@description('Base app name used to derive resource names.')
@minLength(1)
param appName string = 'alcast-hc'

@description('Deployment environment name (dev|staging|prod).')
@minLength(1)
param environment string = 'dev'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Azure region for PostgreSQL Flexible Server. Use when your subscription cannot provision Postgres in `location` (offer restrictions/quota).')
param postgresLocation string = location

@description('Azure region for Static Web Apps (SWA). Note: SWA does not support all regions (e.g., brazilsouth).')
@allowed([
  'westus2'
  'centralus'
  'eastus2'
  'westeurope'
  'eastasia'
])
param swaLocation string = 'eastus2'

@description('Whether to deploy the backend Container App (and AcrPull RBAC). Set false for a first "infra-only" deployment.')
param deployBackend bool = true

@description('Whether to deploy Azure Front Door (Standard) to unify routing under a single domain. Requires deployBackend=true.')
param deployFrontDoor bool = true

@description('Container image for the backend (FastAPI) in the format <loginServer>/<repo>:<tag>. Leave empty when deployBackend=false.')
param backendImage string = ''

@description('Port your FastAPI container listens on.')
param backendPort int = 8000

@description('Backend auth mode (local|entra|both).')
@allowed([
  'local'
  'entra'
  'both'
])
param backendAuthMode string = 'local'

@description('CORS origins JSON array as string (required when environment=prod). Example: ["https://<your-host>"]')
param corsOrigins string = ''

@description('Microsoft Entra tenant ID (GUID). Required when backendAuthMode=entra|both.')
param entraTenantId string = ''

@description('Expected audience for Entra access tokens (aud claim). Typically the API App ID URI, e.g. api://<api-app-client-id>.')
param entraAudience string = ''

@description('Optional override for Entra issuer. If empty, backend defaults from ENTRA_TENANT_ID.')
param entraIssuer string = ''

@description('Optional override for Entra JWKS URL. If empty, backend defaults from ENTRA_TENANT_ID.')
param entraJwksUrl string = ''

@description('Frontend auth mode (local|entra).')
@allowed([
  'local'
  'entra'
])
param frontendAuthMode string = 'local'

@description('SPA Microsoft Entra application (client) ID used by MSAL.')
param frontendEntraClientId string = ''

@description('SPA requested API scope. Typically api://<api-app-client-id>/access_as_user')
param frontendEntraApiScope string = ''

@secure()
@description('Backend SECRET_KEY (required when deployBackend=true). Pass via CLI; do not store in param files.')
param backendSecretKey string = ''

@description('PostgreSQL admin username (server admin).')
param postgresAdminUser string = 'postgres'

@secure()
@description('PostgreSQL admin password (pass via CLI; do not store in param files).')
param postgresAdminPassword string

@description('PostgreSQL availability zone. Use -1 for no preference (no zone defined).')
@allowed([
  -1
  1
  2
  3
])
param postgresAvailabilityZone int = -1

@description('PostgreSQL SKU name, e.g. Standard_D2s_v3.')
param postgresSkuName string = 'Standard_D2s_v3'

@description('PostgreSQL tier. Must align with skuName.')
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param postgresTier string = 'GeneralPurpose'

@description('PostgreSQL database name.')
param postgresDbName string = 'app'

@description('Optional tags applied to resources.')
param tags object = {
  app: appName
  env: environment
}

var suffix = toLower(uniqueString(subscription().id, resourceGroup().id, appName, environment))
// Guard against empty/invalid inputs after normalization.
var appNameDash = (length(appName) > 0) ? appName : 'app'
var environmentDash = (length(environment) > 0) ? environment : 'dev'
var appNameCompact = toLower(replace(replace(appNameDash, '-', ''), '_', ''))
var environmentCompact = toLower(replace(replace(environmentDash, '-', ''), '_', ''))

var normalizedBase = toLower(replace(replace('${appNameDash}-${environmentDash}', '-', ''), '_', ''))

// Must be 3-24 chars, lowercase letters/numbers only.
var storageAccountName = take('${normalizedBase}${suffix}', 24)

// 5-50 chars, lowercase letters/numbers only (no hyphens).
// Prefix with 'acr' to guarantee it starts with a letter.
var acrName = take('acr${appNameCompact}${environmentCompact}${suffix}', 50)

// 3-24 chars, alphanum only.
var kvName = toLower(take(replace('${appNameDash}-${environmentDash}-${suffix}', '-', ''), 24))

// 2-60 chars.
var lawName = toLower(take(replace('${appNameDash}-${environmentDash}-${suffix}', '_', '-'), 60))

var acaEnvName = toLower(take(replace('${appNameDash}-${environmentDash}-aca-${suffix}', '_', '-'), 32))
var containerAppName = toLower(take(replace('${appNameDash}-${environmentDash}-api', '_', '-'), 32))
var apiIdentityName = toLower(take(replace('${appNameDash}-${environmentDash}-api-mi-${suffix}', '_', '-'), 128))

// Postgres flexible server: 3-63 chars, lowercase letters/numbers/hyphens, must start with letter.
// Postgres flexible server: 3-63 chars, lowercase letters/numbers/hyphens, must start with letter.
// Include postgresLocation to avoid name collisions if you need to deploy Postgres to a different region.
var pgServerName = toLower(take(replace('pg-${appName}-${environment}-${postgresLocation}-${suffix}', '_', '-'), 63))

// Deterministic Postgres FQDN for public Azure cloud.
var postgresFqdn = '${pgServerName}.postgres.database.azure.com'

// Static Web Apps: keep conservative limit (module/API validation varies; 40 is safe) and ensure non-empty.
var swaName = toLower('swa-${take(replace('${appNameDash}-${environmentDash}-${suffix}', '_', '-'), 36)}')

// Azure Front Door (AFD) names
var afdProfileName = toLower(take(replace('${appName}-${environment}-afd-${suffix}', '_', '-'), 90))
var afdEndpointName = toLower(take(replace('${appName}-${environment}-edge', '_', '-'), 60))
var afdOriginGroupApiName = 'og-api'
var afdOriginGroupWebName = 'og-web'
var afdRuleSetName = 'rs-strip-api'

// Deterministic ACR login server (public Azure cloud).
var acrLoginServer = '${acrName}.azurecr.io'

// AVM module versions pinned (latest semver as of 2026-01-21)
// NOTE: Bicep module references must be string literals (no interpolation).
module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.15.0' = {
  name: 'law'
  params: {
    name: lawName
    location: location
    tags: tags
  }
}

module keyVault 'br/public:avm/res/key-vault/vault:0.13.3' = {
  name: 'kv'
  params: {
    name: kvName
    location: location
    tags: tags
    // Prefer RBAC authorization (default is typically true, but set explicitly)
    enableRbacAuthorization: true
  }
}

module storage 'br/public:avm/res/storage/storage-account:0.31.0' = {
  name: 'stg'
  params: {
    name: storageAccountName
    location: location
    tags: tags
    secretsExportConfiguration: {
      keyVaultResourceId: keyVault.outputs.resourceId
      // Optional: name the exported secrets so we can reference them deterministically
      connectionString1Name: toLower(take('${appName}-${environment}-${suffix}-storage-conn', 127))
      accessKey1Name: toLower(take('${appName}-${environment}-${suffix}-storage-key', 127))
    }
  }
}

module blobContainer 'br/public:avm/res/storage/storage-account/blob-service/container:0.3.2' = {
  name: 'blob-app'
  params: {
    name: 'app'
    storageAccountName: storage.outputs.name
    publicAccess: 'None'
  }
}

module acr 'br/public:avm/res/container-registry/registry:0.10.0' = {
  name: 'acr'
  params: {
    name: acrName
    location: location
    tags: tags
    acrSku: 'Basic'
    acrAdminUserEnabled: false
  }
}

resource acrRegistry 'Microsoft.ContainerRegistry/registries@2023-06-01-preview' existing = {
  name: acrName
}

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: apiIdentityName
  location: location
  tags: tags
}

// Container Apps managed environment (w/ Log Analytics)
module acaEnv 'br/public:avm/res/app/managed-environment:0.11.3' = {
  name: 'aca-env'
  params: {
    name: acaEnvName
    location: location
    tags: tags
    // Default for the AVM module is zoneRedundant=true, which requires VNet/subnet configuration.
    // For public, non-VNet environments, disable zone redundancy.
    zoneRedundant: false
    // AVM default is Disabled, which blocks all public traffic and yields 403 from the ingress.
    publicNetworkAccess: 'Enabled'
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.outputs.logAnalyticsWorkspaceId
        sharedKey: logAnalytics.outputs.primarySharedKey
      }
    }
  }
}

// PostgreSQL flexible server
module postgres 'br/public:avm/res/db-for-postgre-sql/flexible-server:0.15.1' = {
  name: 'pg'
  params: {
    availabilityZone: postgresAvailabilityZone
    name: pgServerName
    location: postgresLocation
    skuName: postgresSkuName
    tags: tags
    tier: postgresTier
    // Avoid region offer restrictions (e.g., brazilsouth) and keep dev simple.
    highAvailability: 'Disabled'
    geoRedundantBackup: 'Disabled'
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    databases: [
      {
        name: postgresDbName
      }
    ]
  }
}

// Backend API on Azure Container Apps
module api 'br/public:avm/res/app/container-app:0.20.0' = if (deployBackend) {
  name: 'api'
  dependsOn: [
    acrPull
  ]
  params: {
    name: containerAppName
    location: location
    tags: tags
    environmentResourceId: acaEnv.outputs.resourceId
    managedIdentities: {
      userAssignedResourceIds: [
        apiIdentity.id
      ]
    }
    registries: [
      {
        server: acrLoginServer
        identity: apiIdentity.id
      }
    ]
    // Override AVM defaults (minReplicas=3) to speed up first provisioning.
    // Adjust per-environment later if needed.
    scaleSettings: {
      minReplicas: 1
      maxReplicas: 10
    }
    secrets: [
      {
        name: 'db-password'
        value: postgresAdminPassword
      }
      {
        name: 'database-url'
        value: 'postgresql://${postgresAdminUser}:${postgresAdminPassword}@${postgresFqdn}:5432/${postgresDbName}?sslmode=require'
      }
      {
        name: 'secret-key'
        value: backendSecretKey
      }
    ]
    containers: [
      {
        name: 'api'
        image: backendImage
        resources: {
          cpu: json('0.5')
          memory: '1Gi'
        }
        env: [
          {
            name: 'PORT'
            value: string(backendPort)
          }
          {
            name: 'ENVIRONMENT'
            value: environment
          }
          {
            name: 'CORS_ORIGINS'
            value: corsOrigins
          }
          {
            name: 'DATABASE_URL'
            secretRef: 'database-url'
          }
          {
            name: 'SECRET_KEY'
            secretRef: 'secret-key'
          }
          {
            name: 'AUTH_MODE'
            value: backendAuthMode
          }
          {
            name: 'ENTRA_TENANT_ID'
            value: entraTenantId
          }
          {
            name: 'ENTRA_AUDIENCE'
            value: entraAudience
          }
          {
            name: 'ENTRA_ISSUER'
            value: entraIssuer
          }
          {
            name: 'ENTRA_JWKS_URL'
            value: entraJwksUrl
          }
          {
            name: 'RUN_MIGRATIONS_ON_START'
            value: 'false'
          }
        ]
      }
    ]
    ingressExternal: true
    ingressTargetPort: backendPort
    ingressTransport: 'auto'
  }
}

var backendFqdnOrEmpty = api.?outputs.?fqdn ?? ''
var backendBaseUrlOrEmpty = (backendFqdnOrEmpty != '') ? 'https://${backendFqdnOrEmpty}' : ''

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployBackend) {
  name: guid(acrRegistry.id, apiIdentity.id, 'acrpull')
  scope: acrRegistry
  properties: {
    principalId: apiIdentity.properties.principalId!
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// Static Web App (resource only). The actual CI/CD wiring can be done via GitHub Actions or Azure DevOps.
module swa 'br/public:avm/res/web/static-site:0.9.3' = {
  name: 'swa'
  params: {
    name: swaName
    location: swaLocation
    tags: tags
    // App settings can be used to expose the API base URL to the frontend build
    appSettings: deployBackend ? {
      // Frontend uses same-origin /api; SWA routes /api/* to integrated Functions.
      VITE_API_BASE_URL: '/api'
      VITE_AUTH_MODE: frontendAuthMode
      VITE_ENTRA_TENANT_ID: entraTenantId
      VITE_ENTRA_CLIENT_ID: frontendEntraClientId
      VITE_ENTRA_API_SCOPE: frontendEntraApiScope
      // Used by the SWA integrated Azure Functions proxy.
      BACKEND_BASE_URL: backendBaseUrlOrEmpty
    } : {
      VITE_API_BASE_URL: '/api'
      VITE_AUTH_MODE: frontendAuthMode
      VITE_ENTRA_TENANT_ID: entraTenantId
      VITE_ENTRA_CLIENT_ID: frontendEntraClientId
      VITE_ENTRA_API_SCOPE: frontendEntraApiScope
    }
  }
}

// Azure Front Door (Standard) to unify routing under a single domain:
// - /api/* -> Container Apps backend (with rewrite to strip /api)
// - /*     -> Static Web App
var backendOriginHost = replace(replace(backendFqdnOrEmpty, 'https://', ''), 'http://', '')
var frontendOriginHost = swa.outputs.defaultHostname

module frontDoor 'br/public:avm/res/cdn/profile:0.12.1' = if (deployBackend && deployFrontDoor) {
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

var frontDoorHostnameOrEmpty = frontDoor.?outputs.?frontDoorEndpointHostNames[0] ?? ''

@description('Backend public FQDN from Container Apps.')
output backendFqdn string = backendFqdnOrEmpty

@description('Static Web App default hostname.')
output frontendHostname string = swa.outputs.defaultHostname

@description('Key Vault URI.')
output keyVaultUri string = keyVault.outputs.uri

@description('Azure Container Registry name.')
output acrName string = acrName

@description('Azure Container Registry login server (e.g. <name>.azurecr.io).')
output acrLoginServer string = acrLoginServer

@description('Azure Front Door endpoint hostname (use this as the single entry point for the app).')
output frontDoorHostname string = frontDoorHostnameOrEmpty
