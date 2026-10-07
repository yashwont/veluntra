# Free local AI with Ollama

By default Veluntra's assistant is a small rule-based **demo** that understands a handful of phrasings.
With [Ollama](https://ollama.com) you can run a real AI model **on your own computer** instead:

- **Free.** No account, no API key, no per-message cost.
- **Private.** Your tasks, notes and documents never leave your machine.
- **Honest about its limits.** Small local models are far less capable than the big hosted ones. They
  misunderstand things and sometimes pick the wrong tool, and on a laptop without a graphics card they are
  slow. The safety design doesn't change: every action still goes through the same validation, and the
  assistant's reply lists exactly what it did.

You can also use Ollama for **search embeddings**, so documents and memories are found by *meaning*
("car" finds "automobile") instead of by shared words.

## Will my computer cope?

A rough guide for a computer **without a dedicated graphics card** (the model runs on the processor):

| Model | Download | Memory it needs | Feel |
|---|---|---|---|
| `llama3.2:3b` (the default) | about 2 GB | about 4 GB free | Usable: a reply takes some seconds |
| `qwen2.5:3b` | about 2 GB | about 4 GB free | Similar; a good alternative |
| `llama3.1:8b` | about 5 GB | about 8 GB free | Noticeably better, noticeably slower |

Docker also needs memory, so leave headroom. On a machine with around 12 GB of RAM, stay with a 3B model.
The very first message after starting is slowest, because the model is loading into memory.

## 1. Install Ollama

1. Download it from <https://ollama.com/download> and run the installer. On Windows it then runs quietly in
   the background (look for the llama icon in the system tray).
2. Open a new terminal and check it works:

   ```
   ollama --version
   ```

## 2. Download the models

```
ollama pull llama3.2:3b      # the assistant's brain (about 2 GB)
ollama pull all-minilm       # search by meaning (about 45 MB)
```

(`all-minilm` is specifically what Veluntra needs: it produces the 384-number vectors the database stores.)

## 3. Tell Veluntra to use them

Add to your `.env` (project root; it is never committed):

```
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
```

Optional settings (defaults shown):

```
OLLAMA_MODEL=llama3.2:3b
OLLAMA_EMBEDDING_MODEL=all-minilm
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_TIMEOUT_SECONDS=180      # raise it if replies time out on a slow computer
OLLAMA_NUM_CTX=8192             # the model's memory window, in tokens
```

Then restart the API so it picks them up:

```
docker compose up -d backend
```

## 4. Check it works

```
docker compose exec backend python -m scripts.check_ollama
```

It tests, in order: Ollama is reachable, both models are installed, a plain chat works, **tool calling**
works (the part small models most often get wrong), and embeddings are the right size. Each problem comes
with the command that fixes it. The first run may take a minute while the model loads.

## 5. Re-embed your existing data (once)

Vectors from the demo embedder and from a real model can't be compared. After switching
`EMBEDDING_PROVIDER`, rebuild the old ones:

```
docker compose exec backend python -m scripts.reindex_embeddings
```

New memories and documents are embedded with the new model automatically. Switching back later needs the
same command.

## Using it

Open the **Assistant**. The demo banner is gone, and a line above the chat says which model is answering,
for example *"Answering with llama3.2:3b, running on this computer."*

## Troubleshooting

| What you see | What to do |
|---|---|
| "Cannot reach Ollama" | Start the Ollama app (or run `ollama serve`). On **Linux**, the API runs in Docker and can't see Ollama's default loopback-only address: start Ollama with `OLLAMA_HOST=0.0.0.0` and check your firewall. |
| "Ollama does not have the model" | Run the `ollama pull ...` command the message shows. |
| "Ollama did not answer within ... s" | The model is slow on this computer. Wait for the first load to finish, close other heavy programs, try a smaller model, or raise `OLLAMA_TIMEOUT_SECONDS`. |
| The assistant answers in words but never creates anything | That model may not support tool calling. `check_ollama` tells you. Use `llama3.2:3b`, `llama3.1:8b` or `qwen2.5:3b`. |
| It does something odd or misreads a request | Expected with small models. Look at "actions taken" under each reply; rephrase more simply. Nothing runs that didn't pass validation, and nothing can be deleted. |
| Documents fail with an "embedding" message | Ollama or `all-minilm` isn't available. Fix it, then use **Retry** on the document. |
| Docker is out of memory | In Docker Desktop's settings, check how much memory it may use; close other apps. |

To go back to the built-in demo at any time, set `LLM_PROVIDER=fake` and `EMBEDDING_PROVIDER=fake`
(re-run the reindex command for embeddings), and restart the API.

## How it fits in

The assistant doesn't know which model it is talking to. `app/llm/ollama.py` translates between the app's
provider-neutral conversation format and Ollama's, and `app/embeddings/ollama.py` does the same for
embeddings; both share one small HTTP client. The model's output is untrusted exactly like any other
model's: the tool registry checks each call against a strict schema before anything runs, and workspace and
user always come from the signed-in request, never from the model. Tool schemas are flattened before being
sent (references inlined, noise removed) because small models read them better that way.
