"""Exemplos sintéticos de payload e parameters para as APIs do gpt_bridge.

Como usar:
    1. Escolha API_NAME no fim do arquivo.
    2. Altere os valores PREENCHER_... no EXAMPLES[API_NAME].
    3. Execute o arquivo com EXECUTE_REQUEST = False para conferir a configuração.
    4. Altere EXECUTE_REQUEST = True para executar UMA chamada real.

A importação de gpt_bridge acontece apenas após validar os exemplos: o módulo
original solicita token imediatamente ao ser importado. Este arquivo NÃO modifica
nenhuma função, endereço ou mecanismo de autenticação do gpt_bridge.py.

Os campos cuja forma/rota depende de documentação não legível ou de cadastro no
ambiente estão marcados como PREENCHER_...; os contratos de agentes e orquestrador
são apenas ilustrativos e precisam de validação com o proprietário das APIs.
"""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import Any


# Os nomes das funções são exatamente os encontrados em gpt_bridge.py.
# API_CONFIGS do módulo principal também contém exemplos; estes são explícitos,
# independentes e incluem workflow_execute e index_documents separadamente.
EXAMPLES: dict[str, dict[str, Any]] = {
    "texto": {
        "function": "text_generator",
        "payload": "Responda apenas: exemplo sintético concluído.",
        "parameters": {
            "deployment_name": "PREENCHER_MODELO_DE_TEXTO_HABILITADO",
            "temperature": 0,
            "max_tokens": 512,
            "async_mode": False,
            "stream": False,
            "message_format": {"type": "text"},
            "openai_api_version": "2024-02-01",
        },
    },
    "embeddings": {
        "function": "embedding_generator",
        "payload": "Documento sintético para gerar um vetor de teste.",
        "parameters": {
            "deployment_name": "PREENCHER_MODELO_DE_EMBEDDING_HABILITADO",
            # Deixe None: a função não envia dimensions nesse caso.
            "dimensions": None,
            "timeout": 120,
        },
    },
    "ocr": {
        "function": "ocr_generator",
        "payload": {
            "files_path": ["PREENCHER_CAMINHO_DO_ARQUIVO_SINTETICO_NO_CONTAINER"],
            "container": "PREENCHER_CONTAINER_AUTORIZADO",
            "input_text": "Extraia o texto deste documento sintético.",
        },
        "parameters": {"timeout": 120},
    },
    "retriever_documentos": {
        "function": "retriever_search",
        "payload": {
            "index_name": "PREENCHER_INDICE_CADASTRADO",
            "search_query": "Qual é o assunto do documento sintético?",
        },
        "parameters": {"timeout": 120},
    },
    "retriever_proximas_perguntas": {
        "function": "retriever_next_questions",
        "payload": {
            "next_question_config": "PREENCHER_CONFIGURACAO_CADASTRADA",
            "search_query": "O que mais poderia ser perguntado sobre o documento sintético?",
        },
        "parameters": {"timeout": 120},
    },
    "arquivo_listar": {
        "function": "file_manager_list",
        "payload": {
            "container_name": "PREENCHER_CONTAINER_AUTORIZADO",
            "page": 0,
            "page_size": 20,
        },
        "parameters": {"timeout": 120},
    },
    "arquivo_enviar": {
        "function": "file_manager_upload_file",
        "payload": {
            "path_file": "PREENCHER_CAMINHO_LOCAL_DE_ARQUIVO_SINTETICO.txt",
            "file_name": "amostra_sintetica.txt",
            "container_name": "PREENCHER_CONTAINER_AUTORIZADO",
            "create_container": "false",
            # Evita sobrescrever, por padrão, um arquivo existente.
            "overwrite": "false",
        },
        "parameters": {"timeout": 120},
    },
    "arquivo_base64": {
        "function": "file_manager_upload_base64",
        "payload": {
            # Base64 do texto inofensivo 'Teste sintetico.'; não contém dados reais.
            "base64": "VGVzdGUgc2ludGV0aWNvLg==",
            "file_name": "amostra_sintetica.txt",
            "container_name": "PREENCHER_CONTAINER_AUTORIZADO",
            "create_container": False,
            "overwrite": False,
        },
        "parameters": {"timeout": 120},
    },
    "arquivo_download_url": {
        "function": "file_manager_download_url",
        "payload": {"file_id": "PREENCHER_ID_DE_ARQUIVO_SINTETICO"},
        "parameters": {"timeout": 120},
    },
    "arquivo_excluir": {
        "function": "file_manager_delete_file",
        "payload": {"file_id": "PREENCHER_ID_DE_ARQUIVO_SINTETICO"},
        "parameters": {"timeout": 120},
    },
    "workflow_inicio": {
        "function": "workflow_execute",
        "payload": {
            "workflow_configuration_code": "PREENCHER_CODIGO_DE_WORKFLOW_CADASTRADO",
            "input_collection": {
                "input_datas": [
                    {
                        # O número e os campos reais dependem do workflow.
                        "workflow_step_number": "PREENCHER_NUMERO_DA_ETAPA",
                        "workflow_step_input_collection": [
                            {
                                "full_path": "PREENCHER_CAMPO_ESPERADO_PELO_WORKFLOW",
                                "detail_value": "PREENCHER_VALOR_SINTETICO_ESPERADO",
                                "is_valid": True,
                            }
                        ],
                    }
                ]
            },
        },
        "parameters": {"timeout": 120},
    },
    "indexar": {
        "function": "index_documents",
        "payload": {
            # index_documents chama workflow_execute: não existe contrato genérico
            # de indexação independente do workflow configurado.
            "workflow_configuration_code": "PREENCHER_CODIGO_DO_WORKFLOW_DE_INDEXACAO",
            "input_collection": {
                "input_datas": [
                    {
                        "workflow_step_number": "PREENCHER_NUMERO_DA_ETAPA",
                        "workflow_step_input_collection": [
                            {
                                "full_path": "PREENCHER_CAMPO_DO_WORKFLOW_DE_INDEXACAO",
                                "detail_value": "PREENCHER_ID_DE_ARQUIVO_SINTETICO",
                                "is_valid": True,
                            }
                        ],
                    }
                ]
            },
        },
        "parameters": {"timeout": 120},
    },
    "workflow_status": {
        "function": "workflow_get_status",
        "payload": {"workflow_execution_id": "PREENCHER_ID_RETORNADO_PELO_WORKFLOW"},
        # Em homol/prod a variável url_wkf do original é "None"; nesse caso,
        # inclua endpoint_url completo do STATUS, com barra final.
        "parameters": {"timeout": 120},
    },
    "agente": {
        "function": "agent_message",
        # ILUSTRATIVO: campo messages não foi confirmado para esse agente.
        "payload": {"messages": [{"role": "user", "content": "Pergunta sintética."}]},
        "parameters": {
            "endpoint_url": "PREENCHER_URL_HTTPS_COMPLETA_DO_AGENTE",
            "timeout": 120,
        },
    },
    "orquestrador": {
        "function": "orchestrator_message",
        # ILUSTRATIVO: campo messages não foi confirmado para esse fluxo.
        "payload": {"messages": [{"role": "user", "content": "Pergunta sintética."}]},
        "parameters": {
            "endpoint_url": "PREENCHER_URL_HTTPS_COMPLETA_DO_ORQUESTRADOR",
            "timeout": 120,
        },
    },
}


