#!/bin/bash
game schedule T3 --day 2 --hour 20
game schedule T2 --day 2 --hour 20
game end-day
game relay T5
game write T6 --hour 0
game write T1 --hour 1
game write T4 --hour 0
game end-day
game write T5 --hour 1
game end-day
game end-day
game end-day
game end-day
game end-day
