import base64

with open('app/static/icons/icon-512.png', 'rb') as f:
    data = f.read()

b64 = base64.b64encode(data).decode('ascii')
svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <image href="data:image/png;base64,{b64}" x="0" y="0" width="512" height="512" />
</svg>'''

with open('app/static/icons/icon.svg', 'w', encoding='utf-8') as f:
    f.write(svg_content)

print('icon.svg successfully generated!')