# Mantém a escolha de qual operação pode ser disparada explícita e auditável.
# A exclusão demanda uma confirmação adicional e nunca será automática.
DESTRUCTIVE_APIS = {"arquivo_excluir"}


def get_example(api_name: str) -> dict[str, Any]:
    """Fornece uma cópia editável sem modificar os exemplos compartilhados."""
    if api_name not in EXAMPLES:
        available = ", ".join(sorted(EXAMPLES))
        raise ValueError(f"API desconhecida: {api_name}. Disponíveis: {available}")
    return deepcopy(EXAMPLES[api_name])


def _find_placeholders(value: Any, location: str = "config") -> list[str]:
    """Impede enviar marcadores artificiais como IDs, URLs e nomes reais."""
    if isinstance(value, str):
        return [location] if value.startswith("PREENCHER_") else []
    if isinstance(value, dict):
        return [
            issue
            for key, item in value.items()
            for issue in _find_placeholders(item, f"{location}.{key}")
        ]
    if isinstance(value, list):
        return [
            issue
            for index, item in enumerate(value)
            for issue in _find_placeholders(item, f"{location}[{index}]")
        ]
    return []


def validate_example(api_name: str, example: dict[str, Any]) -> None:
    """Valida configurações antes de importar o módulo que dispara o login."""
    if api_name not in EXAMPLES:
        raise ValueError(f"API não cadastrada nos exemplos: {api_name}")
    if not isinstance(example, dict):
        raise TypeError("example deve ser um dicionário.")
    parameters = example.get("parameters")
    if not isinstance(parameters, dict):
        raise TypeError("parameters deve ser um dicionário.")
    if "payload" not in example:
        raise ValueError("O exemplo deve conter payload.")
    placeholders = _find_placeholders(example["payload"], "payload")
    placeholders += _find_placeholders(parameters, "parameters")
    if placeholders:
        raise ValueError("Preencha os campos obrigatórios: " + ", ".join(placeholders))
    if api_name == "arquivo_enviar":
        file_path = Path(example["payload"]["path_file"])
        if not file_path.is_file():
            raise FileNotFoundError("Informe um arquivo de teste local existente em path_file.")
    if api_name in {"workflow_inicio", "indexar"}:
        workflow_steps = example["payload"]["input_collection"]["input_datas"]
        for step in workflow_steps:
            if isinstance(step["workflow_step_number"], bool) or not isinstance(step["workflow_step_number"], int):
                raise TypeError("workflow_step_number deve ser inteiro conforme cadastro do workflow.")
    if api_name in {"agente", "orquestrador"}:
        endpoint = parameters.get("endpoint_url", "")
        if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
            raise ValueError("Informe endpoint_url HTTPS completo conforme documentação interna.")


