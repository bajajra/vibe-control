"""
Voice dictation handler — records while R1 is held, transcribes on release.
Uses PyAudio for recording and Google Speech Recognition for transcription.
"""

import threading
import subprocess
import time

import pyaudio
import speech_recognition as sr


class DictationHandler:

    SAMPLE_RATE = 16000
    CHANNELS = 1
    CHUNK = 1024
    FORMAT = pyaudio.paInt16

    def __init__(self, engine="google", language="en-US"):
        self.engine = engine
        self.language = language
        self.recognizer = sr.Recognizer()

        self._recording = False
        self._frames = []
        self._audio_iface = None
        self._stream = None
        self._on_transcription = None
        self._on_status = None
        self.mic_available = self._check_mic()

    @staticmethod
    def _check_mic():
        try:
            p = pyaudio.PyAudio()
            p.get_default_input_device_info()
            p.terminate()
            return True
        except OSError:
            return False
        except Exception:
            return False

    def set_callbacks(self, on_transcription=None, on_status=None):
        self._on_transcription = on_transcription
        self._on_status = on_status

    def _emit_status(self, status):
        if self._on_status:
            self._on_status(status)

    @property
    def is_recording(self):
        return self._recording

    def start_recording(self):
        if self._recording:
            return
        if not self.mic_available:
            self._emit_status("no_mic")
            print("  [WARN] No microphone found — plug in an external mic or headset")
            return
        self._recording = True
        self._frames = []
        self._emit_status("recording")
        try:
            self._audio_iface = pyaudio.PyAudio()
            self._stream = self._audio_iface.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.SAMPLE_RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
                stream_callback=self._audio_cb,
            )
            self._stream.start_stream()
        except Exception as exc:
            self._emit_status(f"mic_error: {exc}")
            self._recording = False

    def _audio_cb(self, in_data, frame_count, time_info, status):
        if self._recording:
            self._frames.append(in_data)
            return (in_data, pyaudio.paContinue)
        return (in_data, pyaudio.paComplete)

    def stop_recording(self):
        if not self._recording:
            return
        self._recording = False

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._audio_iface:
            try:
                self._audio_iface.terminate()
            except Exception:
                pass
            self._audio_iface = None

        if len(self._frames) < 5:
            self._emit_status("too_short")
            return

        self._emit_status("transcribing")
        threading.Thread(target=self._transcribe, daemon=True).start()

    def _transcribe(self):
        try:
            raw = b"".join(self._frames)
            # 2 bytes per sample for paInt16
            audio = sr.AudioData(raw, self.SAMPLE_RATE, 2)

            if self.engine == "google":
                text = self.recognizer.recognize_google(audio, language=self.language)
            else:
                text = self.recognizer.recognize_google(audio, language=self.language)

            if text:
                self._emit_status("typing")
                if self._on_transcription:
                    self._on_transcription(text)
            self._emit_status("idle")

        except sr.UnknownValueError:
            self._emit_status("not_understood")
            time.sleep(1.5)
            self._emit_status("idle")
        except sr.RequestError as exc:
            self._emit_status(f"api_error: {exc}")
            time.sleep(2)
            self._emit_status("idle")
        except Exception as exc:
            self._emit_status(f"error: {exc}")
            time.sleep(2)
            self._emit_status("idle")

    def cleanup(self):
        self._recording = False
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
        if self._audio_iface:
            try:
                self._audio_iface.terminate()
            except Exception:
                pass
