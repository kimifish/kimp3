#!/usr/bin/python3
# -*- coding: utf-8 -*-
import sys
from kimp3.config import cfg
from time import sleep

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


def yes_or_no(question: str, options: str = "ynA") -> str:
    """Ask user a question and wait for single key response.
    
    Args:
        question: Question to display
        options: String containing allowed key responses (case sensitive)
    
    Returns:
        Pressed key
    """
    print(f"{question} [{'/'.join(options)}]", end=": ", flush=True)
    while True:
        k = getkey().decode()
        if k in options:
            print(k)
            return k

def sep_with_header(header: str):
    length = cfg.runtime.console.width
    header = header.center(length, "─")
    return f"\n{header}\n"

if __name__ == "__main__":
    yes_or_no("Ok?")
