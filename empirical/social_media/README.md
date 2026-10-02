# PUFA-SOCIAL — Algoritmo de Gestão de Mídias Sociais

Gera, a partir do histórico de posts, um **plano semanal de conteúdo**: calendário (dia/hora/pilar/formato),
mix ótimo de pilares, ranking de horários e formatos, tendência e posts fora da curva.
Fundamentação formal: [`domains/SOCIAL/README.md`](../../domains/SOCIAL/README.md).

Somente Python ≥ 3.8, sem dependências.

## Uso rápido

```bash
cd empirical/social_media
python pufa_social.py --demo                      # dados sintéticos
python pufa_social.py --csv meus_posts.csv --posts-semana 5 --saida relatorio.md
python -m unittest test_pufa_social.py            # testes
```

## Formato do CSV

Modelo pronto: [`exemplo_posts.csv`](exemplo_posts.csv) (dados **sintéticos**). Exemplo de saída:
[`exemplo_relatorio.md`](exemplo_relatorio.md).

| Coluna | Exemplo | Observação |
|---|---|---|
| `data` | 2026-09-14 | AAAA-MM-DD |
| `hora` | 18 | hora cheia (0–23) |
| `plataforma` | instagram | livre |
| `pilar` | educativo | categoria editorial |
| `formato` | reels | reels, carrossel, imagem, stories… |
| `alcance` | 2300 | contas alcançadas |
| `curtidas`, `comentarios`, `compartilhamentos`, `salvamentos` | 120, 8, 5, 14 | contagens |

Dá para exportar essas colunas do Meta Business Suite, TikTok Analytics ou LinkedIn e renomear.

## Parâmetros

| Flag | Padrão | Significado |
|---|---|---|
| `--posts-semana N` | 5 | posts no calendário (até 7 → um por dia; acima disso, 2º horário) |
| `--n-efetivo X` | max(2, 0,6·K) | diversidade alvo: "quantos pilares efetivos" o mix deve ter |
| `--beta B` | automático | fixa β diretamente (ignora `--n-efetivo`) |
| `--fadiga λ` | 0 | penaliza pilares super-representados nas últimas 4 semanas |
| `--metrica` | taxa | `taxa` (engajamento/alcance), `interacoes` (volume absoluto) ou `alcance` |
| `--sem-robustez` | — | desliga a winsorização de posts extremos |

## O que cada etapa faz (em linguagem de gestão)

1. **Engajamento ponderado** — compartilhar e salvar valem mais que curtir.
2. **Encolhimento** — pilar com 3 posts e média alta não "vence" por sorte: a estimativa é puxada para a média geral na proporção da incerteza.
3. **Robustez** — um post viral isolado é limitado antes de calcular médias (continua aparecendo como outlier).
4. **Mix KMS** — distribui o volume entre pilares maximizando *engajamento esperado + diversidade*. β regula o quanto concentrar.
5. **Horários** — efeito do dia + efeito da faixa (manhã/tarde/noite/madrugada), estimados separadamente (mais dados por estimativa).
6. **Calendário** — melhores horários espalhados pela semana, sem repetir pilar em sequência.
7. **Outliers** — posts muito acima/abaixo do normal (z robusto > 3,5) para estudar o que replicar ou evitar.

## Limites

- Correlação, não causalidade: para confirmar, rode testes A/B (mesmo pilar, horários diferentes etc.).
- Supõe estabilidade das plataformas; reexecute semanalmente.
- Com menos de ~30 posts o relatório avisa que a incerteza é alta.

## Dados de contas reais

Coloque CSVs de contas reais em `contas/<perfil>/` — essa pasta está no `.gitignore`
(métricas de alcance não são públicas e não devem ir para o repositório).
