import os, re

pine_dir = r'C:\Users\praty\Documents\LASTHOPE\pine'
for f in os.listdir(pine_dir):
    if f.endswith('.pine'):
        content = open(os.path.join(pine_dir, f), encoding='utf-8').read()
        print(f'{f}: {len(content)} chars')

srv = open(r'C:\Users\praty\Documents\LASTHOPE\quantclaw\server.py', encoding='utf-8').read()
print('\nServer length:', len(srv))
# Find routes
for m in re.finditer(r'@app\.(get|post)\("(/[^"]+)"', srv):
    print(f'  {m.group(1).upper()} {m.group(2)}')
