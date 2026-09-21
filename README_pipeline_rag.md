# Pipeline de vetorização e RAG de documentos judiciais — protótipo

## Objetivo e arquitetura

Implementar **um PDF de cada vez**, sem modificar `gpt_bridge.py` nem sua autenticação:

`PDF → PyMuPDF (texto por página + string integral) → text_generator (chunking semântico com evidências) → validação de spans → documento_estruturado.xlsx → leitura do XLSX → embedding → índice local NumPy → pergunta → embedding da pergunta → busca por cosseno → text_generator → resposta + fontes`.

O **índice local** serve para validar o RAG ponta a ponta com as APIs disponíveis. **Não é um índice corporativo da IAGEN**. O Excel é uma base de auditoria/intercâmbio; as buscas são executadas sobre `vectors.npz` com metadados em `metadata.json`. Os vetores não são gravados como milhares de colunas na planilha.

## Arquivos

- `pipeline_rag_juridico.py`: comandos `prepare`, `ask` e `corporate-index`.
- `prompt_chunking.md`: prompt independente, editável e versionável.
- `config_pipeline.json`: parâmetros de modelos e limites, sem segredos.
- `gpt_bridge.py`: arquivo do projeto anterior **sem alterações**; importá-lo executa a autenticação original.
- `test_pipeline_rag_juridico.py`: testes offline com respostas simuladas.
- `modelo_documento_estruturado.xlsx`: exemplo de layout com dados inteiramente sintéticos.

## Pré-requisitos

Python com `pymupdf`, `numpy`, `requests` e `artifact_tool`; o último deve estar disponível no repositório de pacotes aprovado da organização. As versões de PyMuPDF, NumPy e Requests utilizadas nos testes locais estão em `requirements_pipeline.txt`; a distribuição e versão do `artifact_tool` no ambiente corporativo precisam ser confirmadas. O código usa `gpt_bridge` como ponte e, por isso, depende também das bibliotecas já requeridas por ele. A versão original da autenticação deve funcionar isoladamente ANTES de integrar a pipeline; este projeto não modifica seu fluxo.

Use somente documentos sintéticos ou autorizados para teste. Defina o controle de acesso e retenção do PDF, da planilha e do índice com Segurança, Jurídico/Compliance e DPO antes do uso corporativo. **O índice local grava texto de chunks em `metadata.json` e a planilha contém texto e entidades; não possuem criptografia de aplicação**. Use exclusivamente armazenamento corporativo autorizado, com criptografia em repouso e permissões restritas; não publique ou compartilhe esses artefatos em serviços externos.

## Passo a passo

1. Coloque `pipeline_rag_juridico.py`, `prompt_chunking.md`, `config_pipeline.json` e seu **`gpt_bridge.py` funcional** na mesma pasta; use um PDF de teste sintético.
2. Instale dependências aprovadas para o seu ambiente. Em ambiente controlado, o comando é `python -m pip install -r requirements_pipeline.txt`; valide à parte a disponibilidade e distribuição autorizada de `artifact_tool`.
3. Abra `config_pipeline.json` e substitua `PREENCHER_MODELO_DE_TEXTO_HABILITADO` pelo nome **efetivamente autorizado** no serviço. Confirme se `text-embedding-3-large` está disponível para seu identificador no ambiente. Ajuste `max_tokens`, `max_window_chars` e `embedding_batch_size` conforme os limites *documentados* para o modelo e as cotas autorizadas. Mantenha `temperature` e `max_tokens` simultaneamente presentes: a função `text_generator` legada exige ambos quando um é fornecido.
4. Se desejar, ajuste `prompt_chunking.md`; **não altere seu contrato JSON** sem atualizar a validação no código.
5. Execute a preparação:

```bash
python pipeline_rag_juridico.py --config config_pipeline.json prepare --pdf "exemplo_sintetico.pdf" --prompt prompt_chunking.md --output saida_rag
```

6. Confira `saida_rag/documento_estruturado.xlsx`, principalmente `origin=fallback_review`, evidências das entidades e `review_status=PENDENTE`. **Não trate uma extração não revisada como fato jurídico.** Atualmente o código sinaliza a revisão; ele **não bloqueia a indexação até uma aprovação humana**. Se sua governança exigir aprovação, acrescente uma etapa obrigatória de liberação antes de `build_local_index`.
7. Faça uma pergunta:

```bash
python pipeline_rag_juridico.py --config config_pipeline.json ask --index saida_rag/indice --question "Qual é o assunto do documento?"
```

Opcionalmente, restrinja a consulta ao documento exato com `--document-id SHA256_DO_PDF` (retornado por `prepare`), útil para evitar mistura entre processos ao evoluir para múltiplos PDFs.

### Exemplo das funções Python, sem CLI

