"""Resource-limited PDF worker. Input/output stay in memory; no uploads are persisted."""
import io
import json
import sys


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        from pypdf import PdfReader
        content = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            raise ValueError('PDF deve ter no máximo 4 MB.')
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise ValueError('Exporte uma cópia do PDF sem senha para importar.')
        if len(reader.pages) > 30:
            raise ValueError('Importe no máximo 30 páginas por arquivo.')
        parts = []
        size = 0
        for page in reader.pages:
            part = page.extract_text(extraction_mode='layout') or ''
            size += len(part)
            if size > 500_000:
                raise ValueError('O conteúdo é muito extenso. Divida o extrato em arquivos menores.')
            parts.append(part)
        text = '\n'.join(parts)
        if not text.strip():
            raise ValueError('Este PDF não tem texto legível. Use um PDF com texto selecionável, CSV ou OFX.')
        print(json.dumps({'text': text}))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}))
    except Exception:
        print(json.dumps({'error': 'Não foi possível ler este PDF. Exporte novamente pelo banco ou use CSV/OFX.'}))


if __name__ == '__main__':
    main()
