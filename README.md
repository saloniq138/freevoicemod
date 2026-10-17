# VoiceForge

Darmowy prototyp zmieniacza głosu na żywo dla Windows, z ciemnym interfejsem i fioletowymi akcentami.

## Funkcje
- Przekazywanie audio z mikrofonu do wyjścia audio.
- Efekty Clean, Robot, Demon, Radio i Echo.
- Lekka bramka szumów.
- Soundboard dla plików WAV PCM 16-bit.
- Zapisywanie presetów.
- Skróty klawiszowe aktywne, gdy okno aplikacji ma fokus.

## Ograniczenia
- Efekt „Female/Male pitch” jest prostym efektem tonalnym, nie realistyczną konwersją płci głosu.
- Konwersja AI nie jest jeszcze zaimplementowana.
- Aby przesłać dźwięk do Discorda/OBS jako mikrofon, użyj zaufanego wirtualnego kabla audio, np. VB-CABLE.
- Aplikacja przetwarza audio lokalnie; nie wymaga API key.

## Uruchomienie
Wymagany Windows 10/11 i Python 3.12 64-bit.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Kompilacja EXE
Uruchom `build_windows.bat`. Plik będzie w `dist\VoiceForge\VoiceForge.exe`. Zachowaj cały folder `dist\VoiceForge`.

Alternatywnie GitHub Actions buduje aplikację na Windows i publikuje artefakt `VoiceForge-Windows`.

## Status
Kod źródłowy i konfiguracja kompilacji są prototypem. Przed użyciem należy przetestować audio na konkretnym urządzeniu. Nie oznaczamy builda jako gotowego, dopóki nie przejdzie testu.