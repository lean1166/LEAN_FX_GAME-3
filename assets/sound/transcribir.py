import whisper
from pathlib import Path

CARPETA = Path(__file__).parent
SALIDA = CARPETA / "transcripciones.txt"

print("Cargando Whisper...")

model = whisper.load_model("small")

audios = sorted(CARPETA.glob("*.mp3"))

print(f"Encontrados {len(audios)} archivos MP3.")
print("Comenzando transcripción...\n")

with open(SALIDA, "w", encoding="utf-8") as f:

    for i, audio in enumerate(audios, 1):

        print(f"[{i}/{len(audios)}] {audio.name}")

        try:
            resultado = model.transcribe(
                str(audio),
                language="es",
                fp16=False
            )

            texto = resultado["text"].strip()

            f.write(f"{audio.name} → {texto}\n")
            f.flush()

            print(f"    {texto}")

        except Exception as e:
            f.write(f"{audio.name} → ERROR: {e}\n")
            f.flush()

            print(f"    ERROR: {e}")

print("\nLISTO.")
print(f"Archivo generado: {SALIDA}")