html = open('app/dashboard.html', encoding='utf-8').read()
checks = [
    ('buildCurrencyToggle', 'buildCurrencyToggle' in html),
    ('setBaseCur', 'setBaseCur' in html),
    ('currencyToggle id', 'currencyToggle' in html),
    ('localStorage', 'sasha_base_currency' in html),
]
for name, ok in checks:
    print(f'  {"OK" if ok else "FAIL"}: {name}')
print('Total lines:', html.count('\n'))
