"""D-178: Branch eines Entwicklungsstands aus .git/HEAD."""

from kontor import version


def _repo(tmp_path, kopf):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text(kopf, encoding="utf-8")
    datei = tmp_path / "src" / "kontor" / "version.py"
    datei.parent.mkdir(parents=True)
    datei.write_text("", encoding="utf-8")
    return datei


def test_branch_aus_head(tmp_path):
    assert version.zweig(_repo(tmp_path, "ref: refs/heads/feature/detailansicht\n")) == "feature/detailansicht"


def test_losgeloester_head_ohne_branch(tmp_path):
    assert version.zweig(_repo(tmp_path, "0123456789abcdef0123456789abcdef01234567\n")) is None


def test_unzulaessiger_name_wird_nicht_angezeigt(tmp_path):
    assert version.zweig(_repo(tmp_path, 'ref: refs/heads/a"<b>\n')) is None


def test_worktree_datei(tmp_path):
    echt = tmp_path / "echt"
    echt.mkdir()
    (echt / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    arbeit = tmp_path / "arbeit"
    arbeit.mkdir()
    (arbeit / ".git").write_text(f"gitdir: {echt}\n", encoding="utf-8")
    assert version.zweig(arbeit / "x.py") == "main"



def test_link():
    assert version.zweig_url("feature/x y") == "https://github.com/tedeler/kontor-app/tree/feature/x%20y"
