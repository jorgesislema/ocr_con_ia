from src.data.template_manager import TemplateManager

if __name__ == '__main__':
    tm = TemplateManager()
    print('templates_dir:', tm.templates_dir)
    name = 'prueba_template'
    schema = {'fields': ['subtotal', 'total', 'numero_factura']}
    path = tm.save_custom_template(name, schema)
    print('Saved:', path)
    loaded = tm.load_available_templates()
    print('Loaded keys:', list(loaded.keys()))
    print('Content for', name, ':', loaded.get('prueba_template'))
