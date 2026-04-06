# AgrupadorPDF

Agrupa e mescla automaticamente PDFs fiscais (boletos, notas fiscais, comprovantes) no formato:

```
ENTIDADE - TIPO - VALOR
```

**Desenvolvido por Brian Marques — Loglife Logística**

## Instalação

Baixe o instalador na aba [Releases](../../releases) e execute no Windows.  
Não requer Python nem dependências adicionais.

## Funcionalidades

- Agrupamento automático por entidade + valor + tipo de documento
- Merge em PDF único na ordem: Comprovante → Boleto → Nota Fiscal
- Detecção de duplicatas via SimHash
- Fuzzy matching de entidades similares (ex: "MINAS INDUSTRIA" = "MINAS INDUSTRIA E COMERCIO")
- Cross-matching por valor parentético, chave NF-e, CNPJ, parcelas
- Drag & Drop de pastas
- Verificação automática de updates

## Padrão de nomenclatura

```
EMPRESA - BOLETO - R$1.000,00.pdf
EMPRESA - NF - R$1.000,00.pdf
EMPRESA - C - R$1.000,00.pdf        ← comprovante (sufixo -C)
```
