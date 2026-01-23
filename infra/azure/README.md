# Azure IaC (Bicep) — Opção A

Arquitetura alvo:

- Frontend: Azure Static Web Apps
- Backend: Azure Container Apps (FastAPI)
- Imagens: Azure Container Registry
- Banco: Azure Database for PostgreSQL Flexible Server
- Segredos: Azure Key Vault
- Storage: Storage Account + Blob Container
- Logs: Log Analytics Workspace (Container Apps Environment)

## Front Door (single-domain routing)

O template pode criar **Azure Front Door (Standard)** para ter um único domínio que roteia:

- `/*` → Static Web App
- `/api/*` → Container App (com URL rewrite removendo o prefixo `/api`, então `/api/auth/token` vira `/auth/token`)

Static Web Apps é ótimo para hospedar o frontend, mas não deve ser tratado como reverse proxy genérico para um backend externo em todos os métodos/headers. Se aparecer `405 Method Not Allowed` em `POST /api/...` via domínio do SWA, habilite Front Door.

Importante: em algumas subscriptions (Free Trial / Student), o Azure bloqueia Azure Front Door. Se for o seu caso, use a alternativa abaixo com **SWA + Azure Functions integradas**.

### Deploy

O Front Door é controlado por `deployFrontDoor` (default `true`) e requer `deployBackend=true`. Ele é criado já na Fase A (infra-only).

### Test

Depois do deploy, use o output `frontDoorHostname`:

- Frontend (HTML): `curl -I https://<frontdoor-host>/`
- Health do backend (via domínio único): `curl -i https://<frontdoor-host>/api/health`
- Token (form-url-encoded):
  - `curl -i -X POST https://<frontdoor-host>/api/auth/token -H "Content-Type: application/x-www-form-urlencoded" --data "username=<user>&password=<pass>"`

Se `/api/health` funciona mas `/api/auth/token` falha, confirme que o backend expõe `/auth/token` (sem `/api`) e mantenha o rewrite habilitado.

## Alternativa recomendada (sem Front Door): SWA + Azure Functions integradas (proxy)

Para manter **same-origin** e suportar `POST /api/...` sem depender de Front Door, use Azure Functions integradas no SWA como proxy.

- Frontend continua chamando `VITE_API_BASE_URL=/api`
- O SWA encaminha `/api/*` para as Functions do projeto (pasta `api/` no repo do frontend)
- A Function faz proxy para o Container App usando `BACKEND_BASE_URL` (Application Setting do SWA)

Checklist de deploy (GitHub Actions / SWA build settings):

- `app_location`: `.`
- `output_location`: `dist`
- `api_location`: `api`

Depois do deploy, valide:

- `curl -i https://<SWA_HOST>/api/health`
- `curl -i -X POST https://<SWA_HOST>/api/auth/token -H "Content-Type: application/x-www-form-urlencoded" --data "username=<user>&password=<pass>"`

Para endpoints autenticados via SWA (proxy), prefira enviar o token também em `x-hc-authorization`:

- `curl -i https://<SWA_HOST>/api/auth/me -H "x-hc-authorization: Bearer <TOKEN>"`

## Microsoft Entra ID (login corporativo)

O backend suporta validar tokens do Entra (RS256/JWKS) com `AUTH_MODE=entra|both`.

Parâmetros novos no Bicep (veja `main.bicep`):

- `backendAuthMode`: `local|entra|both`
- `entraTenantId`, `entraAudience` (recomendado: `api://<api-app-client-id>`)
- `frontendAuthMode`: `local|entra`
- `frontendEntraClientId` (clientId do app SPA)
- `frontendEntraApiScope` (ex.: `api://<api-app-client-id>/access_as_user`)

Importante:

- Em `environment=prod`, o backend exige `CORS_ORIGINS` explícito.
  - Use o parâmetro `corsOrigins` (JSON array como string), por exemplo:
    - `corsOrigins='["https://<seu-host-do-frontend>"]'`

Se estiver usando `swa deploy` local, recomenda-se fixar Node 18 para a API:

- `--api-language node --api-version 18`


## Pré-requisitos

- Azure CLI (`az`)
- Bicep CLI (`az bicep`) — já vem com o Azure CLI moderno
- Permissão para criar recursos no Resource Group

## Estrutura

- `main.bicep`: orquestra todos os recursos via AVM (pinned versions)
- `dev.bicepparam` / `prod.bicepparam`: exemplos de parâmetros por ambiente

## Build (validação local)

No Windows (PowerShell):

```powershell
cd c:\Projetos\Hedge_Control_Alcast-Backend\infra\azure
az bicep build --file .\main.bicep
```

## Deploy (exemplo)

1) Faça login e selecione subscription (se necessário):

```powershell
az login
# az account set --subscription '<subscription-id-ou-nome>'
```

1) Defina variáveis e crie/seleciona um Resource Group:

```powershell
$rg = '<seu-rg>'
$location = 'eastus2'

az group create --name $rg --location $location
```

1) Deploy recomendado em 2 fases (evita depender de imagem na 1ª execução)

Fase A — infra-only (sem backend / sem imagem):

```powershell
$deploymentName = "${rg}-hc-${env:USERNAME}-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

$pgPasswordSecure = Read-Host -AsSecureString 'Postgres admin password'
$pgPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPasswordSecure)
)

az deployment group create `
  --name $deploymentName `
  --resource-group $rg `
  --template-file .\main.bicep `
  --parameters .\dev.bicepparam `
  --parameters location=$location deployBackend=false postgresAdminPassword=$pgPasswordPlain
