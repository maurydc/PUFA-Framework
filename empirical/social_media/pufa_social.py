"""
PUFA-SOCIAL — Algoritmo de gestão de mídias sociais.

Implementa o domínio formal descrito em domains/SOCIAL/README.md:

    A_SOC = M_K(C)              álgebra de observáveis sobre K pilares de conteúdo
    H     = -diag(z_1,...,z_K)   "hamiltoniano" = menos o engajamento padronizado
    ω_β(a) = Tr(e^{-βH} a)/Z     estado de Gibbs = único estado (σ,β)-KMS

A diagonal de ω_β fornece o mix de conteúdo p_k(β) ∝ exp(β z_k).
β controla exploração (β→0, estado tracial/uniforme) versus explotação
(β→∞, estado fundamental concentrado no melhor pilar).

Pipeline:
    1. Leitura de posts (CSV)                   -> F_emp: métricas da plataforma
    2. Observável de engajamento ponderado       -> e_post
    3. Encolhimento empírico-Bayes por pilar     -> ê_k   [REQUER HIPÓTESE: permutabilidade]
    4. Estado de Gibbs/KMS com β por entropia    -> p_k   [PROVADO: princípio variacional]
    5. Ranking de horários (dia, hora)           -> slots
    6. Calendário semanal + detecção de outliers -> relatório Markdown

Somente biblioteca padrão (sem dependências externas).

Uso:
    python pufa_social.py --demo
    python pufa_social.py --csv posts.csv --posts-semana 5 --saida relatorio.md
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]

# Pesos das interações: ações de maior custo cognitivo valem mais.
# Hipótese de modelagem explícita (ajustável via CLI), não derivada dos axiomas.
PESOS_PADRAO = {"curtidas": 1.0, "comentarios": 3.0, "compartilhamentos": 5.0, "salvamentos": 4.0}

COLUNAS = [
    "data", "hora", "plataforma", "pilar", "formato",
    "alcance", "curtidas", "comentarios", "compartilhamentos", "salvamentos",
]


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------

@dataclass
class Post:
    data: date
    hora: int
    plataforma: str
    pilar: str
    formato: str
    alcance: float
    curtidas: float
    comentarios: float
    compartilhamentos: float
    salvamentos: float

    @property
    def dia_semana(self) -> str:
        return DIAS[self.data.weekday()]

    def engajamento(self, pesos: Dict[str, float] = PESOS_PADRAO) -> Optional[float]:
        """Taxa de engajamento ponderada (%), e = 100 · Σ w_i x_i / alcance."""
        if self.alcance <= 0:
            return None
        bruto = sum(pesos[k] * getattr(self, k) for k in pesos)
        return 100.0 * bruto / self.alcance


def ler_csv(caminho: str) -> List[Post]:
    posts: List[Post] = []
    with open(caminho, newline="", encoding="utf-8") as f:
        leitor = csv.DictReader(f)
        faltando = set(COLUNAS) - set(leitor.fieldnames or [])
        if faltando:
            raise ValueError(f"CSV sem colunas obrigatórias: {sorted(faltando)}")
        for linha in leitor:
            posts.append(Post(
                data=datetime.strptime(linha["data"].strip(), "%Y-%m-%d").date(),
                hora=int(linha["hora"]),
                plataforma=linha["plataforma"].strip(),
                pilar=linha["pilar"].strip(),
                formato=linha["formato"].strip(),
                alcance=float(linha["alcance"] or 0),
                curtidas=float(linha["curtidas"] or 0),
                comentarios=float(linha["comentarios"] or 0),
                compartilhamentos=float(linha["compartilhamentos"] or 0),
                salvamentos=float(linha["salvamentos"] or 0),
            ))
    return posts


def gerar_dados_sinteticos(n: int = 120, semente: int = 42, inicio: date = date(2026, 6, 1)) -> List[Post]:
    """Dados SINTÉTICOS para demonstração — não representam nenhuma conta real."""
    rng = random.Random(semente)
    pilares = {"educativo": 4.0, "bastidores": 3.0, "produto": 2.2, "humor": 3.4, "depoimento": 2.8}
    formatos = {"reels": 1.3, "carrossel": 1.15, "imagem": 0.85, "stories": 0.7}
    bonus_hora = {9: 1.0, 12: 1.15, 18: 1.25, 20: 1.35, 22: 0.9}
    bonus_dia = [1.0, 1.05, 1.1, 1.1, 0.95, 0.8, 0.85]
    posts = []
    for i in range(n):
        d = inicio + timedelta(days=rng.randrange(0, 120))
        hora = rng.choice(list(bonus_hora))
        pilar = rng.choice(list(pilares))
        formato = rng.choice(list(formatos))
        plataforma = rng.choice(["instagram", "instagram", "tiktok", "linkedin"])
        alcance = max(50.0, rng.lognormvariate(7.5, 0.6))
        taxa = pilares[pilar] * formatos[formato] * bonus_hora[hora] * bonus_dia[d.weekday()]
        taxa *= rng.lognormvariate(0, 0.35)
        if rng.random() < 0.03:  # cauda pesada ocasional ("viral")
            taxa *= 4
        interacoes = alcance * taxa / 100.0
        posts.append(Post(
            data=d, hora=hora, plataforma=plataforma, pilar=pilar, formato=formato,
            alcance=round(alcance),
            curtidas=round(interacoes * 0.55),
            comentarios=round(interacoes * 0.05),
            compartilhamentos=round(interacoes * 0.03),
            salvamentos=round(interacoes * 0.05),
        ))
    posts.sort(key=lambda p: (p.data, p.hora))
    return posts


def salvar_csv(posts: Iterable[Post], caminho: str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUNAS)
        for p in posts:
            w.writerow([p.data.isoformat(), p.hora, p.plataforma, p.pilar, p.formato,
                        int(p.alcance), int(p.curtidas), int(p.comentarios),
                        int(p.compartilhamentos), int(p.salvamentos)])


# ---------------------------------------------------------------------------
# Estimação: encolhimento empírico-Bayes
# ---------------------------------------------------------------------------

@dataclass
class Estimativa:
    grupo: str
    n: int
    media_bruta: float
    media_encolhida: float
    erro_padrao: float


def encolhimento(grupos: Dict[str, List[float]]) -> List[Estimativa]:
    """
    Estimador de James–Stein / empírico-Bayes normal:
        ê_k = (n_k x̄_k + m μ) / (n_k + m),   m = σ²_dentro / τ²_entre.
    [REQUER HIPÓTESE] permutabilidade dos pilares a priori (prior comum N(μ, τ²)).
    Reduz o erro quadrático médio para K ≥ 3 sob normalidade [PROVADO: Stein 1956].
    """
    todos = [x for xs in grupos.values() for x in xs]
    if not todos:
        return []
    mu = statistics.fmean(todos)
    # variância dentro dos grupos (combinada)
    ss, gl = 0.0, 0
    for xs in grupos.values():
        if len(xs) > 1:
            m_ = statistics.fmean(xs)
            ss += sum((x - m_) ** 2 for x in xs)
            gl += len(xs) - 1
    sigma2 = ss / gl if gl > 0 else (statistics.pvariance(todos) if len(todos) > 1 else 1.0)
    sigma2 = max(sigma2, 1e-12)
    # variância entre grupos pelo método dos momentos
    medias = [statistics.fmean(xs) for xs in grupos.values() if xs]
    n_medio = statistics.fmean([len(xs) for xs in grupos.values() if xs])
    var_medias = statistics.pvariance(medias) if len(medias) > 1 else 0.0
    tau2 = var_medias - sigma2 / n_medio
    saida = []
    for g, xs in grupos.items():
        n = len(xs)
        if n == 0:
            continue
        xb = statistics.fmean(xs)
        if tau2 > 1e-12:
            m = sigma2 / tau2
            est, ep = (n * xb + m * mu) / (n + m), math.sqrt(sigma2 / (n + m))
        else:
            # τ² ≤ 0: dados não distinguem os grupos ⇒ encolhimento total para μ;
            # a incerteza restante é a da própria média global.
            est, ep = mu, math.sqrt(sigma2 / len(todos))
        saida.append(Estimativa(grupo=g, n=n, media_bruta=xb, media_encolhida=est, erro_padrao=ep))
    saida.sort(key=lambda e: e.media_encolhida, reverse=True)
    return saida


# ---------------------------------------------------------------------------
# Estado de Gibbs / KMS sobre M_K(C)
# ---------------------------------------------------------------------------

def padronizar(valores: Sequence[float]) -> List[float]:
    """z_k = (ê_k − média)/desvio. Usa as simetrias H→H+c·1 e (H,β)→(λH,β/λ)."""
    if len(valores) < 2:
        return [0.0] * len(valores)
    mu = statistics.fmean(valores)
    sd = statistics.pstdev(valores)
    if sd < 1e-12:
        return [0.0] * len(valores)
    return [(v - mu) / sd for v in valores]


def gibbs(z: Sequence[float], beta: float) -> List[float]:
    """Diagonal do estado KMS: p_k = exp(β z_k) / Σ_j exp(β z_j) (forma numericamente estável)."""
    zmax = max(z)
    w = [math.exp(beta * (zi - zmax)) for zi in z]
    s = sum(w)
    return [wi / s for wi in w]


def entropia(p: Sequence[float]) -> float:
    return -sum(pi * math.log(pi) for pi in p if pi > 0)


def beta_por_entropia(z: Sequence[float], n_efetivo: float, beta_max: float = 50.0) -> float:
    """
    Resolve exp(S(ω_β)) = n_efetivo por bissecção.
    [PROVADO] dS/dβ = −β·Var_ω(H) ≤ 0, logo S é monótona e a raiz é única quando existe.
    """
    k = len(z)
    if k <= 1 or max(z) - min(z) < 1e-12:
        return 0.0
    alvo = math.log(min(max(n_efetivo, 1.0 + 1e-9), k))
    if entropia(gibbs(z, 0.0)) <= alvo:
        return 0.0
    if entropia(gibbs(z, beta_max)) >= alvo:
        return beta_max
    lo, hi = 0.0, beta_max
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if entropia(gibbs(z, mid)) > alvo:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def energia_livre(z: Sequence[float], p: Sequence[float], beta: float) -> float:
    """Funcional variacional F(ω) = ω(E) + S(ω)/β, maximizado por ω_β [PROVADO: princípio de Gibbs]."""
    if beta <= 0:
        return entropia(p)
    return sum(pi * zi for pi, zi in zip(p, z)) + entropia(p) / beta


# ---------------------------------------------------------------------------
# Horários, calendário, outliers, tendência
# ---------------------------------------------------------------------------

def ranking_slots(posts: Sequence[Post], pesos=PESOS_PADRAO) -> List[Estimativa]:
    """
    Modelo aditivo: ê(d,h) = ê_dia(d) + ê_hora(h) − μ, cada efeito com encolhimento próprio.
    [REQUER HIPÓTESE] ausência de interação dia×hora. Usa ~K vezes mais dados por
    parâmetro que o ajuste célula a célula e permite pontuar combinações nunca testadas.
    """
    validos = [(p, p.engajamento(pesos)) for p in posts]
    validos = [(p, e) for p, e in validos if e is not None]
    if not validos:
        return []
    mu = statistics.fmean(e for _, e in validos)
    dias = {e.grupo: e for e in encolhimento(_agrupar([p for p, _ in validos], lambda p: p.dia_semana, pesos))}
    horas = {e.grupo: e for e in encolhimento(_agrupar([p for p, _ in validos], lambda p: f"{p.hora:02d}h", pesos))}
    celulas: Dict[str, List[float]] = defaultdict(list)
    for p, e in validos:
        celulas[f"{p.dia_semana} {p.hora:02d}h"].append(e)
    saida = []
    for d in DIAS:
        if d not in dias:
            continue
        for h, eh in horas.items():
            g = f"{d} {h}"
            xs = celulas.get(g, [])
            saida.append(Estimativa(
                grupo=g, n=len(xs),
                media_bruta=statistics.fmean(xs) if xs else float("nan"),
                media_encolhida=dias[d].media_encolhida + eh.media_encolhida - mu,
                erro_padrao=math.hypot(dias[d].erro_padrao, eh.erro_padrao),
            ))
    saida.sort(key=lambda e: e.media_encolhida, reverse=True)
    return saida


def alocar(n_posts: int, probs: Dict[str, float]) -> Dict[str, int]:
    """Arredondamento pelo maior resto (método de Hamilton): Σ n_k = N exatamente."""
    cotas = {k: n_posts * v for k, v in probs.items()}
    base = {k: int(math.floor(c)) for k, c in cotas.items()}
    resto = n_posts - sum(base.values())
    for k in sorted(cotas, key=lambda k: cotas[k] - base[k], reverse=True)[:resto]:
        base[k] += 1
    return base


def ordenar_sem_repeticao(contagem: Dict[str, int]) -> List[str]:
    """Sequência gulosa que evita o mesmo pilar em posts consecutivos sempre que possível."""
    restante = dict(contagem)
    seq: List[str] = []
    while sum(restante.values()) > 0:
        candidatos = sorted((k for k, v in restante.items() if v > 0), key=lambda k: -restante[k])
        escolha = next((k for k in candidatos if not seq or k != seq[-1]), candidatos[0])
        seq.append(escolha)
        restante[escolha] -= 1
    return seq


def escolher_slots(slots: Sequence[Estimativa], n_posts: int) -> List[str]:
    """Melhor horário por dia primeiro (espalha a semana); depois segundos horários se N > 7."""
    usados_dia: Dict[str, int] = defaultdict(int)
    escolhidos: List[str] = []
    for rodada in range(1, 10):
        for s in slots:  # já ordenados por média encolhida
            if len(escolhidos) >= n_posts:
                break
            dia = s.grupo.split()[0]
            if s.grupo not in escolhidos and usados_dia[dia] < rodada:
                escolhidos.append(s.grupo)
                usados_dia[dia] += 1
        if len(escolhidos) >= n_posts:
            break
    ordem = {d: i for i, d in enumerate(DIAS)}
    escolhidos.sort(key=lambda g: (ordem[g.split()[0]], g.split()[1]))
    return escolhidos


def outliers(posts: Sequence[Post], pesos=PESOS_PADRAO, limiar: float = 3.5) -> List[Tuple[Post, float, float]]:
    """z robusto (Iglewicz–Hoaglin): z = 0.6745 (x − mediana)/MAD."""
    pares = [(p, p.engajamento(pesos)) for p in posts]
    pares = [(p, e) for p, e in pares if e is not None]
    if len(pares) < 5:
        return []
    xs = [e for _, e in pares]
    med = statistics.median(xs)
    mad = statistics.median([abs(x - med) for x in xs])
    if mad < 1e-12:
        return []
    saida = [(p, e, 0.6745 * (e - med) / mad) for p, e in pares]
    return sorted([t for t in saida if abs(t[2]) > limiar], key=lambda t: -t[2])


def tendencia_semanal(posts: Sequence[Post], pesos=PESOS_PADRAO) -> Optional[Tuple[float, int]]:
    """Inclinação (pontos percentuais / semana) por mínimos quadrados sobre médias semanais."""
    sem: Dict[int, List[float]] = defaultdict(list)
    for p in posts:
        e = p.engajamento(pesos)
        if e is not None:
            sem[p.data.toordinal() // 7].append(e)
    if len(sem) < 3:
        return None
    xs = sorted(sem)
    ys = [statistics.fmean(sem[x]) for x in xs]
    xm, ym = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - xm) ** 2 for x in xs)
    return (sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den, len(xs))


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

@dataclass
class Plano:
    pilares: List[Estimativa]
    formatos: List[Estimativa]
    plataformas: List[Estimativa]
    mix: Dict[str, float]
    beta: float
    n_efetivo: float
    slots: List[Estimativa]
    calendario: List[Tuple[str, str, str]]  # (slot, pilar, formato sugerido)
    outliers: List[Tuple[Post, float, float]]
    tendencia: Optional[Tuple[float, int]]
    n_posts: int
    fadiga: float = 0.0
    avisos: List[str] = field(default_factory=list)


def _agrupar(posts: Sequence[Post], chave, pesos) -> Dict[str, List[float]]:
    g: Dict[str, List[float]] = defaultdict(list)
    for p in posts:
        e = p.engajamento(pesos)
        if e is not None:
            g[chave(p)].append(e)
    return g


def planejar(posts: Sequence[Post], posts_semana: int = 5, n_efetivo: Optional[float] = None,
             beta: Optional[float] = None, fadiga: float = 0.0, janela_fadiga_dias: int = 28,
             pesos: Dict[str, float] = PESOS_PADRAO) -> Plano:
    if not posts:
        raise ValueError("Nenhum post fornecido.")
    avisos = []
    validos = [p for p in posts if p.engajamento(pesos) is not None]
    if len(validos) < len(posts):
        avisos.append(f"{len(posts) - len(validos)} post(s) com alcance 0 ignorados.")
    if len(validos) < 30:
        avisos.append("Menos de 30 posts válidos: estimativas com alta incerteza.")

    pilares = encolhimento(_agrupar(validos, lambda p: p.pilar, pesos))
    formatos = encolhimento(_agrupar(validos, lambda p: p.formato, pesos))
    plataformas = encolhimento(_agrupar(validos, lambda p: p.plataforma, pesos))

    nomes = [e.grupo for e in pilares]
    z = padronizar([e.media_encolhida for e in pilares])

    # Fadiga [REQUER HIPÓTESE]: retorno marginal decrescente com a participação recente.
    if fadiga > 0:
        ultimo = max(p.data for p in validos)
        recentes = [p for p in validos if (ultimo - p.data).days <= janela_fadiga_dias]
        tot = max(len(recentes), 1)
        k = len(nomes)
        share = {n: sum(1 for p in recentes if p.pilar == n) / tot for n in nomes}
        z = [zi - fadiga * k * (share[n] - 1.0 / k) for zi, n in zip(z, nomes)]

    if n_efetivo is None:
        n_efetivo = max(2.0, 0.6 * len(nomes))
    if beta is None:
        beta = beta_por_entropia(z, n_efetivo)
    p = gibbs(z, beta)
    mix = dict(zip(nomes, p))

    slots = ranking_slots(validos, pesos)
    escolhidos = escolher_slots(slots, posts_semana)
    if len(escolhidos) < posts_semana:
        avisos.append("Poucos horários distintos no histórico; calendário parcial.")
    seq = ordenar_sem_repeticao(alocar(len(escolhidos), mix))
    # Formato: alterna entre os dois melhores para manter variedade.
    top_fmt = [f.grupo for f in formatos[:2]] or ["-"]
    calendario = [(s, pil, top_fmt[i % len(top_fmt)]) for i, (s, pil) in enumerate(zip(escolhidos, seq))]

    return Plano(
        pilares=pilares, formatos=formatos, plataformas=plataformas, mix=mix, beta=beta,
        n_efetivo=math.exp(entropia(p)), slots=slots, calendario=calendario,
        outliers=outliers(validos, pesos), tendencia=tendencia_semanal(validos, pesos),
        n_posts=len(validos), fadiga=fadiga, avisos=avisos,
    )


def _tabela(estimativas: Sequence[Estimativa], titulo: str, limite: int = 99) -> List[str]:
    linhas = [f"| {titulo} | n | Média bruta (%) | Média encolhida (%) | ± EP |",
              "|---|---:|---:|---:|---:|"]
    for e in estimativas[:limite]:
        bruta = "—" if math.isnan(e.media_bruta) else f"{e.media_bruta:.2f}"
        linhas.append(f"| {e.grupo} | {e.n} | {bruta} | {e.media_encolhida:.2f} | {e.erro_padrao:.2f} |")
    return linhas


def relatorio(plano: Plano) -> str:
    L: List[str] = ["# Relatório PUFA-SOCIAL — Gestão de Mídias Sociais", ""]
    L.append(f"Posts analisados: **{plano.n_posts}** · Engajamento = 100·Σwᵢxᵢ/alcance (ponderado).")
    L.append("")
    if plano.avisos:
        L += ["> **Avisos**"] + [f"> - {a}" for a in plano.avisos] + [""]

    L += ["## 1. Calendário sugerido (próxima semana)", "",
          "| Horário | Pilar | Formato |", "|---|---|---|"]
    L += [f"| {s} | {pil} | {fmt} |" for s, pil, fmt in plano.calendario]
    L.append("")

    L += ["## 2. Mix de conteúdo (estado de Gibbs/KMS)", "",
          f"β = **{plano.beta:.3f}** · número efetivo de pilares exp(S) = **{plano.n_efetivo:.2f}**"
          + (f" · fadiga λ = {plano.fadiga}" if plano.fadiga else ""), "",
          "| Pilar | Participação recomendada |", "|---|---:|"]
    for k, v in sorted(plano.mix.items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {100 * v:.1f}% |")
    L += ["", "*β baixo ⇒ mais exploração (testar pilares); β alto ⇒ concentrar no que já performa.*", ""]

    L += ["## 3. Desempenho por pilar", ""] + _tabela(plano.pilares, "Pilar") + [""]
    L += ["## 4. Desempenho por formato", ""] + _tabela(plano.formatos, "Formato") + [""]
    L += ["## 5. Desempenho por plataforma", ""] + _tabela(plano.plataformas, "Plataforma") + [""]
    L += ["## 6. Melhores horários (top 10)", ""] + _tabela(plano.slots, "Dia/hora", 10) + [""]

    L += ["## 7. Tendência", ""]
    if plano.tendencia:
        incl, n = plano.tendencia
        direcao = "alta" if incl > 0 else "queda"
        L.append(f"Inclinação: **{incl:+.3f} p.p./semana** ({direcao}) sobre {n} semanas.")
    else:
        L.append("Histórico insuficiente (< 3 semanas).")
    L.append("")

    L += ["## 8. Posts fora da curva (z robusto > 3.5)", ""]
    if plano.outliers:
        L += ["| Data | Pilar | Formato | Plataforma | Engaj. (%) | z |", "|---|---|---|---|---:|---:|"]
        for p, e, zz in plano.outliers[:15]:
            L.append(f"| {p.data} {p.hora:02d}h | {p.pilar} | {p.formato} | {p.plataforma} | {e:.2f} | {zz:+.1f} |")
        L.append("")
        L.append("*Outliers positivos: investigar o que replicar. Negativos: revisar gancho, horário ou formato.*")
    else:
        L.append("Nenhum.")
    L += ["", "---",
          "*Consistência formal ≠ verdade empírica: recomendações dependem das hipóteses "
          "documentadas em `domains/SOCIAL/README.md`. Valide com testes A/B.*", ""]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PUFA-SOCIAL: planejamento de conteúdo para mídias sociais.")
    ap.add_argument("--csv", help="Histórico de posts (ver COLUNAS).")
    ap.add_argument("--demo", action="store_true", help="Usa dados sintéticos de demonstração.")
    ap.add_argument("--posts-semana", type=int, default=5)
    ap.add_argument("--n-efetivo", type=float, default=None,
                    help="Diversidade alvo: número efetivo de pilares exp(S). Padrão: max(2, 0.6·K).")
    ap.add_argument("--beta", type=float, default=None, help="Fixa β (ignora --n-efetivo).")
    ap.add_argument("--fadiga", type=float, default=0.0, help="Penalidade de saturação λ ≥ 0.")
    ap.add_argument("--saida", help="Arquivo Markdown de saída (padrão: stdout).")
    ap.add_argument("--exportar-demo", help="Salva o CSV sintético neste caminho e sai.")
    a = ap.parse_args(argv)

    if a.exportar_demo:
        salvar_csv(gerar_dados_sinteticos(), a.exportar_demo)
        print(f"CSV sintético salvo em {a.exportar_demo}")
        return 0
    if not a.csv and not a.demo:
        ap.error("informe --csv ARQUIVO ou --demo")
    posts = gerar_dados_sinteticos() if a.demo else ler_csv(a.csv)
    plano = planejar(posts, a.posts_semana, a.n_efetivo, a.beta, a.fadiga)
    texto = relatorio(plano)
    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"Relatório salvo em {a.saida}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
