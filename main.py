import sys, json, os, wave, queue, zipfile
from pathlib import Path
import numpy as np
import sounddevice as sd
import miniaudio
from villager_autotune import install_villager_autotune
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
 QPushButton,QComboBox,QSlider,QCheckBox,QGroupBox,QGridLayout,QMessageBox,QFileDialog,
 QListWidget,QInputDialog,QScrollArea,QLineEdit)

APP = Path(os.getenv("APPDATA", str(Path.home()))) / "VoiceForge"
APP.mkdir(parents=True, exist_ok=True)
SOUNDS = APP / "sounds"; SOUNDS.mkdir(exist_ok=True)
PRESETS = APP / "presets.json"
SOUND_EXTENSIONS = {".wav", ".ogg", ".mp3"}

# Bundle the Villager sample archive with the Windows build and import it on
# first launch, so the live Villager filter works without manual file copying.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
try:
    import shutil
    for bundled_archive in RESOURCE_DIR.glob("Villager*.zip"):
        target_archive = SOUNDS / bundled_archive.name
        if not target_archive.exists():
            shutil.copy2(bundled_archive, target_archive)
except OSError as exc:
    print(f"Nie udało się skopiować paczki dźwięków villagera: {exc}")

def extract_sound_archives():
    """Import supported audio files from ZIPs placed in the sounds folder."""
    for archive in SOUNDS.glob("*.zip"):
        try:
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    # Use only the filename, preventing ZIP path traversal.
                    name = Path(info.filename).name
                    if not name or Path(name).suffix.lower() not in SOUND_EXTENSIONS:
                        continue
                    target = SOUNDS / name
                    if target.exists():
                        continue
                    with zf.open(info) as source, target.open("wb") as dest:
                        dest.write(source.read())
        except (OSError, zipfile.BadZipFile) as exc:
            print(f"Nie udało się rozpakować {archive.name}: {exc}")

extract_sound_archives()
EFFECTS = ["Clean", "Robot", "Demon", "Radio", "Echo", "Female", "Male", "Villager", "Chicken", "Zombie", "Skeleton", "Creeper", "Enderman", "Ghast", "Witch", "Spider", "Pig", "Cow", "Sheep", "Ender Dragon", "Ghost", "Alien", "Helium", "Deep", "Megaphone", "Chipmunk"]

