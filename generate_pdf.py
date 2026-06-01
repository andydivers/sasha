"""Generate Sasha pitch PDF from DECK.html content."""
import os

# Check what's available
for mod_name in ['fpdf', 'reportlab', 'weasyprint', 'pdfkit']:
    try:
        exec(f'import {mod_name}')
        print(f'{mod_name} available')
    except ImportError:
        print(f'{mod_name} not available')
