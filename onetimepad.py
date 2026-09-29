#!/usr/bin/env python
# onetimepad.py - Echter Zufallszahlengenerator aus Quantentunnelrauschen
# Ziele: Diehard (inkl. Bitstream-Test), NIST SP 800-22
#
# Ausgabe:
#   onetimepad.txt       ASCII '0'/'1'   (fuer xor.py / dxor.py)
#   onetimepad.txt.bin   echtes Binaer   (fuer Diehard / NIST STS)
#   onetimepad.txt.meta  Metadaten

import os
import sys
import time
import hashlib
import argparse
from math import erfc, sqrt

import numpy as np

try:
    import pyaudio
    HAVE_PYAUDIO = True
except ImportError:
    HAVE_PYAUDIO = False

try:
    import RPi.GPIO as GPIO
    HAVE_GPIO = True
except ImportError:
    HAVE_GPIO = False


# ============================================================
# Konfiguration
# ============================================================
FORMAT      = pyaudio.paInt16 if HAVE_PYAUDIO else None
SPS         = 44100
SECONDS     = 20
CHUNK       = 4096
CHANNELS    = 2
DEVICE_INDEX = None

GPIO_PIN     = 17
GPIO_SAMPLES = 1_000_000


# ============================================================
# Entropie
# ============================================================
def shannon_entropy_bits(bits):
    if len(bits) == 0:
        return 0.0
    p1 = float(bits.mean())
    p0 = 1.0 - p1
    h = 0.0
    for p in (p0, p1):
        if p > 0:
            h -= p * np.log2(p)
    return float(h)


def min_entropy_bits(bits):
    if len(bits) == 0:
        return 0.0
    p1 = float(bits.mean())
    p_max = max(p1, 1.0 - p1)
    if p_max <= 0 or p_max >= 1:
        return 0.0
    return float(-np.log2(p_max))


def monobit_test(bits):
    n = len(bits)
    if n == 0:
        return 0.0, 0.0
    s = int(np.sum(2 * bits.astype(np.int64) - 1))
    s_obs = abs(s) / sqrt(n)
    p_value = erfc(s_obs / sqrt(2))
    return float(s_obs), float(p_value)


def runs_test(bits):
    n = len(bits)
    if n < 100:
        return 0.0, 0.0
    pi = float(bits.mean())
    if abs(pi - 0.5) > (2.0 / sqrt(n)):
        return 0.0, 0.0
    v = 1 + int(np.sum(bits[1:] != bits[:-1]))
    num = abs(v - 2.0 * n * pi * (1 - pi))
    den = 2.0 * sqrt(2.0 * n) * pi * (1 - pi)
    p_value = erfc(num / den)
    return float(v), float(p_value)


# ============================================================
# Diehard Bitstream-Test (Original)
# ============================================================
def diehard_bitstream_test(bits, repeat=20, seed=None):
    """
    Original Diehard Bitstream-Test.

    Der Bitstrom wird als Folge ueberlappender 20-Bit-Woerter betrachtet.
    Gezaehlt wird, wie viele der 2^20 moeglichen 20-Bit-Woerter
    in 2^21 aufeinanderfolgenden, ueberlappenden Fenstern NICHT vorkommen.

    Theoretische Verteilung fuer echten Zufall:
        Mittelwert  = 141909
        Standardabw. = 428

    Benoetigt mindestens 2^21 + 19 = 2.097.171 Bits pro Durchlauf.

    Parameter:
        bits    : np.ndarray uint8 (0/1)
        repeat  : Anzahl Wiederholungen (Diehard-Standard: 20)
        seed    : Zufallsseed fuer Startpositionen

    Rueckgabe:
        Liste der p-Werte (einer pro Durchlauf)
    """
    n = len(bits)
    required_bits = (2**21) + 19
    if n < required_bits:
        print(f"Bitstream: benoetigt {required_bits} Bits, "
              f"vorhanden sind nur {n}")
        return []

    rng = np.random.default_rng(seed)
    p_values = []

    print(f"Diehard Bitstream-Test (Wiederholungen: {repeat})...")

    for r in range(repeat):
        if seed is not None:
            start = int(rng.integers(0, n - required_bits + 1))
        else:
            start = (r * required_bits) % (n - required_bits + 1)

        segment = bits[start:start + required_bits]

        # Ueberlappende 20-Bit-Fenster extrahieren
        window_bits = np.lib.stride_tricks.sliding_window_view(
            segment, 20
        )
        # Jedes 20-Bit-Fenster in eine Ganzzahl umwandeln
        powers = 2 ** np.arange(19, -1, -1)
        values = (window_bits * powers).sum(axis=1)

        # Auftreten markieren
        seen = np.zeros(2**20, dtype=bool)
        seen[values] = True
        missing = int(np.sum(~seen))

        # z-Wert und p-Wert (zweiseitig, Standardnormalverteilung)
        z = (missing - 141909) / 428.0
        p_value = erfc(abs(z) / sqrt(2))
        p_values.append(p_value)

        status = "BESTANDEN" if 0.01 < p_value < 0.99 else "FEHLGESCHLAGEN"
        print(f"  [{r+1:2d}] fehlend={missing:6d}  z={z:+.3f}  "
              f"p={p_value:.6f}  [{status}]")

    passed = sum(1 for p in p_values if 0.01 < p < 0.99)
    print(f"Bitstream: {passed}/{repeat} Durchlaeufe bestanden")
    return p_values


