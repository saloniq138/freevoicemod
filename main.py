import sys, json, os, wave
from pathlib import Path
import numpy as np
import sounddevice as sd
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
 QPushButton,QComboBox,QSlider,QCheckBox,QGroupBox,QGridLayout,QMessageBox,QFileDialog,
 QListWidget,QInputDialog)

APP = Path(os.getenv("APPDATA", str(Path.home()))) / "VoiceForge"
APP.mkdir(parents=True, exist_ok=True)
SOUNDS = APP / "sounds"; SOUNDS.mkdir(exist_ok=True)
PRESETS = APP / "presets.json"
EFFECTS = ["Clean", "Robot", "Demon", "Radio", "Echo", "Female/Male pitch", "Villager", "Chicken", "Zombie"]

class Engine:
    def __init__(self):
        self.stream=None; self.effect="Clean"; self.mix=.7; self.denoise=False
        self.echo=np.zeros(48000,dtype=np.float32); self.pos=0; self.phase=0; self.voice_phase=0.0; self.sample_rate=48000
        self.output=None
    def start(self, inp, out):
        self.stop()
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        in_dev, out_dev = devices[int(inp)], devices[int(out)]
        in_api, out_api = int(in_dev["hostapi"]), int(out_dev["hostapi"])
        if in_api != out_api:
            raise RuntimeError(
                "Mikrofon i wyjście używają różnych systemów audio: "
                f"{hostapis[in_api]['name']} oraz {hostapis[out_api]['name']}.\\n\\n"
                "Wybierz urządzenia z tym samym dopiskiem API, np. oba WASAPI albo oba MME."
            )
        self.echo[:] = 0
        self.pos = 0
        self.output = int(out)
        rates = [48000, 44100, int(round(in_dev["default_samplerate"])),
                 int(round(out_dev["default_samplerate"]))]
        rates = list(dict.fromkeys(r for r in rates if r > 0))
        errors = []
        for rate in rates:
            try:
                self.sample_rate = rate
                self.stream = sd.Stream(
                    device=(int(inp), int(out)), samplerate=rate, blocksize=0,
                    channels=(1, 1), dtype="float32", callback=self.cb, latency="high"
                )
                self.stream.start()
                return
            except Exception as exc:
                errors.append(f"{rate} Hz: {exc}")
                if self.stream:
                    try: self.stream.close()
                    except Exception: pass
                    self.stream = None
        raise RuntimeError("Nie udało się uruchomić audio. Próby:\\n" + "\\n".join(errors))
    def stop(self):
        if self.stream:
            try: self.stream.stop(); self.stream.close()
            except Exception: pass
            self.stream=None
    def cb(self, indata,outdata,frames,time_info,status):
        x=indata[:,0].copy()
        if self.denoise and np.sqrt(np.mean(x*x)+1e-12)<.012: x*=.15
        t=(np.arange(frames,dtype=np.float32)+self.phase)/self.sample_rate
        if self.effect=="Robot":
            x=np.tanh(x*2.2)*np.sin(2*np.pi*65*t)
        elif self.effect=="Demon":
            x=np.tanh(x*5.5)*.9 + .18*np.sin(2*np.pi*48*t)*x
        elif self.effect=="Radio":
            x=np.tanh(x*2.8); x=np.concatenate((x[:1],np.diff(x))); x=np.round(x*24)/24
        elif self.effect=="Echo":
            for i in range(frames):
                delayed=self.echo[(self.pos-7200)%len(self.echo)]
                cur=x[i]; self.echo[self.pos]=cur+delayed*.42
                x[i]=cur+delayed*.42; self.pos=(self.pos+1)%len(self.echo)
        elif self.effect=="Female/Male pitch":
            # Lightweight tonal coloration only; this is not a true pitch shifter or AI conversion.
            x=np.tanh(x*1.7)
            x=.75*x+.25*np.concatenate(([x[0]],x[:-1]))
        elif self.effect=="Villager":
            # Nasal, buzzy villager-like coloration with a voiced wobble.
            wobble=.82+.18*np.sin(2*np.pi*5.2*t)
            x=np.tanh(x*3.2)*wobble
            x=.72*x+.28*np.concatenate(([x[0]],x[:-1]))
            x=np.clip(x + .12*np.sin(2*np.pi*145*t)*np.abs(x),-1,1)
        elif self.effect=="Chicken":
            # High, squeaky cartoon-like coloration (not an original Minecraft sound sample).
            squeak=np.sin(2*np.pi*(330+65*np.sin(2*np.pi*7*t))*t)
            x=np.tanh(x*2.4)*.55 + .32*squeak*np.abs(x)
            x=np.concatenate((x[:1],np.diff(x))) * 1.25
        elif self.effect=="Zombie":
            # Low, rough, growly coloration.
            growl=np.sin(2*np.pi*58*t)
            x=np.tanh(x*4.8)*.82 + .25*growl*np.abs(x)
            x=.8*x+.2*np.concatenate(([x[0]],x[:-1]))
        self.phase=(self.phase+frames)%self.sample_rate
        outdata[:,0]=np.clip(x*self.mix,-.98,.98)
    def play_wav(self,path):
        with wave.open(str(path),"rb") as w:
            ch,width,rate,n=w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getnframes()
            if width!=2: raise ValueError("Soundboard wymaga WAV PCM 16-bit.")
            x=np.frombuffer(w.readframes(n),dtype=np.int16).astype(np.float32)/32768
        if ch>1: x=x.reshape(-1,ch).mean(axis=1)
        target_rate = getattr(self, "sample_rate", 48000)
        if rate != target_rate:
            x=np.interp(np.arange(int(len(x)*target_rate/rate))/target_rate,np.arange(len(x))/rate,x).astype(np.float32)
        sd.play(x,target_rate,device=self.output)

