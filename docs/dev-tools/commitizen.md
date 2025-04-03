## 🚀 Commitizen – Commit-Konventionen & automatisches Versionieren

### 🔍 Was ist Commitizen?

[Commitizen](https://github.com/commitizen-tools/commitizen) hilft dabei, einheitliche **Commit-Nachrichten** zu schreiben und daraus automatisch **Versionen** und **Changelogs** zu generieren – z. B. für semantisches Versionieren (SemVer).

---

### ✅ Warum verwenden?

- 🚦 Automatisierte Prüfung von Commit-Nachrichten (CI/CD)
- 📝 Automatische Changelog-Erstellung
- 🔖 Versionierung und Tagging direkt aus Commits
- 🔧 Unterstützung für „Conventional Commits“

---

### ⚙️ Einrichtung

1. **Installieren:**

```bash
pip install commitizen
```

---

### ✍️ Commit schreiben

Mit dem Commitizen-Tool:

```bash
cz commit
```

Beispielhafter Commit-Dialog:
```
type: feat
scope: api
subject: add new endpoint for user data
```

Oder manuell (wenn du es ohne Tool schreibst):

```
feat(api): add new endpoint for user data
```

---

### ✅ Commit prüfen

```bash
cz check --rev-range origin/main...
```

Prüft, ob alle Commits zwischen Branches gültig sind.

---

### 🚀 Version bump + Changelog

```bash
cz bump
```

- Erhöht die Version automatisch basierend auf deinen Commits (Major/Minor/Patch)
- Erstellt einen neuen Git-Tag
- Generiert/aktualisiert den `CHANGELOG.md`

---

### 🔗 GitHub Action Integration

Du kannst Commitizen in CI/CD-Pipelines integrieren (z. B. `.github/workflows/commitizen.yml`), um fehlerhafte Commits automatisch zu blockieren.

---

### 📌 Commit-Typen (Conventional Commits)

| Typ      | Beschreibung                    |
|----------|---------------------------------|
| `feat`   | Neues Feature                   |
| `fix`    | Bugfix                          |
| `docs`   | Dokumentation                   |
| `style`  | Formatierung, kein Code-Change  |
| `refactor` | Code-Umstrukturierung        |
| `test`   | Tests hinzugefügt/geändert      |
| `chore`  | Build-Prozess, Hilfstools, etc. |
