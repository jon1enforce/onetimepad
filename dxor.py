#!/usr/bin/env python
# dxor.py - One-Time-Pad-Entschluesselung
#
# Liest:
#   secret<timestamp>.txt    Geheimtext (ASCII '0'/'1')
#   <timestamp>.txt          verbrauchter Pad-Abschnitt
#
# Schreibt:
#   <timestamp>.READ.tex     entschluesselter Klartext
#
# Danach kann pdflatex aufgerufen werden, um eine PDF zu erzeugen.

import os
import sys
import time
import calendar
import subprocess


# ============================================================
# Binaer-Tabelle: 7-Bit-Code -> ASCII-Zeichen
# ============================================================
def bits_to_char(bits):
    """
    Wandelt einen 7-Bit-Code zurueck in ein ASCII-Zeichen.
    Gibt None zurueck, wenn der Code unbekannt ist.
    """
    reverse = {
        "0000000": u'\u000A',   # Zeilenumbruch
        "0100000": u'\u0020',   # Leerzeichen
        "0010000": u'\u0060',   # Backtick
        "0100001": '!',  "0100010": '"',  "0100011": '#',  "0100100": '$',
        "0100101": '%',  "0100110": '&',  "0100111": "'",  "0101000": '(',
        "0101001": ')',  "0101010": '*',  "0101011": '+',  "0101100": ',',
        "0101101": '-',  "0101110": '.',  "0101111": '/',
        "0110000": '0',  "0110001": '1',  "0110010": '2',  "0110011": '3',
        "0110100": '4',  "0110101": '5',  "0110110": '6',  "0110111": '7',
        "0111000": '8',  "0111001": '9',  "0111010": ':',  "0111011": ';',
        "0111100": '<',  "0111101": '=',  "0111110": '>',  "0111111": '?',
        "1000000": '@',
        "1000001": 'A',  "1000010": 'B',  "1000011": 'C',  "1000100": 'D',
        "1000101": 'E',  "1000110": 'F',  "1000111": 'G',  "1001000": 'H',
        "1001001": 'I',  "1001010": 'J',  "1001011": 'K',  "1001100": 'L',
        "1001101": 'M',  "1001110": 'N',  "1001111": 'O',  "1010000": 'P',
        "1010001": 'Q',  "1010010": 'R',  "1010011": 'S',  "1010100": 'T',
        "1010101": 'U',  "1010110": 'V',  "1010111": 'W',  "1011000": 'X',
        "1011001": 'Y',  "1011010": 'Z',
        "1011011": '[',  "1011100": '\\', "1011101": ']',  "1011110": '^',
        "1011111": '_',
        "1100001": 'a',  "1100010": 'b',  "1100011": 'c',  "1100100": 'd',
        "1100101": 'e',  "1100110": 'f',  "1100111": 'g',  "1101000": 'h',
        "1101001": 'i',  "1101010": 'j',  "1101011": 'k',  "1101100": 'l',
        "1101101": 'm',  "1101110": 'n',  "1101111": 'o',  "1110000": 'p',
        "1110001": 'q',  "1110010": 'r',  "1110011": 's',  "1110100": 't',
        "1110101": 'u',  "1110110": 'v',  "1110111": 'w',  "1111000": 'x',
        "1111001": 'y',  "1111010": 'z',
        "1111011": '{',  "1111100": '|',  "1111101": '}',  "1111110": '~',
    }
    return reverse.get(bits, None)


# ============================================================
# Kernfunktion: Entschluesselung
# ============================================================
def decrypt_file(secret_file, pad_file, out_file):
    """
    Entschluesselt secret_file mit pad_file (XOR).
    Schreibt Klartext nach out_file.
    """
    if not os.path.exists(secret_file):
        print(f"FEHLER: {secret_file} nicht gefunden.")
        return False
    if not os.path.exists(pad_file):
        print(f"FEHLER: {pad_file} nicht gefunden.")
        return False

    with open(secret_file, 'r') as f:
        secret = f.read().replace('\n', '').replace('\r', '')
    with open(pad_file, 'r') as f:
        pad = f.read().replace('\n', '').replace('\r', '')

    if len(secret) != len(pad):
        print(f"WARNUNG: Laengen unterschiedlich: "
              f"secret={len(secret)}, pad={len(pad)}")
    n = min(len(secret), len(pad))

    # XOR rueckgaengig machen
    plain_bits = []
    for i in range(n):
        if int(secret[i]) + int(pad[i]) == 1:
            plain_bits.append('1')
        else:
            plain_bits.append('0')

    # Bits in Zeichen umwandeln (7-Bit-Gruppen)
    text = []
    error_count = 0
    for i in range(0, len(plain_bits) - 6, 7):
        code = ''.join(plain_bits[i:i+7])
        ch = bits_to_char(code)
        if ch is None:
            error_count += 1
            continue
        text.append(ch)

    print(f"Entschluesselte Zeichen: {len(text)}")
    print(f"Nicht druckbare Zeichen: {error_count}")

    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(''.join(text))

    return True


# ============================================================
# Hauptprogramm
# ============================================================
def main():
    print("=" * 60)
    print("One-Time-Pad-Entschluesselung")
    print("=" * 60)
    print("Dieses Skript nimmt die aeltesten 2 Dateien im Ordner:")
    print("  - secret<timestamp>.txt  (Geheimtext)")
    print("  - <timestamp>.txt        (verbrauchter Pad)")
    print("und erzeugt daraus:")
    print("  - <timestamp>.READ.tex   (Klartext)")
    print()
    print("WICHTIG: Nach dem Lesen sollten die Eingabe-.txt-Dateien")
    print("         geloescht werden. Ordner sauber halten.")
    print("=" * 60)

    # Alle Dateien sammeln
    entries = []
    for name in os.listdir('.'):
        if name.endswith('.txt') and name.startswith('secret'):
            ts = name[len('secret'):-len('.txt')]
            pad_name = ts + '.txt'
            if os.path.exists(pad_name):
                entries.append((name, pad_name, ts))

    if not entries:
        print("Keine passenden Datei-Paare gefunden.")
        print("Erwartet: secret<timestamp>.txt UND <timestamp>.txt")
        return 1

    # Nach Zeitstempel sortieren (aelteste zuerst)
    entries.sort(key=lambda e: int(e[2]) if e[2].isdigit() else 0)

    for secret_file, pad_file, ts in entries:
        out_file = ts + '.READ.tex'
        print()
        print(f"Verarbeite: {secret_file} + {pad_file}")
        ok = decrypt_file(secret_file, pad_file, out_file)
        if not ok:
            print(f"FEHLER bei {secret_file}, ueberspringe.")
            continue

        print(f"Geschrieben: {out_file}")

        # Optional: pdflatex aufrufen
        try:
            subprocess.run(['pdflatex', '-interaction=nonstopmode',
                            out_file],
                           check=False,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            print(f"pdflatex ausgefuehrt auf {out_file}")
        except FileNotFoundError:
            print("pdflatex nicht gefunden, ueberspringe PDF-Erzeugung.")

    print()
    print("Fertig. Bitte die .txt-Eingabedateien loeschen.")
    return 0


if __name__ == '__main__':
    sys.exit(main())