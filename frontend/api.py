import os

import requests


class ApiError(Exception):
    """Falha de comunicação ou resposta recusada pela API."""


class ApiClient:
    def __init__(self, base_url=None):
        self.base_url = (base_url or os.getenv("API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")

    def request(self, method, path, payload=None):
        try:
            response = requests.request(
                method, self.base_url + path, json=payload, timeout=(3.05, 15)
            )
        except requests.Timeout as error:
            raise ApiError("A API demorou para responder. Confira os dados antes de repetir uma gravação.") from error
        except requests.ConnectionError as error:
            raise ApiError("Não foi possível conectar à API. Verifique se o backend está iniciado.") from error
        except requests.RequestException as error:
            raise ApiError("Falha na comunicação com a API.") from error
        try:
            body = response.json()
        except ValueError as error:
            raise ApiError(f"A API retornou uma resposta inválida (HTTP {response.status_code}).") from error
        if not response.ok:
            detail = body.get("detail", "Operação recusada") if isinstance(body, dict) else "Operação recusada"
            if isinstance(detail, list):
                detail = "; ".join(
                    f"{'.'.join(str(v) for v in item.get('loc', []) if v != 'body')}: {item.get('msg', 'Valor inválido')}"
                    for item in detail
                )
            raise ApiError(f"HTTP {response.status_code}: {detail}")
        return body

    def listar(self, recurso):
        resultado = self.request("GET", f"/{recurso}/")
        if not isinstance(resultado, list):
            raise ApiError("A API retornou uma listagem inválida.")
        return resultado
