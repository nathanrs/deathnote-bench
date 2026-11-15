#!/bin/bash
game schedule T1 --day 2 --hour 10
game relay T4
game end-day
game write T3 --hour 4
game write T4 --hour 0
game end-day
game end-day
game end-day
game relay T5
game end-day
game schedule T2 --day 7 --hour 10
game write T5 --hour 0
game end-day
game end-day
