"""Cliente Python para os serviços Bridge / IAGEN apresentados nos vídeos.

Referências: nove vídeos anexados e ``gpt_bradesco(7).py``. O módulo mantém LITERALMENTE o corpo da função original
``text_generator(payload, llm_parameter)`` e as assinaturas das funções de
File Manager do arquivo de referência. Rotas cujo caminho integral não está
legível nos vídeos (agente e orquestrador) exigem configuração explícita;
nenhuma rota ou campo obrigatório dessas APIs é presumido.

Pré-requisito: ``requests``. Configure ``BRADESCO_AMBIENTE`` (dev, homol, prod)
e ``BRADESCO_AUTHORIZATION_TOKEN``; alternativamente configure
``BRADESCO_IDENTIFICADOR`` e ``BRADESCO_SENHA`` para obter o token de serviço.
A CA corporativa, quando necessária, deve ser indicada em
``BRADESCO_CA_BUNDLE``. As NOVAS APIs verificam TLS; a função text_generator
LEGADA preserva ``verify=False`` literalmente para compatibilidade. Este ponto
precisa ser corrigido no código de origem após aprovação da equipe de segurança.

Decisões: autenticação sob demanda evita solicitações e threads no import;
respostas completas são preservadas nas APIs sem contrato textual único;
requisições POST não sofrem repetição automática para evitar duplicações.
"""

from __future__ import annotations

import json
import base64
import copy
import binascii
import logging
import mimetypes
import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import requests


_LOGGER = logging.getLogger(__name__)
_TOKEN_LOCK = threading.RLock()
_TOKEN_CACHE: str | None = None
# As credenciais existem apenas na memória do processo, nunca em logs ou artefatos.
_AUTH_CONFIG: dict[str, Any] = {}
_ALLOWED_ENVIRONMENTS = {"dev", "homol", "prod"}

# Hosts recuperados do arquivo Python anexado; caminhos de novos serviços
# derivam das páginas da documentação filmadas, quando legíveis.
_BASE_URLS = {
    "dev": "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br",
    "homol": "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br",
    "prod": "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br",
}
_SERVICE_PATHS = {
    "text": "/iagen-textgenerator/v1/text/generate",
    "embedding": "/iagen-embedding/v1/embedding",
    "files": "/iagen-filemanager/v1/files",
    "identity": "/iagen-identity/v1/usuarios/login-servico",
    "ocr": "/iagen-ocr/v1/ocr",
    "retriever": "/iagen-retriever/v1",
    "workflow_request": "/iagen-workflow-request/v1/request/start-workflow",
    "workflow_status": "/iagen-workflow-response/v1/response/workflow-execution-status/",
}
_URL_OVERRIDES = {
    "text": "BRADESCO_TEXT_URL",
    "embedding": "BRADESCO_EMBEDDING_URL",
    "files": "BRADESCO_FILE_MANAGER_URL",
    "identity": "BRADESCO_IDENTITY_URL",
    "ocr": "BRADESCO_OCR_URL",
    "retriever": "BRADESCO_RETRIEVER_URL",
    "workflow_request": "BRADESCO_WORKFLOW_REQUEST_URL",
    "workflow_status": "BRADESCO_WORKFLOW_STATUS_URL",
}


class BridgeAPIError(RuntimeError):
    """Erro sanitizado de comunicação ou de contrato com uma API Bridge."""

    def __init__(
        self, message: str, *, status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


def _log(event: str, **fields: Any) -> None:
    """Registra somente metadados operacionais, sem documentos ou segredos."""
    _LOGGER.info(json.dumps({"event": event, **fields}, ensure_ascii=False))


def _require_text(value: Any, name: str) -> str:
    """Rejeita nulos e valores sem conteúdo antes de qualquer chamada remota."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} deve ser uma string não vazia.")
    return value.strip()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    """Normaliza dicionários mantendo os campos documentados sem renomeá-los."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} deve ser um dicionário.")
    return dict(value)


