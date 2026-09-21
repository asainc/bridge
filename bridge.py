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


# === FUNÇÕES ADICIONAIS: CHAMADAS HTTP DIRETAS, COMO NOS EXEMPLOS cURL ===
# O código acima (inclusive autenticação e text_generator) foi preservado.
# As funções abaixo reutilizam o token que o código original já disponibiliza.
# verify=False replica a configuração legada; alinhe TLS com Segurança antes de produção.

from urllib.parse import quote


def _bridge_response(response):
    """Retorna o JSON completo; em falhas informa apenas status e ID de rastreio."""
    if not 200 <= response.status_code < 300:
        request_id = response.headers.get("x-request-id", "não informado")
        raise RuntimeError(
            f"API retornou HTTP {response.status_code}; request_id={request_id}. "
            "Confira autorização, ambiente e contrato da requisição."
        )
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def embedding(text_list, model="text-embedding-3-large", dimensions=None):
    """Gera embeddings para uma lista de textos; retorna o JSON completo da API."""
    if not isinstance(text_list, list) or not text_list or any(
        not isinstance(text, str) or not text.strip() for text in text_list
    ):
        raise ValueError("text_list deve ser uma lista não vazia de textos.")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model deve ser o nome do modelo habilitado.")

    url = url_embeddings
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    payload = {"input": text_list, "model": model}
    if dimensions is not None:
        if type(dimensions) is not int or dimensions <= 0:
            raise ValueError("dimensions deve ser um inteiro positivo.")
        payload["dimensions"] = dimensions
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def ocr(payload):
    """Envia o JSON do OCR sem renomear campos ou modificar o login original."""
    if not isinstance(payload, dict):
        raise TypeError("payload deve ser um dicionário JSON.")
    if not payload.get("files_path") or not payload.get("container"):
        raise ValueError("Informe files_path e container no payload de OCR.")

    url = url_ocr if url_ocr.endswith("/ocr") else f"{url_ocr.rstrip('/')}/ocr"
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def retriever_documentos(payload):
    """Consulta documentos no Retriever; os filtros opcionais vão no próprio payload."""
    if not isinstance(payload, dict) or not payload.get("index_name") or not payload.get("search_query"):
        raise ValueError("Informe index_name e search_query em um dicionário.")

    url = url_generate.split("/iagen-textgenerator/")[0] + "/iagen-retriever/v1/indices/documentos"
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def retriever_proximas_perguntas(payload):
    """Consulta próximas perguntas do Retriever usando o JSON documentado."""
    if not isinstance(payload, dict) or not payload.get("next_question_config") or not payload.get("search_query"):
        raise ValueError("Informe next_question_config e search_query em um dicionário.")

    url = url_generate.split("/iagen-textgenerator/")[0] + "/iagen-retriever/v1/indices/proximas-perguntas"
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def upload_base64(payload):
    """Envia o JSON de upload Base64; não registra o conteúdo do arquivo."""
    if not isinstance(payload, dict) or not all(
        payload.get(key) for key in ("base64", "file_name", "container_name")
    ):
        raise ValueError("Informe base64, file_name e container_name no payload.")

    url = url_filemanager.rstrip("/") + "/upload/base64"
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def download_arquivo(file_id):
    """Obtém o JSON/URL de download; não imprime URLs assinadas."""
    if not isinstance(file_id, str) or not file_id.strip():
        raise ValueError("file_id deve ser uma string não vazia.")

    url = url_filemanager.rstrip("/") + "/" + quote(file_id, safe="") + "/filedownload"
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def iniciar_workflow(payload, endpoint_url=None):
    """Inicia um workflow com o JSON e o código cadastrados na plataforma."""
    if not isinstance(payload, dict) or not payload.get("workflow_configuration_code"):
        raise ValueError("Informe workflow_configuration_code no payload JSON.")
    if not isinstance(payload.get("input_collection"), dict):
        raise ValueError("Informe input_collection conforme o workflow cadastrado.")

    url = endpoint_url or (
        url_generate.split("/iagen-textgenerator/")[0]
        + "/iagen-workflow-request/v1/request/start-workflow"
    )
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("endpoint_url deve ser uma URL HTTPS completa.")
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def indexar_documentos(payload, endpoint_url=None):
    """Usa o workflow de indexação cadastrado, sem supor uma API independente."""
    return iniciar_workflow(payload, endpoint_url=endpoint_url)


def status_workflow(workflow_execution_id, endpoint_url=None):
    """Consulta o status de uma execução; endereço específico pode ser informado."""
    if not isinstance(workflow_execution_id, str) or not workflow_execution_id.strip():
        raise ValueError("workflow_execution_id deve ser uma string não vazia.")

    url_base = endpoint_url or url_wkf
    if not isinstance(url_base, str) or not url_base.startswith("https://"):
        raise ValueError("Informe endpoint_url HTTPS para o status neste ambiente.")
    url = url_base.rstrip("/") + "/" + quote(workflow_execution_id, safe="")
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def agente(payload, endpoint_url):
    """Chama o endpoint HTTPS e JSON específicos do agente autorizado."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload deve conter o JSON documentado do agente.")
    if not isinstance(endpoint_url, str) or not endpoint_url.startswith("https://"):
        raise ValueError("Informe endpoint_url HTTPS do agente conforme documentação.")

    url = endpoint_url
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)


def orquestrador(payload, endpoint_url):
    """Chama o endpoint HTTPS e JSON específicos do orquestrador autorizado."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("payload deve conter o JSON documentado do orquestrador.")
    if not isinstance(endpoint_url, str) or not endpoint_url.startswith("https://"):
        raise ValueError("Informe endpoint_url HTTPS do orquestrador conforme documentação.")

    url = endpoint_url
    token = os.environ["BRADESCO_AUTHORIZATION_TOKEN"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(url, json=payload, headers=headers, verify=False, timeout=600)
    return _bridge_response(response)
