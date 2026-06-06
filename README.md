# Transcritor

Ferramenta pessoal de transcrição de áudio em texto (PT-BR). Upload de um arquivo
→ transcrição via Gemini (Google AI Studio) → texto editável, copiável e baixável.

Sem login, sem banco, sem histórico. Documentação no vault:
`03_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/03_TRANSCRITOR_AUDIO/`.

## Stack

- Python 3 + FastAPI
- google-genai (File API do Gemini)
- Frontend estático servido pelo próprio FastAPI (sem build step)

## Como rodar

```powershell
# 1. Criar e ativar a venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar a chave
copy .env.example .env
# edite .env e preencha GEMINI_API_KEY=... (gerada no Google AI Studio)

# 4. Subir o servidor
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000

## Notas

- A `GEMINI_API_KEY` fica só no `.env` (ignorado pelo Git). Nunca vai pro browser.
- Modelo padrão: `gemini-2.5-flash`. Sobrescreva com `GEMINI_MODEL` no `.env`.
- Formatos aceitos nativamente pelo Gemini: wav, mp3, aiff, aac, ogg, flac.
  Outros (ex: `.m4a`, `.opus`, `.wma`) são convertidos para flac via **ffmpeg**
  automaticamente (precisa do ffmpeg no PATH).
- Teto de upload: `MAX_UPLOAD_MB` no `.env` (default 100 MB).
- **Privacidade:** no free tier do AI Studio o Google pode usar os dados para
  melhorar os produtos dele. Evite áudio sensível.
