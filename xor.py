#!/usr/bin/env python
# xor.py - One-Time-Pad-Verschluesselung
#
# Liest:
#   template.tex     Klartext (ASCII, latin, englische Tastatur)
#   onetimepad.txt   One-Time-Pad (ASCII '0'/'1', wird verbraucht)
#
# Schreibt:
#   <timestamp>.txt          verbrauchter Pad-Abschnitt (mit Zeitstempel)
#   secret<timestamp>.txt    Geheimtext (ASCII '0'/'1')
#
# WICHTIG: Der Pad wird nach Gebrauch gekuerzt (verbrauchte Bits entfernt).

import os
import sys
import time
import calendar
import codecs

# ============================================================
# Konfiguration
# ============================================================
# Der Pad wird bei jedem Aufruf verbraucht.
# Die verbrauchten Bits werden in <timestamp>.txt gespeichert,
# der Rest verbleibt in onetimepad.txt.

PAD_FILE   = "onetimepad.txt"
TEXT_FILE  = "template.tex"
USED_PREFIX = ""              # Praefix fuer die verbrauchte Pad-Datei
SECRET_PREFIX = "secret"      # Praefix fuer die Geheimtext-Datei


# ============================================================
# Binaer-Tabelle: ASCII-Zeichen -> 7-Bit-Code
# ============================================================
def char_to_bits(ch):
    """
    Wandelt ein druckbares ASCII-Zeichen in seinen 7-Bit-Code um.
    Gibt None zurueck, wenn das Zeichen nicht unterstuetzt wird.
    """
    # Zeilenumbruch
    if ch == u'\u000A':
        return "0000000"
    # Leerzeichen
    if ch == u'\u0020':
        return "0100000"
    # Backtick
    if ch == u'\u0060':
        return "0010000"

    # Alle druckbaren ASCII-Zeichen 0x21 - 0x7E
    # (mit Ausnahme der bereits behandelten)
    mapping = {
        '!': "0100001", '"': "0100010", '#': "0100011", '$': "0100100",
        '%': "0100101", '&': "0100110", "'": "0100111", '(': "0101000",
        ')': "0101001", '*': "0101010", '+': "0101011", ',': "0101100",
        '-': "0101101", '.': "0101110", '/': "0101111",
        '0': "0110000", '1': "0110001", '2': "0110010", '3': "0110011",
        '4': "0110100", '5': "0110101", '6': "0110110", '7': "0110111",
        '8': "0111000", '9': "0111001", ':': "0111010", ';': "0111011",
        '<': "0111100", '=': "0111101", '>': "0111110", '?': "0111111",
        '@': "1000000",
        'A': "1000001", 'B': "1000010", 'C': "1000011", 'D': "1000100",
        'E': "1000101", 'F': "1000110", 'G': "1000111", 'H': "1001000",
        'I': "1001001", 'J': "1001010", 'K': "1001011", 'L': "1001100",
        'M': "1001101", 'N': "1001110", 'O': "1001111", 'P': "1010000",
        'Q': "1010001", 'R': "1010010", 'S': "1010011", 'T': "1010100",
        'U': "1010101", 'V': "1010110", 'W': "1010111", 'X': "1011000",
        'Y': "1011001", 'Z': "1011010",
        '[': "1011011", '\\': "1011100", ']': "1011101", '^': "1011110",
        '_': "1011111",
        'a': "1100001", 'b': "1100010", 'c': "1100011", 'd': "1100100",
        'e': "1100101", 'f': "1100110", 'g': "1100111", 'h': "1101000",
        'i': "1101001", 'j': "1101010", 'k': "1101011", 'l': "1101100",
        'm': "1101101", 'n': "1101110", 'o': "1101111", 'p': "1110000",
        'q': "1110001", 'r': "1110010", 's': "1110011", 't': "1110100",
        'u': "1110101", 'v': "1110110", 'w': "1110111", 'x': "1111000",
        'y': "1111001", 'z': "1111010",
        '{': "1111011", '|': "1111100", '}': "1111101", '~': "1111110",
    }
    return mapping.get(ch, None)


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
# Kernfunktion: Verschluesselung
# ============================================================
def encrypt_file(ts_file, text_file, pad_file, secret_file):
    """
    Verschlusselt text_file mit pad_file (XOR).
    Verbrauchte Pad-Bits werden in ts_file gespeichert,
    der Rest verbleibt in pad_file.
    """
    # Klartext einlesen
    if not os.path.exists(text_file):
        print(f"FEHLER: {text_file} nicht gefunden.")
        return False
    if not os.path.exists(pad_file):
        print(f"FEHLER: {pad_file} nicht gefunden.")
        return False

    with codecs.open(text_file, 'r', 'utf-8') as f:
        text = f.read()

    # Klartext in 7-Bit-Codes umwandeln
    lst = []
    counter = 0
    for ch in text:
        code = char_to_bits(ch)
        if code is None:
            print(f"Zeichen nicht unterstuetzt: {repr(ch)}")
            counter += 1
            continue
        lst.append(code)

    print(f"Nicht unterstuetzte Zeichen: {counter}")
    print(f"Zu verschluesselnde Zeichen: {len(lst)}")

    # Pad einlesen
    with open(pad_file, 'r') as f:
        pad = f.read().replace('\n', '').replace('\r', '')

    needed = len(lst) * 7
    if len(pad) < needed:
        print(f"FEHLER: Pad zu kurz. Benoetigt {needed} Bits, "
              f"vorhanden {len(pad)} Bits.")
        return False

    # XOR durchfuehren
    used_bits = []
    secret_bits = []
    idx = 0
    for code in lst:
        for k in code:
            c = pad[idx]
            idx += 1
            used_bits.append(c)
            if int(k) + int(c) == 1:
                secret_bits.append('1')
            else:
                secret_bits.append('0')

    # Verbrauchten Pad-Abschnitt schreiben
    with open(ts_file, 'w') as f:
        f.write(''.join(used_bits))

    # Geheimtext schreiben
    with open(secret_file, 'w') as f:
        f.write(''.join(secret_bits))

    # Pad kuerzen
    rest = pad[idx:]
    with open(pad_file, 'w') as f:
        f.write(rest)

    print(f"Verbraucht: {idx} Pad-Bits")
    print(f"Verbleibend: {len(rest)} Pad-Bits")
    return True


# ============================================================
# Hauptprogramm
# ============================================================
def main():
    current_gmt = time.gmtime()
    ts = calendar.timegm(current_GMT)

    print("=" * 60)
    print("One-Time-Pad-Verschluesselung")
    print("=" * 60)
    print("Hinweis: Bitte lateinische Buchstaben und eine")
    print("         englische Tastatur verwenden.")
    print("Warnung: Der One-Time-Pad wird um die Laenge der")
    print("         Nachricht gekuerzt (verbraucht).")
    print("=" * 60)

    ts_file     = str(ts) + ".txt"
    secret_file = SECRET_PREFIX + str(ts) + ".txt"

    success = encrypt_file(ts_file, TEXT_FILE, PAD_FILE, secret_file)
    if success:
        print(f"Erfolg! Geheimtext: {secret_file}")
        print(f"Verbrauchter Pad:  {ts_file}")
    else:
        print("Verschluesselung fehlgeschlagen.")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())