```

Fase B — build/push e deploy completo (backend + AcrPull):

```powershell
$outs = az deployment group show -g $rg -n $deploymentName --query properties.outputs -o json | ConvertFrom-Json
$acrName = $outs.acrName.value
$acrLoginServer = $outs.acrLoginServer.value

az acr login --name $acrName

# Opção 1 (recomendado): build local + push (requer Docker local)
docker build -t "$acrLoginServer/hedge-control-api:dev" -f ..\..\backend\Dockerfile ..\..\backend
docker push "$acrLoginServer/hedge-control-api:dev"

# Opção 2: ACR Build (ACR Tasks) — não requer Docker local, mas pode ser bloqueado por política/offer na subscription
# Exemplo de erro quando bloqueado: (TasksOperationsNotAllowed)
# az acr build `
#   --registry $acrName `
#   --image hedge-control-api:dev `
#   --file ..\..\backend\Dockerfile `
#   ..\..\backend

$backendImage = "$acrLoginServer/hedge-control-api:dev"

$backendSecretKeySecure = Read-Host -AsSecureString 'Backend SECRET_KEY (>= 32 chars, random)'
$backendSecretKeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($backendSecretKeySecure)
)

az deployment group create `
  --name $deploymentName `
  --resource-group $rg `
  --template-file .\main.bicep `
  --parameters .\dev.bicepparam `
  --parameters location=$location deployBackend=true backendImage=$backendImage postgresAdminPassword=$pgPasswordPlain backendSecretKey=$backendSecretKeyPlain
```

Alternativa — deploy em 1 fase (se você já tem a imagem publicada):

```powershell
$deploymentName = "${rg}-hc-${env:USERNAME}-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# Imagem do backend no formato <loginServer>/<repo>:<tag>
# Dica: você pode usar um valor provisório na 1ª vez (o container pode falhar para puxar).
$backendImage = '<loginServer>/<repo>:<tag>'

$backendSecretKeySecure = Read-Host -AsSecureString 'Backend SECRET_KEY (>= 32 chars, random)'
$backendSecretKeyPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($backendSecretKeySecure)
)

# Não commitar senha; passe via CLI.
$pgPasswordSecure = Read-Host -AsSecureString 'Postgres admin password'
$pgPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPasswordSecure)
)

az deployment group create `
  --name $deploymentName `
  --resource-group $rg `
  --template-file .\main.bicep `
  --parameters .\dev.bicepparam `
  --parameters location=$location deployBackend=true backendImage=$backendImage postgresAdminPassword=$pgPasswordPlain backendSecretKey=$backendSecretKeyPlain
```

1) Pegue os outputs (útil para ACR/SWA/API):

```powershell
$outs = az deployment group show -g $rg -n $deploymentName --query properties.outputs -o json | ConvertFrom-Json
$outs

"ACR: $($outs.acrLoginServer.value)"
"Backend FQDN: $($outs.backendFqdn.value)"
"Frontend Hostname: $($outs.frontendHostname.value)"
```

1) (Opcional) Build + push da imagem para o ACR criado pelo template:

```powershell
$acrName = $outs.acrName.value
$acrLoginServer = $outs.acrLoginServer.value

az acr login --name $acrName

# Exemplo: build local + push (ajuste caminho/contexto do Dockerfile conforme seu repo)
# docker build -t "$acrLoginServer/hedge-control-api:dev" ..
# docker push "$acrLoginServer/hedge-control-api:dev"

# Depois atualize o parâmetro backendImage para apontar para essa tag.
```

## Observações importantes

- `postgresAdminPassword` é `@secure()` e deve ser passado via CLI (não commitar em arquivo).
- Se seu subscription estiver **restrito** para criar PostgreSQL em `eastus2` (ex.: erro `LocationIsOfferRestricted`), use `postgresLocation` para colocar **só o Postgres** em outra região (ex.: `centralus`), mantendo o resto em `eastus2`.
  - Nota: ao mudar `postgresLocation`, o template gera um **novo** nome de servidor Postgres (para evitar colisão com recursos anteriores). Se ficou um servidor antigo com `Failed` no RG, vale remover depois para manter limpo.
- Recomendado: usar `eastus2` para `location` e `swaLocation` (tudo na mesma região). SWA não está disponível em todas as regiões; se você trocar `location` para uma região sem SWA, mantenha `swaLocation` em uma região suportada.
- O Container Apps Environment (Managed Environment) tem `zoneRedundant` como default em alguns módulos/versões e isso exige configuração de VNet/subnet. Este template força `zoneRedundant=false` para suportar deploy público sem VNet.
- O Managed Environment pode ter `publicNetworkAccess` como default `Disabled` (no AVM). Se ficar `Disabled`, **toda chamada pública** ao Container App retorna `403` com mensagem de rede pública desabilitada. Este template seta `publicNetworkAccess='Enabled'`.
- O PostgreSQL Flexible Server tem `highAvailability` default `ZoneRedundant` e `geoRedundantBackup` default `Enabled` no módulo AVM; em `brazilsouth` isso pode falhar por restrições de oferta. Este template seta `highAvailability='Disabled'` e `geoRedundantBackup='Disabled'`.
- O pull da imagem no Container Apps usa uma **User-Assigned Managed Identity** com role `AcrPull` no ACR, criada antes do Container App (evita corrida/timing quando se usa `SystemAssigned` no mesmo deployment).
- O `backendImage` aponta para uma imagem já publicada (ex.: ACR). Se você quiser, eu posso também adicionar um fluxo de build/push (GitHub Actions) para publicar no ACR.
- `staticwebapp.config.json` no frontend controla fallback SPA e o proxy `/api`.
