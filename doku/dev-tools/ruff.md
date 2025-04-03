## 🐶 Ruff – ultraschnelles Python Linting

### 🔍 Was ist Ruff?

**Ruff** ist ein extrem schneller Linter und Code-Formatter für Python, geschrieben in Rust. Er vereint die Funktionalität vieler Tools wie `flake8`, `pycodestyle`, `pyflakes`, `isort`, `pylint`, usw. – in einem einzigen, performanten Tool.

---

## 🚀 Vorteile

- ⚡️ **Sehr schnell** – ideal für große Repos und CI/CD
- 🔧 Konfigurierbar & erweiterbar
- 🧩 Unterstützt über 500 Regeln aus beliebten Linting-Tools
- ✨ Optional: Auto-Fix für viele Fehler

---

## 🖥 Installation

### 📦 Mit pip (Python ≥ 3.7)

```bash
pip install ruff
```

Oder mit Homebrew (macOS/Linux):

```bash
brew install ruff
```

Oder über `pipx`:

```bash
pipx install ruff
```
---

## ✅ Benutzung

### Linting starten:

```bash
ruff .
```

### Nur bestimmte Datei:

```bash
ruff my_script.py
```

### Probleme automatisch beheben:

```bash
ruff check . --fix
```

---

## 🔗 Nützliche Links

- Offizielle Doku: https://docs.astral.sh/ruff
- Regeln: https://docs.astral.sh/ruff/rules/