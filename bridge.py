"""Transcrição do código visível nas fotografias fornecidas.

As imagens cobrem aproximadamente as linhas 104 a 464 do arquivo original.
As linhas 1 a 103 e o início de ``get_token_iagen`` não aparecem nas fotos.
Os imports e a assinatura dessa função foram acrescentados somente para manter
o trecho transcrito organizado como um arquivo Python.
"""

import json
import requests
import os
import threading
import base64
import time
import numpy as np
from numpy import ndarray
from json.decoder import JSONDecodeError
from pathlib import Path


path_proj = Path(__file__)
secrets_file = os.path.join(path_proj, ".env")

identificador = ""
senha = ""

def get_urls(ambiente):
    """
    Função que seleciona os links de acordo com o ambiente.

    Parâmetros:
        ambiente: str
            Ambiente a ser utilizado. Pode ser "dev", "homol" ou "prod".

    Retorna:
        url_generate: str
            link para geração de texto.
        url_embeddings: str
            link para geração de embeddings.
        url_filemanager: str
            link para gerenciamento de arquivos.
    """
    if ambiente == "dev":
        url_generate = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-textgenerator/v1/text/generate"
        url_embeddings = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-embedding/v1/embedding"
        url_filemanager = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-filemanager/v1/files"
        url_token = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-identity/v1/usuarios/login-servico"
        url_ocr = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-ocr/v1/ocr"
        url_wkf = "https://api-leap-platse.apps.arodvplatsepi11.arocorpp.bradesco.com.br"\
            "/iagen-workflow-response/v1/response/workflow-execution-status/"

    elif ambiente == "homol":
        url_generate = "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-textgenerator/v1/text/generate"
        url_embeddings = "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-embedding/v1/embedding"
        url_filemanager = "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-filemanager/v1/files"
        url_token = "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-identity/v1/usuarios/login-servico"
        url_ocr = "https://api-platfu.apps.arohoplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-ocr/v1"
        url_wkf = "None"
        
    elif ambiente == "prod":
        url_generate = "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-textgenerator/v1/text/generate"
        url_embeddings = "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-embedding/v1/embedding"
        url_filemanager = "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-filemanager/v1/files"
        url_token = "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-identity/v1/usuarios/login-servico"
        url_ocr = "https://api-platfu.apps.aroprplatfupi.arocorpp.bradesco.com.br"\
            "/iagen-ocr/v1"
        url_wkf = "None"
    else:
        raise ValueError("Ambiente não encontrado")
    return url_generate, url_embeddings, url_filemanager, url_token, url_ocr, url_wkf


url_generate, url_embeddings, url_filemanager, url_token, url_ocr, url_wkf = get_urls("dev")
 

def get_token_iagen():
    """
    Obtém o token para o serviço de IAGEN.
    Retorna:
        token: str
            Token de autorização para acessar os serviços da IAGEN.
    """
    url = url_token
    payload = json.dumps({"identificador": identificador, "senha": senha})
    
    headers = {
        "Content-Type": "application/json",
    }

    response = requests.request(
        "POST", url, headers=headers, data=payload, verify=False
    )
    try:
        token = json.loads(response.text)["token"]
    except KeyError:
        token = response.text
        raise Exception(f"Error in the response: {response.text}")

    os.environ["BRADESCO_AUTHORIZATION_TOKEN"] = token

    return token


# Função para renovar o token a cada 20 minutos
def renew_token():
    while True:
        get_token_iagen()
        time.sleep(1200)  # 20 minutos = 1200 segundos


# Iniciar a thread que renova o token
token_thread = threading.Thread(target=renew_token)
token_thread.daemon = True
token_thread.start()

get_token_iagen()


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


## Leitura PDF - OCR


def file_manager_list_files(container_name: str):
    """Lista os arquivos de um container

    Parâmetros:
        # token: str
            # Token de autorização.
        # url_filemanager: str
            # URL do filemanager.
        container_name: str
            Nome do container.
    Retorna:
        response_json: dict
            Retorna um dicionário com a lista de arquivos.
    """
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]

    url_list = (
        url_filemanager
        + f"?container_name={container_name}&page=0&page_size=50000"
    )
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {}

    response = requests.request(
        "GET", url_list, headers=headers, data=payload, verify=False
    )
    response_json = json.loads(response.text)
    return response_json


