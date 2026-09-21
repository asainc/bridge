# gpt_bradesco.py — versão revisada

## O que foi mantido e o que foi corrigido

O corpo de `text_generator(payload, llm_parameter)` foi **copiado integralmente, sem alterar seu código**, do arquivo anexado `gpt_bradesco(7).py`. Um teste compara a árvore sintática das duas funções. Seu comportamento original continua sendo: texto (`str`) ou lista de mensagens, retorno `response.output_text` no modo síncrono, consulta ao workflow no modo assíncrono e leitura de JSON Lines no streaming. Os `print` e o `verify=False` **continuam no legado** porque a solicitação foi de preservação literal. Atenção: `verify=False` desativa a validação TLS; a equipe de segurança deve aprovar uma alteração futura no legado antes de operar com dados sensíveis. Não use seus erros brutos como logs de produção, pois o legado imprime `response.text`.

O arquivo anexado é uma **transcrição de fotografias**, conforme declarado em seu próprio cabeçalho, e não necessariamente todo o código-fonte original. Nessa transcrição, `get_urls` não tinha `return`, embora o módulo tente desempacotar seis URLs, e `identificador` e `senha` estão vazios. Corrigimos a função `get_urls`, inicializamos as seis URLs globais para o gerador legado e criamos autenticação explícita e compatível. Nenhum login automático, thread ou chamada de rede ocorre no `import`.

As **novas APIs** usam `verify=True` ou CA corporativa (`BRADESCO_CA_BUNDLE`), timeout, validação de argumentos, identificação da operação e erros com status HTTP e ID de rastreio quando presentes. O transporte não inclui tokens, payloads, textos, PDFs ou URL assinada nos logs. Não há repetição automática de POST.

## Início rápido — primeiro diagnostique, depois autentique

Instale `requests` na versão aprovada pelo banco (`requirements_gpt_bradesco.txt` contém `requests==2.32.5`, versão local de teste). Não é necessário ambiente virtual. Mantenha todos os arquivos na mesma pasta, em especial `gpt_bradesco.py` e `exemplo_uso_gpt_bradesco.py`.

**1. Teste offline, sem credenciais:**

```bash
python exemplo_uso_gpt_bradesco.py
python -m unittest -v test_gpt_bradesco.py
```

O primeiro comando está configurado com `EXECUTAR_REQUISICAO = False`; ele informa somente presença/ausência de credenciais e o ambiente escolhido. Os testes simulam respostas e não se conectam à rede interna.

**2. Configure credenciais com o gerenciador de segredos corporativo.** Sem incluir valores reais em scripts versionados, disponibilize as variáveis `BRADESCO_IDENTIFICADOR`, `BRADESCO_SENHA` e `BRADESCO_AMBIENTE` (dev, homol ou prod). Se a equipe fornecer um token já emitido, use `BRADESCO_AUTHORIZATION_TOKEN` no lugar do identificador/senha. Para certificados internos confiáveis, informe `BRADESCO_CA_BUNDLE` com o caminho de uma CA corporativa válida. Não publique tokens, senhas, cookies, requisições reais nem headers completos. O `.env` do módulo anexado não era carregado automaticamente, e apontava para um caminho formado a partir do arquivo `.py`; o novo módulo lê **variáveis de ambiente já configuradas**, mas não importa `.env`.

O mesmo fluxo sem ler um arquivo `.env` pode ser usado diretamente:

```python
import os
from gpt_bradesco import AUTH_PARAMETERS, configure_iagen, get_token_iagen, auth_diagnostics

auth = {
    **AUTH_PARAMETERS,
    "ambiente": os.getenv("BRADESCO_AMBIENTE", "dev"),
    "identificador": os.getenv("BRADESCO_IDENTIFICADOR", ""),
    "senha": os.getenv("BRADESCO_SENHA", ""),
    "token": os.getenv("BRADESCO_AUTHORIZATION_TOKEN", ""),
    "ca_bundle": os.getenv("BRADESCO_CA_BUNDLE", ""),
}

print(auth_diagnostics())  # Só metadados; opcional.
configure_iagen(auth)
get_token_iagen(force_refresh=not bool(auth["token"]))
```

`get_token_iagen()` procura primeiro token fornecido; sem token, faz **POST de login** com `{"identificador": ..., "senha": ...}` para `/iagen-identity/v1/usuarios/login-servico` no ambiente selecionado, lê `token` na raiz do JSON retornado e disponibiliza esse token ao `text_generator` original via `BRADESCO_AUTHORIZATION_TOKEN`. A existência de um token **não garante** que esteja válido ou tenha autorização para outra API. O login deve ser executado antes do `text_generator` legado; nas funções novas a autenticação é sob demanda.

