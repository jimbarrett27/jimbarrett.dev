"""Tests for the Drive helper's folder logic, against an in-memory fake service."""

import re

from gcp_util import drive


class _Exec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class FakeFiles:
    """Just enough of ``service.files()`` for find/ensure/list: parsed name + parent queries."""

    def __init__(self):
        self.items: list[dict] = []
        self._next_id = 0

    def list(self, q, fields, pageToken=None, pageSize=100):
        parent = re.search(r"'((?:[^'\\]|\\.)*)' in parents", q).group(1).replace("\\'", "'")
        name = re.search(r"name = '((?:[^'\\]|\\.)*)'", q)
        folders_only = drive.FOLDER_MIME in q
        files = [
            f
            for f in self.items
            if parent in f["parents"]
            and (name is None or f["name"] == name.group(1).replace("\\'", "'"))
            and (not folders_only or f["mimeType"] == drive.FOLDER_MIME)
        ]
        return _Exec({"files": files})

    def create(self, body, fields, media_body=None):
        self._next_id += 1
        item = {"id": f"id{self._next_id}", "mimeType": "application/pdf", **body}
        self.items.append(item)
        return _Exec({"id": item["id"]})


class FakeService:
    def __init__(self):
        self._files = FakeFiles()

    def files(self):
        return self._files


def test_quote_escapes_quotes_and_backslashes():
    assert drive._quote("Jim's \\ notes") == "Jim\\'s \\\\ notes"


def test_ensure_folder_creates_nested_path_once():
    service = FakeService()
    first = drive.ensure_folder("Papers/To read", service=service)
    second = drive.ensure_folder("Papers/To read", service=service)

    assert first == second
    folders = [f for f in service.files().items if f["mimeType"] == drive.FOLDER_MIME]
    assert [(f["name"], f["parents"]) for f in folders] == [
        ("Papers", ["root"]),
        ("To read", [folders[0]["id"]]),
    ]


def test_find_folder_handles_apostrophes():
    service = FakeService()
    folder_id = drive.ensure_folder("Jim's papers", service=service)
    assert drive.find_folder("Jim's papers", service=service) == folder_id
    assert drive.find_folder("Other", service=service) is None


def test_list_files_returns_only_direct_children():
    service = FakeService()
    papers = drive.ensure_folder("Papers", service=service)
    service.files().create(body={"name": "a.pdf", "parents": [papers]}, fields="id")
    service.files().create(body={"name": "b.pdf", "parents": ["root"]}, fields="id")

    assert [f["name"] for f in drive.list_files(papers, service=service)] == ["a.pdf"]
