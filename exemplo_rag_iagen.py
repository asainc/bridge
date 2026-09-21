"""Exemplo de fluxo RAG 100% por APIs do gpt_bridge, sem índice local.

Antes de executar: configure config_rag_iagen.json e valide o workflow corporativo.
O login do gpt_bridge original ocorre somente quando a primeira API é chamada.
"""

from rag_iagen_apis import (
    ask_rag,
    chunk_document,
    extract_text,
    generate_embeddings,
    load_config,
    start_indexing,
    upload_document,
    wait_indexing,
)

# Proteção para impedir upload e indexação acidental ao abrir o exemplo.
EXECUTAR = False
ENVIAR_ARQUIVO = True
EXTRAIR_OCR = True
CHUNKING_AGENTICO = True
GERAR_EMBEDDINGS = False  # Ative SOMENTE se o workflow indexador realmente receber vetores.
INDEXAR = True
AGUARDAR_WORKFLOW = True
PERGUNTAR_AO_RAG = True

# Dados fictícios; o ID, o container e o índice são definidos no JSON.
PERGUNTA = "Qual é o assunto do documento sintético?"


def main() -> None:
    """Orquestra chamadas HTTP já implementadas, sem bibliotecas de índice local."""
    config = load_config("config_rag_iagen.json")
    if not EXECUTAR:
        print("Pré-visualização: ajuste config_rag_iagen.json e defina EXECUTAR=True.")
        return

    if ENVIAR_ARQUIVO:
        status = upload_document(config)
        print(f"Upload confirmado (HTTP {status}).")
        # O File Manager original só devolve status: informe remote_path/file_id no JSON.

    chunks = None
    vectors = None
    if EXTRAIR_OCR:
        full_text = extract_text(config)
        print(f"OCR concluído; caracteres extraídos: {len(full_text)}.")
        if CHUNKING_AGENTICO:
            chunks = chunk_document(config, full_text)
            print(f"Chunking retornou {len(chunks)} trecho(s) com evidência literal.")
            if GERAR_EMBEDDINGS:
                vectors = generate_embeddings(config, chunks)
                print("API de embeddings respondeu; nenhum índice local foi criado.")

    if INDEXAR:
        # O contrato do workflow deve estar validado. O envio NÃO prova indexação concluída.
        run = start_indexing(config, chunks=chunks, embeddings=vectors)
        execution_id = run["workflow_execution_id"]
        print(f"Workflow submetido; ID de execução: {execution_id}.")
        if AGUARDAR_WORKFLOW:
            result = wait_indexing(config, execution_id)
            print(f"Workflow finalizado: {result['state']}.")
        else:
            print("Sem confirmação de indexação: consulta RAG será omitida nesta execução.")
            return

    if PERGUNTAR_AO_RAG:
        result = ask_rag(config, PERGUNTA)
        print("Resposta:", result["answer"])
        print("Quantidade de fontes retornadas:", len(result["sources"]))
        # Não imprima conteúdo de documentos, payloads, embeddings nem tokens em logs.


if __name__ == "__main__":
    main()
