"""Testes do PUFA-SOCIAL: python -m unittest test_pufa_social.py"""

import math
import os
import tempfile
import unittest
from datetime import date

import pufa_social as ps


class TestGibbsKMS(unittest.TestCase):
    z = [1.2, 0.3, -0.5, -1.0]

    def test_normalizacao_e_positividade(self):
        for beta in (0.0, 0.7, 5.0, 40.0):
            p = ps.gibbs(self.z, beta)
            self.assertAlmostEqual(sum(p), 1.0)
            self.assertTrue(all(pi > 0 for pi in p))  # estado fiel

    def test_limites_tracial_e_fundamental(self):
        self.assertTrue(all(abs(pi - 0.25) < 1e-12 for pi in ps.gibbs(self.z, 0.0)))
        self.assertGreater(ps.gibbs(self.z, 50.0)[0], 0.999)

    def test_simetrias(self):
        p = ps.gibbs(self.z, 1.3)
        # translação H → H + c·1
        self.assertTrue(all(math.isclose(a, b) for a, b in zip(p, ps.gibbs([x + 7 for x in self.z], 1.3))))
        # covariância de escala (H, β) → (λH, β/λ)
        self.assertTrue(all(math.isclose(a, b) for a, b in zip(p, ps.gibbs([2 * x for x in self.z], 0.65))))
        # permutação de pilares (S_K)
        perm = [2, 0, 3, 1]
        pp = ps.gibbs([self.z[i] for i in perm], 1.3)
        self.assertTrue(all(math.isclose(pp[j], p[i]) for j, i in enumerate(perm)))

    def test_entropia_monotona(self):
        ss = [ps.entropia(ps.gibbs(self.z, b / 10)) for b in range(0, 100)]
        self.assertTrue(all(a >= b - 1e-12 for a, b in zip(ss, ss[1:])))

    def test_beta_por_entropia(self):
        beta = ps.beta_por_entropia(self.z, 2.5)
        self.assertAlmostEqual(math.exp(ps.entropia(ps.gibbs(self.z, beta))), 2.5, places=6)

    def test_principio_variacional(self):
        beta = 1.5
        p = ps.gibbs(self.z, beta)
        f_gibbs = ps.energia_livre(self.z, p, beta)
        for q in ([0.25] * 4, [0.7, 0.1, 0.1, 0.1], [0.4, 0.4, 0.1, 0.1], [1, 0, 0, 0]):
            self.assertGreaterEqual(f_gibbs + 1e-12, ps.energia_livre(self.z, q, beta))


class TestEstimacao(unittest.TestCase):
    def test_encolhimento_entre_bruta_e_global(self):
        grupos = {"a": [5, 6, 7, 6], "b": [2, 3, 2, 3], "c": [4, 4, 5, 3, 4]}
        mu = sum(sum(v) for v in grupos.values()) / sum(len(v) for v in grupos.values())
        for e in ps.encolhimento(grupos):
            lo, hi = sorted((e.media_bruta, mu))
            self.assertTrue(lo - 1e-12 <= e.media_encolhida <= hi + 1e-12)
            self.assertGreater(e.erro_padrao, 0)

    def test_sem_sinal_colapsa_na_media(self):
        grupos = {"a": [1, 9, 5], "b": [2, 8, 5], "c": [9, 1, 5]}
        ests = ps.encolhimento(grupos)
        self.assertTrue(all(math.isclose(e.media_encolhida, 5.0) for e in ests))
        self.assertTrue(all(e.erro_padrao > 0 for e in ests))

    def test_alocacao_exata(self):
        for n in range(0, 15):
            alloc = ps.alocar(n, {"a": 0.5, "b": 0.3, "c": 0.2})
            self.assertEqual(sum(alloc.values()), n)

    def test_sem_repeticao_consecutiva(self):
        seq = ps.ordenar_sem_repeticao({"a": 3, "b": 2, "c": 2})
        self.assertEqual(len(seq), 7)
        self.assertTrue(all(x != y for x, y in zip(seq, seq[1:])))

    def test_engajamento_alcance_zero(self):
        p = ps.Post(date(2026, 1, 1), 10, "ig", "x", "reels", 0, 1, 1, 1, 1)
        self.assertIsNone(p.engajamento())


class TestRobustez(unittest.TestCase):
    def test_winsorizar_limita_extremo_e_preserva_resto(self):
        xs = [10, 11, 9, 10, 12, 10, 500]
        ws = ps.winsorizar(xs)
        self.assertEqual(ws[:-1], xs[:-1])
        self.assertLess(ws[-1], 500)
        self.assertGreater(ws[-1], 12)

    def test_post_viral_nao_domina_pilar(self):
        posts = ps.gerar_dados_sinteticos(80, semente=1)
        viral = ps.Post(date(2026, 7, 5), 10, "instagram", "lancamento", "imagem", 80, 14, 7, 89, 1)
        normais = [ps.Post(date(2026, 7, d), 10, "instagram", "lancamento", "imagem", 100, 3, 0, 0, 0)
                   for d in range(6, 9)]
        robusto = ps.planejar(posts + [viral] + normais, metrica="taxa")
        cru = ps.planejar(posts + [viral] + normais, metrica="taxa", robusto=False)
        self.assertLess(robusto.mix["lancamento"], cru.mix["lancamento"])
        self.assertTrue(any(p is viral for p, _, _ in robusto.outliers))  # continua sinalizado

    def test_metricas(self):
        p = ps.Post(date(2026, 1, 1), 10, "ig", "x", "reels", 200, 10, 2, 1, 1)
        self.assertAlmostEqual(p.valor("interacoes"), 10 + 6 + 5 + 4)
        self.assertAlmostEqual(p.valor("taxa"), 100 * 25 / 200)
        self.assertEqual(p.valor("alcance"), 200)
        for m in ps.METRICAS:
            self.assertEqual(len(ps.planejar(ps.gerar_dados_sinteticos(), metrica=m).calendario), 5)

    def test_faixas(self):
        self.assertEqual([ps.faixa(h) for h in (3, 9, 15, 21)], ["madrugada", "manhã", "tarde", "noite"])


class TestPipeline(unittest.TestCase):
    def test_demo_ponta_a_ponta(self):
        posts = ps.gerar_dados_sinteticos()
        plano = ps.planejar(posts, posts_semana=6)
        self.assertEqual(len(plano.calendario), 6)
        self.assertAlmostEqual(sum(plano.mix.values()), 1.0)
        dias = [s.split()[0] for s, _, _ in plano.calendario]
        self.assertEqual(len(dias), len(set(dias)))  # 1 post/dia quando N ≤ 7
        texto = ps.relatorio(plano)
        self.assertIn("Calendário sugerido", texto)

    def test_csv_ida_e_volta(self):
        posts = ps.gerar_dados_sinteticos(30)
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "p.csv")
            ps.salvar_csv(posts, caminho)
            lidos = ps.ler_csv(caminho)
        self.assertEqual(len(lidos), 30)
        self.assertEqual(lidos[0].pilar, posts[0].pilar)

    def test_mais_de_sete_posts(self):
        plano = ps.planejar(ps.gerar_dados_sinteticos(), posts_semana=10)
        self.assertEqual(len(plano.calendario), 10)


if __name__ == "__main__":
    unittest.main()
