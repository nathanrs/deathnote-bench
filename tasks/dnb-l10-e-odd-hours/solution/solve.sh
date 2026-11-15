#!/bin/bash
game schedule T1 --day 2 --hour 8
game write T3 --hour 1
game relay T4
game end-day
game relay T2
game write T4 --hour 0
game end-day
game schedule T2 --day 4 --hour 0
game write T5 --hour 5
game end-day
game end-day
game end-day
game end-day
game end-day