def file_manager_upload(
    path_file: str,
    file_name: str,
    container_name: str,
    create_container="false",
    overwrite="true",
):
    """Faz o upload de um arquivo para o filemanager

    Parâmetros:
        path_file: str
            Caminho do arquivo a ser enviado.
        file_name: str
            Nome do arquivo.
        token: str
            Token de autorização.
        container_name: str
            Nome do container.
        url_filemanager: str
            URL do filemanager.
        create_container: str
            Se o container não existir, cria um novo.
        overwrite: str
            Se o arquivo já existir, sobrescreve.

    Retorna:
        response.status_code: int
            Retorna o código de status da requisição.
    """
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]

    url_upload = url_filemanager + "/upload"
    file_extention = path_file.split(".")[-1]
    print(f"Enviando arquivo {file_name} para o container {container_name}")
    payload = {
        "container_name": container_name,
        "create_container": create_container,
        "overwrite": overwrite,
    }

    with open(path_file, "rb") as file_input:
        files = [
            (
                "file",
                (
                    file_name.replace(".PDF", ".pdf"),
                    file_input,
                    f"application/{file_extention}",
                ),
            )
        ]

        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

        response = requests.request(
            "POST",
            url_upload,
            headers=headers,
            data=payload,
            files=files,
            verify=False,
        )
        if response.status_code == 500 or response.status_code == 502:
            print(f"Erro ao enviar arquivo {file_name} - {response.text}")
        return response.status_code


def file_manager_delete(file_id: str):
    """Deleta um arquivo do filemanager

    Parâmetros:
        file_id: str
            ID do arquivo a ser deletado.

    Retorna:
        str
            Retorna uma string com a mensagem de sucesso ou erro.
    """
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]

    url = url_filemanager + f"/{file_id}"
    payload = {}
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.request(
        "DELETE", url, headers=headers, data=payload, verify=False
    )
    resp = response.status_code
    print(resp)
    if resp == 200:
        return f"{resp} Arquivo deletado com sucesso"
    elif resp == 204:
        return f"{resp} Arquivo não encontrado"
    else:
        return f"Status code: {resp}"


## Teste


def file_manager_upload(
    path_file: str,
    file_name: str,
    container_name: str,
    create_container="false",
    overwrite="true",
):
    """
    Faz o upload de um arquivo para o filemanager com correção da extensão e log.
    """
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    url_upload = url_filemanager + "/upload"

    _, ext = os.path.splitext(path_file)
    ext = ext.lower()
    if not file_name.lower().endswith(ext):
        new_file_name = file_name + ext
    else:
        new_file_name = file_name

    print(f"[INFO] Nome original: {file_name} | Nome convertido: {new_file_name}")

    file_extension = ext.replace(".", "")
    print(
        f"[INFO] Enviando arquivo '{new_file_name}' para o container "
        f"'{container_name}'"
    )

    payload = {
        "container_name": container_name,
        "create_container": create_container,
        "overwrite": overwrite,
    }

    try:
        with open(path_file, "rb") as file_input:
            files = [
                (
                    "file",
                    (
                        new_file_name,
                        file_input,
                        f"application/{file_extension}",
                    ),
                )
            ]

            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {token}",
            }

            response = requests.post(
                url_upload,
                headers=headers,
                data=payload,
                files=files,
                verify=False,
            )

            if response.status_code == 200:
                print(f"[INFO] Upload concluído com sucesso: {new_file_name}")
            else:
                print(
                    f"[ERRO] Falha no upload ({response.status_code}): "
                    f"{response.text}"
                )

            return response.status_code

    except Exception as e:
        print(f"[ERRO] Exceção durante upload: {e}")
        return None