def _positive_number(value: Any, name: str) -> float:
    """Valida tempos sem aceitar bool, zero ou valores negativos."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} deve ser um número positivo.")
    return float(value)


def _environment(environment: str | None = None) -> str:
    """Define o ambiente explicitamente e evita produção como escolha implícita."""
    selected = environment or _AUTH_CONFIG.get("ambiente") or os.getenv("BRADESCO_AMBIENTE", "dev")
    if selected not in _ALLOWED_ENVIRONMENTS:
        raise ValueError("Ambiente inválido: utilize dev, homol ou prod.")
    return selected


def _validate_url(value: str) -> str:
    """Aceita somente URLs HTTPS absolutas para proteger tokens Bearer."""
    url = _require_text(value, "URL")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A URL da API deve ser HTTPS, absoluta e sem credenciais.")
    if parsed.fragment:
        raise ValueError("A URL da API não pode conter fragmentos.")
    return url.rstrip("/")


def _service_url(service: str, environment: str | None = None) -> str:
    """Escolhe uma rota documentada ou uma substituição explícita por ambiente."""
    if service not in _SERVICE_PATHS:
        raise ValueError(f"Serviço desconhecido: {service}.")
    selected = _environment(environment)
    override = os.getenv(f"{_URL_OVERRIDES[service]}_{selected.upper()}")
    override = override or os.getenv(_URL_OVERRIDES[service])
    if override:
        return _validate_url(override)
    # O arquivo de referência só documenta o status de workflow em DEV.
    if service == "workflow_status" and selected != "dev":
        raise ValueError(
            "Configure BRADESCO_WORKFLOW_STATUS_URL para homol/prod: "
            "a rota não está confirmada nesses ambientes."
        )
    return _BASE_URLS[selected] + _SERVICE_PATHS[service]


def _tls_verify() -> bool | str:
    """Usa a cadeia de confiança padrão ou a CA interna fornecida pela equipe."""
    ca_bundle = _AUTH_CONFIG.get("ca_bundle") or os.getenv("BRADESCO_CA_BUNDLE")
    if not ca_bundle:
        return True
    path = Path(ca_bundle).expanduser()
    if not path.is_file():
        raise ValueError("BRADESCO_CA_BUNDLE aponta para um arquivo inexistente.")
    return str(path)


def _timeout(parameters: Mapping[str, Any] | None = None) -> float:
    """Permite ajustar timeout por operação, com fallback configurável."""
    source = parameters or {}
    raw = source.get("timeout", os.getenv("BRADESCO_TIMEOUT", "120"))
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout deve ser numérico.") from exc
    return _positive_number(parsed, "timeout")


def get_urls(ambiente: str) -> tuple[str, str, str, str, str, str | None]:
    """Mantém o retorno de seis URLs do arquivo legado, sem disparar login."""
    env = _environment(ambiente)
    urls = tuple(_service_url(key, env) for key in (
        "text", "embedding", "files", "identity", "ocr"
    ))
    workflow = _service_url("workflow_status", env) if env == "dev" or (
        os.getenv(f"BRADESCO_WORKFLOW_STATUS_URL_{env.upper()}")
        or os.getenv("BRADESCO_WORKFLOW_STATUS_URL")
    ) else None
    return (*urls, workflow)


# Globais mantidas porque a função text_generator original as consulta diretamente.
# A função get_urls no arquivo transcrito não tinha instrução return; aqui foi corrigida.
url_generate, url_embeddings, url_filemanager, url_token, url_ocr, url_wkf = get_urls(
    _environment()
)


def configure_iagen(auth_parameter: Mapping[str, Any]) -> dict[str, Any]:
    """Configura autenticação e ambiente sem imprimir, persistir ou enviar segredos.

    A configuração é explícita e não executa rede; get_token_iagen autentica depois.
    Retorna apenas diagnóstico sem valores sensíveis para facilitar suporte.
    """
    global _AUTH_CONFIG, _TOKEN_CACHE
    global url_generate, url_embeddings, url_filemanager, url_token, url_ocr, url_wkf
    config = _require_mapping(auth_parameter, "auth_parameter")
    environment = _environment(config.get("ambiente") or os.getenv("BRADESCO_AMBIENTE", "dev"))
    for key in ("identificador", "senha", "token", "ca_bundle"):
        value = config.get(key, "")
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{key} deve ser uma string.")
    # O arquivo do certificado, se configurado, deve existir antes do primeiro login.
    if config.get("ca_bundle") and not Path(config["ca_bundle"]).is_file():
        raise ValueError("ca_bundle deve apontar para um certificado CA existente.")
    with _TOKEN_LOCK:
        _AUTH_CONFIG = {**config, "ambiente": environment}
        _TOKEN_CACHE = None
        url_generate, url_embeddings, url_filemanager, url_token, url_ocr, url_wkf = get_urls(environment)
        # Token injetado explicitamente precisa ficar visível para o text_generator legado.
        if config.get("token"):
            os.environ["BRADESCO_AUTHORIZATION_TOKEN"] = config["token"].removeprefix("Bearer ").strip()
        return auth_diagnostics()


def auth_diagnostics() -> dict[str, Any]:
    """Mostra apenas presença de credenciais e ambiente, nunca valores sensíveis."""
    return {
        "ambiente": _environment(),
        "identity_url": _service_url("identity"),
        "token_disponivel": bool(_TOKEN_CACHE or _AUTH_CONFIG.get("token")
                                 or os.getenv("BRADESCO_AUTHORIZATION_TOKEN")),
        "identificador_configurado": bool(_AUTH_CONFIG.get("identificador")
                                         or os.getenv("BRADESCO_IDENTIFICADOR")),
        "senha_configurada": bool(_AUTH_CONFIG.get("senha") or os.getenv("BRADESCO_SENHA")),
        "ca_corporativa_configurada": bool(_AUTH_CONFIG.get("ca_bundle")
                                          or os.getenv("BRADESCO_CA_BUNDLE")),
        "observacao": "Presença de token não comprova validade nem permissão na API.",
    }


def get_token_iagen(force_refresh: bool = False) -> str:
    """Recupera token disponível ou autentica usando variáveis de ambiente.

    O token é mantido apenas em memória; não há renovação em background nem
    gravação em .env. Um token pré-provisionado sempre é aceito sem login.
    """
    global _TOKEN_CACHE
    with _TOKEN_LOCK:
        # O token externo é aceito sem login; a origem real permanece não verificada.
        if _TOKEN_CACHE and not force_refresh:
            return _TOKEN_CACHE
        provided = (_AUTH_CONFIG.get("token")
                    or os.getenv("BRADESCO_AUTHORIZATION_TOKEN", "")).strip()
        if provided and not force_refresh:
            _TOKEN_CACHE = provided.removeprefix("Bearer ").strip()
            # Contrato legado: text_generator lê o token diretamente do ambiente.
            os.environ["BRADESCO_AUTHORIZATION_TOKEN"] = _TOKEN_CACHE
            return _TOKEN_CACHE
        identifier = _AUTH_CONFIG.get("identificador") or os.getenv("BRADESCO_IDENTIFICADOR")
        password = _AUTH_CONFIG.get("senha") or os.getenv("BRADESCO_SENHA")
        if not identifier or not password:
            if force_refresh and provided:
                raise BridgeAPIError(
                    "Não é possível renovar um token informado manualmente sem "
                    "identificador e senha. Solicite um novo token ao provedor."
                )
            raise BridgeAPIError(
                "Faltam credenciais: configure_iagen(AUTH_PARAMETERS) com identificador "
                "e senha, ou forneça BRADESCO_AUTHORIZATION_TOKEN. "
                "Não inclua credenciais em logs ou mensagens de suporte."
            )
        url = _service_url("identity")
        try:
            response = requests.request(
                "POST", url,
                headers={"Accept": "application/json"},
                json={"identificador": identifier, "senha": password},
                timeout=_timeout(), verify=_tls_verify(),
            )
        except requests.exceptions.SSLError as exc:
            raise BridgeAPIError(
                "Falha de certificado TLS no login: configure BRADESCO_CA_BUNDLE "
                "com uma CA corporativa confiável; não desative a validação TLS."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise BridgeAPIError(
                "Tempo de conexão excedido no login: confirme VPN/rede interna, "
                "ambiente e URL da API de identidade."
            ) from exc
        except requests.RequestException as exc:
            raise BridgeAPIError(
                "Falha de rede no login: confirme VPN, DNS e URL da API de identidade."
            ) from exc
        _check_status(response, "identity.login")
        result = _json_response(response, "identity.login")
        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise BridgeAPIError("Autenticação não retornou o campo token esperado.")
        _TOKEN_CACHE = token
        # Obrigatório para a função text_generator original, que permanece intacta.
        os.environ["BRADESCO_AUTHORIZATION_TOKEN"] = token
        # Evita reutilizar token fornecido antes de um login explícito de renovação.
        _AUTH_CONFIG.pop("token", None)
        _log("identity.token_obtained")
        return token


def renew_token() -> str:
    """Compatibilidade: renova somente quando chamada, sem criar threads."""
    return get_token_iagen(force_refresh=True)


def _headers(json_body: bool = True) -> dict[str, str]:
    """Centraliza autenticação e negociação de conteúdo, sem expor token."""
    result = {
        "Authorization": f"Bearer {get_token_iagen()}",
        "Accept": "application/json",
    }
    if json_body:
        result["Content-Type"] = "application/json"
    return result


def _request_id(response: requests.Response) -> str | None:
    """Extrai ID de rastreio, quando o gateway o disponibilizar."""
    return response.headers.get("X-Request-ID") or response.headers.get("x-correlation-id")


def _check_status(response: requests.Response, operation: str) -> None:
    """Não incorpora corpos de erro: eles podem conter dados pessoais."""
    request_id = _request_id(response)
    _log("bridge.http_result", operation=operation,
         status_code=response.status_code, request_id=request_id)
    if not 200 <= response.status_code < 300:
        guidance = ""
        if response.status_code == 401:
            guidance = (" Token ausente, inválido, expirado ou inadequado ao serviço; "
                        "verifique ambiente e renove via get_token_iagen(force_refresh=True) "
                        "se possuir credenciais.")
        elif response.status_code == 403:
            guidance = (" Acesso negado: confirme autorização do identificador "
                        "para esta API e este ambiente com a equipe responsável.")
        raise BridgeAPIError(
            f"{operation} falhou: HTTP {response.status_code}. "
            f"Identificador da requisição: {request_id or 'não informado'}." + guidance,
            status_code=response.status_code, request_id=request_id,
        )


def _json_response(response: requests.Response, operation: str) -> dict[str, Any]:
    """Rejeita JSON inválido ou tipo divergente com mensagem objetiva."""
    try:
        result = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise BridgeAPIError(f"{operation}: resposta não é um JSON válido.") from exc
    if not isinstance(result, dict):
        raise BridgeAPIError(f"{operation}: a resposta deve ser um objeto JSON.")
    return result


def _call(
    operation: str, method: str, url: str, *,
    payload: dict[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Realiza uma única requisição e devolve o contrato JSON sem alterações."""
    verified_url = _validate_url(url)
    started_at = time.monotonic()
    try:
        response = requests.request(
            method, verified_url, headers=_headers(), json=payload, params=query,
            timeout=_timeout(parameters), verify=_tls_verify(),
        )
    except requests.RequestException as exc:
        _log("bridge.connection_error", operation=operation)
        raise BridgeAPIError(f"{operation}: falha de conexão com a API.") from exc
    _check_status(response, operation)
    _log("bridge.elapsed", operation=operation,
         elapsed_ms=round((time.monotonic() - started_at) * 1000))
    return _json_response(response, operation)


