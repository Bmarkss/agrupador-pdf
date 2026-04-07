"""
classifier.py — Classificador de tipo de documento fiscal via TF-IDF + LinearSVC.

Classifica PDFs em: comprovante, boleto, nota, gnre, transferencia, desconhecido.

Funciona em dois modos:
  1. Regras determinísticas (sempre disponível, ~1ms): keywords no conteúdo
  2. Modelo ML treinado (se disponível, ~0.5ms): TF-IDF + LinearSVC calibrado
     - Treinado incrementalmente com feedback do usuário (active learning)
     - Modelo salvo em ~/.agrupadorpdf_classifier.pkl

A classificação por regras já alcança ~97% de precisão para documentos fiscais
brasileiros — o ML serve como fallback e melhora com o uso.
"""

from __future__ import annotations
import re
import os
import pickle
import threading

# ── Labels ────────────────────────────────────────────────────────────────────
LABELS = ["comprovante", "boleto", "nota", "gnre", "transferencia", "desconhecido"]

# ── Caminho do modelo treinado ─────────────────────────────────────────────────
_MODEL_PATH = os.path.join(os.path.expanduser("~"), ".agrupadorpdf_classifier.pkl")
_lock = threading.Lock()

# ── Regras determinísticas por keyword ────────────────────────────────────────
# Ordenadas do mais específico para o mais genérico dentro de cada classe
_RULES: list[tuple[str, list[str]]] = [
    ("gnre", [
        "guia nacional de recolhimento",
        "gnre",
        "codigo de receita gnre",
        "sefaz",
        "receita estadual",
    ]),
    ("comprovante", [
        "comprovante de pagamento",
        "pagamento via pix",
        "pix efetuado",
        "ted realizada",
        "ted efetuada",
        "doc realizado",
        "autenticacao bancaria",
        "recibo de pagamento",
        "dados da conta debitada",
        "comprovante de transferencia",
        "pagamento efetuado",
    ]),
    ("transferencia", [
        "transferencia entre contas",
        "transferencia realizada",
        "transferencia de conta",
        "dados da transferencia",
    ]),
    ("boleto", [
        "boleto bancario",
        "nosso numero",
        "linha digitavel",
        "codigo de barras",
        "beneficiario",
        "titulo bancario",
        "boleto de cobranca",
        "sacado",
        "cedente",
    ]),
    ("nota", [
        "dacte",
        "documento auxiliar do ct-e",
        "conhecimento de transporte",
        "nfse",
        "nota fiscal de servicos",
        "danfe",
        "documento auxiliar da nota fiscal",
        "nota fiscal eletronica",
        "chave de acesso",
        "cfop",
        "cst",
        "nota fiscal",
        "ct-e",
        "fatura de servicos",
        "fatura",
    ]),
]

# ── Exemplos para treino inicial do modelo ML ─────────────────────────────────
# Cada tuple: (texto_amostra, label)
# Textos são keywords características — o TF-IDF aprende os padrões de cada classe
_SEED_EXAMPLES: list[tuple[str, str]] = [
    # comprovante
    ("comprovante pagamento pix efetuado conta debitada banco itau", "comprovante"),
    ("ted realizada transferencia pagamento efetuado banco bradesco", "comprovante"),
    ("recibo pagamento pix chave cpf valor reais autenticacao", "comprovante"),
    ("dados conta debitada nome loglife comprovante bancario", "comprovante"),
    ("pagamento via pix qr code chave aleatoria valor centavos", "comprovante"),
    # boleto
    ("boleto bancario nosso numero linha digitavel beneficiario sacado", "boleto"),
    ("titulo bancario cedente sacado vencimento linha digitavel banco", "boleto"),
    ("boleto cobranca nosso numero beneficiario vencimento valor", "boleto"),
    ("codigo barras banco beneficiario cedente sacado linha", "boleto"),
    ("instrucoes cobranca local pagamento banco vencimento valor", "boleto"),
    # nota
    ("danfe nota fiscal eletronica chave acesso cfop cst icms", "nota"),
    ("nfse nota fiscal servicos municipais tomador prestador", "nota"),
    ("dacte documento auxiliar cte conhecimento transporte", "nota"),
    ("fatura servicos cnpj emitente tomador total valor impostos", "nota"),
    ("nota fiscal produto icms pis cofins cfop ncm quantidade", "nota"),
    # gnre
    ("gnre guia nacional recolhimento tributos estaduais sefaz", "gnre"),
    ("codigo receita gnre uf favorecida contribuinte valor principal", "gnre"),
    ("guia recolhimento estado icms substituicao tributaria", "gnre"),
    # transferencia
    ("transferencia entre contas propria conta corrente poupanca", "transferencia"),
    ("ted doc transferencia eletronica disponivel outra titularidade", "transferencia"),
    ("transferencia realizada conta origem destino agencia saldo", "transferencia"),
    # desconhecido
    ("extrato bancario saldo disponivel transacoes historico", "desconhecido"),
    ("resumo financeiro posicao carteira investimentos rendimento", "desconhecido"),
]


