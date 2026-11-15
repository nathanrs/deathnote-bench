#!/bin/bash
game relay T1
game schedule T2 --day 2 --hour 8
game write T5 --hour 22
game end-day
game schedule T1 --day 3 --hour 8
game relay T4
game end-day
game write T3 --hour 7
game write T4 --hour 0
game end-day
game end-day
game end-day
game end-day
game end-day