**3. Execute uma API:** no arquivo `exemplo_uso_gpt_bradesco.py`, altere `API = "texto"` para a API desejada; preencha `CONFIG["payload"]` e `CONFIG["parameters"]` conforme a documentação interna e altere `EXECUTAR_REQUISICAO = True`. O script valida campos obrigatórios dos exemplos e só imprime tipo do resultado, não seu conteúdo. A exclusão de arquivos é intencionalmente bloqueada no script de demonstração.

## Dicionários de parâmetros prontos para copiar

No `gpt_bradesco.py`, `AUTH_PARAMETERS` contém as chaves de autenticação e `API_CONFIGS` reúne os exemplos completos de **payload + parameters**. Use `get_api_config("nome")` para receber uma cópia independente. Campos `""` são **valores a preencher**, não nomes reais de modelos/índices/agentes/arquivos. `ambiente` precisa apontar para **o mesmo ambiente usado na autenticação**. Todos os exemplos textuais são sintéticos.

```python
from gpt_bradesco import get_api_config, embedding_generator

config = get_api_config("embeddings")
config["parameters"]["deployment_name"] = "MODELO_EMBEDDING_HABILITADO"
config["parameters"]["ambiente"] = "dev"
config["payload"] = "Texto sintético para teste"

# Após configure_iagen(auth) e get_token_iagen() com credenciais válidas:
vector = embedding_generator(config["payload"], config["parameters"])
```

O nome de implantação de embedding **não aparece confirmado de modo suficientemente legível nos materiais** e deve ser substituído pelo identificador habilitado no ambiente. `dimensions` é opcional e só deve ser incluído se o modelo escolhido permitir essa opção.

| Chave em `get_api_config` | Função `(payload, parameters)` | Campos do payload / ajustes obrigatórios |
|---|---|---|
| `texto` | `text_generator` | Payload string ou mensagens; `parameters.deployment_name`, `temperature`, `max_tokens`, `async_mode`, `stream`, `message_format`, `openai_api_version`. O modelo `iagen-llm-7b` aparece como **exemplo no código original**, sem validação de disponibilidade. |
| `embeddings` | `embedding_generator` | `payload`: texto; `parameters.deployment_name` obrigatório; `dimensions` opcional. Corpo HTTP: `input`, `model` e, se indicado, `dimensions`. |
| `ocr` | `ocr_generator` | `files_path`: lista de nomes/caminhos; `container`: container habilitado; `input_text`: instrução. O vídeo menciona variantes `files_id`, modo assíncrono e streaming; só adicione esses campos se exigidos para o seu fluxo. |
| `retriever_documentos` | `retriever_search` | `index_name`, `search_query`; outros filtros apenas conforme documentação do índice. |
| `retriever_proximas_perguntas` | `retriever_next_questions` | `next_question_config`, `search_query` (confirmar configuração cadastrada). |
| `arquivo_listar` | `file_manager_list` | `container_name`, `page` = 0, `page_size` = 50000; requisição GET com **query params**, não corpo JSON. |
| `arquivo_enviar` | `file_manager_upload_file` | `path_file` local, `file_name`, `container_name`, `create_container` e `overwrite`; **multipart/form-data**. |
| `arquivo_base64` | `file_manager_upload_base64` | `base64`, `file_name`, `container_name`, flags booleanas; **JSON**. |
| `arquivo_download_url` | `file_manager_download_url` | `file_id`; retorna URL temporária; trate-a como credencial. |
| `arquivo_excluir` | `file_manager_delete_file` | `file_id`; ação destrutiva; obter autorização para executar. |
| `indexar` | `index_documents` | `workflow_configuration_code` e `input_collection.input_datas[].workflow_step_input_collection[]`; preencha `full_path`, `detail_value`, `is_valid` de acordo com o código de workflow cadastrado. O exemplo é um **esqueleto**; a combinação exata de campos depende do workflow. |
| `workflow_status` | `workflow_get_status` | `workflow_execution_id` retornado na iniciação; GET de status, sem criar execução. |
| `agente` | `agent_message` | Corpo JSON do agente cadastrado e `parameters.endpoint_url` HTTPS integral. Exemplo de `messages` é ilustrativo: o contrato completo **não ficou confirmado nas gravações**. |
| `orquestrador` | `orchestrator_message` | Corpo JSON do orquestrador cadastrado e `parameters.endpoint_url` HTTPS integral. Exemplo de `messages` é ilustrativo: o contrato completo **não ficou confirmado nas gravações**. |

Os métodos existentes `file_manager_list_files`, `file_manager_upload`, `file_manager_delete`, `get_text_ocr`, `workflow_execute`, `workflow_status` e `wait_for_workflow` também continuam disponíveis. Os novos wrappers para arquivos/status adicionam o padrão `(payload, parameters)` sem eliminar as interfaces anteriores.

### Exemplo de OCR

