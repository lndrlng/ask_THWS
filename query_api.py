import requests
import time


def ask_question(question):
    url = "http://localhost:8000/ask"
    response = requests.post(url, json={"query": question})
    return response.json()


if __name__ == "__main__":
    print("🔄 THWS Assistent – API Modus (ENTER zum Beenden)")
    while True:
        try:
            question = input("\n❓ Frage: ").strip()
            if not question:
                print("👋 Tschüss!")
                break

            start = time.time()
            result = ask_question(question)
            duration = round(time.time() - start, 2)

            print("\n📝 Frage:", result["question"])
            print("💬 Antwort:", result["answer"])
            print("🕒 Berechnungszeit (gesamt):", result["time_seconds"], "Sekunden")
            print("📡 Antwortzeit Client → Server → Client:", duration, "Sekunden")
            print("🔗 Quellen:")
            for src in result["sources"]:
                print(" -", src)

        except KeyboardInterrupt:
            print("\n👋 Manuell beendet. Tschüss!")
            break
        except Exception as e:
            print(f"\n⚠️ Fehler bei der Anfrage: {e}")
