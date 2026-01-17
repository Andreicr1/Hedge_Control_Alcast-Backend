# Alcast Hedge Control - Documentação Institucional de Referência

**Sistema de Gestão de Exposições e Hedge de Commodities**  
**Versão:** 1.0  
**Data:** Janeiro 2026  
**Empresa:** Previse Capital

---

## Índice

1. [Visão Geral do Sistema](#1-visão-geral-do-sistema)
2. [Arquitetura em Camadas](#2-arquitetura-em-camadas)
3. [Camada 1: Originação](#3-camada-1-originação)
4. [Camada 2: Hub de Comunicação](#4-camada-2-hub-de-comunicação)
5. [Camada 3: Análise de Exposição](#5-camada-3-análise-de-exposição)
6. [Camada 4: Suporte à Decisão & Ação Humana](#6-camada-4-suporte-à-decisão--ação-humana)
7. [Camada 5: Processo de RFQ](#7-camada-5-processo-de-rfq)
8. [Camada 6: Contratação](#8-camada-6-contratação)
9. [Camada 7: Pós-Trade & Valuation](#9-camada-7-pós-trade--valuation)
10. [Camada 8: Governança Transversal](#10-camada-8-governança-transversal)
11. [Camada 9: Rastreabilidade & Exportação](#11-camada-9-rastreabilidade--exportação)
12. [Fluxos Operacionais Críticos](#12-fluxos-operacionais-críticos)
13. [Serviços e APIs](#13-serviços-e-apis)
14. [Estados e Transições](#14-estados-e-transições)
15. [Glossário](#15-glossário)

---

## 1. Visão Geral do Sistema

### 1.1 Propósito

O **Alcast Hedge Control** é um sistema corporativo para gestão integrada de exposições de preço em operações de commodities (especificamente alumínio), permitindo:

- Identificação automática de exposições de mercado
- Suporte à decisão de hedge
- Processo estruturado de Request for Quote (RFQ)
- Formalização de contratos de hedge
- Avaliação mark-to-market (MTM) contínua
- Reporting financeiro consolidado
- Rastreabilidade completa end-to-end
- Governança e auditoria institucional

### 1.2 Contexto de Negócio

O sistema atende operações de trading de alumínio onde:

- **Sales Orders (SO)** representam vendas físicas a clientes
- **Purchase Orders (PO)** representam compras físicas de fornecedores
- Preços podem ser **fixos** (sem risco de mercado) ou **flutuantes** (expostos a variação)
- **Exposições** surgem quando há descasamento entre SO e PO flutuantes
- **Hedge** é realizado através de contratos financeiros (derivativos, swaps, etc.)

### 1.3 Princípios Fundamentais

1. **Rastreabilidade completa**: Toda operação é rastreável desde a origem (Deal) até o resultado financeiro (P&L)
2. **Decisão humana explícita**: Pontos críticos sempre requerem ação consciente do time de Financeiro
3. **Imutabilidade**: Contratos e registros históricos são preservados (não editados)
4. **Governança by design**: Autenticação, autorização e auditoria em todas as ações sensíveis
5. **Separação clara**: RFQ (processo de cotação) ≠ Contrato (compromisso financeiro real)

### 1.4 Escopo do Release (v1.0) e Não-Requisitos

Este documento descreve o **modelo institucional** do sistema. Para o marco de conclusão do projeto (v1.0), os itens abaixo são **explicitamente não-requisitos** (de-scoped) e não bloqueiam o “project complete”:

- **Comentários/Anotações/@mentions/Uploads na Timeline**: a Timeline é um hub de eventos (observabilidade e coordenação). Interações humanas ricas são **deferidas**.
- **Exportações formais (CSV/PDF/Excel) e reconciliação externa**: formatos e rotinas completas de exportação/reconciliação são **deferidas**.
- **Cenários/sensitividade no Cashflow**: análises de stress/sensibilidade são **fora de escopo** do v1.0.
- **Workflow de aprovação multinível**: o sistema usa RBAC + auditoria; não é um workflow engine de aprovações.

Itens de roadmap podem ser implementados posteriormente sem alterar os princípios centrais descritos aqui.

---

## 2. Arquitetura em Camadas

O sistema é organizado em **9 camadas funcionais** que operam de forma coordenada:

| Camada | Nome | Função Principal |
|--------|------|------------------|
| 1 | Originação | Entrada de operações físicas (SO/PO) |
| 2 | Hub de Comunicação | Coordenação e visibilidade entre times |
| 3 | Análise de Exposição | Cálculo e gestão de exposições de mercado |
| 4 | Suporte à Decisão & Ação Humana | Interface de decisão do Financeiro |
| 5 | Processo de RFQ | Cotação estruturada com contrapartes |
| 6 | Contratação | Formalização de hedges |
| 7 | Pós-Trade & Valuation | MTM, P&L e projeções |
| 8 | Governança Transversal | Auth, RBAC, KYC, Audit |
| 9 | Rastreabilidade & Exportação | Cadeia completa e compliance |

---

## 3. Camada 1: Originação

### 3.1 Objetivo

Entrada de operações comerciais físicas no sistema.

### 3.2 Componentes

#### 3.2.1 Deal Comercial

- **Definição**: Negociação comercial inicial que origina operações
- **Fonte**: Equipes de Compras ou Vendas
- **Saídas**: Gera SOs (vendas) ou POs (compras)

#### 3.2.2 Sales Order (SO)

- **Definição**: Venda física registrada no sistema
- **Atributos obrigatórios**:
  - Volume (toneladas)
  - Tipo de preço: Fixo ou Flutuante
  - Período de entrega
  - Contraparte (cliente)
  - Identificador único
- **Sistema de origem**: Pode ser integrado de ERP externo ou criado diretamente

#### 3.2.3 Purchase Order (PO)

- **Definição**: Compra física registrada no sistema
- **Atributos obrigatórios**:
  - Volume (toneladas)
  - Tipo de preço: Fixo ou Flutuante
  - Período de entrega
  - Contraparte (fornecedor)
  - Identificador único
- **Relação**: 1 SO pode gerar N POs (para suprir a venda)

### 3.3 Fluxo de Dados

```
Deal Comercial
    ├─> Sales Order (SO)
    └─> Purchase Order (PO)
         └─> [Relação: 1 SO → N POs]
```

### 3.4 Eventos Gerados

- `SO_CREATED`: Quando um novo SO é registrado
- `PO_CREATED`: Quando um novo PO é registrado

Estes eventos são enviados automaticamente para a **Timeline** (Camada 2).

---

## 4. Camada 2: Hub de Comunicação

### 4.1 Objetivo

Centralizar visibilidade e coordenação entre times (Compras, Vendas, Financeiro).

### 4.2 Componente Principal: Timeline

#### 4.2.1 Função

- **NÃO é um workflow engine**: Não executa ações críticas
- **É um hub de coordenação**: Permite que times vejam, comentem e contextualizem operações

#### 4.2.2 Eventos Registrados Automaticamente

- Criação de SOs e POs
- Cálculo de exposições
- Decisões de hedge
- Envio de RFQs
- Respostas recebidas de contrapartes
- Contratos criados
- Atualizações de MTM relevantes

#### 4.2.3 Interação Humana

- Usuários podem adicionar **comentários contextuais**
- Podem **@mencionar** outros usuários
- Podem anexar **justificativas** de decisões
- Podem iniciar **discussões** sobre exposições específicas

#### 4.2.4 Visibilidade

- **Compras**: Vê eventos relacionados a POs e contexto de hedge
- **Vendas**: Vê eventos relacionados a SOs e contexto de hedge
- **Financeiro**: Vê todos os eventos e tem acesso completo

### 4.3 Princípio Fundamental

> **A Timeline é o canal oficial de comunicação, mas não substitui decisões explícitas nos módulos especializados.**

Exemplo:

- ✅ Financeiro vê exposição na Timeline, vai ao Dashboard/Inbox e decide fazer hedge
- ❌ Financeiro NÃO cria RFQ diretamente pela Timeline

---

## 5. Camada 3: Análise de Exposição

### 5.1 Objetivo

Identificar e quantificar exposições de preço não cobertas.

### 5.2 Análise de Preço

Quando SO ou PO entra no sistema:

```
SO/PO
  ├─> Tipo de preço = Fixo
  │       └─> Sem exposição (não gera risco de mercado)
  │
  └─> Tipo de preço = Flutuante
          └─> Potencial exposição
              (preço será determinado no futuro)
```

### 5.3 Cálculo de Exposição

#### 5.3.1 Serviço: `exposure_aggregation.py`

**Função**: Calcular exposição líquida de forma automática

**Lógica**:

1. Agrega todos SOs e POs com preço flutuante
2. Agrupa por período de referência (ex: mês de entrega)
3. Calcula net exposure:

   ```
   Net Exposure = Volume SO Flutuante - Volume PO Flutuante - Volume Hedgeado
   ```

4. Classifica como Ativa (compra exposta) ou Passiva (venda exposta)
5. Desconta volumes já hedgeados de contratos existentes

**Execução**: Contínua (triggered por novos SOs/POs) ou on-demand

#### 5.3.2 Estado: Exposição Calculada

**Atributos**:

- Volume total em aberto
- Volume já hedgeado
- Volume exposto (não coberto)
- Classificação: Ativa ou Passiva
- Período de referência
- Vínculo com SO/PO originais
- Timestamp de cálculo

**Definição crítica**:
> **Exposição ativa** = SO ou PO com preço flutuante sem hedge 100% correspondente

### 5.4 Exposição Residual

Quando um **hedge parcial** é executado:

1. Parte da exposição é coberta por contrato(s)
2. Exposição residual é **recalculada automaticamente**
3. Exposição residual **volta ao Dashboard/Inbox**
4. Permanece no **ciclo de decisão** (pode gerar novo hedge)

**Fluxo**:

```
Exposição 100t
    └─> Hedge parcial 60t
        └─> Exposição residual 40t
            └─> Volta ao Dashboard
                └─> Nova decisão possível
```

### 5.5 Loop de Monitoramento

Exposições **não hedgeadas** permanecem:

- Visíveis no Dashboard
- Ativas no Inbox do Financeiro
- Sujeitas a revisão contínua
- Sem enforcement de prazo (decisão operacional)

---

## 6. Camada 4: Suporte à Decisão & Ação Humana

### 6.1 Objetivo

Fornecer interface e informações para decisões de hedge do time de Financeiro.

### 6.2 Dashboard Consolidado

**Visualizações disponíveis**:

- Exposições por período (gráfico temporal)
- Volume total vs volume hedgeado
- Tendências históricas
- Métricas de risco (VaR, sensibilidade)
- Comparativo com metas de hedge

**Público**: Financeiro (acesso completo), Gestão (acesso read-only)

### 6.3 Inbox do Financeiro

**Interface de trabalho principal** para gestão de exposições.

**Apresenta**:

- **Exposições ativas**: Requerem ação ou decisão
- **Exposições passivas**: Em monitoramento
- **Net exposure por período**: Visão consolidada
- **Exposições residuais**: Resultantes de hedge parcial
- **Contexto da Timeline**: Comentários e comunicação relevante

**Funcionalidades**:

- Priorização de exposições
- Drill-down para detalhes (SO/PO vinculados)
- Acesso ao histórico de decisões anteriores
- Início direto de RFQ

### 6.4 Decisão Crítica: Fazer Hedge?

**Responsável**: Time de Financeiro  
**Input**: Exposição calculada + contexto de mercado + Timeline  
**Tipo**: Decisão humana consciente (não automatizada)

**Opções**:

#### 6.4.1 NÃO fazer hedge

- **Resultado**: Exposição permanece aberta
- **Registro**: Decisão é registrada em log de auditoria
- **Fluxo**: Exposição volta ao ciclo de monitoramento contínuo
- **Justificativa**: Pode ser adicionada opcionalmente na Timeline

**Cenários comuns**:

- Expectativa de movimento favorável de mercado
- Exposição de valor baixo (abaixo de threshold)
- Estratégia de natural hedge (aguardando operações opostas)

#### 6.4.2 SIM, fazer hedge

- **Resultado**: Prosseguir para definição de escopo
- **Próxima decisão**: Hedge total ou parcial?

### 6.5 Decisão: Escopo do Hedge

**Opções**:

#### 6.5.1 Hedge Parcial

- **Definição**: Cobre parte do volume exposto
- **Exemplo**: Exposição de 100t, hedge de 60t
- **Resultado**:
  - Volume hedgeado: 60t (coberto)
  - Exposição residual: 40t (ainda exposta)
- **Fluxo**: Exposição residual é recalculada e volta ao Dashboard

#### 6.5.2 Hedge Total

- **Definição**: Cobre 100% do volume exposto
- **Resultado**: Exposição é zerada para aquele período
- **Registro**: Estado da exposição muda para "fully hedged"

### 6.6 Definição de Parâmetros

Após escolher fazer hedge (total ou parcial), Financeiro define:

| Parâmetro | Descrição |
|-----------|-----------|
| Volume a hedgear | Toneladas exatas |
| Timing de execução | Imediato, janela específica, ou condicional |
| Contrapartes alvo | Lista de contrapartes para envio de RFQ |
| Estrutura de trade | Fixing vs average, swap, etc. |
| Canais de comunicação | WhatsApp, API, e-mail |

**Output**: Parâmetros prontos para criação de RFQ (Camada 5)

---

## 7. Camada 5: Processo de RFQ

### 7.1 Objetivo

Executar processo estruturado de Request for Quote com contrapartes selecionadas.

### 7.2 Princípio Fundamental

> **RFQ ≠ Contrato**  
> RFQ é um **processo de cotação**  
> Contrato é um **compromisso financeiro real**

### 7.3 Criação de RFQ

**Responsável**: Financeiro  
**Input**: Parâmetros definidos na Camada 4

**Define**:

- Trade(s) desejado(s) (estrutura, volume, período)
- Lista de contrapartes (pode ser múltiplas)
- Canais de envio (pode ser múltiplos por contraparte)
- Prazo de resposta (opcional, não enforcement rígido)
- Contexto adicional (comentários, documentos)

**Output**: RFQ criado no sistema com ID único

### 7.4 Orquestração: `rfq_engine.py`

**Serviço automatizado** que coordena todo o processo de RFQ.

**Responsabilidades**:

1. Validar parâmetros recebidos
2. Criar registro persistente de RFQ
3. Gerar identificadores únicos
4. Coordenar envio para contrapartes
5. Gerenciar estado do RFQ
6. Estabelecer vínculo com exposição original
7. Notificar usuários sobre progresso

**Estados gerenciados**:

- `CREATED`: RFQ criado, aguardando envio
- `SENDING`: Em processo de envio
- `SENT`: Enviado para todas as contrapartes
- `PARTIAL_RESPONSE`: Respostas parciais recebidas
- `CLOSED`: RFQ fechado (aceito ou recusado)
- `ARCHIVED`: Arquivado sem contratação

### 7.5 Construção de Mensagens: `rfq_message_builder.py`

**Serviço automatizado** para personalização de mensagens.

**Função**:

- Personalizar mensagem por contraparte (idioma, formato)
- Adaptar para canal específico (WhatsApp, API, e-mail)
- Incluir contexto relevante
- Gerar identificadores únicos por mensagem
- Estruturar dados para parsing de respostas

**Output**: Mensagens formatadas prontas para envio

### 7.6 Seleção de Canal

RFQ pode ser enviado por **múltiplos canais simultaneamente**:

| Canal | Características |
|-------|-----------------|
| **WhatsApp Business** | Mensagem direta, resposta rápida, informal |
| **API Direta** | Integração técnica, resposta estruturada, automatizada |
| **E-mail** | Comunicação formal, documentação anexável |

### 7.7 Envio: `rfq_sender.py`

**Serviço automatizado** com garantias de confiabilidade.

**Características**:

- **Idempotência**: Mesmo RFQ não é enviado duplicado
- **Status tracking**: Rastreamento preciso de cada envio
- **Timestamp completo**: Registro de quando foi enviado
- **Auditoria**: Registro em log de auditoria
- **Retry automático**: Para falhas temporárias (configurável)

**Estados de envio**:

- `sent`: Enviado com sucesso
- `queued`: Na fila para envio
- `failed`: Falha (registrada com motivo)

### 7.8 Ingestão de Respostas

**Processo contínuo** que recebe e processa respostas de contrapartes.

**Para cada resposta**:

1. **Vinculação**: Associar ao RFQ original (por ID)
2. **Validação**: Verificar estrutura e completude
3. **Parsing**: Extrair dados estruturados (preço, volume, condições)
4. **Armazenamento**: Persistir resposta com timestamp
5. **Ranking**: Aplicar algoritmo determinístico de classificação
6. **Notificação**: Alertar Financeiro sobre nova resposta

**Ranking determinístico**:

- Baseado em preço (principal fator)
- Considera condicionais e restrições
- Mantém histórico de performance da contraparte
- Permite override manual

### 7.9 Decisão: RFQ Fechado?

**Responsável**: Financeiro  
**Input**: Respostas recebidas + análise de preços + contexto de mercado

**Baseado em**:

- Qualidade das cotações
- Análise de preços vs expectativa
- Contexto de mercado no momento
- Timing estratégico

**Opções**:

#### 7.9.1 RFQ NÃO FECHADO

- **Resultado**: Processo encerrado sem contrato
- **Possíveis razões**:
  - Cotações insatisfatórias (preços fora de expectativa)
  - Mudança de estratégia (decisão de não hedgear)
  - Timing inadequado (aguardar melhor momento)
  - Condições de mercado desfavoráveis
- **Fluxo**: RFQ vai para arquivo

#### 7.9.2 RFQ FECHADO

- **Resultado**: Prosseguir para contratação (Camada 6)
- **Indica**:
  - Resposta(s) aceita(s)
  - Contraparte(s) selecionada(s)
  - Termos acordados (preço, volume, estrutura)
  - Pronto para formalização

### 7.10 Arquivo de RFQ

**Estado final** para RFQs não convertidos em contratos.

**Preserva**:

- Parâmetros originais do RFQ
- Todas as respostas recebidas
- Histórico de comunicação
- Decisão de não prosseguir (com justificativa)
- Timestamps completos
- Contexto da Timeline

**Uso**:

- Auditoria histórica
- Análise de performance de contrapartes
- Benchmark de preços
- Revisão de estratégias

### 7.11 Cenário: RFQ → Múltiplos Contratos

**Cenário comum**: 1 RFQ pode gerar múltiplos contratos

**Exemplo**:

```
RFQ para hedge de 100t
  ├─> Resposta Contraparte A: 60t @ $2,450
  ├─> Resposta Contraparte B: 40t @ $2,455
  └─> Decisão: Aceitar ambas
      └─> Gera 2 contratos (Camada 6)
```

**Razões**:

- Diversificação de risco de contraparte
- Melhores preços em volumes menores
- Liquidez limitada por contraparte
- Estratégia deliberada

---

## 8. Camada 6: Contratação

### 8.1 Objetivo

Formalizar compromissos financeiros de hedge através de contratos.

### 8.2 Decisão Final: Criar Contrato(s)?

**Responsável**: Financeiro  
**Input**: RFQ fechado com termos acordados  
**Tipo**: Validação final antes de compromisso

**Razão desta decisão adicional**:

- Última oportunidade de revisão
- Validação de condições finais
- Aprovação interna (se requerida)
- Verificação de limites de exposição

**Opções**:

#### 8.2.1 NÃO criar contrato

- **Resultado**: Decisão consciente de não prosseguir
- **Registro**: Log de decisão com justificativa
- **Possíveis razões**:
  - Validação final negativa (ex: erro nos termos)
  - Mudança abrupta de cenário
  - Revisão de estratégia
  - Problema operacional identificado

#### 8.2.2 SIM, criar contrato(s)

- **Resultado**: Formalização de hedge
- **Fluxo**: Aciona `deal_engine.py`

### 8.3 Criação de Trade: `deal_engine.py`

**Serviço automatizado** que cria contratos no sistema.

**Responsabilidades**:

1. Validar estrutura do contrato
2. Gerar identificadores únicos (Contract ID, Trade ID)
3. Estabelecer vínculos (RFQ → Contrato, Exposição → Contrato)
4. Persistir contrato no banco de dados
5. Notificar sistemas downstream (MTM, P&L)
6. Gerar evento para Timeline
7. Atualizar estado da exposição

**Validações**:

- Estrutura de preço é válida
- Volume não excede exposição
- Cliente (do SO) está em KYC approved
- Contraparte passa por controles operacionais (não-KYC), quando aplicável
- Usuário tem permissão (RBAC)

### 8.4 Estrutura do Contrato

#### 8.4.1 Definição

> **1 Contrato = 1 Trade = 2 Legs (buy e sell)**

**Conceito**: Cada contrato representa uma única operação financeira com duas pernas (buy e sell) que formam a estrutura de hedge.

#### 8.4.2 Características

**Imutabilidade**:

- Contrato criado **não pode ser editado**
- Histórico é preservado permanentemente
- Ajustes/correções geram **novos contratos**
- Cancelamentos são registrados, não deletados

**Atributos obrigatórios**:

- Contract ID (único)
- Trade ID (único)
- Contraparte(s)
- Volume (toneladas)
- Estrutura de preço
- Período de referência
- Data de criação
- Usuário criador
- Vínculo com RFQ
- Vínculo com Exposição original
- Vínculo com SO/PO (via exposição)

#### 8.4.3 Tipos de Estrutura

Exemplos comuns:

| Estrutura | Descrição |
|-----------|-----------|
| **Buy Fixing vs Sell Monthly Average** | Compra a preço fixo (fixing), vende à média mensal |
| **Swap / Against** | Troca de exposições (ex: LME vs regional premium) |
| **Collar** | Proteção com teto e piso |
| **Forward simples** | Preço fixo para entrega futura |
| **Estruturas customizadas** | Combinações específicas por estratégia |

### 8.5 Estabelecimento de Vínculos

**Função crítica**: Criar rastreabilidade completa

**Vínculos criados**:

```
Deal → SO → PO → Exposição → RFQ → Contrato
```

**Bidirecionais**:

- Contrato conhece RFQ e Exposição de origem
- RFQ conhece Contrato(s) gerado(s)
- Exposição conhece Contrato(s) que a cobrem

**Atualizações automáticas**:

1. **Volume hedgeado incrementado**:

   ```
   Exposição.volume_hedgeado += Contrato.volume
   ```

2. **Exposição residual recalculada**:

   ```
   Exposição.volume_exposto = Exposição.volume_total - Exposição.volume_hedgeado
   ```

3. **Estado da exposição atualizado**:
   - Se volume_exposto = 0: `FULLY_HEDGED`
   - Se volume_exposto > 0: `PARTIALLY_HEDGED`
   - Exposição residual volta ao Dashboard

4. **Histórico completo mantido**:
   - Registro de qual contrato cobriu qual parte da exposição
   - Timestamps de cada operação
   - Usuário responsável

### 8.6 Notificação e Eventos

Após criação do contrato:

**Eventos gerados**:

- `CONTRACT_CREATED`: Para Timeline
- `EXPOSURE_UPDATED`: Para Dashboard
- `MTM_REQUIRED`: Para serviços de pós-trade

**Notificações**:

- Financeiro: Confirmação de criação
- Compras/Vendas: Visibilidade na Timeline
- Middle Office: Para confirmação com contraparte
- Back Office: Para settlement futuro

---

## 9. Camada 7: Pós-Trade & Valuation

### 9.1 Objetivo

Avaliar continuamente contratos ativos através de mark-to-market (MTM) e gerar reporting financeiro.

### 9.2 Fontes de Mercado

**Provedores de dados**:

| Fonte | Serviço | Dados Fornecidos |
|-------|---------|------------------|
| **LME** | `lme_public.py` | Preços oficiais LME 3-meses, curvas forward, settlement prices |
| **Westmetall** | `westmetall.py` | Prêmios regionais, preços spot Europa, indicadores físicos |
| **Outras** | Configurável | Bloomberg, Reuters, feeds proprietários |

**Tipos de dados**:

- Preços spot (instantâneos)
- Curvas forward (estrutura a termo)
- Volatilidade implícita
- Prêmios regionais
- Dados históricos (para backtesting)

### 9.3 Scheduler: `scheduler.py`

**Serviço automatizado** de execução recorrente.

**Função**:

- **Frequência padrão**: Diária (após fechamento de mercado)
- **Frequência configurável**: Pode ser intraday se necessário
- **Tarefas**:
  1. Ingestão de dados de mercado
  2. Trigger de cálculos MTM
  3. Geração de snapshots
  4. Gestão de retry (se fonte indisponível)
  5. Log de execução e status

**Horário típico**:

- 20:00 UTC (após fechamento LME)
- Configurável por timezone

### 9.4 Cálculo de MTM: `mtm_service.py`

**Serviço automatizado** de mark-to-market.

**Princípio fundamental**:
> **MTM é calculado APENAS para contratos ativos**  
> **Nunca para RFQs ou exposições**

**Fluxo**:

1. Recebe lista de contratos ativos
2. Para cada contrato:
   - Identifica estrutura de preço
   - Obtém preços de mercado relevantes
   - Aplica fórmula de valuation
   - Calcula P&L não realizado
   - Identifica variações desde último cálculo
3. Persiste resultados
4. Dispara geração de snapshots

**Fórmula genérica (simplificada)**:

```
MTM = (Preço_Mercado_Atual - Preço_Contrato) × Volume × Fator_Conversão
```

**Considerações**:

- Ajuste para curvas forward (contratos futuros)
- Desconto de prêmios regionais (se aplicável)
- Tratamento de opções (se houver)
- Impacto de câmbio (se exposição em moeda estrangeira)

### 9.5 Snapshots Históricos: `mtm_snapshot_service.py`

**Serviço automatizado** para registro temporal.

**Função**:

- Criar **snapshot point-in-time** de cada MTM calculado
- Preservar histórico imutável
- Permitir análise de evolução temporal

**Dados armazenados**:

- Contract ID
- Timestamp do snapshot
- MTM calculado
- Preços de mercado utilizados
- P&L não realizado
- Variação desde snapshot anterior
- Fontes de dados (LME, Westmetall, etc.)

**Uso**:

- Reconciliação histórica
- Análise de performance
- Backtesting de estratégias
- Auditoria externa

### 9.6 MTM por Contrato: `contract_mtm_service.py`

**Serviço automatizado** de detalhamento individual.

**Função**:

- Cálculo **individualizado** por contrato
- Detalhamento de componentes
- Breakdown por leg (buy vs sell)
- Sensibilidade a variações de mercado

**Análises disponíveis**:

- MTM total do contrato
- Contribuição de cada leg
- Sensibilidade a 1% de variação de preço (Delta)
- Impacto de tempo (Theta)
- Exposição a volatilidade (Vega) - se houver opções

### 9.7 P&L Consolidado

**Visão financeira integrada** de todos os contratos.

**Consolidações disponíveis**:

| Visão | Descrição |
|-------|-----------|
| **Por contrato individual** | P&L de cada contrato separadamente |
| **Por exposição original** | P&L agregado por exposição que originou hedge |
| **Por período** | P&L por mês/trimestre de referência |
| **Por contraparte** | P&L agregado por contraparte |
| **Visão global** | P&L consolidado de toda a carteira |

**Componentes**:

- **P&L realizado**: De contratos já liquidados
- **P&L não realizado**: MTM de contratos ativos
- **Variação diária**: Mudança de MTM vs dia anterior
- **Acumulado no período**: P&L total do mês/ano

**Fórmula**:

```
P&L Total = P&L Realizado + P&L Não Realizado (MTM)
```

### 9.8 Projeções de Cashflow

**Análise forward-looking** de liquidações futuras.

**Função**:

- Projetar fluxos de caixa esperados
- Identificar necessidades de liquidez
- Simular cenários de mercado
- Analisar sensibilidade

**Projeções incluem**:

- **Liquidações futuras**: Quando contratos serão liquidados
- **Fluxo de caixa esperado**: Valores projetados (entrada/saída)
- **Análise de risco de liquidez**: Períodos críticos
- **Cenários de mercado**: Otimista, base, pessimista
- **Sensibilidade**: Impacto de variações de +/-5%, +/-10%

**Uso**:

- Gestão de tesouraria
- Planejamento financeiro
- Gestão de risco
- Decisões de hedge futuro

---

## 10. Camada 8: Governança Transversal

### 10.1 Objetivo

Garantir controles institucionais de segurança, autorização e auditoria em todas as operações.

### 10.2 Autenticação: `auth.py`

**Serviço de autenticação** de usuários.

**Funções**:

- Login de usuários (usuário/senha ou SSO)
- Gestão de sessões
- Token management (JWT)
- Integração com SSO (se aplicável)
- Multi-factor authentication (se configurado)
- Renovação automática de tokens
- Logout e revogação de sessões

**Mecanismos**:

- Senha hasheada (bcrypt)
- Tokens com expiração
- Rate limiting (proteção contra brute force)

### 10.3 Controle de Acesso: RBAC

**Role-Based Access Control** - controle baseado em perfis.

#### 10.3.1 Perfis Definidos

| Perfil | Permissões |
|--------|------------|
| **Compras** | • Visualizar POs<br/>• Visualizar Timeline<br/>• Adicionar comentários<br/>• READ ONLY em exposições e contratos |
| **Vendas** | • Visualizar SOs<br/>• Visualizar Timeline<br/>• Adicionar comentários<br/>• READ ONLY em exposições e contratos |
| **Financeiro** | • Full access a todas as funcionalidades<br/>• Decisões de hedge<br/>• Criação de RFQs<br/>• Criação de contratos<br/>• Acesso a P&L e MTM |
| **Auditoria** | • READ ONLY global<br/>• Acesso completo a logs<br/>• Exportação de dados<br/>• Não pode executar ações |
| **Admin** | • Gestão de usuários<br/>• Configuração de sistema<br/>• Não necessariamente acessa operações |

#### 10.3.2 Controla

**Quem pode VER cada tela**:

- Dashboard → Financeiro, Auditoria
- Inbox → Financeiro
- Timeline → Todos os perfis
- P&L detalhado → Financeiro, Auditoria

**Quem pode EXECUTAR cada ação**:

- Decisão de hedge → Financeiro
- Criação de RFQ → Financeiro
- Criação de contrato → Financeiro
- Comentários na Timeline → Todos (exceto Auditoria)

#### 10.3.3 Princípios

- **Segregação de funções**: Times operacionais não decidem hedge
- **Least privilege**: Cada perfil tem mínimo necessário
- **Não é workflow de aprovação**: RBAC bloqueia ou permite, não cria aprovações multinível

### 10.4 Know Your Customer: `kyc.py`

### 10.4 KYC (Cliente / SO): `kyc.py`

**Serviço de validação** de **clientes (Customer)** vinculados a **Sales Orders (SO)**.

**Princípio institucional (regra de controle)**:
> **KYC é aplicado ao Cliente/SO (originação)** — não é um gate de compliance para contrapartes de hedge.

**Funções**:

- Verificar documentação do cliente
- Validar status de compliance
- Manter histórico de verificações
- Gerar alertas regulatórios (quando aplicável)

**Validações típicas**:

- Cadastro completo
- Documentos atualizados
- Status KYC do cliente: `approved` / `pending` / `rejected`

**Uso no sistema (gating)**:

- Antes de criar RFQ: o **cliente do SO** deve estar com KYC `approved`
- Antes de award/contratar: o **cliente do SO** deve continuar `approved`

#### 10.4.1 Controles de Contraparte (Não-KYC)

Controles sobre **contrapartes** (corretoras/bancos/etc.) são tratados como **controles operacionais e de risco**, não como “KYC institucional” do fluxo.

Exemplos (quando aplicável):

- Contraparte ativa/habilitada para o canal
- Limites e condições comerciais
- Controles internos (listas restritivas corporativas, risco operacional)

### 10.5 Auditoria: `audit.py`

**Serviço de trilha de auditoria** completa.

#### 10.5.1 Função

Registrar **TODAS as ações sensíveis** de forma:

- **Persistente**: Não pode ser deletado ou editado
- **Completa**: Inclui contexto suficiente para reconstituir ação
- **Precisa**: Timestamps em milissegundos
- **Rastreável**: Vinculado a usuário e sessão

#### 10.5.2 Ações Registradas

**Decisões críticas**:

- Decisão de fazer (ou não) hedge
- Decisão de escopo (total/parcial)
- Decisão de fechar (ou não) RFQ
- Decisão de criar (ou não) contrato

**Criações**:

- Criação de SO/PO
- Criação de exposição (calculada)
- Criação de RFQ
- Envio de RFQ
- Recebimento de resposta
- Criação de contrato

**Atualizações**:

- Atualização de exposição (hedgeada)
- Cálculo de MTM
- Atualização de P&L

**Acessos**:

- Login de usuário
- Visualização de tela sensível (P&L, contratos)
- Exportação de dados

#### 10.5.3 Dados Registrados

Para cada ação:

- **Timestamp**: Data/hora com precisão de milissegundos
- **Usuário**: ID e nome do usuário responsável
- **Ação**: Tipo de ação executada
- **Contexto**: Dados relevantes (IDs de entidades, valores)
- **Estado before/after**: Se aplicável
- **IP e geolocalização**: De onde ação foi executada
- **Session ID**: Identificador da sessão

#### 10.5.4 Princípios

**Log passivo**:
> Auditoria **registra** ações, **não bloqueia** ou **não gera alertas** em tempo real

- Não há enforcement automático
- Não interrompe fluxo operacional
- Revisão é post-facto (após a ação)

**Uso**:

- Auditoria externa
- Investigações internas
- Compliance regulatório
- Análise forense (se necessário)

### 10.6 Conexões com Outras Camadas

**RBAC controla acesso**:

- Dashboard (Camada 4)
- Inbox (Camada 4)
- Decisões de hedge (Camada 4)
- Criação de RFQ (Camada 5)
- Criação de contrato (Camada 6)

**Audit registra**:

- Todas as decisões críticas (Camada 4)
- Todas as decisões de RFQ (Camada 5)
- Todas as decisões de contrato (Camada 6)
- Alimenta Timeline (Camada 2)
- Alimenta rastreabilidade (Camada 9)

---

## 11. Camada 9: Rastreabilidade & Exportação

### 11.1 Objetivo

Garantir rastreabilidade completa end-to-end e preparar dados para auditoria externa.

### 11.2 Cadeia de Rastreabilidade

**Fluxo completo rastreável**:

```
Deal Comercial
    ↓
Sales Order (SO) / Purchase Order (PO)
    ↓
Exposição Calculada
    ↓
RFQ (Request for Quote)
    ↓
Contrato / Trade
    ↓
MTM (Mark-to-Market)
    ↓
P&L Consolidado
    ↓
Cashflow Projetado
```

### 11.3 Vínculos Bidirecionais

**Para cada elemento**:

- **ID único**: Identificador imutável
- **Timestamps**: Criação e atualização
- **Vínculos upstream**: De onde veio (ex: Contrato sabe qual RFQ o originou)
- **Vínculos downstream**: Para onde foi (ex: RFQ sabe quais Contratos gerou)
- **Histórico de modificações**: Log de mudanças de estado
- **Usuário responsável**: Quem executou cada ação

### 11.4 Perguntas Respondidas pela Rastreabilidade

A cadeia completa permite responder:

| Pergunta | Como Responder |
|----------|----------------|
| **De onde veio este P&L?** | P&L → Contrato → RFQ → Exposição → SO/PO → Deal |
| **Qual contrato hedgeou qual exposição?** | Contrato.exposure_id → Exposição |
| **Qual SO/PO originou esta exposição?** | Exposição.so_ids / Exposição.po_ids |
| **Qual RFQ gerou este contrato?** | Contrato.rfq_id → RFQ |
| **Quem tomou decisão de hedge?** | Audit log → Usuário + Timestamp |
| **Por que não fizemos hedge?** | Decision log → Justificativa |
| **Quando contrato foi criado?** | Contrato.created_at |
| **Qual foi o MTM em data X?** | MTM Snapshot na data X |

### 11.5 Exportação & Reconciliação

**Preparação para sistemas externos** e compliance.

#### 11.5.1 Finalidade

- **Auditoria externa**: Big Four, auditores independentes
- **Compliance regulatório**: CVM, BACEN (se aplicável)
- **Análise forense**: Investigações internas
- **Backup institucional**: Disaster recovery
- **Integração ERP/Contabilidade**: SAP, Oracle, etc.

#### 11.5.2 Formatos de Exportação

**Histórico completo**:

- Todas as transações (SO, PO, Exposições, RFQs, Contratos)
- Estados em cada momento
- Vínculos preservados

**Log de auditoria**:

- Todas as ações sensíveis
- Usuários responsáveis
- Timestamps completos
- Contexto de cada ação

**Justificativas de decisões**:

- Por que não hedgeou
- Por que hedge parcial (não total)
- Por que RFQ não fechado
- Por que contrato não criado

**Snapshots temporais**:

- Estado do sistema em data/hora específica
- MTM em datas históricas
- Exposições abertas em momento passado

**Documentação de vínculos**:

- Grafos de relacionamento
- Cadeia completa de rastreabilidade
- Mapeamento de IDs

**Análise de P&L reconciliada**:

- P&L por contrato
- P&L por exposição
- P&L por período
- Reconciliação com contabilidade

#### 11.5.3 Formatos Técnicos

- **JSON**: Estruturado, completo, programático
- **CSV**: Tabular, compatível com Excel
- **PDF**: Relatórios executivos, documentação formal
- **XML**: Integração com sistemas legados
- **API REST**: Exportação programática em tempo real

---

## 12. Fluxos Operacionais Críticos

### 12.1 Fluxo: Hedge Total de Exposição

**Cenário**: Exposição de 100t, decisão de hedge 100%

```
1. SO criado (100t, preço flutuante)
2. PO criado (0t) → Exposição de 100t
3. exposure_aggregation.py calcula exposição
4. Dashboard mostra exposição de 100t
5. Financeiro decide: "Fazer hedge total"
6. Define parâmetros (100t, contrapartes A, B, C)
7. Cria RFQ
8. rfq_engine.py orquestra envio
9. Contrapartes respondem
10. Financeiro fecha RFQ com Contraparte A
11. Cria contrato: 100t com Contraparte A
12. deal_engine.py atualiza exposição:
    - Volume hedgeado = 100t
    - Volume exposto = 0t
    - Estado = FULLY_HEDGED
13. Exposição sai do Inbox (totalmente coberta)
14. mtm_service.py inicia cálculo de MTM do contrato
```

**Resultado**: Exposição totalmente hedgeada, 1 contrato ativo

---

### 12.2 Fluxo: Hedge Parcial com Exposição Residual

**Cenário**: Exposição de 100t, decisão de hedge 60%

```
1. SO criado (100t, preço flutuante)
2. PO criado (0t) → Exposição de 100t
3. exposure_aggregation.py calcula exposição
4. Dashboard mostra exposição de 100t
5. Financeiro decide: "Fazer hedge parcial de 60t"
6. Define parâmetros (60t, contrapartes)
7. Cria RFQ
8. Processo de RFQ (envio, respostas)
9. Fecha RFQ e cria contrato: 60t
10. deal_engine.py atualiza exposição:
    - Volume hedgeado = 60t
    - Volume exposto = 40t (EXPOSIÇÃO RESIDUAL)
    - Estado = PARTIALLY_HEDGED
11. Exposição residual (40t) VOLTA ao Dashboard
12. Inbox mostra: "Exposição residual de 40t"
13. Financeiro pode decidir novo hedge (loop)
```

**Resultado**:

- 1 contrato de 60t ativo
- Exposição residual de 40t em monitoramento
- Possibilidade de novo ciclo de hedge

---

### 12.3 Fluxo: RFQ Não Fechado

**Cenário**: RFQ enviado, mas cotações insatisfatórias

```
1. Exposição identificada
2. Decisão: "Fazer hedge"
3. RFQ criado e enviado
4. Contrapartes respondem:
   - Contraparte A: $2,500/t (acima de expectativa)
   - Contraparte B: $2,510/t (acima de expectativa)
   - Contraparte C: não respondeu
5. Financeiro analisa: "Preços muito altos"
6. Decisão: "NÃO fechar RFQ"
7. RFQ vai para arquivo:
   - Preserva todas as respostas
   - Registra decisão: "Cotações insatisfatórias"
   - Mantém histórico completo
8. Exposição permanece aberta
9. Volta ao ciclo de monitoramento no Dashboard
```

**Resultado**:

- RFQ arquivado (histórico preservado)
- Nenhum contrato criado
- Exposição continua ativa

---

### 12.4 Fluxo: Decisão de Não Hedgear

**Cenário**: Exposição identificada, decisão consciente de não hedgear

```
1. Exposição calculada: 50t
2. Dashboard mostra exposição
3. Financeiro analisa contexto:
   - Preço de mercado em tendência de queda
   - Exposição é de venda (beneficia de queda)
   - Estratégia: manter exposição aberta
4. Decisão: "NÃO fazer hedge"
5. Sistema registra:
   - Decisão em audit log
   - Timestamp e usuário
   - Justificativa (opcional, adicionada na Timeline)
6. Exposição permanece no Dashboard
7. Estado: OPEN (não hedgeada)
8. Monitoramento contínuo
```

**Resultado**:

- Exposição permanece aberta (decisão consciente)
- Registrada em auditoria
- Sujeita a revisão futura

---

### 12.5 Fluxo: 1 RFQ → Múltiplos Contratos

**Cenário**: Hedge dividido entre múltiplas contrapartes

```
1. Exposição: 100t
2. RFQ criado para 100t
3. Respostas:
   - Contraparte A: 60t @ $2,450
   - Contraparte B: 40t @ $2,455
4. Financeiro decide: "Aceitar ambas"
5. Fecha RFQ
6. Decisão: "Criar 2 contratos"
7. deal_engine.py cria:
   - Contrato 1: 60t com Contraparte A
   - Contrato 2: 40t com Contraparte B
8. Ambos vinculados ao mesmo RFQ
9. Ambos vinculados à mesma Exposição
10. Exposição atualizada:
    - Volume hedgeado = 100t
    - Volume exposto = 0t
11. MTM calculado para ambos os contratos
```

**Resultado**:

- 1 RFQ gerou 2 contratos
- Exposição totalmente hedgeada
- Diversificação de contraparte

---

## 13. Serviços e APIs

### 13.1 Visão Geral

O sistema é composto por **serviços Python** especializados que implementam a lógica de negócio.

### 13.2 Catálogo de Serviços

| Serviço | Camada | Função | Tipo |
|---------|--------|--------|------|
| `exposure_aggregation.py` | 3 | Cálculo de exposição líquida | Automático |
| `rfq_engine.py` | 5 | Orquestração de RFQ | Automático |
| `rfq_message_builder.py` | 5 | Construção de mensagens | Automático |
| `rfq_sender.py` | 5 | Envio controlado de RFQ | Automático |
| `deal_engine.py` | 6 | Criação de contratos | Automático |
| `scheduler.py` | 7 | Job recorrente de ingestão | Automático |
| `lme_public.py` | 7 | Ingestão dados LME | Automático |
| `westmetall.py` | 7 | Ingestão dados Westmetall | Automático |
| `mtm_service.py` | 7 | Cálculo de MTM | Automático |
| `mtm_snapshot_service.py` | 7 | Snapshots históricos | Automático |
| `contract_mtm_service.py` | 7 | MTM individualizado | Automático |
| `auth.py` | 8 | Autenticação | Sistema |
| `kyc.py` | 8 | Validação de clientes (SO/Customer) | Sistema |
| `audit.py` | 8 | Trilha de auditoria | Sistema |

### 13.3 Padrões de Integração

**Automáticos (trigger)**:

- Executados por eventos (ex: novo SO → trigger `exposure_aggregation.py`)
- Não requerem intervenção humana

**Scheduled**:

- Executados em horários definidos (ex: `scheduler.py` às 20:00 UTC)

**On-demand**:

- Executados por solicitação de usuário (ex: `deal_engine.py` quando Financeiro cria contrato)

### 13.4 Tecnologia

- **Linguagem**: Python 3.10+
- **Framework web**: FastAPI
- **Banco de dados**: PostgreSQL
- **Cache**: Redis
- **Message queue**: RabbitMQ (para jobs assíncronos)
- **Observabilidade**: Prometheus + Grafana

---

## 14. Estados e Transições

### 14.1 Estados de Exposição

| Estado | Descrição | Próximo Estado Possível |
|--------|-----------|-------------------------|
| `CALCULATED` | Exposição calculada, aguardando análise | `HEDGING_IN_PROGRESS`, `OPEN` |
| `OPEN` | Decisão de não hedgear (monitoramento) | `HEDGING_IN_PROGRESS` (revisão) |
| `HEDGING_IN_PROGRESS` | RFQ em andamento | `PARTIALLY_HEDGED`, `FULLY_HEDGED`, `OPEN` |
| `PARTIALLY_HEDGED` | Parte hedgeada, exposição residual | `HEDGING_IN_PROGRESS` (novo hedge), `FULLY_HEDGED` |
| `FULLY_HEDGED` | 100% coberta | `CLOSED` (após liquidação) |
| `CLOSED` | Liquidada e encerrada | - (final) |

### 14.2 Estados de RFQ

| Estado | Descrição | Próximo Estado Possível |
|--------|-----------|-------------------------|
| `CREATED` | RFQ criado, aguardando envio | `SENDING` |
| `SENDING` | Em processo de envio | `SENT`, `FAILED` |
| `SENT` | Enviado para contrapartes | `PARTIAL_RESPONSE`, `CLOSED`, `ARCHIVED` |
| `PARTIAL_RESPONSE` | Respostas parciais recebidas | `CLOSED`, `ARCHIVED` |
| `CLOSED` | Fechado (aceito) | `CONTRACTED` (após criação de contrato) |
| `ARCHIVED` | Arquivado sem contrato | - (final) |
| `CONTRACTED` | Contrato(s) criado(s) | - (final) |

### 14.3 Estados de Contrato

| Estado | Descrição | Próximo Estado Possível |
|--------|-----------|-------------------------|
| `ACTIVE` | Contrato ativo, MTM calculado | `SETTLED`, `CANCELLED` |
| `SETTLED` | Liquidado (entrega concluída) | - (final) |
| `CANCELLED` | Cancelado (raro, por acordo) | - (final) |

---

## 15. Glossário

### Termos de Negócio

**Deal**: Negociação comercial inicial que origina operações físicas de compra e venda.

**Sales Order (SO)**: Ordem de venda física de commodity a um cliente.

**Purchase Order (PO)**: Ordem de compra física de commodity de um fornecedor.

**Exposição**: Descasamento de preço entre operações físicas (SO/PO) que gera risco de mercado.

**Exposição Ativa**: SO ou PO com preço flutuante sem hedge 100% correspondente.

**Exposição Residual**: Parte da exposição que permanece após hedge parcial.

**Hedge**: Operação financeira (contrato) para proteger contra variação de preço.

**RFQ (Request for Quote)**: Processo estruturado de solicitação de cotação a contrapartes.

**Contrato / Trade**: Compromisso financeiro formal de hedge (1 contrato = 1 trade = 2 legs).

**MTM (Mark-to-Market)**: Avaliação a mercado do valor atual de contratos.

**P&L (Profit & Loss)**: Resultado financeiro (lucro ou prejuízo) de operações.

### Termos Técnicos

**Fixing**: Preço fixado em data específica (ex: média de 3 dias).

**Monthly Average**: Média de preços ao longo de um mês.

**Swap / Against**: Troca de exposições entre diferentes índices ou períodos.

**LME (London Metal Exchange)**: Bolsa de metais de Londres, referência para preços de alumínio.

**Westmetall**: Provedor de dados de mercado para metais (prêmios regionais).

**RBAC (Role-Based Access Control)**: Controle de acesso baseado em perfis de usuário.

**KYC (Know Your Customer)**: Processo de validação e compliance de **clientes** (Customer) vinculados a Sales Orders (SO).

**Idempotência**: Garantia de que operação repetida não gera duplicação.

### Conceitos do Sistema

**Timeline**: Hub central de comunicação e visibilidade entre times.

**Dashboard**: Visualização consolidada de exposições e métricas.

**Inbox do Financeiro**: Interface de trabalho para decisões de hedge.

**Exposição líquida (Net Exposure)**: Volume total exposto após descontar hedges.

**Rastreabilidade end-to-end**: Capacidade de rastrear desde Deal até P&L.

**Auditoria passiva**: Log que registra mas não bloqueia ações.

**Snapshot point-in-time**: Registro do estado do sistema em momento específico.

---

## Apêndices

### A. Referências

- Diagrama institucional de referência (FigJam)
- Especificação técnica de APIs (Swagger/OpenAPI)
- Manual de usuário por perfil
- Runbooks operacionais

### B. Histórico de Versões

| Versão | Data | Autor | Mudanças |
|--------|------|-------|----------|
| 1.0 | Janeiro 2026 | Andrei - Previse Capital | Versão inicial completa |

### C. Contatos

**Desenvolvimento**: [equipe técnica]  
**Financeiro (Product Owner)**: Andrei  
**Suporte**: [equipe de suporte]

---

**Fim do Documento**