# ============================================================
# Debias / Extraktor
# ============================================================
def von_neumann_debias(bits):
    """
    Von-Neumann-Extraktor:
    Paarweise 01 -> 0, 10 -> 1, 00/11 verworfen.
    Beweisbar unverzerrt, wenn die Paare i.i.d. sind.
    """
    if len(bits) % 2:
        bits = bits[:-1]
    pairs = bits.reshape(-1, 2)
    keep = pairs[:, 0] != pairs[:, 1]
    kept = pairs[keep]
    return kept[:, 0].astype(np.uint8)


def toeplitz_extract(bits, out_bits, seed=None):
    """
    Toeplitz-Hash-Extraktor (universeller Extrakor).
    Leftover-Hash-Lemma: Wenn die Min-Entropie der Eingabe
    ausreicht, ist die Ausgabe statistisch nahezu uniform.
    """
    n = len(bits)
    if out_bits > n:
        raise ValueError(f"out_bits ({out_bits}) > Eingabe-Bits ({n})")
    rng = np.random.default_rng(seed)
    col = rng.integers(0, 2, size=out_bits, dtype=np.uint8)
    row = rng.integers(0, 2, size=n - out_bits + 1, dtype=np.uint8)
    out = np.zeros(out_bits, dtype=np.uint8)
    for i in range(out_bits):
        acc = 0
        jmax = min(i, n - 1)
        if jmax >= 0:
            seg = bits[:jmax + 1] & col[i - np.arange(jmax + 1)]
            if len(seg):
                acc ^= int(np.bitwise_xor.reduce(seg))
        if i + 1 <= n - 1:
            seg = bits[i + 1:] & row[1:n - i]
            if len(seg):
                acc ^= int(np.bitwise_xor.reduce(seg))
        out[i] = acc & 1
    return out


# ============================================================
# Hardware
# ============================================================
def mic_record(seconds=SECONDS, device_index=DEVICE_INDEX):
    """Zener-Diode am Mikrofoneingang / ADC. Liefert int32-Samples."""
    if not HAVE_PYAUDIO:
        raise RuntimeError("pyaudio ist nicht installiert")
    p = pyaudio.PyAudio()
    width = p.get_sample_size(FORMAT)
    stream = p.open(
        format=FORMAT, rate=SPS, channels=CHANNELS,
        input_device_index=device_index, input=True,
        frames_per_buffer=CHUNK,
    )
    print("ADC-Stream starten (Zener-Rauschen)")
    stream.start_stream()
    frames = []
    for _ in range(int(SPS / CHUNK * seconds)):
        frames.append(stream.read(CHUNK, exception_on_overflow=False))
    stream.stop_stream()
    stream.close()
    p.terminate()
    print("ADC-Stream stoppen")

    raw = b"".join(frames)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.int32)
    if CHANNELS == 2:
        samples = samples.reshape(-1, 2).mean(axis=1).astype(np.int32)
    return width, samples


def gpio_jitter_record(n_samples=GPIO_SAMPLES, pin=GPIO_PIN):
    """
    Komparator am GPIO. Misst die Zeit zwischen Flanken.
    Paritaet der Nanosekunden-Differenz -> Bit.
    """
    if not HAVE_GPIO:
        raise RuntimeError("RPi.GPIO ist nicht verfuegbar")
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    bits = np.empty(n_samples, dtype=np.uint8)
    last = GPIO.input(pin)
    t_last = time.perf_counter_ns()
    i = 0
    print("Warte auf Flanken am GPIO...")
    while i < n_samples:
        cur = GPIO.input(pin)
        if cur != last:
            t_now = time.perf_counter_ns()
            dt = t_now - t_last
            bits[i] = dt & 1
            t_last = t_now
            last = cur
            i += 1
    GPIO.cleanup()
    return bits


def raw_bits_from_adc(samples, n_lsb=1):
    """
    Nutzt die niederwertigsten n_lsb Bits jedes Samples.
    Bei Zener-Rauschen ist das LSB am staerksten rauschdominiert.
    """
    u = (samples.astype(np.int32) + 32768).astype(np.uint16)
    if n_lsb == 1:
        return (u & 1).astype(np.uint8)
    outs = [((u >> b) & 1).astype(np.uint8) for b in range(n_lsb)]
    return np.concatenate(outs)