```python
from gpt_bradesco import get_api_config, ocr_generator

config = get_api_config("ocr")
config["payload"]["files_path"] = ["arquivo_ficticio.pdf"]
config["payload"]["container"] = "CONTAINER_AUTORIZADO"
config["payload"]["input_text"] = "Extraia o texto do documento."
config["parameters"]["ambiente"] = "dev"
# result = ocr_generator(config["payload"], config["parameters"])
```

### Exemplo de workflow de indexação

```python
from gpt_bradesco import get_api_config, index_documents, workflow_get_status

config = get_api_config("indexar")
config["payload"]["workflow_configuration_code"] = "CODIGO_WORKFLOW_CADASTRADO"
step = config["payload"]["input_collection"]["input_datas"][0]
step["workflow_step_input_collection"][0]["full_path"] = "CAMPO_EXATO_DO_WORKFLOW"
step["workflow_step_input_collection"][0]["detail_value"] = "ID_FICTICIO_DO_ARQUIVO"
# result = index_documents(config["payload"], config["parameters"])
# status = workflow_get_status(
#     {"workflow_execution_id": result["workflow_execution_id"]},
#     config["parameters"],
# )
```

**Atenção:** `input_collection` varia conforme o workflow aprovado. Nos vídeos há exemplo de `workflow_step_number`, `workflow_step_input_collection`, `full_path`, `detail_value` e `is_valid`, mas não é correto inventar código, ID, índice ou campo lógico. Antes de executar, preencha os valores reais da documentação autorizada.

## Tratamento de autenticação — como localizar a falha

| Evidência observada | O que conferir |
|---|---|
| `Faltam credenciais` antes de qualquer requisição | Não há token nem `identificador` + `senha` configurados. Use `configure_iagen(auth)` com valores obtidos do cofre corporativo. |
| HTTP 401 no login (`identity.login`) | Identificador/senha, ambiente selecionado, validade do serviço e eventuais exigências da plataforma. Não é possível afirmar a causa exata sem o retorno sanitizado e verificação interna. |
| HTTP 401 em outra API, após login | Validade do token, ambiente da autenticação versus ambiente da API e esquema de autorização requerido pela API. Se você possui credenciais, `get_token_iagen(force_refresh=True)` permite uma nova emissão; reenvie a operação manualmente apenas se for seguro. |
| HTTP 403 em uma API | Confirme autorização/perfil do identificador para **aquele serviço e ambiente**. Ter token não assegura permissão para indexação, Retriever ou agente. |
| `SSLError` na API nova | Configure CA corporativa confiável via `BRADESCO_CA_BUNDLE`; não contorne usando `verify=False`. O erro é de TLS, não necessariamente de login. |
| HTTP 400/422 | Revise payload e esquema da operação; esses códigos por si só não demonstram falha na autenticação. |
| URL de agente/orquestrador ausente | Informe `endpoint_url` **completo** e confirme seu corpo no catálogo interno. |

Os erros das funções novas contêm `status_code` e `request_id` quando disponíveis. Compartilhe apenas operação, código HTTP, ID de rastreio e ambiente com o suporte; **nunca** token, senha, dados do processo ou corpo HTTP sem saneamento.

## Validação, limitações e decisões

**Validado localmente:** sintaxe do Python, equivalência estrutural do gerador legado e testes `unittest` offline com mocks (autenticação, rotas, payloads, limites e erros). **Não validado:** rede corporativa, credenciais reais, modelos disponíveis, autorização por API, contratos específicos de agentes/orquestrador e retorno real dos serviços. Testes locais não comprovam a integração com o banco.

- **2026-09-21, compatibilidade:** a implementação de `text_generator` foi restaurada literalmente, preservando inclusive restrições conhecidas: `verify=False`, logs de corpo de erro, dependência de `BRADESCO_AUTHORIZATION_TOKEN`, streaming JSON Lines e lógica original de `temperature`/`max_tokens`. Justificativa: requisito expresso de não alterar seu funcionamento. Responsável: adaptação técnica; revisão de segurança pendente.
- **2026-09-21, autenticação:** corrigido o `return` de URLs da transcrição e acrescentados `configure_iagen`, `auth_diagnostics` e disponibilização do token ao legado. Justificativa: possibilitar diagnosticar e configurar login sem exibir segredo. Responsável: adaptação técnica; homologação interna pendente.
- **2026-09-21, contratos adicionais:** `API_CONFIGS` oferece modelos editáveis para serviços documentados; campos não confirmados ficam vazios. Justificativa: evitar apresentar como fato parâmetros inventados. Responsável: adaptação técnica; confirmação com responsáveis pelas APIs pendente.
- **2026-09-21, segurança de novos clientes:** HTTPS com verificação TLS, erros sanitizados e sem retry implícito de POST. Responsável: adaptação técnica; revisão pela segurança corporativa pendente.

Não utilize arquivos judiciais de produção nos testes. A disponibilização do serviço e o tratamento desses documentos devem ser validados pelos times de Segurança, Jurídico, Compliance e DPO de acordo com as políticas internas aplicáveis.