class Engine:
    def __init__(self):
        self.stream = None
        self.in_stream = None; self.out_stream = None
        self.effect = "Clean"; self.mix = .8; self.denoise = False
        self.echo = np.zeros(96000, dtype=np.float32); self.pos = 0
        self.phase = 0; self.input_rate = 48000; self.output_rate = 48000
        self.audio_queue = queue.Queue(maxsize=80); self.sound_queue = queue.Queue(maxsize=100); self.output = None
        self.pending_chunk = np.zeros(0, dtype=np.float32); self.pending_offset = 0
        self.pending_sound_chunk = np.zeros(0, dtype=np.float32); self.pending_sound_offset = 0
        self.formant_state = {}

    def start(self, inp, out):
        self.stop()
        devices = sd.query_devices()
        idev, odev = devices[int(inp)], devices[int(out)]
        self.input_rate = int(round(idev["default_samplerate"])) or 48000
        self.output_rate = int(round(odev["default_samplerate"])) or 48000
        self.output = int(out); self.echo[:] = 0; self.pos = 0; self.phase = 0
        self.pending_chunk = np.zeros(0, dtype=np.float32); self.pending_offset = 0
        self.pending_sound_chunk = np.zeros(0, dtype=np.float32); self.pending_sound_offset = 0
        self.formant_state.clear()
        for q in (self.audio_queue, self.sound_queue):
            while not q.empty():
                try: q.get_nowait()
                except queue.Empty: break
        # Separate streams allow the microphone and speakers to use different Windows audio APIs.
        try:
            self.out_stream = sd.OutputStream(device=int(out), samplerate=self.output_rate,
                channels=1, dtype="float32", blocksize=0, callback=self.output_cb, latency="high")
            self.out_stream.start()
            self.in_stream = sd.InputStream(device=int(inp), samplerate=self.input_rate,
                channels=1, dtype="float32", blocksize=0, callback=self.input_cb, latency="high")
            self.in_stream.start()
            self.stream = self.in_stream
        except Exception:
            self.stop()
            raise

    def stop(self):
        for name in ("in_stream", "out_stream"):
            s = getattr(self, name, None)
            if s:
                try: s.stop()
                except Exception: pass
                try: s.close()
                except Exception: pass
            setattr(self, name, None)
        self.stream = None

    def input_cb(self, indata, frames, time_info, status):
        x = self.process(indata[:, 0].copy())
        if self.input_rate != self.output_rate and len(x):
            n = max(1, int(round(len(x) * self.output_rate / self.input_rate)))
            x = np.interp(np.linspace(0, len(x)-1, n), np.arange(len(x)), x).astype(np.float32)
        try: self.audio_queue.put_nowait(x)
        except queue.Full:
            try: self.audio_queue.get_nowait()
            except queue.Empty: pass
            try: self.audio_queue.put_nowait(x)
            except queue.Full: pass

    def output_cb(self, outdata, frames, time_info, status):
        # Keep partially consumed audio at the front; re-queueing it at the
        # tail can reorder chunks when the device block size differs.
        out = np.zeros(frames, dtype=np.float32)
        offset = 0
        while offset < frames:
            if self.pending_offset >= len(self.pending_chunk):
                try:
                    self.pending_chunk = self.audio_queue.get_nowait()
                    self.pending_offset = 0
                except queue.Empty:
                    break
            available = len(self.pending_chunk) - self.pending_offset
            take = min(available, frames - offset)
            out[offset:offset + take] = self.pending_chunk[self.pending_offset:self.pending_offset + take]
            offset += take
            self.pending_offset += take
        # Mix soundboard clips over the live microphone signal.
        offset = 0
        while offset < frames:
            if self.pending_sound_offset >= len(self.pending_sound_chunk):
                try:
                    self.pending_sound_chunk = self.sound_queue.get_nowait()
                    self.pending_sound_offset = 0
                except queue.Empty:
                    break
            available = len(self.pending_sound_chunk) - self.pending_sound_offset
            take = min(available, frames - offset)
            out[offset:offset + take] += self.pending_sound_chunk[
                self.pending_sound_offset:self.pending_sound_offset + take]
            offset += take
            self.pending_sound_offset += take
        outdata[:, 0] = np.clip(out, -0.98, 0.98)

    def _formant_resonator(self, samples, frequency, bandwidth, key):
        """Small stateful resonator to add vowel-like formants without extra packages."""
        fs = max(float(self.input_rate), 8000.0)
        radius = float(np.exp(-np.pi * bandwidth / fs))
        coeff = 2.0 * radius * float(np.cos(2.0 * np.pi * frequency / fs))
        gain = (1.0 - radius) ** 2
        y1, y2 = self.formant_state.get(key, (0.0, 0.0))
        out = np.empty_like(samples)
        for i, sample in enumerate(samples):
            y = gain * float(sample) + coeff * y1 - radius * radius * y2
            out[i] = y
            y2, y1 = y1, y
        self.formant_state[key] = (y1, y2)
        return out

    def process(self, x):
        if not len(x): return x
        if self.denoise and np.sqrt(np.mean(x*x)+1e-12) < .012: x *= .15
        t = (np.arange(len(x), dtype=np.float32) + self.phase) / self.input_rate
        prev = np.concatenate(([x[0]], x[:-1]))
        if self.effect == "Robot":
            x = np.tanh(x*2.5) * (.5 + .5*np.sin(2*np.pi*75*t))
        elif self.effect == "Demon":
            x = np.tanh(x*5) + .18*np.sin(2*np.pi*48*t)*np.abs(x)
        elif self.effect == "Radio":
            x = np.round(np.tanh(x*3)*16)/16
            x = x - np.concatenate(([x[0]], x[:-1]))*.45
        elif self.effect == "Echo":
            y = np.empty_like(x)
            for i, v in enumerate(x):
                delayed = self.echo[(self.pos-7200) % len(self.echo)]
                y[i] = v + delayed*.45
                self.echo[self.pos] = v + delayed*.45
                self.pos = (self.pos+1) % len(self.echo)
            x = y
        elif self.effect == "Female":
            x = np.tanh(x*1.8)*.7 + (x-prev)*.3
        elif self.effect == "Male":
            x = np.tanh(x*2.8)*.85 + prev*.15
        elif self.effect == "Villager":
            # Live Villager-inspired voice filter; no prerecorded clips mixed in.
            # Keep speech intelligible while emphasizing nasal "hrrm" formants.
            voiced = np.tanh(x * 2.2)
            f1 = self._formant_resonator(voiced, 480, 190, "villager_f1")
            f2 = self._formant_resonator(voiced, 980, 260, "villager_f2")
            f3 = self._formant_resonator(voiced, 1680, 380, "villager_f3")
            previous = np.concatenate(([voiced[0]], voiced[:-1]))
            body = 0.72 * voiced + 0.28 * previous
            nasal = 0.48 * f1 + 0.42 * f2 + 0.18 * f3
            wobble = 0.94 + 0.06 * np.sin(2 * np.pi * 2.7 * t)
            x = (0.72 * body + 1.35 * nasal) * wobble
            x = np.tanh(x * 1.35)
        elif self.effect == "Chicken":
            squeak = np.sin(2*np.pi*(340+70*np.sin(2*np.pi*6*t))*t)
            x = np.tanh(x*2.4)*.65 + .3*squeak*np.abs(x)
            x = x-prev*.25
        elif self.effect == "Zombie":
            x = np.tanh(x*5)*.8 + .28*np.sin(2*np.pi*58*t)*np.abs(x)
            x = x*.8 + prev*.2
        elif self.effect == "Skeleton":
            x = np.tanh(x*4.2)*.62 + (x-prev)*.55
            x += .12*np.sin(2*np.pi*(185+24*np.sin(2*np.pi*7*t))*t)*np.abs(x)
        elif self.effect == "Creeper":
            wobble = np.sin(2*np.pi*2.2*t)
            x = np.tanh(x*4.8)*(.72+.22*wobble) + .16*np.sin(2*np.pi*(62+16*wobble)*t)*np.abs(x)
        elif self.effect == "Enderman":
            x = np.tanh(x*3.5)*.72 + .22*np.sin(2*np.pi*(95+18*np.sin(2*np.pi*1.3*t))*t)*np.abs(x)
            x = x*.72 + prev*.28
        elif self.effect == "Ghast":
            x = np.tanh(x*2.2)*(.48+.42*np.sin(2*np.pi*1.1*t)) + .22*np.sin(2*np.pi*260*t)*np.abs(x)
        elif self.effect == "Witch":
            x = np.tanh(x*3.8)*.7 + .22*np.sin(2*np.pi*(125+35*np.sin(2*np.pi*4*t))*t)*np.abs(x)
        elif self.effect == "Spider":
            x = np.tanh(x*3.2)*(.6+.4*np.sin(2*np.pi*12*t)) + .18*(x-prev)
        elif self.effect == "Pig":
            x = np.tanh(x*2.6)*.55 + .32*np.sin(2*np.pi*(290+80*np.sin(2*np.pi*5*t))*t)*np.abs(x)
        elif self.effect == "Cow":
            x = np.tanh(x*3.2)*.72 + prev*.24 + .08*np.sin(2*np.pi*82*t)*np.abs(x)
        elif self.effect == "Sheep":
            x = np.tanh(x*2.8)*(.68+.25*np.sin(2*np.pi*5.5*t)) + .16*np.sin(2*np.pi*210*t)*np.abs(x)
        elif self.effect == "Ender Dragon":
            x = np.tanh(x*5)*(.7+.25*np.sin(2*np.pi*.7*t)) + .22*np.sin(2*np.pi*48*t)*np.abs(x)
            x = x*.82 + prev*.18
        elif self.effect == "Ghost":
            x = np.tanh(x*2)*(.65+.35*np.sin(2*np.pi*2*t)) + prev*.2
        elif self.effect == "Alien":
            x = np.tanh(x*3)*np.sin(2*np.pi*(100+35*np.sin(2*np.pi*3*t))*t)
        elif self.effect == "Helium":
            x = np.tanh(x*2.3)*.55 + (x-prev)*.45
        elif self.effect == "Deep":
            x = np.tanh(x*4)*.8 + prev*.2
        elif self.effect == "Megaphone":
            x = np.round(np.tanh(x*4)*10)/10
        elif self.effect == "Chipmunk":
            x = np.tanh(x*2.5)*.5 + (x-prev)*.5
        self.phase = (self.phase + len(x)) % max(self.input_rate, 1)
        return np.clip(x*self.mix, -.98, .98).astype(np.float32)

    def play_file(self, path, output_device=None):
        """Decode WAV/OGG/MP3 to float audio and play via the selected output."""
        device = output_device if output_device is not None else self.output
        if device is not None and self.out_stream is not None:
            rate = self.output_rate
        elif device is not None:
            rate = int(round(sd.query_devices(int(device))["default_samplerate"])) or 48000
        else:
            rate = 48000
        decoded = miniaudio.decode_file(
            str(path),
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
            sample_rate=rate,
        )
        samples = np.frombuffer(decoded.samples, dtype=np.float32).copy()
        if not len(samples):
            return
        if self.out_stream is not None and self.out_stream.active:
            # Separate queue lets effects play over the live mic without
            # interrupting or reordering microphone audio.
            chunk_size = 2048
            for offset in range(0, len(samples), chunk_size):
                chunk = samples[offset:offset + chunk_size].copy()
                try:
                    self.sound_queue.put_nowait(chunk)
                except queue.Full:
                    try: self.sound_queue.get_nowait()
                    except queue.Empty: pass
                    try: self.sound_queue.put_nowait(chunk)
                    except queue.Full: pass
        else:
            sd.play(samples, samplerate=rate, device=int(device) if device is not None else None, blocking=False)