# ============================================================
# Pipeline
# ============================================================
def generate_onetimepad(n_bits, source="adc", seconds=SECONDS,
                        use_toeplitz=True, seed=None):
    if source == "adc":
        _, samples = mic_record(seconds=seconds)
        print(f"Samples: {len(samples)}")
        raw = raw_bits_from_adc(samples, n_lsb=1)
    elif source == "gpio":
        raw = gpio_jitter_record()
    else:
        raise ValueError("source muss 'adc' oder 'gpio' sein")

    print(f"Rohbits: {len(raw)} | "
          f"H_shannon={shannon_entropy_bits(raw):.5f} | "
          f"H_min={min_entropy_bits(raw):.5f}")

    debiased = von_neumann_debias(raw)
    print(f"Nach Von Neumann: {len(debiased)} | "
          f"H_shannon={shannon_entropy_bits(debiased):.5f} | "
          f"H_min={min_entropy_bits(debiased):.5f}")

    if use_toeplitz:
        if len(debiased) < n_bits:
            print(f"WARNUNG: nur {len(debiased)} debiased Bits, "
                  f"benoetigt werden {n_bits}. Kuerze Ausgabe.")
            n_bits = len(debiased)
        hmin_total = min_entropy_bits(debiased) * len(debiased)
        safe_out = int(min(n_bits, hmin_total // 2))
        if safe_out < 1:
            raise RuntimeError("Zu wenig Min-Entropie fuer Toeplitz.")
        print(f"Toeplitz: hmin_total={hmin_total:.0f} | safe_out={safe_out}")
        final = toeplitz_extract(debiased, safe_out, seed=seed)
    else:
        final = debiased[:n_bits]

    s_obs, p_mono = monobit_test(final)
    v_runs, p_runs = runs_test(final)
    print(f"Monobit : S_obs={s_obs:.4f} | p={p_mono:.6f} "
          f"({'BESTANDEN' if p_mono > 0.01 else 'FEHLGESCHLAGEN'})")
    print(f"Runs    : V={v_runs:.0f} | p={p_runs:.6f} "
          f"({'BESTANDEN' if p_runs > 0.01 else 'FEHLGESCHLAGEN'})")
    print(f"Final   : {len(final)} Bits | "
          f"H_shannon={shannon_entropy_bits(final):.5f} | "
          f"H_min={min_entropy_bits(final):.5f}")
    return final


# ============================================================
# Ausgabe
# ============================================================
def save_bits_ascii(bits, path):
    """ASCII '0'/'1' - fuer xor.py / dxor.py."""
    with open(path, "w") as f:
        f.write("".join(map(str, bits.tolist())))


def save_bits_binary(bits, path):
    """
    Echtes Binaerformat: 8 Bits -> 1 Byte, MSB zuerst.
    Auffuellen mit 0 am Ende, falls nicht durch 8 teilbar.
    """
    pad = (-len(bits)) % 8
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    packed = np.packbits(bits.astype(np.uint8), bitorder="big")
    with open(path, "wb") as f:
        f.write(packed.tobytes())
    return len(packed)


def save_metadata(bits, path):
    meta = {
        "n_bits":            int(len(bits)),
        "ones":              int(bits.sum()),
        "zeros":             int(len(bits) - bits.sum()),
        "shannon_entropy":   shannon_entropy_bits(bits),
        "min_entropy":       min_entropy_bits(bits),
        "sha256":            hashlib.sha256(bits.tobytes()).hexdigest(),
        "timestamp":         time.time(),
    }
    with open(path, "w") as f:
        for k, v in meta.items():
            f.write(f"{k}: {v}\n")


def show_devices():
    if not HAVE_PYAUDIO:
        print("pyaudio ist nicht installiert.")
        return
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"[{i}] {info.get('name')} (in={info.get('maxInputChannels')})")
    p.terminate()


# ============================================================
# Kommandozeile
# ============================================================
def main():
    ap = argparse.ArgumentParser(
        description="Quantentunnel-RNG -> One-Time-Pad (+ Diehard Bitstream)"
    )
    ap.add_argument("--source", choices=["adc", "gpio"], default="adc")
    ap.add_argument("--seconds", type=int, default=SECONDS)
    ap.add_argument("--bits", type=int, default=200_000)
    ap.add_argument("--out", default="onetimepad.txt")
    ap.add_argument("--no-toeplitz", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--diehard", action="store_true",
                    help="Diehard Bitstream-Test ausfuehren")
    args = ap.parse_args()

    if args.source == "adc":
        show_devices()

    bits = generate_onetimepad(
        n_bits=args.bits,
        source=args.source,
        seconds=args.seconds,
        use_toeplitz=not args.no_toeplitz,
        seed=args.seed,
    )

    # ASCII
    save_bits_ascii(bits, args.out)
    print(f"Geschrieben: {args.out} ({len(bits)} ASCII-Bits)")

    # Binaer
    bin_path = args.out + ".bin"
    n_bytes = save_bits_binary(bits, bin_path)
    print(f"Geschrieben: {bin_path} ({n_bytes} Bytes = "
          f"{n_bytes * 8} Bits)")

    # Metadaten
    meta_path = args.out + ".meta"
    save_metadata(bits, meta_path)
    print(f"Geschrieben: {meta_path}")

    # Diehard Bitstream-Test (optional)
    if args.diehard:
        print("\n" + "=" * 60)
        diehard_bitstream_test(bits, repeat=20, seed=args.seed)


if __name__ == "__main__":
    main()