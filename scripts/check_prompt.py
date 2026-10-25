from src.core.prompt_manager import PROMPTS_DIR, load_render_prompt
print('PROMPTS_DIR=', PROMPTS_DIR)
try:
    text, name, checksum = load_render_prompt(['facturas_contable.tpl','default.tpl'], {'profile':'Facturas/Contable','mode':'single_invoice'})
    print('Loaded:', name, 'checksum=', checksum)
    print('Text sample:', text[:120])
except Exception as e:
    print('Error:', e)
