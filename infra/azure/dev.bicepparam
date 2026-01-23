using './main.bicep'

param environment = 'dev'

// Concentrate everything in eastus2
param location = 'eastus2'

// Static Web Apps location (keep aligned with location)
param swaLocation = 'eastus2'

// Optional override
// param appName = 'alcast-hc'

// Two-phase deploy tip:
// - First run: deployBackend=false (backendImage can be omitted)
// - Second run: deployBackend=true + backendImage='<acrLoginServer>/<repo>:<tag>'
// param deployBackend = false
// param backendImage = 'myregistry.azurecr.io/hedge-control-api:dev'

param backendPort = 8000

// Auth
// param backendAuthMode = 'both'
// param frontendAuthMode = 'local'

// Entra / MSAL (non-secret identifiers)
// param entraTenantId = '<tenant-guid>'
// param entraAudience = 'api://<api-app-client-id>'
// param frontendEntraClientId = '<spa-app-client-id>'
// param frontendEntraApiScope = 'api://<api-app-client-id>/access_as_user'

// Do NOT store secrets in param files. Supply via CLI:
// --parameters postgresAdminPassword='...'
// --parameters backendSecretKey='...'
param postgresAdminPassword = ''

// Intentionally empty; override via CLI. Example:
// --parameters postgresAdminPassword=$pgPasswordPlain
