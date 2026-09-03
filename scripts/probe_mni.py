"""Probe publico do WSDL MNI dos TRTs alvo da fase 0.

O script faz exatamente uma requisicao GET por tribunal selecionado. Ele nao envia
credencial, nao chama operacao SOAP e nao segue redirecionamentos automaticamente.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Final

import httpx

DEFAULT_TRIBUNALS: Final[tuple[str, ...]] = ("TRT4", "TRT2", "TRT13")
WSDL_URLS: Final[dict[str, str]] = {
    "TRT4": "https://pje.trt4.jus.br/primeirograu/intercomunicacao?wsdl",
    "TRT2": "https://pje.trt2.jus.br/primeirograu/intercomunicacao?wsdl",
    "TRT13": "https://pje.trt13.jus.br/primeirograu/intercomunicacao?wsdl",
}
EXPECTED_PARAMETERS: Final[tuple[str, ...]] = (
    "incluirDocumentos",
    "incluirCabecalho",
    "movimentos",
    "idConsultante",
    "senhaConsultante",
)
USER_AGENT: Final[str] = (
    "trt-extractor-fase0-mni-probe/0.1 "
    "(GET publico de WSDL MNI; sem credenciais; sem chamada SOAP)"
)


@dataclass(frozen=True)
class ProbeResult:
    tribunal: str
    url: str
    http_status: int | None
    responded: bool
    operations: tuple[str, ...]
    has_consultar_processo: bool
    parameters: tuple[str, ...]
    namespace: str
    version: str
    observation: str


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def attr_local_name(name: str | None) -> str:
    if not name:
        return ""
    return name.rsplit(":", 1)[-1]


def children_by_local_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def descendants_by_local_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element.iter() if local_name(child.tag) == name]


def collect_operations(root: ET.Element) -> tuple[str, ...]:
    names: set[str] = set()
    for port_type in descendants_by_local_name(root, "portType"):
        for operation in children_by_local_name(port_type, "operation"):
            name = operation.attrib.get("name")
            if name:
                names.add(name)
    if not names:
        for binding in descendants_by_local_name(root, "binding"):
            for operation in children_by_local_name(binding, "operation"):
                name = operation.attrib.get("name")
                if name:
                    names.add(name)
    return tuple(sorted(names))


def collect_operation_message_names(root: ET.Element, operation_name: str) -> set[str]:
    names: set[str] = set()
    for port_type in descendants_by_local_name(root, "portType"):
        for operation in children_by_local_name(port_type, "operation"):
            if operation.attrib.get("name") != operation_name:
                continue
            for io_element in list(operation):
                if local_name(io_element.tag) in {"input", "output"}:
                    message_name = attr_local_name(io_element.attrib.get("message"))
                    if message_name:
                        names.add(message_name)
    return names


def collect_message_part_targets(root: ET.Element, message_names: set[str]) -> set[str]:
    targets: set[str] = set()
    for message in descendants_by_local_name(root, "message"):
        if message.attrib.get("name") not in message_names:
            continue
        for part in children_by_local_name(message, "part"):
            for attr in ("name", "element", "type"):
                value = attr_local_name(part.attrib.get(attr))
                if value:
                    targets.add(value)
    return targets


def collect_element_parameters(root: ET.Element, target_names: set[str]) -> set[str]:
    parameters: set[str] = set()
    for element in descendants_by_local_name(root, "element"):
        if element.attrib.get("name") not in target_names:
            continue
        for nested in descendants_by_local_name(element, "element"):
            name = nested.attrib.get("name")
            if name:
                parameters.add(name)
    return parameters


def collect_parameters(root: ET.Element, operation_name: str) -> tuple[str, ...]:
    message_names = collect_operation_message_names(root, operation_name)
    target_names = collect_message_part_targets(root, message_names)
    target_names.add(operation_name)

    discovered = collect_element_parameters(root, target_names)

    # Alguns WSDLs incluem os tipos por import ou formato document/literal mais raso.
    # Neste caso, registrar ao menos os nomes esperados quando aparecem no contrato.
    all_element_names = {
        element.attrib["name"]
        for element in descendants_by_local_name(root, "element")
        if "name" in element.attrib
    }
    for expected in EXPECTED_PARAMETERS:
        if expected in all_element_names:
            discovered.add(expected)

    return tuple(sorted(discovered))


def extract_version(namespace: str, xml_text: str) -> str:
    patterns = (
        r"intercomunicacao[-/](\d+(?:\.\d+)+)",
        r"servico-intercomunicacao[-/](\d+(?:\.\d+)+)",
        r"mni[-_/]?(\d+(?:\.\d+)+)",
    )
    for pattern in patterns:
        match = re.search(pattern, namespace, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    for pattern in patterns:
        match = re.search(pattern, xml_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return "nao identificado"


def parse_wsdl(tribunal: str, url: str, response: httpx.Response) -> ProbeResult:
    status = response.status_code
    if not response.content:
        return ProbeResult(
            tribunal=tribunal,
            url=url,
            http_status=status,
            responded=True,
            operations=(),
            has_consultar_processo=False,
            parameters=(),
            namespace="nao identificado",
            version="nao identificado",
            observation="HTTP sem corpo de WSDL",
        )

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        return ProbeResult(
            tribunal=tribunal,
            url=url,
            http_status=status,
            responded=True,
            operations=(),
            has_consultar_processo=False,
            parameters=(),
            namespace="nao identificado",
            version="nao identificado",
            observation=f"resposta nao XML ({exc})",
        )

    xml_text = response.text
    operations = collect_operations(root)
    has_consultar_processo = "consultarProcesso" in operations
    parameters = (
        collect_parameters(root, "consultarProcesso") if has_consultar_processo else ()
    )
    namespace = root.attrib.get("targetNamespace", "nao identificado")
    version = extract_version(namespace, xml_text)

    observation = "WSDL parseado"
    if status in {401, 403}:
        observation = "WSDL exige autenticacao ou credenciamento"
    elif status >= 400:
        observation = "HTTP nao sucesso; contrato nao confirmado"
    elif not operations:
        observation = "XML recebido, mas sem operacoes WSDL identificadas"

    return ProbeResult(
        tribunal=tribunal,
        url=url,
        http_status=status,
        responded=True,
        operations=operations,
        has_consultar_processo=has_consultar_processo,
        parameters=parameters,
        namespace=namespace,
        version=version,
        observation=observation,
    )


def probe_tribunal(client: httpx.Client, tribunal: str) -> ProbeResult:
    url = WSDL_URLS[tribunal]
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return ProbeResult(
            tribunal=tribunal,
            url=url,
            http_status=None,
            responded=False,
            operations=(),
            has_consultar_processo=False,
            parameters=(),
            namespace="nao respondeu",
            version="nao respondeu",
            observation=f"nao respondeu: {type(exc).__name__}: {exc}",
        )
    return parse_wsdl(tribunal, url, response)


def format_bool(value: bool) -> str:
    return "sim" if value else "nao"


def format_status(result: ProbeResult) -> str:
    if not result.responded:
        return "nao respondeu"
    return f"sim (HTTP {result.http_status})"


def format_list(values: tuple[str, ...]) -> str:
    if not values:
        return "nenhum identificado"
    return ", ".join(values)


def format_result_table(results: list[ProbeResult]) -> str:
    lines = [
        "| tribunal | WSDL responde | operacoes | consultarProcesso | "
        "incluirDocumentos aceito | observacao |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        incluir_documentos = (
            "sim" if "incluirDocumentos" in result.parameters else "nao identificado"
        )
        lines.append(
            "| {tribunal} | {responded} | {operations} | {consultar} | "
            "{incluir_documentos} | {observation} |".format(
                tribunal=result.tribunal,
                responded=format_status(result),
                operations=format_list(result.operations),
                consultar=format_bool(result.has_consultar_processo),
                incluir_documentos=incluir_documentos,
                observation=result.observation.replace("|", "/"),
            )
        )
    return "\n".join(lines)


def print_details(results: list[ProbeResult]) -> None:
    print(format_result_table(results))
    print()
    for result in results:
        print(f"## {result.tribunal}")
        print(f"- WSDL: {result.url}")
        print(f"- namespace: {result.namespace}")
        print(f"- versao MNI: {result.version}")
        print(f"- parametros consultarProcesso: {format_list(result.parameters)}")
        print()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe publico de WSDL MNI para TRT2, TRT4 e TRT13."
    )
    parser.add_argument(
        "--tribunal",
        action="append",
        choices=sorted(WSDL_URLS),
        help="Tribunal alvo. Pode ser repetido. Padrao: TRT4, TRT2 e TRT13.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout por GET ao WSDL, em segundos. Padrao: 15.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    tribunals = tuple(args.tribunal or DEFAULT_TRIBUNALS)
    timeout = httpx.Timeout(args.timeout)
    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=False) as client:
        results = [probe_tribunal(client, tribunal) for tribunal in tribunals]

    print_details(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
