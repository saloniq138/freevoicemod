# VoiceForge

Darmowy prototyp zmieniacza głosu na żywo dla Windows, z ciemnym interfejsem i fioletowymi akcentami.

## Efekty głosu
- Clean, Robot, Demon, Radio, Echo.
- Female/Male pitch: lekka zmiana barwy, nie pełna zmiana wysokości głosu.
- Villager: nosowa, bucząca modulacja inspirowana wieśniakiem z Minecrafta.
- Chicken: wysoka, piskliwa modulacja inspirowana kurczakiem.
- Zombie: niska, chropowata modulacja inspirowana zombie.

Efekty Villager/Chicken/Zombie są generowanymi efektami DSP, a nie oryginalnymi próbkami dźwiękowymi z Minecrafta. Realistyczna konwersja głosu AI nie jest jeszcze zaimplementowana.

## Inne funkcje
- Przekazywanie audio z mikrofonu do wyjścia audio.
- Lekka bramka szumów.
- Soundboard dla plików WAV PCM 16-bit.
- Zapisywanie presetów.
- Skróty Ctrl+1 do Ctrl+9 wybierają efekty; Ctrl+Shift+V uruchamia/zatrzymuje audio, gdy okno aplikacji ma fokus.

## Discord / OBS
Zainstaluj zaufany wirtualny kabel audio, np. VB-CABLE. W VoiceForge ustaw wyjście na `CABLE Input`, a w Discordzie/OBS wybierz `CABLE Output` jako mikrofon. Efekt usłyszysz dopiero po uruchomieniu strumienia audio.

## Uruchomienie
Wymagany Windows 10/11 i Python 3.12 64-bit.

```powershell
py -3.12 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Kompilacja EXE
Uruchom `build_windows.bat`. Plik będzie w `dist\\VoiceForge\\VoiceForge.exe`. Zachowaj cały folder `dist\\VoiceForge`.

GitHub Actions automatycznie buduje aplikację na Windows po zmianach na `main` i publikuje artefakt `VoiceForge-Windows` w przebiegu workflow.

## Status
To prototyp. Efekty są aproksymacjami DSP i wymagają testów na konkretnym sprzęcie. Nie deklarujemy gotowości pliku EXE, dopóki build nie zakończy się pomyślnie.