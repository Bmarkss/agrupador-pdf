"""
graph_resolver.py — Resolve ambiguidades de agrupamento via grafo bipartido (NetworkX).

Problema que resolve:
  O grouper agrupa por group_id idêntico. Mas há casos onde dois grupos distintos
  deveriam ser um só — ex: "CRYOBRAS" e "CRYOBRAS GELO SECO" com mesmo valor.
  O scorer calculou alta confiança entre eles, mas o grouper não sabe disso.

  O grafo representa:
    Nós: documentos fiscais
    Arestas: score de confiança entre pares de docs de grupos diferentes
    Peso: 1 - score (menor = mais provável ser o mesmo pagamento)

  Algoritmos:
    1. Componentes conectadas com threshold alto (>= 0.85): grupos óbvios
    2. Minimum weight matching para resolver ambiguidades 1-para-1

Integração:
  Chamado pelo merger ANTES de gerar os PDFs finais.
  Pode sugerir merges adicionais que o grouper não detectou.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DocInfo


def build_cross_group_edges(
    groups: dict[str, list["DocInfo"]],
    score_fn,
    threshold: float = 0.65,
) -> list[tuple[str, str, float]]:
    """
    Calcula scores entre grupos diferentes para identificar candidatos a merge.

    Compara grupos por seus documentos âncora (comprovante ou primeiro doc).
    Retorna lista de (gid_a, gid_b, score) apenas quando score >= threshold.

    threshold: score mínimo para considerar candidato (0.65 = amarelo)
    """
    gids = list(groups.keys())
    edges = []

    for i, ga in enumerate(gids):
        docs_a = groups[ga]
        # Âncora = comprovante se existir, senão primeiro doc
        anchor_a = next((d for d in docs_a if d.doc_type == "comprovante"), docs_a[0])

        for gb in gids[i+1:]:
            docs_b = groups[gb]
            anchor_b = next((d for d in docs_b if d.doc_type == "comprovante"), docs_b[0])

            score, _ = score_fn(anchor_a, anchor_b)
            if score >= threshold:
                edges.append((ga, gb, score))

    return edges


def resolve_with_graph(
    groups: dict[str, list["DocInfo"]],
    score_fn,
    merge_threshold: float = 0.85,
    suggest_threshold: float = 0.65,
    log_cb=None,
) -> tuple[dict[str, list["DocInfo"]], list[dict]]:
    """
    Analisa o grafo de grupos e:
      1. Faz merges automáticos quando score >= merge_threshold
      2. Retorna sugestões de merge quando score está entre suggest_threshold e merge_threshold

    Retorna:
      groups_updated — dict de grupos (possivelmente com merges aplicados)
      suggestions    — lista de dicts com sugestões para a UI revisar
                       [{gid_a, gid_b, score, reason}]
    """
    try:
        import networkx as nx
    except ImportError:
        if log_cb:
            log_cb("    -- networkx não disponível, pulando resolução de grafo")
        return groups, []

    if len(groups) < 2:
        return groups, []

    # ── Constrói grafo ────────────────────────────────────────────────────────
    G = nx.Graph()
    for gid in groups:
        G.add_node(gid)

    edges = build_cross_group_edges(groups, score_fn, threshold=suggest_threshold)

    for ga, gb, score in edges:
        G.add_edge(ga, gb, weight=score)

    if log_cb and edges:
        log_cb(f"    -- grafo: {len(groups)} grupos, {len(edges)} arestas candidatas")

    suggestions = []
    merged: set[str] = set()

    # ── Merges automáticos (score muito alto) ─────────────────────────────────
    # Ordena por score decrescente para processar os mais confiantes primeiro
    auto_edges = sorted(
        [(ga, gb, d["weight"]) for ga, gb, d in G.edges(data=True)
         if d["weight"] >= merge_threshold],
        key=lambda x: -x[2]
    )

    for ga, gb, score in auto_edges:
        if ga in merged or gb in merged or ga not in groups or gb not in groups:
            continue

        # Nunca faz auto-merge de grupos GNRE — GNREs de mesmo valor/período
        # são pagamentos distintos para estados diferentes, não duplicatas.
        docs_a = groups[ga]; docs_b = groups[gb]
        if any(d.doc_type == "gnre" or getattr(d, "content_type", None) == "gnre"
               for d in docs_a + docs_b):
            continue

        # Verifica que os grupos não têm o mesmo tipo de doc (evita merge inválido)
        tipos_a = {d.doc_type for d in groups[ga]}
        tipos_b = {d.doc_type for d in groups[gb]}
        if tipos_a & tipos_b:
            # Mesmos tipos — provavelmente são pagamentos diferentes, não merge
            continue

        # Merge: absorve gb em ga
        if log_cb:
            log_cb(f"    -> grafo-merge ({score:.0%}): '{gb}' → '{ga}'")
        for d in groups[gb]:
            d.group_id = ga
            groups[ga].append(d)
        del groups[gb]
        merged.add(gb)

    # ── Sugestões (score médio — deixa o usuário decidir) ─────────────────────
    for ga, gb, d in G.edges(data=True):
        score = d["weight"]
        if score < merge_threshold and score >= suggest_threshold:
            if ga not in merged and gb not in merged:
                if ga in groups and gb in groups:
                    suggestions.append({
                        "gid_a":  ga,
                        "gid_b":  gb,
                        "score":  round(score, 3),
                        "reason": f"score {score:.0%} — revisar se são o mesmo pagamento",
                    })

    if log_cb and suggestions:
        log_cb(f"    -- {len(suggestions)} sugestão(ões) de merge para revisão")

    return groups, suggestions


def find_orphan_matches(
    groups: dict[str, list["DocInfo"]],
    conferir: list[str],
    all_docs: list["DocInfo"],
    score_fn,
    threshold: float = 0.70,
    log_cb=None,
) -> dict[str, str]:
    """
    Tenta encontrar um grupo existente para cada arquivo em CONFERIR.
    Retorna dict {fname: gid_sugerido} para os orphans que tiveram match.

    Um orphan casa com um grupo quando:
    - score >= threshold com o comprovante do grupo
    - O grupo ainda não tem um doc do mesmo tipo que o orphan
    """
    matches: dict[str, str] = {}
    orphan_docs = [d for d in all_docs if d.fname in set(conferir)]

    for orphan in orphan_docs:
        best_gid, best_score = None, 0.0

        for gid, gdocs in groups.items():
            tipos_grupo = {d.doc_type for d in gdocs}
            # Não sugere se o grupo já tem esse tipo
            if orphan.doc_type and orphan.doc_type in tipos_grupo:
                continue

            anchor = next((d for d in gdocs if d.doc_type == "comprovante"), gdocs[0])
            score, _ = score_fn(orphan, anchor)
            if score > best_score:
                best_score, best_gid = score, gid

        if best_gid and best_score >= threshold:
            matches[orphan.fname] = best_gid
            if log_cb:
                log_cb(
                    f"    -- orphan match ({best_score:.0%}): "
                    f"'{orphan.fname[:40]}' → '{best_gid}'"
                )

    return matches