def get_text_ocr(files_path, container, input_text):
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    url_base = (
        "https://api-platfu.apps.aroprplatfupi.arocorp.bradesco.com.br/"
        "iagen-ocr/v1"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {
        "files_path": files_path,
        "container": container,
        "input_text": input_text,
    }

    try:
        response = requests.post(
            f"{url_base}/ocr", headers=headers, json=payload, verify=False
        )
        response.raise_for_status()
        response_payload = response.json()
        return response_payload

    except requests.exceptions.RequestException as e:
        print(f"Erro na requisição: {e}")
        return None



# exemplo de como chamar a função text_generator
# llm_parameters = {
#     "deployment_name": "iagen-llm-7b",
#     "temperature": 0,
#     "max_tokens": 16384,
#     "async_mode": False,
#     "stream": False,
#     "message_format": {"type": "json_object"},
# }

# llm_output = text_generator(payload, llm_parameters)


# === INICIO DAS APIS ADICIONAIS; AUTENTICACAO ORIGINAL PRESERVADA ===
# Funções adicionais incluídas no arquivo único gpt_bridge.py.
# Não altera get_token_iagen, renew_token ou text_generator.
# Nunca copie tokens, identificadores ou senhas para este arquivo.

import os
import requests
import base64
from pathlib import Path

from copy import deepcopy as _api_deepcopy
from urllib.parse import quote as _api_quote, urlsplit as _api_urlsplit
import binascii as _api_binascii
import mimetypes as _api_mimetypes


class IagenAPIError(RuntimeError):
    """Erro de API sem revelar token, corpo de resposta ou dados judiciais."""

    def __init__(self, message, status_code=None, request_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


def _api_parameters(parameters):
    """Valida apenas parâmetros da API, sem interferir na autenticação legada."""
    if not isinstance(parameters, dict):
        raise TypeError('parameters deve ser um dicionário.')
    timeout = parameters.get('timeout', 600)
    if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or timeout <= 0:
        raise ValueError('timeout deve ser um número positivo.')
    return parameters


def _api_required_text(value, name):
    """Impede requisições com identificadores/documentos não preenchidos."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} deve ser uma string não vazia.')
    return value.strip()


def _api_body(payload):
    """Recebe JSON já estruturado no formato do endpoint documentado."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError('payload deve ser um dicionário JSON não vazio.')
    return dict(payload)


def _api_root_url():
    """Reutiliza o host do ambiente definido no get_urls ORIGINAL."""
    parsed = _api_urlsplit(url_generate)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('url_generate original não contém um host HTTPS válido.')
    return f'{parsed.scheme}://{parsed.netloc}'


def _api_endpoint(parameters, path=None, original_url=None):
    """Permite corrigir só endpoint_url caso a rota varie na plataforma."""
    custom = parameters.get('endpoint_url')
    if custom is not None and custom != '':
        endpoint = _api_required_text(custom, 'endpoint_url')
    elif original_url is not None:
        endpoint = original_url
    elif path:
        endpoint = _api_root_url() + path
    else:
        raise ValueError('Preencha parameters["endpoint_url"] conforme a documentação.')
    parsed = _api_urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('endpoint_url deve ser HTTPS, absoluta e sem credenciais.')
    return endpoint


def _api_http(method, endpoint, parameters, *, body=None, query=None, data=None, files=None):
    """Utiliza o Bearer JÁ emitido pelo login original, sem renovar ou trocar token."""
    config = _api_parameters(parameters)
    token = os.environ['BRADESCO_AUTHORIZATION_TOKEN']
    headers = {'Authorization': f'Bearer {token}', 'accept': 'application/json'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    # Mantém verify=False do padrão original para não mudar a conexão existente.
    # A validação TLS deve ser tratada separadamente com a equipe de segurança.
    try:
        response = requests.request(
            method, endpoint, headers=headers, json=body, params=query,
            data=data, files=files, timeout=config.get('timeout', 600),
            verify=False,
        )
    except requests.exceptions.RequestException as exc:
        raise IagenAPIError(f'Falha de conexão ao chamar a API ({method}).') from exc
    request_id = response.headers.get('x-request-id') or response.headers.get('x-correlation-id')
    if not 200 <= response.status_code < 300:
        hint = ''
        if response.status_code == 401:
            hint = ' Confirme validade do token original e correspondência do ambiente.'
        elif response.status_code == 403:
            hint = ' Confirme autorização do serviço para esta API.'
        elif response.status_code in (400, 422):
            hint = ' Confira os campos e os tipos do payload na documentação.'
        raise IagenAPIError(
            f'API retornou HTTP {response.status_code}; request_id={request_id or "não informado"}.' + hint,
            status_code=response.status_code, request_id=request_id,
        )
    # JSON de outras APIs não deve ser reduzido a output_text do text_generator.
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise IagenAPIError('A API retornou uma resposta que não é JSON válido.') from exc


def embedding_generator(payload, embedding_parameter: dict):
    """POST /iagen-embedding/v1/embedding; aceita texto e parâmetros do modelo."""
    config = _api_parameters(embedding_parameter)
    body = {
        'input': _api_required_text(payload, 'payload'),
        'model': _api_required_text(config.get('deployment_name'), 'deployment_name'),
    }
    if config.get('dimensions') is not None:
        dimensions = config['dimensions']
        if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
            raise ValueError('dimensions deve ser inteiro positivo.')
        body['dimensions'] = dimensions
    result = _api_http('POST', _api_endpoint(config, original_url=url_embeddings), config, body=body)
    if not isinstance(result, dict) or 'response' not in result:
        raise IagenAPIError('Embedding sem campo response no retorno; valide o contrato da API.')
    return result['response']


def ocr_generator(payload, ocr_parameter: dict):
    """POST OCR; aceita files_path/files_id e os demais campos documentados."""
    config = _api_parameters(ocr_parameter)
    body = _api_body(payload)
    if not body.get('files_path') and not body.get('files_id'):
        raise ValueError('Informe files_path ou files_id no payload OCR.')
    for name in ('files_path', 'files_id'):
        if name in body and (not isinstance(body[name], list) or not body[name]
                             or any(not isinstance(item, str) or not item.strip() for item in body[name])):
            raise ValueError(f'{name} deve ser uma lista de identificadores não vazios.')
    return _api_http('POST', _api_endpoint(config, original_url=url_ocr), config, body=body)


def retriever_search(payload, retriever_parameter: dict):
    """POST /iagen-retriever/v1/indices/documentos; mantém scores e chunks."""
    config = _api_parameters(retriever_parameter)
    body = _api_body(payload)
    for name in ('index_name', 'search_query'):
        _api_required_text(body.get(name), name)
    url = _api_endpoint(config, path='/iagen-retriever/v1/indices/documentos')
    return _api_http('POST', url, config, body=body)


def retriever_next_questions(payload, retriever_parameter: dict):
    """POST /iagen-retriever/v1/indices/proximas-perguntas."""
    config = _api_parameters(retriever_parameter)
    body = _api_body(payload)
    for name in ('next_question_config', 'search_query'):
        _api_required_text(body.get(name), name)
    url = _api_endpoint(config, path='/iagen-retriever/v1/indices/proximas-perguntas')
    return _api_http('POST', url, config, body=body)


def file_manager_list(payload, file_parameter: dict):
    """GET arquivos com query parameters, sem substituir file_manager_list_files."""
    config = _api_parameters(file_parameter)
    body = _api_body(payload)
    container = _api_required_text(body.get('container_name'), 'container_name')
    page, page_size = body.get('page', 0), body.get('page_size', 50000)
    if isinstance(page, bool) or not isinstance(page, int) or page < 0:
        raise ValueError('page deve ser inteiro maior ou igual a zero.')
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
        raise ValueError('page_size deve ser inteiro positivo.')
    query = {'container_name': container, 'page': page, 'page_size': page_size}
    return _api_http('GET', _api_endpoint(config, original_url=url_filemanager), config, query=query)


def file_manager_upload_file(payload, file_parameter: dict):
    """POST multipart/form-data; mantém a função file_manager_upload original."""
    config = _api_parameters(file_parameter)
    body = _api_body(payload)
    path = Path(_api_required_text(body.get('path_file'), 'path_file'))
    if not path.is_file():
        raise FileNotFoundError('path_file deve apontar para arquivo existente.')
    filename = _api_required_text(body.get('file_name'), 'file_name')
    if Path(filename).name != filename or filename in ('.', '..'):
        raise ValueError('file_name deve conter somente o nome do arquivo.')
    if path.suffix and not filename.lower().endswith(path.suffix.lower()):
        filename += path.suffix.lower()
    data = {'container_name': _api_required_text(body.get('container_name'), 'container_name')}
    for key, default in (('create_container', 'false'), ('overwrite', 'true')):
        value = body.get(key, default)
        if isinstance(value, bool):
            value = str(value).lower()
        if value not in ('true', 'false'):
            raise ValueError(f'{key} deve ser true ou false.')
        data[key] = value
    mimetype = _api_mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    with path.open('rb') as file_stream:
        return _api_http(
            'POST', _api_endpoint(config, original_url=url_filemanager).rstrip('/') + '/upload',
            config, data=data, files={'file': (filename, file_stream, mimetype)},
        )


def file_manager_upload_base64(payload, file_parameter: dict):
    """POST /files/upload/base64; sem imprimir nem persistir conteúdo base64."""
    config = _api_parameters(file_parameter)
    body = _api_body(payload)
    for name in ('base64', 'file_name', 'container_name'):
        _api_required_text(body.get(name), name)
    try:
        base64.b64decode(body['base64'], validate=True)
    except (_api_binascii.Error, ValueError) as exc:
        raise ValueError('base64 não contém dados válidos.') from exc
    for name in ('create_container', 'overwrite'):
        if name in body and not isinstance(body[name], bool):
            raise TypeError(f'{name} deve ser booleano.')
    endpoint = _api_endpoint(config, original_url=url_filemanager).rstrip('/') + '/upload/base64'
    return _api_http('POST', endpoint, config, body=body)


def file_manager_download_url(payload, file_parameter: dict):
    """GET /files/{id}/filedownload; não registrar URL assinada em logs."""
    config = _api_parameters(file_parameter)
    body = _api_body(payload)
    file_id = _api_required_text(body.get('file_id'), 'file_id')
    endpoint = (_api_endpoint(config, original_url=url_filemanager).rstrip('/') + '/'
                + _api_quote(file_id, safe='') + '/filedownload')
    return _api_http('GET', endpoint, config)


def file_manager_delete_file(payload, file_parameter: dict):
    """DELETE /files/{id}; wrapper adicional, não altera file_manager_delete."""
    config = _api_parameters(file_parameter)
    body = _api_body(payload)
    file_id = _api_required_text(body.get('file_id'), 'file_id')
    endpoint = (_api_endpoint(config, original_url=url_filemanager).rstrip('/') + '/'
                + _api_quote(file_id, safe=''))
    return _api_http('DELETE', endpoint, config)


def workflow_execute(payload, workflow_parameter: dict):
    """POST workflow com input_collection do workflow realmente cadastrado."""
    config = _api_parameters(workflow_parameter)
    body = _api_body(payload)
    _api_required_text(body.get('workflow_configuration_code'), 'workflow_configuration_code')
    if not isinstance(body.get('input_collection'), dict):
        raise TypeError('input_collection deve ser um dicionário.')
    endpoint = _api_endpoint(config, path='/iagen-workflow-request/v1/request/start-workflow')
    return _api_http('POST', endpoint, config, body=body)


def index_documents(payload, index_parameter: dict):
    """Dispara o workflow de indexação configurado no payload recebido."""
    return workflow_execute(payload, index_parameter)


def workflow_get_status(payload, workflow_parameter: dict):
    """GET status pelo ID da execução; utiliza url_wkf definido originalmente."""
    config = _api_parameters(workflow_parameter)
    body = _api_body(payload)
    execution_id = _api_required_text(body.get('workflow_execution_id'), 'workflow_execution_id')
    endpoint = _api_endpoint(config, original_url=url_wkf)
    if endpoint == 'None':
        raise ValueError('Preencha endpoint_url da API workflow em homol/prod.')
    return _api_http('GET', endpoint.rstrip('/') + '/' + _api_quote(execution_id, safe=''), config)


def agent_message(payload, agent_parameter: dict):
    """POST agente: URL integral e JSON dependem do agente autorizado."""
    config = _api_parameters(agent_parameter)
    body = _api_body(payload)
    return _api_http('POST', _api_endpoint(config), config, body=body)


def orchestrator_message(payload, orchestrator_parameter: dict):
    """POST orquestrador: URL integral e JSON dependem do fluxo autorizado."""
    config = _api_parameters(orchestrator_parameter)
    body = _api_body(payload)
    return _api_http('POST', _api_endpoint(config), config, body=body)


# Modelos sintéticos prontos para preencher. NÃO incluem credenciais nem tokens.
# Campos vazios representam valores não confirmados na documentação/ambiente.
# URL de agentes e orquestradores exigida explicitamente, sem inventar rotas.
API_CONFIGS = {
    'texto': {
        'payload': 'Pergunta sintética, sem dados pessoais.',
        'parameters': {
            'deployment_name': '', 'temperature': 0, 'max_tokens': 16384,
            'async_mode': False, 'stream': False,
            'message_format': {'type': 'text'},
            'openai_api_version': '2024-02-01',
        },
    },
    'embeddings': {
        'payload': 'Texto sintético para vetorização.',
        'parameters': {'deployment_name': '', 'dimensions': None, 'timeout': 600},
    },
    'ocr': {
        'payload': {'files_path': [''], 'container': '', 'input_text': 'Extraia o texto do documento.'},
        'parameters': {'timeout': 600},
    },
    'retriever_documentos': {
        'payload': {'index_name': '', 'search_query': 'Pergunta fictícia.'},
        'parameters': {'timeout': 600},
    },
    'retriever_proximas_perguntas': {
        'payload': {'next_question_config': '', 'search_query': 'Pergunta fictícia.'},
        'parameters': {'timeout': 600},
    },
    'arquivo_listar': {
        'payload': {'container_name': '', 'page': 0, 'page_size': 50000},
        'parameters': {'timeout': 600},
    },
    'arquivo_enviar': {
        'payload': {'path_file': '', 'file_name': '', 'container_name': '',
                    'create_container': 'false', 'overwrite': 'true'},
        'parameters': {'timeout': 600},
    },
    'arquivo_base64': {
        'payload': {'base64': '', 'file_name': '', 'container_name': '',
                    'create_container': False, 'overwrite': True},
        'parameters': {'timeout': 600},
    },
    'arquivo_download_url': {'payload': {'file_id': ''}, 'parameters': {'timeout': 600}},
    'arquivo_excluir': {'payload': {'file_id': ''}, 'parameters': {'timeout': 600}},
    'workflow_inicio': {
        'payload': {
            'workflow_configuration_code': '',
            'input_collection': {'input_datas': [
                {'workflow_step_number': 0,
                 'workflow_step_input_collection': [
                     {'full_path': '', 'detail_value': '', 'is_valid': True},
                 ]},
            ]},
        },
        'parameters': {'timeout': 600},
    },
    'workflow_status': {
        'payload': {'workflow_execution_id': ''},
        'parameters': {'timeout': 600},
    },
    'agente': {
        'payload': {'messages': [{'role': 'user', 'content': 'Pergunta fictícia.'}]},
        'parameters': {'endpoint_url': '', 'timeout': 600},
    },
    'orquestrador': {
        'payload': {'messages': [{'role': 'user', 'content': 'Pergunta fictícia.'}]},
        'parameters': {'endpoint_url': '', 'timeout': 600},
    },
}


def get_api_config(api_name: str):
    """Entrega uma cópia independente do exemplo, pronta para preencher."""
    if api_name not in API_CONFIGS:
        raise ValueError(f'API desconhecida: {api_name}. Opções: {", ".join(API_CONFIGS)}')
    return _api_deepcopy(API_CONFIGS[api_name])
