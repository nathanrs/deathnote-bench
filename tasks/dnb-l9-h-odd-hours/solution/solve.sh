#!/bin/bash
game write T1 --hour 22
game write T2 --hour 22
game schedule T3 --day 2 --hour 0
game schedule T4 --day 2 --hour 0
game relay T5
game end-day
game write T5 --hour 0
game end-day
game end-day
game end-day
game end-day
game end-day
game end-day
