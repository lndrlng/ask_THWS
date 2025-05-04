import json
import os

# Pfade anpassen, falls nötig
input_path = '/Users/lelange/Uni/Projektarbeit/rag/data/studiengaenge_triplets.json'
output_path = '/Users/lelange/Uni/Projektarbeit/rag/data/studiengaenge_triplets_converted.json'

# Backup der Originaldatei erstellen
if os.path.exists(input_path):
    os.rename(input_path, input_path + '.bak')

# Originaldatei einlesen
with open(input_path + '.bak', 'r', encoding='utf-8') as f:
    data = json.load(f)

converted = []
skipped = []

# Konvertierung
for entry in data:
    if isinstance(entry, list) and len(entry) == 3:
        converted.append({
            'subject': entry[0],
            'relation': entry[1],
            'object': entry[2]
        })
    else:
        skipped.append(entry)

# In neue Datei schreiben
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(converted, f, ensure_ascii=False, indent=2)

print(f'Konvertiert: {len(converted)} Tripel')
print(f'Übersprungen: {len(skipped)} Einträge mit unpassender Struktur')