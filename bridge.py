"""Cliente Python para os serviços Bridge / IAGEN apresentados nos vídeos.

Referências: nove vídeos anexados e ``gpt_bradesco(7).py``. O módulo mantém
``text_generator(payload, llm_parameter)`` e as assinaturas das funções de
File Manager do arquivo de referência. Rotas cujo caminho integral não está
legível nos vídeos (agente e orquestrador) exigem configuração explícita;
nenhuma rota ou campo obrigatório dessas APIs é presumido.

Pré-requisito: ``requests``. Configure ``BRADESCO_AMBIENTE`` (dev, homol, prod)
e ``BRADESCO_AUTHORIZATION_TOKEN``; alternativamente configure
``BRADESCO_IDENTIFICADOR`` e ``BRADESCO_SENHA`` para obter o token de serviço.
A CA corporativa, quando necessária, deve ser indicada em
``BRADESCO_CA_BUNDLE``. Nunca desative a verificação TLS.

Decisões: autenticação sob demanda evita solicitações e threads no import;
respostas completas são preservadas nas APIs sem contrato textual único;
requisições POST não sofrem repetição automática para evitar duplicações.
"""

from __future__ import annotations

import json
import base64
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
    selected = environment or os.getenv("BRADESCO_AMBIENTE", "dev")
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
    ca_bundle = os.getenv("BRADESCO_CA_BUNDLE")
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


def get_token_iagen(force_refresh: bool = False) -> str:
    """Recupera token disponível ou autentica usando variáveis de ambiente.

    O token é mantido apenas em memória; não há renovação em background nem
    gravação em .env. Um token pré-provisionado sempre é aceito sem login.
    """
    global _TOKEN_CACHE
    with _TOKEN_LOCK:
        if _TOKEN_CACHE and not force_refresh:
            return _TOKEN_CACHE
        provided = os.getenv("BRADESCO_AUTHORIZATION_TOKEN")
        if provided and not force_refresh:
            _TOKEN_CACHE = provided
            return provided
        identifier = os.getenv("BRADESCO_IDENTIFICADOR")
        password = os.getenv("BRADESCO_SENHA")
        if not identifier or not password:
            raise BridgeAPIError(
                "Configure BRADESCO_AUTHORIZATION_TOKEN ou as variáveis "
                "BRADESCO_IDENTIFICADOR e BRADESCO_SENHA."
            )
        url = _service_url("identity")
        try:
            response = requests.request(
                "POST", url,
                headers={"Accept": "application/json"},
                json={"identificador": identifier, "senha": password},
                timeout=_timeout(), verify=_tls_verify(),
            )
        except requests.RequestException as exc:
            raise BridgeAPIError("Falha de conexão ao autenticar no IAGEN.") from exc
        _check_status(response, "identity.login")
        result = _json_response(response, "identity.login")
        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise BridgeAPIError("Autenticação não retornou o campo token esperado.")
        _TOKEN_CACHE = token
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
        raise BridgeAPIError(
            f"{operation} falhou: HTTP {response.status_code}. "
            f"Identificador da requisição: {request_id or 'não informado'}.",
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


def text_generator(payload: str | list[dict[str, Any]], llm_parameter: dict) -> str:
    """Gera texto com a mesma interface e retorno do arquivo original.

    ``llm_parameter``: deployment_name (obrigatório), temperature, max_tokens,
    message_format, openai_api_version, async_mode, stream, timeout,
    poll_interval, max_wait_seconds. A combinação async_mode + stream é inválida.
    """
    config = _require_mapping(llm_parameter, "llm_parameter")
    model = _require_text(config.get("deployment_name"), "deployment_name")
    if isinstance(payload, str):
        messages = [{"role": "user", "content": _require_text(payload, "payload")}]
    elif isinstance(payload, list) and payload and all(isinstance(m, dict) for m in payload):
        messages = payload
    else:
        raise ValueError("payload deve ser texto não vazio ou lista de mensagens.")
    async_mode = config.get("async_mode", False)
    stream = config.get("stream", False)
    if not isinstance(async_mode, bool) or not isinstance(stream, bool):
        raise TypeError("async_mode e stream devem ser booleanos.")
    if async_mode and stream:
        raise ValueError("async_mode e stream não podem ser verdadeiros simultaneamente.")
    body: dict[str, Any] = {
        "async_mode": async_mode,
        "stream": stream,
        "model": model,
        "response_format": config.get("message_format", {"type": "text"}),
        "messages": messages,
        "openai_api_version": config.get("openai_api_version", "2024-02-01"),
    }
    if "temperature" in config:
        temperature = config["temperature"]
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ValueError("temperature deve ser numérico.")
        body["temperature"] = temperature
    if "max_tokens" in config:
        limit = config["max_tokens"]
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("max_tokens deve ser inteiro positivo.")
        body["max_tokens"] = limit
    url = _service_url("text", config.get("ambiente"))
    if stream:
        return _stream_call("text.generate.stream", url, body, config)
    result = _call("text.generate", "POST", url, payload=body, parameters=config)
    if async_mode:
        execution_id = _require_text(
            result.get("workflow_execution_id"), "workflow_execution_id"
        )
        return _extract_workflow_text(
            wait_for_workflow(execution_id, config)
        )
    return _extract_output_text(result)


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


__all__ = [
    "BridgeAPIError", "get_urls", "get_token_iagen", "renew_token",
    "text_generator", "embedding_generator", "ocr_generator", "get_text_ocr",
    "retriever_search", "retriever_next_questions", "file_manager_list_files",
    "file_manager_upload", "file_manager_upload_base64",
    "file_manager_get_download_url", "file_manager_delete", "workflow_execute",
    "index_documents", "workflow_status", "wait_for_workflow", "agent_message",
    "orchestrator_message",
]
