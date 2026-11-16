# Eval: simulado / palavras-chave

2026-11-16 16:03 UTC · 40 de 40 conversas avaliadas

| Métrica | Valor |
| --- | --- |
| Acerto exato por critério | 73% |
| Acerto com até 1 nível de diferença | 85% |
| Kappa de Cohen (geral) | 0.51 |
| Erro médio da nota (0 a 100) | 27.4 pontos |
| Correlação da nota (Pearson) | 0.50 |
| Falha crítica: precisão / revocação | 80% / 31% |
| Falha crítica: perdidas / falsos alarmes | 9 / 1 |
| Tentativas extras (validação recusou) | 0 |
| Custo estimado | US$ 0.00 |
| Tokens (entrada / saída) | 0 / 0 |
| Tempo médio por conversa | 0.0 s |

## Por critério

| Critério | Acerto | Até 1 nível | Kappa |
| --- | --- | --- | --- |
| `saudacao` | 100% | 100% | 1.00 |
| `identificacao_titular` | 57% | 62% | 0.37 |
| `entendimento` | 78% | 88% | 0.00 |
| `diagnostico` | 72% | 82% | 0.52 |
| `solucao_correta` | 70% | 85% | 0.00 |
| `procedimento` | 42% | 62% | 0.00 |
| `informacao_precisa` | 68% | 78% | 0.00 |
| `clareza` | 80% | 90% | 0.00 |
| `empatia` | 75% | 88% | 0.00 |
| `retencao` | 82% | 92% | 0.64 |
| `protocolo` | 88% | 98% | 0.78 |
| `encerramento` | 62% | 100% | 0.40 |

## Matriz de confusão (linhas: referência; colunas: juiz)

| | atende | parcial | nao_atende | nao_se_aplica |
| --- | --- | --- | --- | --- |
| **atende** | 251 | 10 | 2 | 10 |
| **parcial** | 40 | 20 | 3 | 2 |
| **nao_atende** | 37 | 7 | 25 | 5 |
| **nao_se_aplica** | 10 | 0 | 4 | 54 |