def _stream_call(
    operation: str, url: str, payload: dict[str, Any],
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Lê JSON Lines ou SSE do gerador de texto, respeitando [DONE]."""
    chunks: list[str] = []
    try:
        with requests.request(
            "POST", _validate_url(url), headers=_headers(), json=payload,
            timeout=_timeout(parameters), verify=_tls_verify(), stream=True,
        ) as response:
            _check_status(response, operation)
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if line.startswith(":") or line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if not line or line == "[DONE]":
                    if line == "[DONE]":
                        break
                    continue
                try:
                    item = json.loads(line)
                except ValueError as exc:
                    raise BridgeAPIError(f"{operation}: fragmento de stream inválido.") from exc
                if not isinstance(item, dict):
                    raise BridgeAPIError(f"{operation}: fragmento de stream inesperado.")
                output = item.get("response", {}).get("output_text")
                if output is None:
                    output = item.get("output_text", "")
                if not isinstance(output, str):
                    raise BridgeAPIError(f"{operation}: fragmento sem texto válido.")
                chunks.append(output)
    except requests.RequestException as exc:
        raise BridgeAPIError(f"{operation}: conexão de streaming interrompida.") from exc
    return "".join(chunks)


def _extract_output_text(response: Mapping[str, Any]) -> str:
    """Preserva o retorno string da função text_generator original."""
    nested = response.get("response")
    result = nested.get("output_text") if isinstance(nested, Mapping) else None
    if not isinstance(result, str):
        raise BridgeAPIError("Gerador de texto: response.output_text ausente ou inválido.")
    return result


def text_generator(payload, llm_parameter: dict):
    """
    Esta função gera texto usando um modelo e configuração especificados.
    """
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]

    message_format = llm_parameter.get("message_format", {"type": "text"})

    async_mode = llm_parameter.get("async_mode", False)

    stream = llm_parameter.get("stream", False)

    openai_api_version = llm_parameter.get("openai_api_version", "2024-02-01")

    if type(payload) is str:
        messages = [{"role": "user", "content": payload}]
    elif type(payload) is list:
        messages = payload
    else:
        raise ValueError("O payload deve ser uma string ou uma lista de mensagens.")

    if not llm_parameter.get("temperature", False) and not llm_parameter.get(
        "max_tokens", False
    ):
        payload_json = {
            "async_mode": async_mode,
            "stream": stream,
            "model": llm_parameter["deployment_name"],
            "response_format": message_format,
            "messages": messages,
            "openai_api_version": openai_api_version,
        }
    else:
        payload_json = {
            "async_mode": async_mode,
            "stream": stream,
            "model": llm_parameter["deployment_name"],
            "temperature": llm_parameter["temperature"],
            "max_tokens": llm_parameter["max_tokens"],
            "response_format": message_format,
            "messages": messages,
            "openai_api_version": openai_api_version,
        }

    headers = {"Authorization": f"Bearer {token}"}

    if not async_mode and not stream:
        print("Gerando texto no modo síncrono.")
        response = requests.request(
            "POST",
            url_generate,
            headers=headers,
            verify=False,
            timeout=600,
            json=payload_json,
        )

        if response.status_code == 200:
            print("Sucesso na execução.")
            result = json.loads(response.text)["response"]["output_text"]
            return result
        else:
            print(
                f"Erro na execução: {response.status_code} - {response.text}"
            )
            raise Exception(
                f"Erro na execução: {response.status_code} - {response.text}"
            )

    elif async_mode and not stream:
        print(f"Gerando texto no modo assíncrono.")
        response = requests.request(
            "POST",
            url_generate,
            headers=headers,
            verify=False,
            timeout=600,
            json=payload_json,
        )

        if response.status_code == 200:
            print("Sucesso na execução.")
            result = json.loads(response.text)
            workflow_execution_id = result["workflow_execution_id"]
        else:
            print(
                f"Erro na execução: {response.status_code} - {response.text}"
            )
            raise Exception(
                f"Erro na execução: {response.status_code} - {response.text}"
            )
        counter = 0
        max_counter = 120
        while counter < max_counter:  # Espera no máximo 10 minutos
            counter += 1
            print("Aguardando a conclusão do workflow...")
            print(
                f"Verificando o status do workflow. Tentativa {counter} de "
                f"{max_counter}."
            )
            time.sleep(5)
            url_wkf_id = f"{url_wkf}{workflow_execution_id}"
            response = requests.request(
                "GET",
                url_wkf_id,
                headers=headers,
                verify=False,
                timeout=600,
            )
            if response.status_code == 200:
                result = json.loads(response.text)
                if result["status"] == "WF_COMPLETED_SUCCESS":
                    print("Workflow concluído com sucesso.")
                    result_wkf = result["output_collection"]["output_datas"][0][
                        "workflow_step_output_collection"
                    ]["output"]["json_data"]["output_text"]
                    return result_wkf

    elif not async_mode and stream:
        print("Gerando texto no modo de streaming.")
        result = ""
        with requests.request(
            "POST",
            url_generate,
            headers=headers,
            timeout=600,
            json=payload_json,
            stream=False,
            verify=False,
        ) as response:
            try:
                response.raise_for_status()
                print("Rodando no modo de streaming.")
                for line in response.iter_lines():
                    if line:
                        chunck = json.loads(line.decode("utf-8"))["response"][
                            "output_text"
                        ]
                        # print(f"Chunk recebido: {chunck}")
                        result += chunck
                return result

            except Exception as e:
                print(f"Erro na execução: {e}")
                raise Exception(f"Erro na execução: {e}")

    else:
        raise ValueError(
            "Parâmetros inválidos: async_mode e stream não podem ser ambos True."
        )

def embedding_generator(payload: str, embedding_parameter: dict) -> list[float]:
    """Gera um vetor; documentação: input, model e dimensions (opcional).

    Mantém o padrão ``(payload, parameters)`` da text_generator. O retorno
    ``response`` da API de embeddings é uma lista de números.
    """
    config = _require_mapping(embedding_parameter, "embedding_parameter")
    body: dict[str, Any] = {
        "input": _require_text(payload, "payload"),
        "model": _require_text(config.get("deployment_name", config.get("model")), "model"),
    }
    if "dimensions" in config:
        dimensions = config["dimensions"]
        if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError("dimensions deve ser um inteiro positivo.")
        body["dimensions"] = dimensions
    result = _call(
        "embedding.generate", "POST", _service_url("embedding", config.get("ambiente")),
        payload=body, parameters=config,
    )
    vector = result.get("response")
    if not isinstance(vector, list) or not vector or not all(
        isinstance(x, (float, int)) and not isinstance(x, bool) for x in vector
    ):
        raise BridgeAPIError("Embedding: campo response não contém um vetor numérico.")
    if "dimensions" in body and len(vector) != body["dimensions"]:
        raise BridgeAPIError("Embedding: dimensão retornada diverge da solicitada.")
    return vector


def ocr_generator(payload: dict, ocr_parameter: dict | None = None) -> dict[str, Any]:
    """Executa POST /ocr sem descartar metadados de execução.

    A documentação mostra: files_id, files_path, container, input_text,
    async_mode, workflow_configuration_code, stream_mode e
    stream_mode_timeout. Não pressupõe que todos sejam obrigatórios.
    """
    body = _require_mapping(payload, "payload")
    config = _require_mapping(ocr_parameter or {}, "ocr_parameter")
    if not any(body.get(key) for key in ("files_id", "files_path")):
        raise ValueError("OCR requer files_id ou files_path com pelo menos um arquivo.")
    for key in ("files_id", "files_path"):
        if key in body and (not isinstance(body[key], list) or not body[key]
                            or not all(isinstance(v, str) and v.strip() for v in body[key])):
            raise ValueError(f"{key} deve ser uma lista não vazia de strings.")
    if "async_mode" in body and not isinstance(body["async_mode"], bool):
        raise TypeError("async_mode deve ser booleano.")
    if "stream_mode" in body and not isinstance(body["stream_mode"], bool):
        raise TypeError("stream_mode deve ser booleano.")
    return _call("ocr.execute", "POST", _service_url("ocr", config.get("ambiente")),
                 payload=body, parameters=config)


def get_text_ocr(files_path: list[str], container: str, input_text: str) -> dict[str, Any]:
    """Compatibilidade com a função OCR original sem fixar URL de produção."""
    return ocr_generator({
        "files_path": files_path,
        "container": _require_text(container, "container"),
        "input_text": input_text,
    })


def retriever_search(payload: dict, retriever_parameter: dict | None = None) -> dict[str, Any]:
    """Consulta POST /indices/documentos; devolve chunks e scores originais."""
    body = _require_mapping(payload, "payload")
    _require_text(body.get("index_name"), "index_name")
    _require_text(body.get("search_query"), "search_query")
    config = _require_mapping(retriever_parameter or {}, "retriever_parameter")
    url = _service_url("retriever", config.get("ambiente")) + "/indices/documentos"
    return _call("retriever.documents", "POST", url, payload=body, parameters=config)


def retriever_next_questions(
    payload: dict, retriever_parameter: dict | None = None,
) -> dict[str, Any]:
    """Consulta POST /indices/proximas-perguntas, preservando a resposta."""
    body = _require_mapping(payload, "payload")
    _require_text(body.get("next_question_config"), "next_question_config")
    _require_text(body.get("search_query"), "search_query")
    config = _require_mapping(retriever_parameter or {}, "retriever_parameter")
    url = _service_url("retriever", config.get("ambiente")) + "/indices/proximas-perguntas"
    return _call("retriever.next_questions", "POST", url, payload=body, parameters=config)


def file_manager_list_files(container_name: str, page: int = 0,
                            page_size: int = 50000) -> dict[str, Any]:
    """Lista arquivos do container com paginação, como na função original."""
    _require_text(container_name, "container_name")
    for value, name in ((page, "page"), (page_size, "page_size")):
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if name == "page_size" else 0):
            raise ValueError(f"{name} inválido.")
    return _call("files.list", "GET", _service_url("files"), query={
        "container_name": container_name, "page": page, "page_size": page_size,
    })


def file_manager_upload(
    path_file: str, file_name: str, container_name: str,
    create_container: str | bool = "false", overwrite: str | bool = "true",
) -> int:
    """Envia arquivo via multipart e mantém retorno HTTP numérico legado."""
    path = Path(_require_text(path_file, "path_file"))
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path.name}.")
    name = _require_text(file_name, "file_name")
    if Path(name).name != name or name in {".", ".."}:
        raise ValueError("file_name deve ser um nome simples, sem diretórios.")
    extension = path.suffix.lower()
    if extension and not name.lower().endswith(extension):
        name += extension
    _require_text(container_name, "container_name")

    def as_boolean_string(value: str | bool, field: str) -> str:
        """Evita que 'False' seja enviado com semântica ambígua ao gateway."""
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower()
        raise ValueError(f"{field} deve ser true ou false.")

    data = {
        "container_name": container_name,
        "create_container": as_boolean_string(create_container, "create_container"),
        "overwrite": as_boolean_string(overwrite, "overwrite"),
    }
    mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        with path.open("rb") as file_object:
            response = requests.request(
                "POST", _validate_url(_service_url("files") + "/upload"),
                headers=_headers(json_body=False), data=data,
                files={"file": (name, file_object, mime_type)},
                timeout=_timeout(), verify=_tls_verify(),
            )
    except OSError as exc:
        raise BridgeAPIError("Não foi possível ler o arquivo para upload.") from exc
    except requests.RequestException as exc:
        raise BridgeAPIError("Falha de conexão durante upload.") from exc
    _check_status(response, "files.upload")
    return response.status_code


def file_manager_upload_base64(
    payload: dict, file_parameter: dict | None = None,
) -> dict[str, Any]:
    """Envia POST /files/upload/base64 com os campos da documentação.

    O payload contém ``base64``, ``file_name``, ``container_name``,
    ``create_container`` e ``overwrite``. O conteúdo em base64 não é
    registrado nos logs nem incluído em mensagens de erro.
    """
    body = _require_mapping(payload, "payload")
    for field in ("base64", "file_name", "container_name"):
        _require_text(body.get(field), field)
    try:
        base64.b64decode(body["base64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("base64 deve conter dados válidos.") from exc
    for field in ("create_container", "overwrite"):
        if field in body and not isinstance(body[field], bool):
            raise TypeError(f"{field} deve ser booleano neste endpoint.")
    config = _require_mapping(file_parameter or {}, "file_parameter")
    return _call(
        "files.upload_base64", "POST",
        _service_url("files", config.get("ambiente")) + "/upload/base64",
        payload=body, parameters=config,
    )


def file_manager_get_download_url(
    file_id: str, file_parameter: dict | None = None,
) -> str:
    """Obtém URL assinada via GET /files/{id}/filedownload.

    O resultado contém credenciais temporárias de acesso ao objeto: não
    registre, compartilhe publicamente ou persista a URL assinada.
    """
    identifier = _require_text(file_id, "file_id")
    config = _require_mapping(file_parameter or {}, "file_parameter")
    url = (_service_url("files", config.get("ambiente")) + "/"
           + quote(identifier, safe="") + "/filedownload")
    try:
        result = requests.request(
            "GET", _validate_url(url), headers=_headers(),
            timeout=_timeout(config), verify=_tls_verify(),
        )
    except requests.RequestException as exc:
        raise BridgeAPIError("Falha de conexão ao solicitar URL de download.") from exc
    _check_status(result, "files.download_url")
    try:
        signed_url = result.json()
    except ValueError as exc:
        raise BridgeAPIError("Resposta de download não contém uma URL JSON válida.") from exc
    if not isinstance(signed_url, str):
        raise BridgeAPIError("Resposta de download não é uma URL assinada.")
    # O serviço retorna uma string JSON contendo URL com SAS token.
    return _validate_url(signed_url)


def file_manager_delete(file_id: str) -> str:
    """Remove arquivo por ID; mantém retorno string do módulo legado."""
    file_id = _require_text(file_id, "file_id")
    url = _service_url("files") + "/" + quote(file_id, safe="")
    try:
        response = requests.request("DELETE", _validate_url(url),
                                    headers=_headers(), timeout=_timeout(),
                                    verify=_tls_verify())
    except requests.RequestException as exc:
        raise BridgeAPIError("Falha de conexão ao excluir arquivo.") from exc
    _check_status(response, "files.delete")
    return f"{response.status_code} Arquivo deletado com sucesso"


def workflow_execute(payload: dict, workflow_parameter: dict | None = None) -> dict[str, Any]:
    """Inicia POST /request/start-workflow com o JSON documentado pelo fluxo.

    Recebe o objeto pronto com workflow_configuration_code e input_collection.
    Não inventa códigos de workflow nem nomes de campos no input_collection.
    """
    body = _require_mapping(payload, "payload")
    _require_text(body.get("workflow_configuration_code"), "workflow_configuration_code")
    if not isinstance(body.get("input_collection"), dict):
        raise ValueError("input_collection deve ser um dicionário.")
    config = _require_mapping(workflow_parameter or {}, "workflow_parameter")
    return _call("workflow.start", "POST",
                 _service_url("workflow_request", config.get("ambiente")),
                 payload=body, parameters=config)


def index_documents(payload: dict, index_parameter: dict | None = None) -> dict[str, Any]:
    """Executa o workflow de indexação fornecido; não cria um esquema fictício."""
    return workflow_execute(payload, index_parameter)


def workflow_status(workflow_execution_id: str,
                    workflow_parameter: dict | None = None) -> dict[str, Any]:
    """Consulta GET /workflow-execution-status/{id}."""
    execution_id = _require_text(workflow_execution_id, "workflow_execution_id")
    config = _require_mapping(workflow_parameter or {}, "workflow_parameter")
    url = _service_url("workflow_status", config.get("ambiente"))
    return _call("workflow.status", "GET", url.rstrip("/") + "/" + quote(execution_id, safe=""),
                 parameters=config)


def wait_for_workflow(workflow_execution_id: str,
                      workflow_parameter: dict | None = None) -> dict[str, Any]:
    """Aguarda conclusão usando tempo máximo real, inclusive entre consultas."""
    config = _require_mapping(workflow_parameter or {}, "workflow_parameter")
    poll_interval = _positive_number(config.get("poll_interval", 5), "poll_interval")
    max_wait = _positive_number(config.get("max_wait_seconds", 600), "max_wait_seconds")
    deadline = time.monotonic() + max_wait
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BridgeAPIError("Tempo máximo de espera do workflow excedido.")
        # Uma consulta iniciada perto do prazo não deve exceder todo o orçamento.
        query_config = {**config, "timeout": min(_timeout(config), remaining)}
        result = workflow_status(workflow_execution_id, query_config)
        state = result.get("status")
        if state == "WF_COMPLETED_SUCCESS":
            return result
        if state in {"WF_COMPLETED_ERROR", "WF_COMPLETED_FAILURE", "WF_FAILED", "WF_CANCELLED"}:
            raise BridgeAPIError(f"Workflow encerrado sem sucesso (status: {state}).")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BridgeAPIError("Tempo máximo de espera do workflow excedido.")
        time.sleep(min(poll_interval, remaining))


def _extract_workflow_text(result: Mapping[str, Any]) -> str:
    """Interpreta a estrutura aninhada exibida no módulo Python original."""
    try:
        output = result["output_collection"]["output_datas"][0]
        text = output["workflow_step_output_collection"]["output"]["json_data"]["output_text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BridgeAPIError("Workflow concluído sem output_text no formato esperado.") from exc
    if not isinstance(text, str):
        raise BridgeAPIError("Workflow retornou output_text inválido.")
    return text


def _configured_endpoint(config: Mapping[str, Any], env_key: str) -> str:
    """Exige a URL integral das rotas não legíveis na gravação.

    Isto impede que uma rota inventada seja interpretada como documentação
    corporativa. URLs podem variar conforme o contrato do agente cadastrado.
    """
    url = config.get("endpoint_url") or os.getenv(env_key)
    if not url:
        raise ValueError(
            f"Informe endpoint_url no dicionário ou configure {env_key}. "
            "O caminho exato do endpoint não é legível nos vídeos."
        )
    return _validate_url(url)


def agent_message(payload: dict, agent_parameter: dict | None = None) -> dict[str, Any]:
    """Chama o agente Bridge com corpo JSON e endpoint completo configurado.

    O payload é enviado sem transformação para preservar o contrato particular
    de cada agente. Preencha ``endpoint_url`` com a rota obtida da API interna.
    """
    body = _require_mapping(payload, "payload")
    if not body:
        raise ValueError("payload do agente não pode ser vazio.")
    config = _require_mapping(agent_parameter or {}, "agent_parameter")
    return _call("agent.message", "POST", _configured_endpoint(config, "BRADESCO_AGENT_ENDPOINT"),
                 payload=body, parameters=config)


def orchestrator_message(
    payload: dict, orchestrator_parameter: dict | None = None,
) -> dict[str, Any]:
    """Chama orquestrador de agentes com sua URL específica e JSON original."""
    body = _require_mapping(payload, "payload")
    if not body:
        raise ValueError("payload do orquestrador não pode ser vazio.")
    config = _require_mapping(orchestrator_parameter or {}, "orchestrator_parameter")
    return _call("orchestrator.message", "POST",
                 _configured_endpoint(config, "BRADESCO_ORCHESTRATOR_ENDPOINT"),
                 payload=body, parameters=config)


# Dicionários de exemplo: campos vazios são obrigatórios de preencher antes do uso.
# Valores de modelos, IDs de arquivo, índices e workflows nunca são fabricados.
AUTH_PARAMETERS: dict[str, str] = {
    "ambiente": "dev",               # dev, homol ou prod; confirme onde tem acesso.
    "identificador": "",              # Identificador de serviço liberado para a API.
    "senha": "",                      # Fornecer em runtime; não salvar no repositório.
    "token": "",                      # Opcional: token já emitido, sem prefixo Bearer.
    "ca_bundle": "",                  # Opcional: caminho para CA corporativa.
}

API_CONFIGS: dict[str, dict[str, Any]] = {
    "texto": {
        "payload": "Mensagem sintética sem dados pessoais.",
        "parameters": {
            "deployment_name": "iagen-llm-7b",  # Exemplo do arquivo original; confirmar disponibilidade.
            "temperature": 0, "max_tokens": 16384,
            "async_mode": False, "stream": False,
            "message_format": {"type": "json_object"},
            "openai_api_version": "2024-02-01",
        },
    },
    "embeddings": {
        "payload": "Texto de teste fictício para vetorização.",
        "parameters": {"deployment_name": "", "ambiente": "dev", "timeout": 120},
    },
    "ocr": {
        "payload": {
            "files_path": [""], "container": "", "input_text": "Extraia o texto.",
        },
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "retriever_documentos": {
        "payload": {"index_name": "", "search_query": "Pergunta de exemplo."},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "retriever_proximas_perguntas": {
        "payload": {"next_question_config": "", "search_query": "Pergunta de exemplo."},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "arquivo_listar": {
        "payload": {"container_name": "", "page": 0, "page_size": 50000},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "arquivo_enviar": {
        "payload": {"path_file": "", "file_name": "", "container_name": "",
                    "create_container": "false", "overwrite": "true"},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "arquivo_base64": {
        "payload": {"base64": "", "file_name": "", "container_name": "",
                    "create_container": False, "overwrite": True},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "arquivo_download_url": {
        "payload": {"file_id": ""},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "arquivo_excluir": {
        "payload": {"file_id": ""},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "indexar": {
        "payload": {
            "workflow_configuration_code": "",  # Confirmar código autorizado do workflow.
            "input_collection": {
                "input_datas": [{
                    "workflow_step_number": 0,
                    "workflow_step_input_collection": [{
                        "full_path": "",     # Confirmar caminho lógico no workflow cadastrado.
                        "detail_value": "",  # ID de arquivo, índice ou valor exigido pelo fluxo.
                        "is_valid": True,
                    }],
                }],
            },
        },
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "workflow_status": {
        "payload": {"workflow_execution_id": ""},
        "parameters": {"ambiente": "dev", "timeout": 120},
    },
    "agente": {
        "payload": {"messages": [{"role": "user", "content": "Pergunta fictícia."}]},
        "parameters": {"ambiente": "dev", "endpoint_url": "", "timeout": 120},
    },
    "orquestrador": {
        "payload": {"messages": [{"role": "user", "content": "Pergunta fictícia."}]},
        "parameters": {"ambiente": "dev", "endpoint_url": "", "timeout": 120},
    },
}


def get_api_config(api_name: str) -> dict[str, Any]:
    """Copia um modelo para que alterações não contaminem futuras chamadas."""
    if api_name not in API_CONFIGS:
        raise ValueError(f"API desconhecida: {api_name}. Opções: {', '.join(API_CONFIGS)}")
    return copy.deepcopy(API_CONFIGS[api_name])


def file_manager_list(payload: dict, file_parameter: dict | None = None) -> dict[str, Any]:
    """Wrapper (payload, parameters) para listagem com paginação."""
    body = _require_mapping(payload, "payload")
    config = _require_mapping(file_parameter or {}, "file_parameter")
    _require_text(body.get("container_name"), "container_name")
    page = body.get("page", 0)
    page_size = body.get("page_size", 50000)
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        raise ValueError("page deve ser inteiro não negativo.")
    if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size <= 0:
        raise ValueError("page_size deve ser inteiro positivo.")
    return _call("files.list", "GET", _service_url("files", config.get("ambiente")),
                 parameters=config, query={"container_name": body["container_name"],
                                           "page": page, "page_size": page_size})


def file_manager_upload_file(payload: dict, file_parameter: dict | None = None) -> int:
    """Wrapper (payload, parameters) para upload multipart, sem converter em JSON."""
    body = _require_mapping(payload, "payload")
    config = _require_mapping(file_parameter or {}, "file_parameter")
    path = Path(_require_text(body.get("path_file"), "path_file"))
    if not path.is_file():
        raise FileNotFoundError("path_file não aponta para arquivo existente.")
    filename = _require_text(body.get("file_name"), "file_name")
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("file_name deve ser um nome simples, sem diretórios.")
    extension = path.suffix.lower()
    if extension and not filename.lower().endswith(extension):
        filename += extension
    container = _require_text(body.get("container_name"), "container_name")
    def bool_string(value: Any, name: str) -> str:
        """Normaliza flags multipart no formato true/false documentado."""
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower()
        raise ValueError(f"{name} deve ser true ou false.")
    data = {"container_name": container,
            "create_container": bool_string(body.get("create_container", "false"), "create_container"),
            "overwrite": bool_string(body.get("overwrite", "true"), "overwrite")}
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        with path.open("rb") as stream:
            response = requests.request(
                "POST", _validate_url(_service_url("files", config.get("ambiente")) + "/upload"),
                headers=_headers(json_body=False), data=data,
                files={"file": (filename, stream, mimetype)},
                timeout=_timeout(config), verify=_tls_verify(),
            )
    except OSError as exc:
        raise BridgeAPIError("Não foi possível ler o arquivo para upload.") from exc
    except requests.RequestException as exc:
        raise BridgeAPIError("Falha de conexão durante upload.") from exc
    _check_status(response, "files.upload")
    return response.status_code


def file_manager_download_url(payload: dict, file_parameter: dict | None = None) -> str:
    """Wrapper (payload, parameters) para obter URL de download assinada."""
    body = _require_mapping(payload, "payload")
    return file_manager_get_download_url(
        _require_text(body.get("file_id"), "file_id"), file_parameter
    )


def file_manager_delete_file(payload: dict, file_parameter: dict | None = None) -> str:
    """Wrapper (payload, parameters) para exclusão no ambiente selecionado."""
    body = _require_mapping(payload, "payload")
    config = _require_mapping(file_parameter or {}, "file_parameter")
    file_id = _require_text(body.get("file_id"), "file_id")
    url = _service_url("files", config.get("ambiente")) + "/" + quote(file_id, safe="")
    try:
        response = requests.request("DELETE", _validate_url(url), headers=_headers(),
                                    timeout=_timeout(config), verify=_tls_verify())
    except requests.RequestException as exc:
        raise BridgeAPIError("Falha de conexão ao excluir arquivo.") from exc
    _check_status(response, "files.delete")
    return f"{response.status_code} Arquivo deletado com sucesso"


def workflow_get_status(payload: dict, workflow_parameter: dict | None = None) -> dict[str, Any]:
    """Wrapper (payload, parameters) para consultar status sem iniciar outro job."""
    body = _require_mapping(payload, "payload")
    return workflow_status(
        _require_text(body.get("workflow_execution_id"), "workflow_execution_id"),
        workflow_parameter,
    )


__all__ = [
    "BridgeAPIError", "get_urls", "get_token_iagen", "renew_token",
    "AUTH_PARAMETERS", "API_CONFIGS", "get_api_config", "configure_iagen", "auth_diagnostics",
    "text_generator", "embedding_generator", "ocr_generator", "get_text_ocr",
    "retriever_search", "retriever_next_questions", "file_manager_list_files",
    "file_manager_upload", "file_manager_upload_base64",
    "file_manager_get_download_url", "file_manager_delete", "workflow_execute",
    "index_documents", "workflow_status", "wait_for_workflow", "agent_message",
    "orchestrator_message", "file_manager_list", "file_manager_upload_file",
    "file_manager_download_url", "file_manager_delete_file", "workflow_get_status",
]
