# PUFA-SOCIAL — Gestão de Mídias Sociais

> Domínio aplicado do PUFA para **planejamento de conteúdo** em mídias sociais:
> mix de pilares, horários, formatos e detecção de posts fora da curva.
> Implementação: [`empirical/social_media/pufa_social.py`](../../empirical/social_media/pufa_social.py).

---

## 0. Classificação

| Item | Valor |
|---|---|
| Tipo de Ω | **Teoria empírica** (modelo estatístico de decisão) |
| Funtor empírico | $F_{\text{emp}}$ **existe** — métricas das plataformas (alcance, curtidas, comentários, compartilhamentos, salvamentos) |
| Testabilidade | Estatística (testes A/B, validação fora da amostra) |
| Camadas PUFA usadas | 1 (C*-álgebra), 2 (estados), 3–4 (dinâmica modular / KMS), 5 (superestatística — só conjectura), 7 |

O framework produz **invariantes da descrição** (mix ótimo sob um critério explícito), não
afirmações sobre "como o algoritmo da plataforma funciona". Consistência formal ≠ verdade empírica.

---

## 1. Decomposição Ω = (tipos, axiomas, operações, simetrias)

### 1.1 Tipos

| Símbolo | Tipo | Significado |
|---|---|---|
| $K \in \mathbb{N}$ | inteiro | número de pilares de conteúdo (ex.: educativo, bastidores, produto…) |
| $\mathcal{A}_{\text{SOC}} = M_K(\mathbb{C})$ | C*-álgebra unital | álgebra de descrições sobre os pilares |
| $\mathcal{D}_K \subset \mathcal{A}_{\text{SOC}}$ | subálgebra abeliana maximal (diagonais) | **observáveis com $F_{\text{emp}}$** |
| $P_k = \lvert k\rangle\langle k\rvert$ | projeção | "o post pertence ao pilar $k$" |
| $\hat e_k \in \mathbb{R}$ | escalar | engajamento estimado do pilar $k$ |
| $E = \sum_k z_k P_k \in \mathcal{D}_K^{\text{sa}}$ | observável | engajamento padronizado |
| $H = -E$ | autoadjunto | "hamiltoniano" do domínio |
| $\omega$ | estado | política de publicação (mix de conteúdo) |
| $\beta \ge 0$ | escalar | inverso da "temperatura de exploração" |

**Observação de rigor.** Na álgebra abeliana $\mathcal{D}_K$ a dinâmica $\mathrm{Ad}\,e^{itH}$ é trivial e
*todo* estado é KMS — o formalismo degeneraria. Por isso trabalhamos em $M_K(\mathbb{C})$, onde a
dinâmica age não trivialmente sobre os elementos fora da diagonal. Esses elementos **não têm
$F_{\text{emp}}$** (não existe métrica de plataforma para "coerência entre pilares"); servem
apenas para fixar o estado de equilíbrio de modo único. Só a restrição $\omega|_{\mathcal{D}_K}$ é
usada nas recomendações.

### 1.2 Axiomas

- **S1 (Engajamento ponderado).** Para cada post, $e = 100\cdot\sum_i w_i x_i/\text{alcance}$, com
  pesos $w = (1, 3, 5, 4)$ para (curtidas, comentários, compartilhamentos, salvamentos).
  *Escolha de modelagem — ajustável, não derivada.*
- **S2 (Dinâmica).** $\sigma_t(a) = e^{itH} a\, e^{-itH}$, $a \in \mathcal{A}_{\text{SOC}}$.
- **S3 (Política = estado KMS).** A política recomendada é o estado $(\sigma, \beta)$-KMS $\omega_\beta$.
- **S4 (Diversidade alvo).** $\beta$ é fixado por $\exp S(\omega_\beta) = n_{\text{ef}}$, o número
  efetivo de pilares desejado (padrão $\max(2,\,0{,}6K)$).

### 1.3 Operações (pipeline)

1. $F_{\text{emp}}$: CSV de posts → amostras $\{e\}$ por pilar, formato, plataforma, dia, hora.
2. Encolhimento empírico-Bayes: $\hat e_k = \dfrac{n_k\bar x_k + m\mu}{n_k + m}$, $m = \sigma^2_{\text{dentro}}/\tau^2_{\text{entre}}$.
3. Padronização $z_k = (\hat e_k - \bar{\hat e})/\mathrm{sd}(\hat e)$.
4. Estado de Gibbs: $\omega_\beta(a) = \mathrm{Tr}(e^{-\beta H}a)/Z$, $\;p_k = \omega_\beta(P_k) = e^{\beta z_k}/\sum_j e^{\beta z_j}$.
5. Alocação inteira de $N$ posts/semana pelo maior resto (Hamilton); sequência sem repetição consecutiva.
6. Horários: modelo aditivo dia + hora com encolhimento em cada efeito.
7. Diagnóstico: $z$ robusto (mediana/MAD) para outliers; tendência por mínimos quadrados semanais.

### 1.4 Simetrias

