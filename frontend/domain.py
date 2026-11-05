import re
from decimal import Decimal


UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def moeda(valor):
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def indicadores(produtos, clientes):
    return {
        "clientes": len(clientes),
        "ativos": sum(bool(p["ativo"]) for p in produtos),
        "estoque": sum(p["estoque_atual"] for p in produtos),
        "valor": sum((Decimal(str(p["preco"])) * p["estoque_atual"] for p in produtos), Decimal("0")),
    }


def filtrar_produtos(produtos, busca, status):
    return [p for p in produtos if busca.casefold().strip() in p["nome"].casefold()
            and (status == "Todos" or p["ativo"] == (status == "Ativos"))]


def filtrar_clientes(clientes, busca, uf):
    busca = busca.strip().casefold()
    digitos = re.sub(r"\D", "", busca)
    return [c for c in clientes if (uf == "Todas" or c["uf"] == uf)
            and (busca in c["razao_social"].casefold() or busca in c["cnpj"]
                 or (bool(digitos) and digitos in c["cnpj"]))]


def validar_produto(dados):
    if not dados["nome"].strip():
        return "Informe o nome do produto."
    if dados["preco"] <= 0 or dados["peso_gramas"] <= 0:
        return "Preço e peso devem ser maiores que zero."
    if dados["estoque_atual"] < 0:
        return "O estoque não pode ser negativo."
    return None


def validar_cliente(dados):
    if not dados["razao_social"].strip() or not dados["cidade"].strip():
        return "Informe razão social e cidade."
    if not re.fullmatch(r"[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}", dados["cnpj"].strip()):
        return "Informe CNPJ com 14 dígitos ou pontuação padrão."
    if dados["uf"] not in UFS:
        return "Selecione uma UF válida."
    return None