def run_example(
    api_name: str,
    example: dict[str, Any],
    *,
    execute_request: bool = False,
    confirm_delete: bool = False,
) -> Any:
    """Executa uma API selecionada somente após validação e autorização explícita."""
    if not execute_request:
        # Não exibe payload, tokens, URLs assinadas ou conteúdo dos documentos.
        print(f"Pré-visualização: {api_name}; nenhuma requisição foi enviada.")
        print("Campos de parameters:", ", ".join(example["parameters"].keys()))
        return None
    validate_example(api_name, example)
    if api_name in DESTRUCTIVE_APIS and not confirm_delete:
        raise PermissionError("Exclusão bloqueada: habilite confirm_delete explicitamente.")
    # Importar gpt_bridge inicia o login existente; não mudamos esse comportamento.
    bridge = import_module("gpt_bridge")
    function = getattr(bridge, example["function"])
    return function(example["payload"], example["parameters"])


# Edite APENAS estas três opções e os valores PREENCHER_... do serviço escolhido.
API_NAME = "texto"
EXECUTE_REQUEST = False
CONFIRM_DELETE = False


if __name__ == "__main__":
    selected_example = get_example(API_NAME)
    result = run_example(
        API_NAME,
        selected_example,
        execute_request=EXECUTE_REQUEST,
        confirm_delete=CONFIRM_DELETE,
    )
    if EXECUTE_REQUEST:
        # Use a variável result no Python para inspecionar uma resposta sintética
        # em ambiente autorizado, sem registrar seu conteúdo em logs.
        print("Chamada finalizada; tipo de retorno:", type(result).__name__)
