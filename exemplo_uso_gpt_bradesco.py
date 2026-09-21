"""Exemplo editável de execução; por padrão não acessa APIs nem exibe segredos."""

import os
from typing import Any

from gpt_bradesco import (
    AUTH_PARAMETERS,
    auth_diagnostics,
    configure_iagen,
    get_api_config,
    get_token_iagen,
    text_generator,
    embedding_generator,
    ocr_generator,
    retriever_search,
    retriever_next_questions,
    file_manager_list,
    file_manager_upload_file,
    file_manager_upload_base64,
    file_manager_download_url,
    file_manager_delete_file,
    index_documents,
    workflow_get_status,
    agent_message,
    orchestrator_message,
)

# 1. Selecione um serviço da lista de chaves de API_CONFIGS no módulo principal.
API = "texto"

# 2. Mantenha False até concluir as configurações; True faz requisição REAL.
EXECUTAR_REQUISICAO = False

# 3. Credenciais vêm do ambiente corporativo, sem serem gravadas neste arquivo.
AUTH = {
    **AUTH_PARAMETERS,
    "ambiente": os.getenv("BRADESCO_AMBIENTE", "dev"),
    "identificador": os.getenv("BRADESCO_IDENTIFICADOR", ""),
    "senha": os.getenv("BRADESCO_SENHA", ""),
    "token": os.getenv("BRADESCO_AUTHORIZATION_TOKEN", ""),
    "ca_bundle": os.getenv("BRADESCO_CA_BUNDLE", ""),
}

# 4. Edite SOMENTE payload e parameters do serviço selecionado conforme catálogo.
CONFIG = get_api_config(API)
CONFIG["parameters"]["ambiente"] = AUTH["ambiente"]
# Exemplo para embeddings:
# CONFIG["parameters"]["deployment_name"] = "MODELO_DE_EMBEDDINGS_HABILITADO"
# Exemplo para OCR:
# CONFIG["payload"]["files_path"] = ["nome_do_arquivo_no_container.pdf"]
# CONFIG["payload"]["container"] = "CONTAINER_AUTORIZADO"


API_FUNCTIONS = {
    "texto": text_generator,
    "embeddings": embedding_generator,
    "ocr": ocr_generator,
    "retriever_documentos": retriever_search,
    "retriever_proximas_perguntas": retriever_next_questions,
    "arquivo_listar": file_manager_list,
    "arquivo_enviar": file_manager_upload_file,
    "arquivo_base64": file_manager_upload_base64,
    "arquivo_download_url": file_manager_download_url,
    "arquivo_excluir": file_manager_delete_file,
    "indexar": index_documents,
    "workflow_status": workflow_get_status,
    "agente": agent_message,
    "orquestrador": orchestrator_message,
}


def validate_configuration(api_name: str, config: dict[str, Any]) -> None:
    """Impede solicitações com identificadores vazios dos exemplos."""
    body = config["payload"]
    parameters = config["parameters"]
    if api_name in {"texto", "embeddings"} and not parameters.get("deployment_name"):
        raise ValueError("Preencha CONFIG['parameters']['deployment_name'] com um modelo habilitado.")
    if api_name == "ocr" and (
        not body.get("container") or not body.get("files_path")
        or not all(body["files_path"])
    ):
        raise ValueError("Informe container e files_path reais do OCR.")
    if api_name == "retriever_documentos" and not body.get("index_name"):
        raise ValueError("Informe index_name no payload do Retriever.")
    if api_name == "retriever_proximas_perguntas" and not body.get("next_question_config"):
        raise ValueError("Informe next_question_config no payload.")
    if api_name in {"arquivo_listar", "arquivo_enviar", "arquivo_base64"} and not body.get("container_name"):
        raise ValueError("Informe container_name do serviço de arquivos.")
    if api_name == "arquivo_enviar" and (not body.get("path_file") or not body.get("file_name")):
        raise ValueError("Informe path_file e file_name para upload.")
    if api_name == "arquivo_base64" and (not body.get("base64") or not body.get("file_name")):
        raise ValueError("Informe base64 e file_name para upload.")
    if api_name in {"arquivo_download_url", "arquivo_excluir"} and not body.get("file_id"):
        raise ValueError("Informe file_id da API de arquivos.")
    if api_name == "indexar":
        if not body.get("workflow_configuration_code"):
            raise ValueError("Informe workflow_configuration_code habilitado para indexação.")
        steps = body.get("input_collection", {}).get("input_datas", [])
        if not steps or not steps[0].get("workflow_step_input_collection"):
            raise ValueError("Preencha input_collection conforme workflow cadastrado.")
        for item in steps[0]["workflow_step_input_collection"]:
            if not item.get("full_path") or not item.get("detail_value"):
                raise ValueError("Preencha full_path e detail_value do workflow cadastrado.")
    if api_name == "workflow_status" and not body.get("workflow_execution_id"):
        raise ValueError("Informe workflow_execution_id retornado pela execução.")
    if api_name in {"agente", "orquestrador"} and not parameters.get("endpoint_url"):
        raise ValueError("Informe endpoint_url HTTPS completo conforme documentação interna.")


def main() -> None:
    """Confere configuração sem rede ou executa explicitamente uma única chamada."""
    if API not in API_FUNCTIONS:
        raise ValueError(f"API desconhecida: {API}.")
    configure_iagen(AUTH)
    info = auth_diagnostics()
    print("Ambiente:", info["ambiente"])
    print("Identificador configurado:", info["identificador_configurado"])
    print("Senha configurada:", info["senha_configurada"])
    print("Token fornecido:", info["token_disponivel"])
    print("CA corporativa configurada:", info["ca_corporativa_configurada"])
    print("Serviço selecionado:", API)
    print("Campos do payload:", list(CONFIG["payload"]) if isinstance(CONFIG["payload"], dict) else "texto")
    print("Chaves dos parâmetros:", list(CONFIG["parameters"]))
    if not EXECUTAR_REQUISICAO:
        print("Modo diagnóstico: nenhuma requisição de rede foi enviada.")
        return
    if API == "arquivo_excluir":
        raise ValueError("Exclusão exige executar file_manager_delete_file explicitamente em código autorizado.")
    validate_configuration(API, CONFIG)
    # Token manual pode já estar inválido; presença não comprova autenticação.
    get_token_iagen(force_refresh=not bool(AUTH.get("token")))
    result = API_FUNCTIONS[API](CONFIG["payload"], CONFIG["parameters"])
    # Resposta pode conter documento, vetor ou URL assinada: não imprima seu conteúdo.
    print("Requisição concluída; tipo do retorno:", type(result).__name__)


if __name__ == "__main__":
    main()