| Simetria | Ação | Consequência |
|---|---|---|
| Translação | $H \mapsto H + c\mathbb{1}$ | $\omega_\beta$ invariante → só diferenças de engajamento importam |
| Escala | $(H, \beta) \mapsto (\lambda H, \beta/\lambda)$ | unidade de engajamento é irrelevante; justifica a padronização |
| Permutação $S_K$ | $P_k \mapsto P_{\pi(k)}$ | nomes/ordem dos pilares não afetam o resultado |
| Unitária | $a \mapsto UaU^*$, $[U,H]=0$ | pilares com mesmo $z_k$ recebem a mesma participação |

---

## 2. Resultados

**Proposição 1 [PROVADO].** Em $M_K(\mathbb{C})$ com $\sigma_t = \mathrm{Ad}\,e^{itH}$, o estado de Gibbs
$\omega_\beta$ é o **único** estado $(\sigma,\beta)$-KMS (resultado padrão para álgebras de matrizes;
Bratteli–Robinson, vol. 2, §5.3). Sua restrição a $\mathcal{D}_K$ é a distribuição softmax $p_k(\beta)$.

**Proposição 2 [PROVADO] (princípio variacional).** Para todo estado $\omega$,
$$
\omega(E) + \tfrac{1}{\beta} S(\omega) \;\le\; \omega_\beta(E) + \tfrac{1}{\beta} S(\omega_\beta) = \tfrac{1}{\beta}\log Z,
$$
com igualdade sse $\omega = \omega_\beta$. **Leitura gerencial:** o mix KMS é o que maximiza
engajamento esperado **mais** diversidade (entropia), com $1/\beta$ como taxa de troca entre os dois.

**Proposição 3 [PROVADO].** $\dfrac{dS(\omega_\beta)}{d\beta} = -\beta\,\mathrm{Var}_{\omega_\beta}(H) \le 0$.
Logo o $\beta$ do axioma S4 existe e é único sempre que $1 < n_{\text{ef}} < K$ e $H \notin \mathbb{C}\mathbb{1}$.

**Proposição 4 [PROVADO].** Limites: $\beta \to 0$ dá o estado tracial (mix uniforme, exploração pura);
$\beta \to \infty$ dá o estado fundamental (todo o volume no melhor pilar, explotação pura).

**Proposição 5 [REQUER HIPÓTESE: pilares permutáveis a priori, $\hat e \sim \mathcal{N}(\mu,\tau^2)$].**
O estimador encolhido tem erro quadrático médio menor que as médias brutas para $K \ge 3$ (Stein, 1956;
Efron–Morris, 1973). Quando $\hat\tau^2 \le 0$ os dados não distinguem os grupos e a estimativa colapsa em $\mu$.

**Proposição 6 [REQUER HIPÓTESE: sem interação dia × hora].** O ranking de horários é aditivo:
$\hat e(d,h) = \hat e_{\text{dia}}(d) + \hat e_{\text{hora}}(h) - \mu$.

**Proposição 7 [REQUER HIPÓTESE: retorno marginal decrescente linear].** Com fadiga $\lambda > 0$,
$z_k \mapsto z_k - \lambda K(s_k - 1/K)$, onde $s_k$ é a participação do pilar nas últimas 4 semanas.

**Proposição 8 [REQUER HIPÓTESE: estacionariedade].** As recomendações supõem que a distribuição de
engajamento não muda no horizonte de planejamento. Mudanças de algoritmo das plataformas violam essa hipótese;
recomenda-se reestimar semanalmente.

**Conjectura 1 [CONJECTURA] (superestatística, Camada 5).** A cauda pesada das taxas de engajamento
(posts "virais") é compatível com $\beta$ flutuante na audiência, $f(\beta)$ do tipo $\chi^2$, gerando
estatística de Tsallis. Testável ajustando $q$ às distribuições de alcance; **não implementado**.

**Conjectura 2 [CONJECTURA].** Um $\beta_t$ crescente no tempo (recozimento: explorar no início, concentrar
depois) supera o $\beta$ fixo em engajamento acumulado. Observação: softmax com temperatura fixa **não** é
ótimo em regret no problema de bandidos; o critério aqui é o da Proposição 2, não minimização de regret.

---

## 3. Como interpretar o $\beta$ na prática

| Situação da conta | $n_{\text{ef}}$ sugerido | Efeito |
|---|---|---|
| Conta nova / reposicionamento | próximo de $K$ | testar todos os pilares |
| Conta estável | $0{,}6K$ (padrão) | concentrar sem perder variedade |
| Campanha com meta curta | 1,5 – 2 | quase tudo no pilar campeão |

---

## Referências

- Bratteli, O.; Robinson, D. W. *Operator Algebras and Quantum Statistical Mechanics 2*. Springer, 1997.
- Stein, C. Inadmissibility of the usual estimator for the mean of a multivariate normal distribution. *Proc. 3rd Berkeley Symp.*, 1956.
- Efron, B.; Morris, C. Stein's estimation rule and its competitors. *JASA* 68, 1973.
- Iglewicz, B.; Hoaglin, D. *How to Detect and Handle Outliers*. ASQC, 1993.
- Beck, C.; Cohen, E. G. D. Superstatistics. *Physica A* 322, 2003.
