#!/usr/bin/python3
# -*- coding: utf-8 -*-
import sys
from kimp3.config import cfg

if sys.platform[:3] == 'win':
    import msvcrt


    def getkey():
        key = msvcrt.getch()
        return key
elif sys.platform[:3] == 'lin':
    import termios, sys, os

    TERMIOS = termios


    def getkey():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] = new[3] & ~TERMIOS.ICANON & ~TERMIOS.ECHO
        new[6][TERMIOS.VMIN] = 1
        new[6][TERMIOS.VTIME] = 0
        termios.tcsetattr(fd, TERMIOS.TCSANOW, new)
        c = None
        try:
            c = os.read(fd, 1)
        finally:
            termios.tcsetattr(fd, TERMIOS.TCSAFLUSH, old)
        return c


def yes_or_no(question) -> tuple[bool, bool]:
    print(question, end=":")
    while True:
        k = getkey().decode()
        if k.lower() == 'y':
            print('y')
            return True, False
        if k.lower() == 'a':
            print('a')
            return True, True
        if k.lower() == 'n':
            print('n')
            return False, False

def sep_with_header(header: str):
    length = cfg.runtime.console.width
    header = header.center(length, "─")
    return f"\n{header}\n"

if __name__ == "__main__":
    yes_or_no("Ok?")