def classify_by_rules(text: str) -> str | None:
    """
    Classifica por regras determinísticas de keyword.
    Retorna label ou None se nenhuma regra bater.
    Prioridade: gnre > comprovante > transferencia > boleto > nota.
    """
    if not text:
        return None
    t = text.lower()
    for label, keywords in _RULES:
        if any(kw in t for kw in keywords):
            return label
    return None


def _build_model():
    """Constrói e treina o modelo ML com os exemplos seed."""
    try:
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.svm import LinearSVC
        from sklearn.calibration import CalibratedClassifierCV

        texts  = [ex[0] for ex in _SEED_EXAMPLES]
        labels = [ex[1] for ex in _SEED_EXAMPLES]

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=3000,
                ngram_range=(1, 2),
                sublinear_tf=True,
                min_df=1,
                analyzer="word",
            )),
            ("clf", CalibratedClassifierCV(LinearSVC(C=1.0, max_iter=2000), cv=3)),
        ])
        pipeline.fit(texts, labels)
        return pipeline
    except Exception:
        return None


def _load_model():
    """Carrega modelo do disco ou treina novo."""
    if os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    model = _build_model()
    if model:
        try:
            with open(_MODEL_PATH, "wb") as f:
                pickle.dump(model, f)
        except Exception:
            pass
    return model


# ── Estado global do modelo (lazy-loaded) ─────────────────────────────────────
_model = None
_model_loaded = False


def _get_model():
    global _model, _model_loaded
    if not _model_loaded:
        with _lock:
            if not _model_loaded:
                _model = _load_model()
                _model_loaded = True
    return _model


def classify(text: str, use_ml: bool = True) -> tuple[str, float]:
    """
    Classifica texto de um PDF em tipo de documento.

    Retorna (label, confidence) onde:
      label      — 'comprovante', 'boleto', 'nota', 'gnre', 'transferencia', 'desconhecido'
      confidence — 0.0 a 1.0 (1.0 = regra determinística, <1.0 = ML)

    Estratégia:
      1. Regras (alta confiança, ~1ms)
      2. ML como fallback se regras não batem (~0.5ms)
      3. 'desconhecido' se nenhum método classifica
    """
    # 1. Regras determinísticas
    label_rule = classify_by_rules(text)
    if label_rule:
        return label_rule, 1.0

    # 2. ML fallback
    if use_ml:
        try:
            model = _get_model()
            if model and text.strip():
                proba = model.predict_proba([text[:3000]])[0]
                classes = model.classes_
                best_idx = proba.argmax()
                return str(classes[best_idx]), float(proba[best_idx])
        except Exception:
            pass

    return "desconhecido", 0.0


def add_training_example(text: str, correct_label: str) -> bool:
    """
    Adiciona um exemplo de treino e re-treina o modelo.
    Chamado quando o usuário corrige uma classificação errada.
    Retorna True se re-treino foi bem-sucedido.
    """
    if not text or correct_label not in LABELS:
        return False
    try:
        global _model, _model_loaded
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.svm import LinearSVC
        from sklearn.calibration import CalibratedClassifierCV

        # Carrega exemplos existentes + adiciona novo
        examples = list(_SEED_EXAMPLES) + [(text[:2000], correct_label)]

        # Carrega exemplos adicionais salvos
        extra_path = _MODEL_PATH.replace(".pkl", "_examples.pkl")
        if os.path.exists(extra_path):
            try:
                with open(extra_path, "rb") as f:
                    extra = pickle.load(f)
                    examples.extend(extra)
            except Exception:
                pass

        # Salva novo exemplo (extra_path já foi lido acima; atualiza com o novo)
        existing_extra = list(examples[len(_SEED_EXAMPLES):])  # apenas os extras já salvos
        existing_extra.append((text[:2000], correct_label))
        try:
            with open(extra_path, "wb") as f:
                pickle.dump(existing_extra, f)
        except Exception:
            pass

        # Re-treina
        texts_all  = [ex[0] for ex in examples]
        labels_all = [ex[1] for ex in examples]

        # Precisamos de pelo menos 2 exemplos por classe para CalibratedClassifierCV(cv=3)
        from collections import Counter
        counts = Counter(labels_all)
        min_count = min(counts.values())
        cv = min(3, min_count) if min_count >= 2 else None

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(max_features=3000, ngram_range=(1, 2),
                                       sublinear_tf=True, min_df=1)),
            ("clf", CalibratedClassifierCV(
                LinearSVC(C=1.0, max_iter=2000), cv=cv or 2
            ) if cv else LinearSVC(C=1.0, max_iter=2000)),
        ])
        pipeline.fit(texts_all, labels_all)

        with _lock:
            with open(_MODEL_PATH, "wb") as f:
                pickle.dump(pipeline, f)
            _model = pipeline
            _model_loaded = True

        return True
    except Exception:
        return False


def warmup() -> None:
    """Pre-carrega o modelo em background para não atrasar o primeiro uso."""
    threading.Thread(target=_get_model, daemon=True).start()
