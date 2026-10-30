import sys, os
sys.path.insert(0, r'C:\Users\praty\Documents\LASTHOPE')

content = open(r'C:\Users\praty\Documents\LASTHOPE\quantclaw\dashboard.py', encoding='utf-8').read()
print('Total chars in dashboard.py:', len(content))

# Check triple quotes
tq = content.count('"""')
print('Triple quote count:', tq)

# Try to import it
try:
    from quantclaw.dashboard import get_dashboard_html
    html = get_dashboard_html('testtoken', 8000)
    print('Import OK. HTML length:', len(html))
    print('Has LightweightCharts:', 'LightweightCharts' in html)
    print('Has createChart:', 'createChart' in html)
    print('Has </html>:', html.strip().endswith('</html>'))
    print('Has __TOKEN__ unresolved:', '__TOKEN__' in html)
    print('Has __PORT__ unresolved:', '__PORT__' in html)
    # Check the chart init code
    print('Has initCellChart:', 'initCellChart' in html)
    print('Has binance.com:', 'binance.com' in html)
    # Check for JS syntax: look for unmatched braces
    js_start = html.find('<script>')
    js_end = html.rfind('</script>')
    print('Script tag found:', js_start > 0, 'to', js_end)
    print('\nFirst 500 chars of HTML:')
    print(html[:500])
    print('\nLast 300 chars of HTML:')
    print(html[-300:])
except Exception as e:
    print('IMPORT ERROR:', e)
    import traceback
    traceback.print_exc()
