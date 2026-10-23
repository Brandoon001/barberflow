import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def limpar_texto(valor, limite=500):
    texto = (valor or "").strip()
    if len(texto) > limite:
        raise ValueError(f"O texto deve ter no máximo {limite} caracteres.")
    return texto


def normalizar_telefone(valor):
    """Aceita telefone brasileiro com 10 ou 11 dígitos e devolve só os dígitos."""
    digitos = re.sub(r"\D", "", valor or "")

    if digitos.startswith("55") and len(digitos) in {12, 13}:
        digitos = digitos[2:]

    if len(digitos) not in {10, 11}:
        raise ValueError("Informe um WhatsApp válido com DDD.")

    if digitos[0] == "0" or digitos[1] == "0":
        raise ValueError("Informe um DDD válido.")

    return digitos


def formatar_telefone(valor):
    digitos = re.sub(r"\D", "", valor or "")
    if digitos.startswith("55") and len(digitos) in {12, 13}:
        digitos = digitos[2:]

    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return valor or ""


def telefone_whatsapp(valor):
    digitos = re.sub(r"\D", "", valor or "")
    if digitos.startswith("55") and len(digitos) in {12, 13}:
        digitos = digitos[2:]
    if len(digitos) not in {10, 11}:
        return ""
    return f"55{digitos}"


def parse_preco_centavos(valor):
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("Informe o preço do serviço.")

    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        numero = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError("Preço inválido.") from erro

    if not numero.is_finite() or numero < 0:
        raise ValueError("O preço não pode ser negativo.")

    if numero.as_tuple().exponent < -2:
        raise ValueError("Use no máximo duas casas decimais no preço.")

    centavos = int((numero * 100).to_integral_value())
    if centavos > 100_000_000:
        raise ValueError("Preço acima do limite permitido.")
    return centavos


def formatar_preco_centavos(centavos):
    try:
        valor = Decimal(int(centavos or 0)) / 100
    except (TypeError, ValueError):
        valor = Decimal("0")
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_data(valor):
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d").date()
    except ValueError as erro:
        raise ValueError("Data inválida.") from erro


def parse_hora(valor):
    try:
        return datetime.strptime((valor or "").strip(), "%H:%M").time()
    except ValueError as erro:
        raise ValueError("Horário inválido.") from erro


def combinar_data_hora(data_valor, hora_valor):
    if isinstance(data_valor, str):
        data_valor = parse_data(data_valor)
    if isinstance(hora_valor, str):
        hora_valor = parse_hora(hora_valor)
    return datetime.combine(data_valor, hora_valor)


def data_para_texto(valor):
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


def data_br(valor):
    if isinstance(valor, str):
        valor = parse_data(valor)
    return valor.strftime("%d/%m/%Y")


def dinheiro_para_texto(centavos):
    return formatar_preco_centavos(centavos).replace("R$ ", "")
