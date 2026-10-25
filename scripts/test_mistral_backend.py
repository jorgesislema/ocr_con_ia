from src.core.backends.mistral_backend import MistralOCRBackend

class FakePage:
    def __init__(self, md):
        self.markdown = md

class FakeResp:
    def __init__(self, pages):
        self.pages = pages
        self.usage_info = type('U', (), {'pages_processed': len(pages)})

class FakeClient:
    class OCR:
        def process(self, model, document):
            return FakeResp([FakePage('# Hola\nTexto extraído')])
    def __init__(self):
        self.ocr = self.OCR()

if __name__ == '__main__':
    b = MistralOCRBackend.__new__(MistralOCRBackend)
    # inicializar campos mínimos sin lanzar (bypass init)
    try:
        MistralOCRBackend.__init__(b)
    except Exception:
        # __init__ may try to read env; ignore for test and set api_key
        b.api_key = 'test'
    b._client = FakeClient()
    res = b.process_base64('dummybase64', mode='standard')
    print('RES:', res)
