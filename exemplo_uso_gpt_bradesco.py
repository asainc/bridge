"""Exemplos diretos das funções do gpt_bridge.py, sem framework de configuração.

Escolha API_NAME, preencha os campos de seu ambiente e mude EXECUTAR para True.
Importar gpt_bridge executa o LOGIN ORIGINAL, que não foi reimplementado aqui.
Use apenas arquivos e textos sintéticos; nunca imprima tokens ou dados judiciais.
"""

API_NAME = "embedding"
EXECUTAR = False  # Evita login/requisições enquanto você edita os exemplos.

if __name__ == "__main__":
    if not EXECUTAR:
        print(f"Exemplo escolhido: {API_NAME}. Preencha os campos e altere EXECUTAR=True.")
    else:
        import gpt_bridge as api

        if API_NAME == "texto":
            # O dicionário de parâmetros permanece no formato do text_generator original.
            payload = "Responda apenas com uma saudação breve."
            parameters = {
                "deployment_name": "PREENCHER_MODELO_DE_TEXTO_HABILITADO",
                "temperature": 0,
                "max_tokens": 512,
                "async_mode": False,
                "stream": False,
                "message_format": {"type": "text"},
                "openai_api_version": "2024-02-01",
            }
            resp = api.text_generator(payload, parameters)
            print("Texto gerado:", resp)

        elif API_NAME == "embedding":
            # Exemplo no MESMO formato da fotografia enviada.
            payload = ["O que é Pix?", "Quantos processos fictícios existem?"]
            resp = api.embedding(payload, model="text-embedding-3-large")
            primeiro_vetor = resp["response"]["embedding"][0]
            print("Dimensão do primeiro vetor:", len(primeiro_vetor))

        elif API_NAME == "ocr":
            # files_path refere-se ao arquivo já armazenado no container da plataforma.
            payload = {
                "files_path": ["PREENCHER_ARQUIVO_SINTETICO_NO_CONTAINER.pdf"],
                "container": "PREENCHER_CONTAINER_AUTORIZADO",
                "input_text": "Extraia o texto deste documento de teste.",
            }
            resp = api.ocr(payload)
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "retriever_documentos":
            payload = {
                "index_name": "PREENCHER_NOME_DO_INDICE",
                "search_query": "O que informa o documento de teste?",
                "max_chunks": 3,
            }
            resp = api.retriever_documentos(payload)
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "retriever_proximas_perguntas":
            payload = {
                "next_question_config": "PREENCHER_CONFIGURACAO_CADASTRADA",
                "search_query": "Qual seria a próxima pergunta sobre o documento de teste?",
            }
            resp = api.retriever_proximas_perguntas(payload)
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "listar_arquivos":
            # Função já existente no código original: não foi reimplementada.
            resp = api.file_manager_list_files("PREENCHER_CONTAINER_AUTORIZADO")
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "upload_arquivo":
            # Crie um pequeno arquivo sintético local antes de executar.
            resp = api.file_manager_upload(
                path_file="exemplo_sintetico.txt",
                file_name="exemplo_sintetico.txt",
                container_name="PREENCHER_CONTAINER_AUTORIZADO",
                create_container="false",
                overwrite="false",
            )
            print("HTTP:", resp)

        elif API_NAME == "upload_base64":
            import base64
            # O conteúdo do exemplo é sintético e nunca é exibido no terminal.
            conteudo = base64.b64encode(b"arquivo sintetico de teste").decode("ascii")
            payload = {
                "base64": conteudo,
                "file_name": "exemplo_sintetico.txt",
                "container_name": "PREENCHER_CONTAINER_AUTORIZADO",
                "create_container": False,
                "overwrite": False,
            }
            resp = api.upload_base64(payload)
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "download_arquivo":
            # Retorno pode incluir URL temporária: não imprima seu conteúdo.
            resp = api.download_arquivo("PREENCHER_ID_DO_ARQUIVO_DE_TESTE")
            print("Resposta recebida:", resp is not None)

        elif API_NAME == "excluir_arquivo":
            # ATENÇÃO: destrutivo. Use apenas ID descartável criado especificamente para teste.
            resp = api.file_manager_delete("PREENCHER_ID_DESCARTAVEL_DE_TESTE")
            print("Resultado:", resp)

        elif API_NAME in {"iniciar_workflow", "indexar_documentos"}:
            # Os valores da input_collection dependem do WORKFLOW CADASTRADO.
            payload = {
                "workflow_configuration_code": "PREENCHER_CODIGO_DO_WORKFLOW",
                "input_collection": {
                    "input_datas": [
                        {
                            "workflow_step_number": 0,
                            "workflow_step_input_collection": [
                                {
                                    "full_path": "PREENCHER_CAMINHO_DOCUMENTADO",
                                    "detail_value": "PREENCHER_VALOR_DOCUMENTADO",
                                    "is_valid": True,
                                }
                            ],
                        }
                    ]
                },
            }
            if API_NAME == "iniciar_workflow":
                resp = api.iniciar_workflow(payload)
            else:
                resp = api.indexar_documentos(payload)
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "status_workflow":
            resp = api.status_workflow(
                "PREENCHER_ID_DA_EXECUCAO",
                # Em homol/prod, informe endpoint_url se a URL original for "None".
                # endpoint_url="https://PREENCHER_ENDPOINT_DE_STATUS/",
            )
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "agente":
            # Endpoint e schema são específicos do agente; confirmar na documentação interna.
            payload = {"messages": [{"role": "user", "content": "Pergunta fictícia."}]}
            resp = api.agente(payload, endpoint_url="https://PREENCHER_ENDPOINT_REAL_DO_AGENTE")
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        elif API_NAME == "orquestrador":
            # Endpoint e schema são específicos do orquestrador; confirmar na documentação.
            payload = {"messages": [{"role": "user", "content": "Pergunta fictícia."}]}
            resp = api.orquestrador(payload, endpoint_url="https://PREENCHER_ENDPOINT_REAL_DO_ORQUESTRADOR")
            print("Campos de resposta:", list(resp) if isinstance(resp, dict) else type(resp).__name__)

        else:
            raise ValueError(f"API_NAME não reconhecida: {API_NAME}")
