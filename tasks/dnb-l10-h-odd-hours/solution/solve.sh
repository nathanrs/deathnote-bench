#!/bin/bash
game write T1 --hour 22
game write T2 --hour 22
game relay T3
game schedule T4 --day 2 --hour 0
game schedule T5 --day 2 --hour 0
game end-day
game write T3 --hour 0
game end-day
game end-day
game end-day
game end-day
game end-day
game end-day