```python
from pathlib import Path
import gpt_bridge as api  # IMPORTANTE: executa o login original
from pipeline_rag_juridico import (
    PipelineConfig, extract_pdf, load_chunk_prompt, chunk_document,
    export_xlsx, build_local_index, ask_local_rag,
)

config = PipelineConfig.from_json(Path("config_pipeline.json"))
full_text, pages, document_id = extract_pdf(Path("exemplo_sintetico.pdf"))
# full_text é uma única string; pages conserva a página física de cada trecho.
prompt = load_chunk_prompt(Path("prompt_chunking.md"))
chunks = chunk_document(pages, document_id, prompt, config, api.text_generator)
xlsx_path = Path("saida_rag/documento_estruturado.xlsx")
export_xlsx(xlsx_path, Path("exemplo_sintetico.pdf"), document_id, pages, chunks, config)
build_local_index(xlsx_path, len(chunks), Path("saida_rag/indice"), config, api.embedding)
result = ask_local_rag(
    "Qual é o assunto do documento?", Path("saida_rag/indice"),
    config, api.embedding, api.text_generator, document_id,
)
print(result["answer"])
print(result["sources"])  # chunk_id, página, hash de documento e similaridade
```

## Schema do Excel

- `Documentos`: `document_id`, arquivo de origem (somente nome), páginas com texto, SHA-256 do PDF e data UTC de processamento.
- `Chunks`: identificadores, página 1-based, posição inicial/final 0-based na string da página, título, texto literal, resumo gerado, tipo documental, assunto, origem, revisão pendente e SHA-256 do texto. O hash impede indexação silenciosa se o texto for modificado na planilha.
- `Entidades`: `chunk_id`, página, tipo, valor, evidência literal contida no chunk, revisão pendente.
- `Auditoria`: modelos configurados, tamanho de janela e quantos chunks exigem revisão.

Páginas sem texto selecionável geram aviso, mas o pipeline **não aplica OCR automaticamente**; se o documento for escaneado, extraia OCR em uma etapa aprovada e reconcilie a paginação antes de prosseguir. O código não faz análise de layout de tabelas, rodapés ou múltiplas colunas; validar especialmente documentos dessa natureza.

O texto de cada chunk precisa ser **literalmente encontrado** na janela que o modelo recebeu. Entidades só são aceitas quando sua evidência aparece literalmente no chunk. Lacunas significativas viram `fallback_review` sem entidades inferidas. Isso aumenta rastreabilidade, mas **não prova** que entidades, resumos ou respostas estejam juridicamente corretos.

## Indexação na IAGEN (opcional e ainda não validada)

O arquivo `gpt_bridge.py` contém `indexar_documentos(payload, endpoint_url=None)`, que inicia um workflow usando `workflow_configuration_code` e `input_collection`. **Isso não demonstra que o workflow esteja configurado para ingerir linhas de XLSX, JSONL ou chunks.** O contrato específico do workflow, o método de upload autorizado, o destino (`index_name`), o schema de metadados e a confirmação de conclusão precisam ser fornecidos pelo responsável pela API.

Quando tiver um JSON aprovado para um workflow que consome os chunks, execute:

```bash
python pipeline_rag_juridico.py --config config_pipeline.json corporate-index --payload workflow_indexacao_aprovado.json
```

Esse comando **somente solicita a execução** do workflow e mostra seu ID quando presente. Confira a conclusão com `gpt_bridge.status_workflow(workflow_execution_id)` no ambiente cujo endpoint esteja configurado. Não assuma sucesso de indexação pela resposta de início. **Não copie o payload ilustrativo antigo e presuma que ele indexa o XLSX.**

Para RAG sobre um índice corporativo aprovado, o fluxo muda apenas na recuperação: substitua a busca local por `gpt_bridge.retriever_documentos(payload)` usando `index_name`, `search_query` e filtros documentados (ex.: identificador do processo), valide o schema da resposta e mande os trechos, fonte e página ao mesmo `text_generator`. O método `gpt_bridge.agente(payload, endpoint_url)` requer URL e contrato de entrada/saída de agente cadastrados; este protótipo implementa o **agente RAG como função Python** `ask_local_rag`, não afirma ter provisionado um agente na plataforma.

## Validação e limitações

- Testes automatizados offline simulam LLM e embedding; **não provam autenticação, disponibilidade de modelos ou execução dos serviços internos**.
- Métricas de qualidade (recall@k, cobertura das entidades, fidelidade de resposta, custo/tokens, latência) **ainda não foram medidas** em amostra representativa. Antes de produção, gere um conjunto de perguntas rotuladas, compare referências e faça revisão jurídica amostral.
- Vetorizações repetidas consomem requisições, e o protótipo não traz fila, retries automáticos, cache de vetores ou idempotência transacional entre XLSX e índice. Prepare controles de reprocessamento antes de escalar.
- O resultado da busca inclui similaridade cosseno; **não há threshold inventado**. Calibre decisão de abstenção em dados validados.
- O `text_generator` original emite logs e usa `verify=False`; nenhuma mudança foi feita nele. Valide TLS e logging conforme diretrizes internas antes de enviar conteúdo confidencial.

## Registro de decisões

2026-09-21 — Separação de ponte/API e pipeline; preservar autenticação existente. Responsável: proposta técnica (validar internamente).

2026-09-21 — Vetores em arquivo NumPy e linhas no XLSX; Excel é registro auditável, não banco de vetores. Responsável: proposta técnica.

2026-09-21 — RAG local primeiro, workflow corporativo condicionado ao contrato aprovado; evitar endpoints e payloads não demonstrados. Responsável: proposta técnica.