install_villager_autotune(Engine, SOUNDS)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VoiceForge"); self.resize(1120, 820); self.setMinimumSize(900, 650); self.engine = Engine()
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#0b0a12;color:#f4f0ff;font-size:14px}
        QLineEdit{background:#211b2e;border:1px solid #49395f;border-radius:9px;padding:9px;color:#f4f0ff}
        QScrollArea{border:0;background:transparent}
        QScrollBar:vertical{background:#171321;width:10px;margin:3px;border-radius:5px}
        QScrollBar::handle:vertical{background:#5b467d;min-height:24px;border-radius:5px}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
        QGroupBox{background:#15121f;border:1px solid #3c3154;border-radius:16px;margin-top:14px;padding:14px;font-weight:700}
        QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 7px;color:#c4b5fd}
        QPushButton{background:#282137;border:1px solid #4b3c68;border-radius:10px;padding:10px 12px;font-weight:700}
        QPushButton:checked{background:#7c3aed;border:1px solid #c4b5fd}
        QPushButton:hover{background:#5935a5}
        QComboBox{background:#211b2e;border:1px solid #49395f;border-radius:9px;padding:9px}
        QListWidget{background:#1a1623;border:1px solid #39304e;border-radius:10px;padding:5px}
        QSlider::groove:horizontal{background:#393044;height:6px;border-radius:3px}
        QSlider::handle:horizontal{background:#c4b5fd;width:16px;margin:-5px 0;border-radius:8px}
        """)
        root = QWidget(); self.setCentralWidget(root); main = QVBoxLayout(root); main.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel("VOICEFORGE"); title.setStyleSheet("font-size:30px;font-weight:900;color:#c4b5fd;letter-spacing:2px")
        top.addWidget(title); top.addWidget(QLabel("  REAL-TIME VOICE STUDIO")); top.addStretch()
        self.status = QLabel("● STOPPED"); self.status.setStyleSheet("color:#f87171;font-weight:800"); top.addWidget(self.status)
        main.addLayout(top)

        dev = QGroupBox("AUDIO ROUTING"); dg = QGridLayout(dev)
        self.inputs = QComboBox(); self.outputs = QComboBox()
        try:
            hostapis = sd.query_hostapis()
            for i, d in enumerate(sd.query_devices()):
                api = hostapis[int(d["hostapi"])]["name"]
                label = f"{d['name']}  ·  {api}"
                if d["max_input_channels"]: self.inputs.addItem(label, i)
                if d["max_output_channels"]: self.outputs.addItem(label, i)
        except Exception as e: QMessageBox.critical(self, "Audio devices", str(e))
        dg.addWidget(QLabel("MICROPHONE"),0,0); dg.addWidget(self.inputs,0,1)
        dg.addWidget(QLabel("OUTPUT / VIRTUAL CABLE"),1,0); dg.addWidget(self.outputs,1,1)
        hint = QLabel("Mikrofon i wyjście mogą korzystać z różnych API. Wybierz fizyczne wyjście do odsłuchu albo wirtualny kabel dla Discord/OBS.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#aaa0bd;font-size:12px"); dg.addWidget(hint,2,0,1,2)
        controls = QHBoxLayout()
        self.start = QPushButton("▶  START AUDIO"); self.stop = QPushButton("■  STOP"); self.stop.setEnabled(False)
        self.start.clicked.connect(self.start_audio); self.stop.clicked.connect(self.stop_audio)
        controls.addWidget(self.start); controls.addWidget(self.stop); dg.addLayout(controls,3,0,1,2); main.addWidget(dev)

        row = QHBoxLayout()
        eg = QGroupBox("VOICE EFFECTS"); el = QVBoxLayout(eg); self.effect_buttons = []
        self.selected_voice = QLabel("SELECTED VOICE  ·  Clean")
        self.selected_voice.setAlignment(Qt.AlignCenter); self.selected_voice.setMinimumHeight(62)
        self.selected_voice.setStyleSheet("background:#29213b;color:#d8b4fe;padding:14px;border-radius:12px;font-size:19px;font-weight:900")
        el.addWidget(self.selected_voice)
        self.effect_search = QLineEdit(); self.effect_search.setPlaceholderText("⌕  Search effects… (e.g. Skeleton)")
        self.effect_search.textChanged.connect(self.filter_effects); el.addWidget(self.effect_search)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumHeight(250)
        effect_panel = QWidget(); self.effect_grid = QGridLayout(effect_panel); self.effect_grid.setSpacing(8)
        for i, name in enumerate(EFFECTS):
            b = QPushButton(name); b.setCheckable(True); b.setMinimumHeight(38)
            b.clicked.connect(lambda checked, n=name: self.set_effect(n))
            self.effect_grid.addWidget(b,i//2,i%2); self.effect_buttons.append((name,b))
        scroll.setWidget(effect_panel); el.addWidget(scroll,1)
        self.effect_buttons[0][1].setChecked(True)
        el.addWidget(QLabel("OUTPUT LEVEL")); self.mix = QSlider(Qt.Horizontal); self.mix.setRange(0,100); self.mix.setValue(80)
        self.mix.valueChanged.connect(lambda v: setattr(self.engine,"mix",v/100)); el.addWidget(self.mix)
        self.nr = QCheckBox("Light noise gate"); self.nr.toggled.connect(lambda v: setattr(self.engine,"denoise",v)); el.addWidget(self.nr)
        row.addWidget(eg,3)

        right = QVBoxLayout()
        pg = QGroupBox("PRESETS"); pl = QVBoxLayout(pg); self.presets = QListWidget(); pl.addWidget(self.presets)
        pbtn = QHBoxLayout()
        for label, fn in [("Save",self.save_preset),("Load",self.load_preset),("Delete",self.delete_preset)]:
            b = QPushButton(label); b.clicked.connect(fn); pbtn.addWidget(b)
        pl.addLayout(pbtn); right.addWidget(pg)
        sg = QGroupBox("SOUNDBOARD · WAV / OGG / MP3"); sl = QVBoxLayout(sg); self.sounds = QListWidget(); sl.addWidget(self.sounds)
        sound_hint = QLabel("ZIP-y rozpakowują się automatycznie. Obsługiwane: WAV, OGG i MP3.")
        sound_hint.setWordWrap(True); sound_hint.setStyleSheet("color:#aaa0bd;font-size:12px"); sl.addWidget(sound_hint)
        sbtn = QHBoxLayout()
        for label, fn in [("Add WAV",self.add_sound),("Play",self.play_sound),("Remove",self.remove_sound)]:
            b = QPushButton(label); b.clicked.connect(fn); sbtn.addWidget(b)
        sl.addLayout(sbtn); right.addWidget(sg); row.addLayout(right,4); main.addLayout(row)
        note = QLabel("Minecraft-inspired live effects: Villager, Zombie, Skeleton, Creeper, Enderman, Ghast, Witch, Spider, Pig, Cow, Sheep and Ender Dragon. These are generated voice filters, not original Minecraft voice recordings. Add your own WAVs in Soundboard for authentic sounds.")
        note.setWordWrap(True); note.setStyleSheet("color:#aaa0bd;font-size:12px"); main.addWidget(note)
        QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=self.toggle_audio)
        for i,n in enumerate(EFFECTS,1): QShortcut(QKeySequence(f"Ctrl+{i}"),self,activated=lambda name=n:self.set_effect(name))
        self.refresh()

    def filter_effects(self, text):
        query = text.strip().casefold()
        for name, button in self.effect_buttons:
            button.setVisible(query in name.casefold())

    def set_effect(self, name):
        self.engine.effect = name
        self.selected_voice.setText("SELECTED VOICE  ·  " + name)
        for n,b in self.effect_buttons: b.setChecked(n == name)

    def start_audio(self):
        try:
            if self.inputs.currentData() is None or self.outputs.currentData() is None:
                raise RuntimeError("Nie znaleziono mikrofonu lub wyjścia audio.")
            self.engine.start(self.inputs.currentData(), self.outputs.currentData())
            self.start.setEnabled(False); self.stop.setEnabled(True)
            self.status.setText("● RUNNING"); self.status.setStyleSheet("color:#4ade80;font-weight:800")
        except Exception as e:
            QMessageBox.critical(self,"Audio startup failed",f"{e}\n\nSprawdź, czy urządzenia nie są zajęte przez inną aplikację i czy systemowe uprawnienia mikrofonu są włączone.")

    def stop_audio(self):
        self.engine.stop(); self.start.setEnabled(True); self.stop.setEnabled(False)
        self.status.setText("● STOPPED"); self.status.setStyleSheet("color:#f87171;font-weight:800")

    def toggle_audio(self):
        self.stop_audio() if self.engine.stream else self.start_audio()

    def refresh(self):
        self.presets.clear()
        try:
            d = json.loads(PRESETS.read_text(encoding="utf-8")) if PRESETS.exists() else {}
            self.presets.addItems(d.keys())
        except Exception: pass
        extract_sound_archives()
        self.sounds.clear()
        sound_files = [p.name for p in SOUNDS.iterdir()
                       if p.is_file() and p.suffix.lower() in SOUND_EXTENSIONS]
        self.sounds.addItems(sorted(sound_files, key=str.casefold))

    def save_preset(self):
        name, ok = QInputDialog.getText(self,"Save preset","Name:")
        if not ok or not name.strip(): return
        try: d = json.loads(PRESETS.read_text(encoding="utf-8")) if PRESETS.exists() else {}
        except Exception: d = {}
        d[name.strip()] = {"effect":self.engine.effect,"mix":self.engine.mix,"denoise":self.engine.denoise}
        PRESETS.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8"); self.refresh()

    def load_preset(self):
        item = self.presets.currentItem()
        if not item: return
        d = json.loads(PRESETS.read_text(encoding="utf-8"))[item.text()]
        self.set_effect(d.get("effect","Clean")); self.engine.mix = d.get("mix",.8)
        self.mix.setValue(int(self.engine.mix*100)); self.engine.denoise = d.get("denoise",False); self.nr.setChecked(self.engine.denoise)

    def delete_preset(self):
        item = self.presets.currentItem()
        if not item: return
        d = json.loads(PRESETS.read_text(encoding="utf-8")); d.pop(item.text(),None)
        PRESETS.write_text(json.dumps(d,indent=2),encoding="utf-8"); self.refresh()

    def add_sound(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Dodaj dźwięk", "",
            "Pliki audio (*.wav *.ogg *.mp3);;Wszystkie pliki (*)"
        )
        if p:
            import shutil
            shutil.copy2(p, SOUNDS / Path(p).name)
            self.refresh()

    def play_sound(self):
        item = self.sounds.currentItem()
        if item:
            try:
                self.engine.play_file(SOUNDS / item.text(), self.outputs.currentData())
            except Exception as e:
                QMessageBox.critical(self, "Soundboard", f"Nie udało się odtworzyć dźwięku:\n{e}")

    def remove_sound(self):
        item = self.sounds.currentItem()
        if item: (SOUNDS/item.text()).unlink(missing_ok=True); self.refresh()

    def closeEvent(self,event):
        self.engine.stop(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setApplicationName("VoiceForge")
    w = Window(); w.show(); sys.exit(app.exec())
