# -*- coding: utf-8 -*-
from pathlib import Path

path = Path('pages/4_\U0001F466_Escuteiros.py')
lines = path.read_text(encoding='utf-8').splitlines()
for i, line in enumerate(lines):
    if '###' in line and 'Formul' in line:
        lines[i] = '    ### \U0001F9FA Formulario de Marcacao de Lanche'
        if i + 1 < len(lines):
            lines[i + 1] = '    Preencha o formulario abaixo para marcar o lanche do seu escuteiro.'
        break
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
