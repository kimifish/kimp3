#!/usr/bin/python
#  -*- coding: utf-8 -*-

import eyed3
import sys

mp3 = eyed3.load("/home/kimifish/Музыка/#####/В этой Жизни Меня Подводят Доброта и Пор/02 Мертвое Пламя.mp3")
comments = mp3.tag.comments
print(comments)
x = comments.get(u"Rating")
print(x)
if x is None:
    print("No rating")
else:
    print(x.text)