class Window(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("VoiceForge"); self.resize(950,680); self.engine=Engine()
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#111018;color:#f3efff;font-size:14px}
        QGroupBox{border:1px solid #39304e;border-radius:12px;margin-top:12px;padding:12px;font-weight:600}
        QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 6px;color:#c6a8ff}
        QPushButton{background:#7c3aed;border:0;border-radius:8px;padding:9px 12px;font-weight:600}
        QPushButton:hover{background:#8b5cf6}
        QComboBox{background:#211b2e;border:1px solid #49395f;border-radius:6px;padding:7px}
        QListWidget{background:#1a1623;border:1px solid #39304e;border-radius:8px}
        QSlider::groove:horizontal{background:#393044;height:6px;border-radius:3px}
        QSlider::handle:horizontal{background:#b58aff;width:16px;margin:-5px 0;border-radius:8px}
        """)
        root=QWidget(); self.setCentralWidget(root); main=QVBoxLayout(root)
        top=QHBoxLayout(); title=QLabel("VoiceForge"); title.setStyleSheet("font-size:30px;font-weight:800;color:#c6a8ff")
        top.addWidget(title); top.addWidget(QLabel("Darmowy zmieniacz głosu na żywo")); top.addStretch()
        self.status=QLabel("● ZATRZYMANY"); top.addWidget(self.status); main.addLayout(top)
        dev=QGroupBox("Urządzenia audio"); dg=QGridLayout(dev)
        self.inputs=QComboBox(); self.outputs=QComboBox()
        hostapis = sd.query_hostapis()
        for i,d in enumerate(sd.query_devices()):
            api = hostapis[int(d["hostapi"])]["name"]
            label = f"{i}: {d['name']} [{api}]"
            if d["max_input_channels"]: self.inputs.addItem(label,i)
            if d["max_output_channels"]: self.outputs.addItem(label,i)
        dg.addWidget(QLabel("Mikrofon"),0,0); dg.addWidget(self.inputs,0,1)
        dg.addWidget(QLabel("Wyjście / wirtualny kabel"),1,0); dg.addWidget(self.outputs,1,1)
        hint=QLabel("Mikrofon i wyjście muszą mieć ten sam dopisek API (np. oba WASAPI albo oba MME). Dla Discord/OBS wybierz wirtualny kabel jako wyjście, a drugi koniec jako mikrofon w aplikacji docelowej.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#b7abc9;font-size:12px"); dg.addWidget(hint,2,0,1,2)
        btns=QHBoxLayout(); self.start=QPushButton("▶ Uruchom mikrofon"); self.stop=QPushButton("■ Zatrzymaj")
        self.stop.setEnabled(False); self.start.clicked.connect(self.start_audio); self.stop.clicked.connect(self.stop_audio)
        btns.addWidget(self.start); btns.addWidget(self.stop); dg.addLayout(btns,3,0,1,2); main.addWidget(dev)
        row=QHBoxLayout(); eg=QGroupBox("Efekty głosu"); el=QGridLayout(eg); self.effect_buttons=[]
        for i,n in enumerate(EFFECTS):
            b=QPushButton(n); b.setCheckable(True); b.clicked.connect(lambda checked,name=n:self.set_effect(name))
            el.addWidget(b,i//2,i%2); self.effect_buttons.append((n,b))
        self.effect_buttons[0][1].setChecked(True)
        el.addWidget(QLabel("Miks / głośność"),3,0,1,2)
        self.mix=QSlider(Qt.Horizontal); self.mix.setRange(0,100); self.mix.setValue(70); self.mix.valueChanged.connect(lambda v:setattr(self.engine,"mix",v/100))
        el.addWidget(self.mix,4,0,1,2); self.nr=QCheckBox("Lekka redukcja szumów"); self.nr.toggled.connect(lambda v:setattr(self.engine,"denoise",v)); el.addWidget(self.nr,5,0,1,2)
        row.addWidget(eg,3)
        right=QVBoxLayout()
        pg=QGroupBox("Własne presety"); pl=QVBoxLayout(pg); self.presets=QListWidget(); pl.addWidget(self.presets)
        pbtn=QHBoxLayout()
        for label,fn in [("Zapisz",self.save_preset),("Wczytaj",self.load_preset),("Usuń",self.delete_preset)]:
            b=QPushButton(label); b.clicked.connect(fn); pbtn.addWidget(b)
        pl.addLayout(pbtn); right.addWidget(pg)
        sg=QGroupBox("Soundboard — WAV"); sl=QVBoxLayout(sg); self.sounds=QListWidget(); sl.addWidget(self.sounds)
        sbtn=QHBoxLayout()
        for label,fn in [("Dodaj",self.add_sound),("Odtwórz",self.play_sound),("Usuń",self.remove_sound)]:
            b=QPushButton(label); b.clicked.connect(fn); sbtn.addWidget(b)
        sl.addLayout(sbtn); right.addWidget(sg); row.addLayout(right,4); main.addLayout(row)
        note=QLabel("Efekt Female/Male jest przybliżeniem tonalnym, nie konwersją AI. Realistyczna konwersja AI wymaga dodatkowego modelu i nie jest jeszcze dostępna.")
        note.setWordWrap(True); note.setStyleSheet("color:#a99dbb;font-size:12px"); main.addWidget(note)
        QShortcut(QKeySequence("Ctrl+Shift+V"),self,activated=self.toggle_audio)
        for i,n in enumerate(EFFECTS,1): QShortcut(QKeySequence(f"Ctrl+{i}"),self,activated=lambda name=n:self.set_effect(name))
        self.refresh()
    def set_effect(self,name):
        self.engine.effect=name
        for n,b in self.effect_buttons: b.setChecked(n==name)
    def start_audio(self):
        try:
            self.engine.start(self.inputs.currentData(),self.outputs.currentData())
            self.start.setEnabled(False); self.stop.setEnabled(True); self.status.setText("● DZIAŁA"); self.status.setStyleSheet("color:#4ade80")
        except Exception as e: QMessageBox.critical(self,"Błąd audio",str(e)+"\nSprawdź urządzenia i ustawienia 48 kHz.")
    def stop_audio(self):
        self.engine.stop(); self.start.setEnabled(True); self.stop.setEnabled(False); self.status.setText("● ZATRZYMANY"); self.status.setStyleSheet("color:#f87171")
    def toggle_audio(self): self.stop_audio() if self.engine.stream else self.start_audio()
    def refresh(self):
        self.presets.clear()
        try:
            d=json.loads(PRESETS.read_text(encoding="utf-8")) if PRESETS.exists() else {}
            self.presets.addItems(d.keys())
        except Exception: pass
        self.sounds.clear(); self.sounds.addItems([p.name for p in sorted(SOUNDS.glob("*.wav"))])
    def save_preset(self):
        name,ok=QInputDialog.getText(self,"Zapisz preset","Nazwa:")
        if not ok or not name.strip(): return
        try: d=json.loads(PRESETS.read_text(encoding="utf-8")) if PRESETS.exists() else {}
        except Exception: d={}
        d[name.strip()]={"effect":self.engine.effect,"mix":self.engine.mix,"denoise":self.engine.denoise}
        PRESETS.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8"); self.refresh()
    def load_preset(self):
        item=self.presets.currentItem()
        if not item:return
        d=json.loads(PRESETS.read_text(encoding="utf-8"))[item.text()]; self.set_effect(d.get("effect","Clean"))
        self.engine.mix=d.get("mix",.7); self.mix.setValue(int(self.engine.mix*100)); self.engine.denoise=d.get("denoise",False); self.nr.setChecked(self.engine.denoise)
    def delete_preset(self):
        item=self.presets.currentItem()
        if not item:return
        d=json.loads(PRESETS.read_text(encoding="utf-8")); d.pop(item.text(),None); PRESETS.write_text(json.dumps(d,indent=2),encoding="utf-8"); self.refresh()
    def add_sound(self):
        p,_=QFileDialog.getOpenFileName(self,"Dodaj WAV","","WAV (*.wav)")
        if p:
            import shutil
            shutil.copy2(p,SOUNDS/Path(p).name); self.refresh()
    def play_sound(self):
        item=self.sounds.currentItem()
        if item:
            try:self.engine.play_wav(SOUNDS/item.text())
            except Exception as e:QMessageBox.critical(self,"Soundboard",str(e))
    def remove_sound(self):
        item=self.sounds.currentItem()
        if item:(SOUNDS/item.text()).unlink(missing_ok=True); self.refresh()
    def closeEvent(self,event): self.engine.stop(); event.accept()

if __name__=="__main__":
    app=QApplication(sys.argv); app.setApplicationName("VoiceForge"); w=Window(); w.show(); sys.exit(app.exec())
