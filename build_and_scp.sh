#!/usr/bin/env bash

python cad/erb_lower_chassis.py

python scripts/sync_text_to_cad.py --skip-cad-generate

scp exports.tar.gz jfurr@laptop:/Users/jfurr/

