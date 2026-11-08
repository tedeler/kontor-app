"""Eigene Tests von kontor-app (ergänzen die Tests aus kontor-tests, ersetzen sie nicht)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

KMY_KOPF = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE KMYMONEY-FILE>\n'


def kmy(konten: str = "", payees: str = "", tags: str = "", transaktionen: str = "", gz: bool = True) -> bytes:
    """Baut eine kleine synthetische KMyMoney-Datei."""
    xml = (KMY_KOPF + "<KMYMONEY-FILE>"
           f"<PAYEES>{payees}</PAYEES><TAGS>{tags}</TAGS>"
           '<ACCOUNTS><ACCOUNT id="AStd::Asset" name="Anlage" type="9" parentaccount="" currency="EUR"/>'
           '<ACCOUNT id="AStd::Expense" name="Ausgabe" type="13" parentaccount="" currency="EUR"/>'
           f"{konten}</ACCOUNTS><TRANSACTIONS>{transaktionen}</TRANSACTIONS></KMYMONEY-FILE>").encode("utf-8")
    return gzip.compress(xml, mtime=0) if gz else xml


GIRO = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR">'
        '<KEYVALUEPAIRS><PAIR key="iban" value="DE89 3704 0044 0532 0130 00"/></KEYVALUEPAIRS></ACCOUNT>'
        '<ACCOUNT id="A2" name="Lebensmittel" type="13" parentaccount="AStd::Expense" currency="EUR"/>')


def transaktion(tid: str, datum: str, *splits: tuple[str, str], memo: str = "") -> str:
    s = "".join(f'<SPLIT account="{k}" value="{v}" memo=""/>' for k, v in splits)
    return f'<TRANSACTION id="{tid}" postdate="{datum}" memo="{memo}" commodity="EUR"><SPLITS>{s}</SPLITS></TRANSACTION>'


@pytest.fixture
def config(tmp_path: Path) -> KontorConfig:
    return KontorConfig(datenbank=tmp_path / "kontor.sqlite3")


@pytest.fixture
def client(config) -> TestClient:
    return TestClient(create_app(config))


@pytest.fixture
def mock_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "kontor.sqlite3", mock_modus=True)))
