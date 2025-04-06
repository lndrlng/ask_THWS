## 🎨 Black – der unkompromisslose Python-Formatter

### 🔍 Was ist Black?

**Black** ist ein automatischer Code-Formatter für Python. Er verfolgt das Prinzip: **„Any code style is better than no style, but one style is best.“**  
Statt Stilregeln zu diskutieren, wird der Code automatisch in ein einheitliches Format gebracht – kompromisslos und konsistent.

---

## 🚀 Vorteile

- ✅ **Zero configuration** – funktioniert sofort, ohne viele Einstellungen
- 🎯 Einheitlicher Stil für alle Python-Dateien
- 🛡 Weniger Code-Diskussionen in Code Reviews
- 🔁 Optionaler **CI/CD-Einsatz** zur Formatprüfung

---

## 🖥 Installation

### 📦 Mit pip

```bash
pip install black
```

Oder über `pipx`:

```bash
pipx install black
```

Oder mit Homebrew (macOS/Linux):

```bash
brew install black
```

---

## ✅ Benutzung

### Projekt formatieren:

```bash
black .
```

### Nur bestimmte Datei:

```bash
black my_script.py
```

### Formatierung prüfen (z. B. in CI):

```bash
black --check .
```

### Unterschiede anzeigen:

```bash
black --check --diff .
```

## 🔗 Nützliche Links

- Offizielle Doku: https://black.readthedocs.io/
- PyPI-Seite: https://pypi.org/project/black/
- GitHub: https://github.com/psf/black
