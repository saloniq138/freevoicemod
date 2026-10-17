# VoiceForge

Darmowy prototyp zmieniacza głosu na żywo dla Windows, z ciemnym interfejsem i fioletowymi akcentami.

## Efekty głosu
- **Clean** — bez dodatkowego efektu.
- **Robot, Demon, Radio, Echo** — modulacja, przester i echo.
- **Female, Male, Helium, Deep, Chipmunk** — eksperymentalne zmiany barwy głosu; nie są to zaawansowane algorytmy zmiany wysokości tonu.
- **Villager, Chicken, Zombie, Skeleton, Creeper, Enderman, Ghast, Witch, Spider, Pig, Cow, Sheep, Ender Dragon** — dodatkowe efekty inspirowane mobami z Minecrafta.
- **Ghost, Alien, Megaphone** — pozostałe efekty stylizowane i modulowane.
- Panel efektów ma wyszukiwarkę i przewijanie, więc długa lista nie rozciąga całego okna.
- Wybrany efekt jest widoczny w panelu **SELECTED VOICE**. Lista jest oparta na efektach DSP, nie na instalowanych głosach TTS.

Wszystkie efekty mobów są generowanymi filtrami DSP inspirowanymi brzmieniem Minecrafta, a nie oryginalnymi próbkami ani dokładną emulacją dźwięków gry. Realistyczna konwersja głosu AI nie jest jeszcze zaimplementowana.

## Inne funkcje
- Przekazywanie audio z mikrofonu do wyjścia audio.
- Lekka bramka szumów.
- Soundboard dla plików WAV PCM 16-bit; dźwięki trafiają do aktywnego strumienia wyjściowego, zamiast otwierać drugi strumień na tym samym urządzeniu.
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

GitHub Actions automatycznie sprawdza składnię Pythona, buduje aplikację na Windows po zmianach na `main` lub `master` i publikuje artefakt `VoiceForge-Windows` w przebiegu workflow. Samo sprawdzenie składni nie zastępuje testów audio na fizycznym mikrofonie i urządzeniu wyjściowym.

## Status
To prototyp. Efekty są aproksymacjami DSP i wymagają testów na konkretnym sprzęcie. Nie deklarujemy gotowości pliku EXE, dopóki build nie zakończy się pomyślnie.